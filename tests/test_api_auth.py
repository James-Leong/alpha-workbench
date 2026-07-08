from __future__ import annotations

import importlib
import sys

from fastapi.testclient import TestClient
from sqlmodel import SQLModel


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api_test.sqlite3'}")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    SQLModel.metadata.clear()
    for module_name in list(sys.modules):
        if module_name.startswith("alpha_workbench.api"):
            sys.modules.pop(module_name)
    import alpha_workbench.api.config as config
    import alpha_workbench.api.db as db
    import alpha_workbench.api.main as main

    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(main)
    db.init_db()
    return TestClient(main.app)


def test_register_me_and_logout(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post(
        "/api/auth/register",
        json={
            "email": "researcher@example.com",
            "username": "researcher",
            "password": "strong-password",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "researcher@example.com"
    assert payload["csrf_token"]

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "researcher"

    logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": payload["csrf_token"]})
    assert logout.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_login_rejects_wrong_password(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post(
        "/api/auth/register",
        json={
            "email": "researcher@example.com",
            "username": "researcher",
            "password": "strong-password",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={"email": "researcher@example.com", "password": "wrong"},
    )
    assert response.status_code == 401
