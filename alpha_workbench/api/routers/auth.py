"""Authentication API routes."""

from __future__ import annotations

import re

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from alpha_workbench.api.auth.passwords import hash_password, verify_password
from alpha_workbench.api.auth.sessions import (
    clear_login_session,
    create_login_session,
    get_current_session,
    get_current_user,
    verify_csrf,
)
from alpha_workbench.api.config import settings
from alpha_workbench.api.db import get_db
from alpha_workbench.api.models import OAuthAccount, User, UserSession, utcnow
from alpha_workbench.api.schemas import LoginRequest, RegisterRequest, UserRead


router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth = OAuth()
if settings.github_client_id and settings.github_client_secret:
    oauth.register(
        name="github",
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"},
    )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _normalize_username(username: str) -> str:
    value = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{2,40}", value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username may only contain letters, numbers, dots, underscores, or hyphens",
        )
    return value


def _user_read(user: User, db_session: UserSession) -> UserRead:
    return UserRead(
        id=user.id or 0,
        email=user.email,
        username=user.username,
        csrf_token=db_session.csrf_token,
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)) -> UserRead:
    email = _normalize_email(payload.email)
    username = _normalize_username(payload.username)
    existing = db.exec(
        select(User).where((User.email == email) | (User.username == username))
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists")
    user = User(email=email, username=username, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    db_session = create_login_session(db, response, user)
    return _user_read(user, db_session)


@router.post("/login", response_model=UserRead)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> UserRead:
    email = _normalize_email(payload.email)
    user = db.exec(select(User).where(User.email == email)).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    db_session = create_login_session(db, response, user)
    return _user_read(user, db_session)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_csrf)])
def logout(
    db_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> Response:
    db.delete(db_session)
    db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_login_session(response)
    return response


@router.get("/me", response_model=UserRead)
def me(
    user: User = Depends(get_current_user),
    db_session: UserSession = Depends(get_current_session),
) -> UserRead:
    return _user_read(user, db_session)


@router.get("/github/login")
async def github_login(request: Request):
    if "github" not in oauth:
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")
    redirect_uri = f"{settings.backend_base_url}/api/auth/github/callback"
    return await oauth.github.authorize_redirect(request, redirect_uri)


@router.get("/github/callback")
async def github_callback(request: Request, db: Session = Depends(get_db)):
    if "github" not in oauth:
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")
    token = await oauth.github.authorize_access_token(request)
    github_user = (await oauth.github.get("user", token=token)).json()
    github_email = github_user.get("email")
    if not github_email:
        emails = (await oauth.github.get("user/emails", token=token)).json()
        primary = next((item for item in emails if item.get("primary")), None)
        github_email = (primary or emails[0]).get("email") if emails else None
    if not github_email:
        raise HTTPException(status_code=400, detail="GitHub account has no public email")

    provider_id = str(github_user["id"])
    account = db.exec(
        select(OAuthAccount).where(
            (OAuthAccount.provider == "github")
            & (OAuthAccount.provider_account_id == provider_id)
        )
    ).first()
    user = db.get(User, account.user_id) if account else None
    if user is None:
        email = _normalize_email(github_email)
        user = db.exec(select(User).where(User.email == email)).first()
        if user is None:
            base_username = _normalize_username(github_user.get("login") or email.split("@")[0])
            username = base_username
            suffix = 2
            while db.exec(select(User).where(User.username == username)).first():
                username = f"{base_username}-{suffix}"
                suffix += 1
            user = User(email=email, username=username, password_hash=None)
            db.add(user)
            db.commit()
            db.refresh(user)
        account = OAuthAccount(
            user_id=user.id or 0,
            provider="github",
            provider_account_id=provider_id,
            email=email,
            username=github_user.get("login"),
        )
        db.add(account)
    else:
        account.updated_at = utcnow()
        db.add(account)
    db.commit()

    response = RedirectResponse(f"{settings.frontend_base_url}/dashboard")
    create_login_session(db, response, user)
    return response
