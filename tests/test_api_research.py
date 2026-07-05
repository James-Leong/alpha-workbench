from __future__ import annotations

import importlib
import sys
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

    def fake_workflow(input_text: str, save_trace: bool = False, progress_callback=None):
        if progress_callback:
            progress_callback("正在生成候选因子...")
            progress_callback("正在执行回测...")
        return {
            "input_text": input_text,
            "workflow_mode": "demo_workflow",
            "is_mock": True,
            "idea_spec": {
                "idea_name": "盈利超预期因子研究",
                "hypothesis": "盈利超预期且公告前涨幅有限的股票可能获得超额收益。",
            },
            "backtest_result": {
                "metrics": {
                    "ic_mean": 0.06,
                    "long_short_return": 0.12,
                }
            },
            "report_markdown": "# 盈利超预期因子研究\n\nMock report.",
        }

    monkeypatch.setattr(research_router, "run_demo_workflow", fake_workflow)
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
    assert project["status"] in {"running", "completed"}
    assert project["progress_events"]

    detail_payload = project
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

    listing = client.get("/api/research/projects")
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    progress = client.get(f"/api/research/projects/{project['id']}/progress")
    assert progress.status_code == 200
    assert progress.json()["progress_events"]
