from __future__ import annotations

import importlib
import sys
from datetime import timedelta
from pathlib import Path
from threading import Event
import time

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session


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
    assert all(
        not event["step"].startswith("正在") and not event["message"].startswith("正在")
        for event in detail_payload["progress_events"]
        if event["status"] == "completed"
    )
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


def test_detail_trace_display_localizes_old_codex_and_mercury_payloads(tmp_path, monkeypatch):
    _client(tmp_path, monkeypatch)
    import alpha_workbench.api.routers.research as research_router

    trace = research_router._display_safe_trace(
        {
            "code_agent": {
                "summary": "Implemented the AlphaWorkbench factor plugin.",
                "risks": [
                    "Literal upper-shadow calculation is impossible without open, high, low, and close fields.",
                    "Tests were not executed.",
                ],
            },
            "backtest_result": {
                "mercury_status": {
                    "notes": [
                        "Mercury returned no result for weighted_upper_shadow_freq; used local fallback."
                    ],
                    "attempts": {
                        "weighted_upper_shadow_freq": {
                            "message": (
                                "Mercury returned no result for weighted_upper_shadow_freq; "
                                "used local fallback."
                            )
                        }
                    },
                }
            },
        }
    )

    assert trace["code_agent"]["summary"].startswith("已生成")
    assert all("Mercury returned" not in note for note in trace["backtest_result"]["mercury_status"]["notes"])
    assert all("Literal" not in risk and "Tests were" not in risk for risk in trace["code_agent"]["risks"])


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


def test_running_project_persists_factor_stage_outputs(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    import alpha_workbench.api.routers.research as research_router

    stage_written = Event()
    finish_workflow = Event()
    idea_spec = {
        "idea_name": "阶段性输出",
        "core_hypothesis": "后台运行时也应展示候选因子和表达式校验。",
    }
    factor_specs = [
        {
            "factor_id": "earnings_surprise_gap",
            "factor_name": "盈利超预期缺口",
            "plain_description": "盈利超预期且公告前涨幅有限。",
            "formula_tree": {"op": "sub", "args": ["quarter_net_profit", "expected_net_profit"]},
        }
    ]
    compiled_factors = [
        {
            "factor_id": "earnings_surprise_gap",
            "factor_name": "盈利超预期缺口",
            "status": "compiled",
            "expression_tree_valid": True,
        }
    ]

    def fake_run_resume_workflow(**kwargs):
        kwargs["trace_update_callback"]({"factor_specs": factor_specs})
        kwargs["trace_update_callback"]({"compiled_factors": compiled_factors})
        stage_written.set()
        finish_workflow.wait(timeout=2)
        return {
            "input_text": "test",
            "workflow_mode": "demo_workflow",
            "is_mock": True,
            "idea_spec": idea_spec,
            "research_spec": kwargs["research_spec"],
            "factor_specs": factor_specs,
            "compiled_factors": compiled_factors,
            "backtest_result": {"metrics": {"ic_mean": 0.01}},
            "explanation": {},
            "audit_report": {"checks": []},
            "report_markdown": "# report",
        }

    monkeypatch.setattr(research_router, "extract_idea", lambda text, source_meta=None: idea_spec)
    monkeypatch.setattr(research_router, "run_resume_workflow", fake_run_resume_workflow)

    register = client.post(
        "/api/auth/register",
        json={
            "email": "stages@example.com",
            "username": "stageuser",
            "password": "strong-password",
        },
    )
    csrf = register.json()["csrf_token"]

    created = client.post(
        "/api/research/projects",
        headers={"X-CSRF-Token": csrf},
        json={"title": "阶段性输出", "input_text": "test input"},
    )
    project_id = created.json()["id"]
    for _ in range(20):
        detail = client.get(f"/api/research/projects/{project_id}")
        if detail.json()["trace"].get("research_spec"):
            break
        time.sleep(0.05)

    started = client.post(
        f"/api/research/projects/{project_id}/start",
        headers={"X-CSRF-Token": csrf},
    )
    assert started.status_code == 200

    assert stage_written.wait(timeout=2)
    running_detail = client.get(f"/api/research/projects/{project_id}").json()
    assert running_detail["status"] == "running"
    assert running_detail["trace"]["factor_specs"] == factor_specs
    assert running_detail["trace"]["compiled_factors"] == compiled_factors

    finish_workflow.set()
    for _ in range(20):
        completed = client.get(f"/api/research/projects/{project_id}").json()
        if completed["status"] == "completed":
            break
        time.sleep(0.05)
    assert completed["status"] == "completed"


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


def test_stale_codex_run_is_failed_on_progress_read(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    import alpha_workbench.api.routers.research as research_router
    from alpha_workbench.api.models import (
        ResearchProject,
        ResearchRun,
        ResearchTrace,
        utcnow,
    )

    monkeypatch.setattr(research_router, "_stale_codex_timeout_seconds", lambda: 1)
    monkeypatch.setattr(research_router.core_settings, "data_dir", tmp_path / "data")

    register = client.post(
        "/api/auth/register",
        json={
            "email": "stale@example.com",
            "username": "staleuser",
            "password": "strong-password",
        },
    )
    user_id = register.json()["id"]

    stale_time = (utcnow() - timedelta(seconds=10)).isoformat(timespec="seconds")
    with Session(research_router.engine) as db:
        project = ResearchProject(
            user_id=user_id,
            title="stale codex",
            idea_text="test input",
            status="running",
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        run = ResearchRun(
            project_id=project.id or 0,
            user_id=user_id,
            input_text="test input",
            status="running",
            current_step="正在调用 Codex 生成并验证因子插件",
            progress_events=[
                {
                    "step": "正在调用 Codex 生成并验证因子插件",
                    "status": "running",
                    "message": "正在调用 Codex 生成并验证因子插件...",
                    "time": stale_time,
                }
            ],
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        db.add(
            ResearchTrace(
                run_id=run.id or 0,
                user_id=user_id,
                trace_json={"input_text": "test input"},
                report_markdown="",
                metrics_summary={},
            )
        )
        db.commit()
        project_id = project.id or 0

    progress = client.get(f"/api/research/projects/{project_id}/progress")
    assert progress.status_code == 200
    payload = progress.json()
    assert payload["status"] == "failed"
    assert payload["current_step"] == "失败"
    assert all(event["status"] != "running" for event in payload["progress_events"])
    assert "Codex 因子插件生成超过超时阈值" in payload["progress_events"][-1]["message"]

    detail = client.get(f"/api/research/projects/{project_id}")
    diagnostics = detail.json()["trace"]["workflow_diagnostics"]
    assert diagnostics[-1]["stage"] == "stale_codex_run"
    assert diagnostics[-1]["project_id"] == project_id
    assert diagnostics[-1]["current_step"] == "正在调用 Codex 生成并验证因子插件"
    log_path = Path(detail.json()["trace"]["run_log_path"])
    assert log_path.is_file()
    assert '"event": "stale_codex_run"' in log_path.read_text(encoding="utf-8")
