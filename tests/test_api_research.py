from __future__ import annotations

import importlib
import sys
from threading import Event
import time

from fastapi.testclient import TestClient
from sqlmodel import SQLModel


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'research_test.sqlite3'}")
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


def test_create_and_read_research_project(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    import alpha_workbench.api.routers.research as research_router

    idea_spec = {
        "idea_name": "盈利超预期因子研究",
        "hypothesis": "盈利超预期且公告前涨幅有限的股票可能获得超额收益。",
    }

    complete_trace = {
        "input_text": "单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。",
        "workflow_mode": "demo_workflow",
        "is_mock": True,
        "idea_spec": idea_spec,
        "research_spec": {
            "universe": "默认股票池",
            "rebalance_frequency": "monthly",
            "backtest": {"rebalance_frequency": "monthly"},
        },
        "factor_specs": [],
        "compiled_factors": [],
        "backtest_result": {
            "metrics": {"ic_mean": 0.06, "long_short_return": 0.12}
        },
        "explanation": {"summary": "mock explanation"},
        "audit_report": {"checks": []},
        "report_markdown": "# 盈利超预期因子研究\n\nMock report.",
    }

    monkeypatch.setattr(research_router, "extract_idea", lambda text, source_meta=None: idea_spec)
    monkeypatch.setattr(research_router, "run_resume_workflow", lambda **kwargs: complete_trace)

    register = client.post(
        "/api/auth/register",
        json={
            "email": "quant@example.com",
            "username": "quant",
            "password": "strong-password",
        },
    )
    csrf = register.json()["csrf_token"]

    created = client.post(
        "/api/research/projects",
        headers={"X-CSRF-Token": csrf},
        json={
            "title": "盈利超预期因子研究",
            "input_text": "单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。",
        },
    )
    assert created.status_code == 201
    project = created.json()
    assert project["status"] == "pending"
    assert project["trace"]
    assert project["progress_events"][-1]["status"] == "running"
    assert project["progress_events"]

    for _ in range(20):
        detail = client.get(f"/api/research/projects/{project['id']}")
        assert detail.status_code == 200
        project = detail.json()
        if project["trace"].get("research_spec"):
            break
        time.sleep(0.05)

    assert project["status"] == "pending"
    assert project["trace"]["idea_spec"] == idea_spec
    assert project["trace"]["research_spec"]
    assert project["trace"]["research_spec"]["factor_execution"]["mode"] == "codex"
    assert all(
        event["status"] != "running"
        for event in project["progress_events"]
    )

    patched = client.patch(
        f"/api/research/projects/{project['id']}/research-spec",
        headers={"X-CSRF-Token": csrf},
        json={"universe": "沪深300成分股"},
    )
    assert patched.status_code == 200
    assert patched.json()["trace"]["research_spec"]["universe"] == "沪深300成分股"

    started = client.post(
        f"/api/research/projects/{project['id']}/start",
        headers={"X-CSRF-Token": csrf},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "running"

    detail_payload = started.json()
    for _ in range(20):
        detail = client.get(f"/api/research/projects/{project['id']}")
        assert detail.status_code == 200
        detail_payload = detail.json()
        if detail_payload["status"] == "completed":
            break
        time.sleep(0.05)
    assert detail_payload["status"] == "completed"
    assert detail_payload["trace"]
    assert detail_payload["report_markdown"]
    assert all(
        event["status"] != "running"
        for event in detail_payload["progress_events"]
    )

    listing = client.get("/api/research/projects")
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    progress = client.get(f"/api/research/projects/{project['id']}/progress")
    assert progress.status_code == 200
    assert progress.json()["progress_events"]


def test_create_project_returns_before_initial_research_finishes(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    import alpha_workbench.api.routers.research as research_router

    release = Event()

    def blocking_extract(text, source_meta=None):
        release.wait(timeout=2)
        return {
            "idea_name": "异步研读",
            "core_hypothesis": "创建接口应先返回，智能研读在后台完成。",
        }

    monkeypatch.setattr(research_router, "extract_idea", blocking_extract)

    register = client.post(
        "/api/auth/register",
        json={
            "email": "async@example.com",
            "username": "asyncuser",
            "password": "strong-password",
        },
    )
    csrf = register.json()["csrf_token"]

    start = time.perf_counter()
    created = client.post(
        "/api/research/projects",
        headers={"X-CSRF-Token": csrf},
        json={"title": "异步任务", "input_text": "test input"},
    )
    elapsed = time.perf_counter() - start

    assert created.status_code == 201
    assert elapsed < 1.0
    payload = created.json()
    assert payload["status"] == "pending"
    assert payload["current_step"] == "智能研读"
    assert payload["trace"] == {"input_text": "test input"}

    release.set()
    for _ in range(20):
        detail = client.get(f"/api/research/projects/{payload['id']}")
        if detail.json()["trace"].get("research_spec"):
            break
        time.sleep(0.05)

    assert detail.json()["trace"]["idea_spec"]["idea_name"] == "异步研读"


def test_update_spec_rejected_after_start(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    import alpha_workbench.api.routers.research as research_router

    idea_spec = {"idea_name": "test"}
    complete_trace = {
        "input_text": "test",
        "workflow_mode": "demo_workflow",
        "is_mock": True,
        "idea_spec": idea_spec,
        "research_spec": {"universe": "default"},
        "factor_specs": [],
        "compiled_factors": [],
        "backtest_result": {"metrics": {}},
        "explanation": {},
        "audit_report": {"checks": []},
        "report_markdown": "# report",
    }

    monkeypatch.setattr(research_router, "extract_idea", lambda text, source_meta=None: idea_spec)
    monkeypatch.setattr(research_router, "run_resume_workflow", lambda **kwargs: complete_trace)

    register = client.post(
        "/api/auth/register",
        json={"email": "t@example.com", "username": "testuser", "password": "strong-password"},
    )
    csrf = register.json()["csrf_token"]

    created = client.post(
        "/api/research/projects",
        headers={"X-CSRF-Token": csrf},
        json={"title": "test", "input_text": "test input"},
    )
    project_id = created.json()["id"]
    for _ in range(20):
        detail = client.get(f"/api/research/projects/{project_id}")
        if detail.json()["trace"].get("research_spec"):
            break
        time.sleep(0.05)

    client.post(
        f"/api/research/projects/{project_id}/start",
        headers={"X-CSRF-Token": csrf},
    )

    patched = client.patch(
        f"/api/research/projects/{project_id}/research-spec",
        headers={"X-CSRF-Token": csrf},
        json={"universe": "new"},
    )
    assert patched.status_code == 409


def test_start_requires_pending(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    import alpha_workbench.api.routers.research as research_router

    idea_spec = {"idea_name": "test"}
    complete_trace = {
        "input_text": "test",
        "workflow_mode": "demo_workflow",
        "is_mock": True,
        "idea_spec": idea_spec,
        "research_spec": {"universe": "default"},
        "factor_specs": [],
        "compiled_factors": [],
        "backtest_result": {"metrics": {}},
        "explanation": {},
        "audit_report": {"checks": []},
        "report_markdown": "# report",
    }

    monkeypatch.setattr(research_router, "extract_idea", lambda text, source_meta=None: idea_spec)
    monkeypatch.setattr(research_router, "run_resume_workflow", lambda **kwargs: complete_trace)

    register = client.post(
        "/api/auth/register",
        json={"email": "s@example.com", "username": "startuser", "password": "strong-password"},
    )
    csrf = register.json()["csrf_token"]

    created = client.post(
        "/api/research/projects",
        headers={"X-CSRF-Token": csrf},
        json={"title": "test", "input_text": "test input"},
    )
    project_id = created.json()["id"]
    for _ in range(20):
        detail = client.get(f"/api/research/projects/{project_id}")
        if detail.json()["trace"].get("research_spec"):
            break
        time.sleep(0.05)

    # First start succeeds
    first = client.post(
        f"/api/research/projects/{project_id}/start",
        headers={"X-CSRF-Token": csrf},
    )
    assert first.status_code == 200

    # Wait for completion
    for _ in range(20):
        detail = client.get(f"/api/research/projects/{project_id}")
        if detail.json()["status"] == "completed":
            break
        time.sleep(0.05)

    # Second start on completed project should fail
    second = client.post(
        f"/api/research/projects/{project_id}/start",
        headers={"X-CSRF-Token": csrf},
    )
    assert second.status_code == 409
