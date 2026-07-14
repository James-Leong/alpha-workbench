"""Server-side session helpers backed by SQLite."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from fastapi import Cookie, Depends, Header, HTTPException, Response, status
from sqlmodel import Session, select

from alpha_workbench.api.db import get_db
from alpha_workbench.api.models import User, UserSession, utcnow
from alpha_workbench.core.config import settings


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_login_session(db: Session, response: Response, user: User) -> UserSession:
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.id or 0,
        token_hash=_hash_token(token),
        csrf_token=csrf_token,
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return session


def clear_login_session(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")


def get_current_session(
    token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
    db: Session = Depends(get_db),
) -> UserSession:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    session = db.exec(
        select(UserSession).where(UserSession.token_hash == _hash_token(token))
    ).first()
    if session is None or session.expires_at < utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    session.last_seen_at = utcnow()
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_current_user(
    db_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, db_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def verify_csrf(
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    db_session: UserSession = Depends(get_current_session),
) -> None:
    if not csrf_token or not secrets.compare_digest(csrf_token, db_session.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
