"""Streamlit integration UI for AlphaWorkbench."""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from alpha_workbench.workflows.demo_workflow import DEFAULT_INPUT, run_demo_workflow
from alpha_workbench.workflows.integration_workflow import (
    EMPTY_ROLE_OUTPUTS,
    WORKFLOW_STEPS,
    build_empty_integration_trace,
    build_integration_trace,
)


PAGE_STYLE = """
<style>
    :root {
        --aw-bg: #eef2f7;
        --aw-panel: #ffffff;
        --aw-panel-soft: #f8fafc;
        --aw-border: #cbd5e1;
        --aw-border-strong: #94a3b8;
        --aw-text: #0f172a;
        --aw-muted: #475569;
        --aw-faint: #64748b;
        --aw-blue: #1d4ed8;
        --aw-blue-soft: #dbeafe;
        --aw-green: #047857;
        --aw-green-soft: #d1fae5;
        --aw-amber: #b45309;
        --aw-amber-soft: #ffedd5;
        --aw-purple: #6d28d9;
        --aw-purple-soft: #ede9fe;
        --aw-rose: #be123c;
        --aw-rose-soft: #ffe4e6;
        --aw-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
    }
    .stApp {
        background: var(--aw-bg);
        color: var(--aw-text);
    }
    .block-container {
        padding-top: 1.25rem;
        padding-bottom: 2.5rem;
        max-width: 1380px;
    }
    header[data-testid="stHeader"],
    .stAppHeader {
        display: none;
    }
    div[data-testid="stToolbar"] {
        top: 1.35rem;
        right: max(1.25rem, calc((100vw - 1380px) / 2 + 1.25rem));
        z-index: 900;
    }
    div[data-testid="stToolbar"] button,
    div[data-testid="stToolbar"] a {
        border-radius: 8px;
        color: #1e293b;
        background: transparent;
        border-color: transparent;
        box-shadow: none;
    }
    div[data-testid="stToolbar"] button:hover,
    div[data-testid="stToolbar"] a:hover {
        color: #1d4ed8;
        background: #dbeafe;
    }
    section[data-testid="stSidebar"] {
        background: #0f172a;
        border-right: 1px solid #1e293b;
    }
    section[data-testid="stSidebar"] * {
        color: #f8fafc;
    }
    section[data-testid="stSidebar"] textarea {
        color: #0f172a;
        background: #ffffff;
        border-radius: 8px;
        border: 1px solid #93c5fd;
    }
    section[data-testid="stSidebar"] .stButton > button {
        border-radius: 8px;
        min-height: 2.75rem;
        font-weight: 760;
        border: 1px solid #cbd5e1;
        background: #e0f2fe;
        color: #0c4a6e;
        white-space: normal;
        line-height: 1.2;
    }
    section[data-testid="stSidebar"] .stButton > button * {
        color: #0c4a6e !important;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
        border-color: #60a5fa;
        background: #2563eb;
        color: #ffffff;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"] * {
        color: #ffffff !important;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        border-color: #93c5fd;
        background: #bae6fd;
        color: #075985;
    }
    section[data-testid="stSidebar"] .stButton > button:hover * {
        color: #075985 !important;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
        border-color: #bfdbfe;
        background: #1d4ed8;
        color: #ffffff;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover * {
        color: #ffffff !important;
    }
    .aw-shell-header {
        border: 1px solid #bfdbfe;
        border-radius: 8px;
        background: #ffffff;
        box-shadow: var(--aw-shadow);
        padding: 1.25rem 1.25rem;
        margin-bottom: 0.8rem;
        min-height: 96px;
        overflow: visible;
    }
    .aw-brand-row {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
    }
    .aw-brand-lockup {
        display: flex;
        align-items: center;
        gap: 0.8rem;
        min-width: 280px;
    }
    .aw-logo {
        width: 52px;
        height: 52px;
        min-width: 52px;
        border-radius: 8px;
        display: grid;
        place-items: center;
        font-weight: 820;
        letter-spacing: 0;
        color: #ffffff;
        background: #1d4ed8;
        line-height: 1;
    }
    .aw-logo-standalone {
        width: 52px;
        height: 52px;
        min-width: 52px;
        border-radius: 8px;
        display: grid;
        place-items: center;
        font-weight: 820;
        letter-spacing: 0;
        color: #ffffff;
        background: #1d4ed8;
        line-height: 1;
        margin-top: 0.1rem;
    }
    .app-title {
        font-size: 1.82rem;
        line-height: 1.12;
        font-weight: 790;
        letter-spacing: 0;
        margin: 0;
        color: var(--aw-text);
    }
    .app-subtitle {
        color: var(--aw-muted);
        font-size: 0.94rem;
        margin-top: 0.28rem;
    }
    .aw-header-actions {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        flex-wrap: wrap;
        justify-content: flex-end;
        max-width: 100%;
    }
    .aw-pill {
        display: inline-flex;
        align-items: center;
        min-height: 2rem;
        padding: 0.2rem 0.72rem;
        border-radius: 999px;
        border: 1px solid var(--aw-border);
        color: #1e293b;
        background: #ffffff;
        font-size: 0.82rem;
        font-weight: 720;
        white-space: normal;
        overflow-wrap: anywhere;
    }
    .aw-pill.active {
        border-color: #34d399;
        color: #064e3b;
        background: var(--aw-green-soft);
    }
    .aw-pill.waiting {
        border-color: #fdba74;
        color: var(--aw-amber);
        background: var(--aw-amber-soft);
    }
    .aw-metrics-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.75rem;
        margin: 0.85rem 0 0.95rem;
    }
    .aw-metric-card {
        border: 1px solid #bfdbfe;
        border-radius: 8px;
        background: #ffffff;
        padding: 0.86rem 0.95rem;
        min-height: 92px;
        box-shadow: var(--aw-shadow);
        border-top: 4px solid var(--aw-blue);
        overflow-wrap: anywhere;
    }
    .aw-metric-card.waiting {
        border-color: #fed7aa;
        border-top-color: var(--aw-amber);
    }
    .aw-metric-card.payload {
        border-color: #ddd6fe;
        border-top-color: var(--aw-purple);
    }
    .aw-metric-card.trace {
        border-color: #a7f3d0;
        border-top-color: var(--aw-green);
    }
    .aw-metric-label {
        color: var(--aw-muted);
        font-size: 0.78rem;
        font-weight: 720;
        margin-bottom: 0.32rem;
    }
    .aw-metric-value {
        color: var(--aw-text);
        font-size: 1.5rem;
        font-weight: 800;
        line-height: 1.08;
        overflow-wrap: anywhere;
    }
    .aw-metric-note {
        color: var(--aw-faint);
        font-size: 0.78rem;
        margin-top: 0.25rem;
    }
    .status-chip {
        display: inline-flex;
        align-items: center;
        border: 1px solid var(--aw-border);
        border-radius: 999px;
        padding: 0.24rem 0.72rem;
        margin: 0.12rem 0.25rem 0.12rem 0;
        font-size: 0.81rem;
        font-weight: 720;
        color: #1e293b;
        background: #ffffff;
        white-space: normal;
        overflow-wrap: anywhere;
    }
    .status-chip.completed {
        border-color: #34d399;
        color: #064e3b;
        background: var(--aw-green-soft);
    }
    .status-chip.waiting {
        border-color: #fdba74;
        color: #7c2d12;
        background: var(--aw-amber-soft);
    }
    .aw-pipeline-wrap {
        border: 1px solid #bfdbfe;
        border-radius: 8px;
        background: #ffffff;
        box-shadow: var(--aw-shadow);
        padding: 0.95rem 1rem 1rem;
        margin: 0.85rem 0 1.05rem;
        overflow-x: auto;
        overflow-y: hidden;
    }
    .aw-pipeline-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 0.85rem;
        min-width: 920px;
    }
    .aw-pipeline-title {
        color: var(--aw-text);
        font-size: 1.05rem;
        font-weight: 800;
    }
    .aw-pipeline-caption {
        color: var(--aw-muted);
        font-size: 0.84rem;
        font-weight: 650;
    }
    .aw-pipeline-rail {
        display: flex;
        align-items: stretch;
        gap: 0.8rem;
        min-width: 1240px;
        padding-bottom: 0.15rem;
    }
    .aw-step-card {
        position: relative;
        flex: 0 0 178px;
        border: 1px solid var(--aw-border);
        border-radius: 8px;
        background: #ffffff;
        padding: 0.86rem 0.9rem;
        min-height: 132px;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
        overflow-wrap: anywhere;
    }
    .aw-step-card::after {
        content: "→";
        position: absolute;
        right: -0.67rem;
        top: 50%;
        transform: translateY(-50%);
        color: #64748b;
        font-size: 1.1rem;
        font-weight: 800;
        z-index: 2;
    }
    .aw-step-card:last-child::after {
        content: "";
    }
    .aw-step-card.completed {
        border-color: #22c55e;
        background: #ecfdf5;
        box-shadow: 0 8px 22px rgba(4, 120, 87, 0.14);
    }
    .aw-step-card.waiting {
        border-color: #fed7aa;
        background: #fff7ed;
    }
    .aw-step-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.7rem;
        margin-bottom: 0.7rem;
    }
    .aw-step-index {
        color: #334155;
        font-size: 0.76rem;
        font-weight: 760;
    }
    .aw-step-status {
        border: 1px solid #fed7aa;
        border-radius: 999px;
        padding: 0.12rem 0.48rem;
        color: #7c2d12;
        background: #ffedd5;
        font-size: 0.74rem;
        font-weight: 720;
        white-space: nowrap;
    }
    .aw-step-card.completed .aw-step-status {
        border-color: #34d399;
        color: #064e3b;
        background: #ffffff;
    }
    .aw-step-card.completed::after {
        color: #16a34a;
    }
    .aw-step-card.completed .aw-step-index {
        color: #047857;
    }
    .aw-step-title {
        color: var(--aw-text);
        font-size: 0.96rem;
        font-weight: 760;
        margin-bottom: 0.28rem;
        line-height: 1.35;
    }
    .aw-step-owner {
        color: var(--aw-muted);
        font-size: 0.78rem;
        line-height: 1.35;
    }
    .slot-panel {
        border: 1px dashed var(--aw-border-strong);
        border-radius: 8px;
        padding: 1rem 1.05rem;
        background: #ffffff;
        margin-bottom: 0.75rem;
        min-height: 118px;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
        overflow-wrap: anywhere;
    }
    .slot-title {
        font-weight: 760;
        color: var(--aw-text);
        margin-bottom: 0.28rem;
    }
    .slot-muted {
        color: var(--aw-muted);
        font-size: 0.9rem;
        line-height: 1.45;
    }
    .aw-section-label {
        color: #1d4ed8;
        font-size: 0.78rem;
        font-weight: 760;
        margin-bottom: 0.18rem;
    }
    .aw-section-title {
        color: var(--aw-text);
        font-size: 1.1rem;
        font-weight: 790;
        margin: 0 0 0.65rem;
        overflow-wrap: anywhere;
    }
    .aw-risk-item {
        border-left: 4px solid var(--aw-amber);
        background: var(--aw-amber-soft);
        padding: 0.6rem 0.72rem;
        border-radius: 6px;
        margin-bottom: 0.45rem;
        color: #7c2d12;
        font-size: 0.9rem;
        overflow-wrap: anywhere;
    }
    .aw-bullet {
        border: 1px solid var(--aw-border);
        border-radius: 8px;
        padding: 0.62rem 0.72rem;
        background: #eff6ff;
        margin-bottom: 0.45rem;
        color: #172554;
        font-size: 0.92rem;
        overflow-wrap: anywhere;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.35rem;
        border-bottom: 1px solid var(--aw-border);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 0.55rem 0.8rem;
        color: #1e293b;
        font-weight: 720;
        white-space: normal;
    }
    .stTabs [aria-selected="true"] {
        background: #dbeafe;
        color: #1e3a8a;
    }
    div[data-testid="stMetric"] {
        border: 1px solid #bfdbfe;
        border-radius: 8px;
        background: #ffffff;
        padding: 0.72rem 0.8rem;
        min-height: 108px;
    }
    div[data-testid="stMetricLabel"] {
        color: var(--aw-muted);
    }
    div[data-testid="stMetricValue"] {
        color: var(--aw-text);
        font-size: 1.25rem;
        white-space: normal;
        overflow-wrap: anywhere;
    }
    div[data-testid="stExpander"] {
        border: 1px solid var(--aw-border);
        border-radius: 8px;
        background: #ffffff;
    }
    .stTextArea textarea {
        border-radius: 8px;
        border: 1px solid var(--aw-border);
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 0.88rem;
        color: #0f172a;
        background: #ffffff;
    }
    .stTextArea textarea:focus {
        border-color: #2563eb;
        box-shadow: 0 0 0 1px #2563eb;
    }
    .stButton > button,
    .stFormSubmitButton > button {
        border-radius: 8px;
        min-height: 2.55rem;
        border: 1px solid #2563eb;
        background: #ffffff;
        color: #1d4ed8;
        font-weight: 760;
        white-space: normal;
        line-height: 1.2;
        overflow-wrap: anywhere;
    }
    .stButton > button:hover,
    .stFormSubmitButton > button:hover {
        border-color: #1d4ed8;
        background: #dbeafe;
        color: #1e3a8a;
    }
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"] {
        border-color: #1d4ed8;
        background: #1d4ed8;
        color: #ffffff;
    }
    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover {
        border-color: #1e40af;
        background: #1e40af;
        color: #ffffff;
    }
    .stDataFrame {
        border: 1px solid var(--aw-border);
        border-radius: 8px;
        overflow: hidden;
        background: #ffffff;
    }
    div[data-testid="stAlert"] {
        border-radius: 8px;
        color: #0f172a;
    }
    .small-muted {
        color: var(--aw-muted);
        font-size: 0.86rem;
    }
    @media (max-width: 900px) {
        .aw-metrics-grid {
            grid-template-columns: 1fr;
        }
        .aw-pipeline-header {
            min-width: 760px;
        }
        .aw-pipeline-rail {
            min-width: 1100px;
        }
        .aw-brand-row {
            align-items: stretch;
        }
        .aw-header-actions {
            justify-content: flex-start;
        }
        .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
</style>
"""

JSON_PAYLOADS: list[tuple[str, str, type, Any]] = [
    ("research_spec", "角色 2 / 研究配置 JSON", dict, {}),
    ("idea_spec", "角色 3 / 投资思想 JSON", dict, {}),
    ("factor_specs", "角色 4 / 候选因子 JSON", list, []),
    ("compiled_factors", "角色 4 / 因子编译结果 JSON", list, []),
    ("backtest_result", "角色 5 / 回测结果 JSON", dict, {}),
    ("explanation", "角色 5 / 回测解释 JSON", dict, {}),
    ("audit_report", "角色 6 / 审计报告 JSON", dict, {}),
    ("user_edits", "角色 2 / 用户修改记录 JSON", list, []),
]

MODE_LABELS = {
    "not_started": "尚未开始",
    "mock_demo_workflow": "模拟演示流程",
    "demo_workflow": "完整演示流程",
    "role2_integration_shell": "角色二集成流程",
}

FRAMEWORK_LABELS = {
    "-": "未启动",
    "agno": "Agno 工作流",
    "python_fallback": "Python 兜底流程",
}

OWNER_LABELS = {
    "role_2_ui_workflow": "角色 2：界面与流程串联",
    "role_3_idea_agent": "角色 3：投资思想智能体",
    "role_4_factor_agent": "角色 4：因子生成智能体",
    "role_4_factor_engine": "角色 4：因子编译器",
    "role_5_backtest": "角色 5：回测模块",
    "role_5_backtest_agent": "角色 5：回测解释智能体",
    "role_6_audit_agent": "角色 6：审计智能体",
    "role_6_report_agent": "角色 6：报告智能体",
}

OUTPUT_LABELS = {
    "input_text": "研究输入",
    "idea_spec": "投资思想",
    "research_spec": "研究配置",
    "factor_specs": "候选因子",
    "compiled_factors": "因子编译结果",
    "backtest_result": "回测结果",
    "explanation": "回测解释",
    "audit_report": "审计结果",
    "report_markdown": "最终报告",
    "user_edits": "用户修改记录",
}


def _json_block(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _html(markup: str) -> None:
    st.markdown(markup.strip(), unsafe_allow_html=True)


def _mode_label(value: str) -> str:
    return MODE_LABELS.get(value, value)


def _framework_label(value: str) -> str:
    return FRAMEWORK_LABELS.get(value, value)


def _owner_label(value: str) -> str:
    return OWNER_LABELS.get(value, value)


def _output_label(value: str) -> str:
    return OUTPUT_LABELS.get(value, value)


def _payload_key(name: str) -> str:
    return f"payload_{name}"


def _value_to_payload_text(name: str, value: Any) -> str:
    if name == "report_markdown":
        return value or ""
    return _json_block(value if value is not None else EMPTY_ROLE_OUTPUTS.get(name))


def _set_payloads_from_trace(trace: dict[str, Any]) -> None:
    for name, _, _, default in JSON_PAYLOADS:
        st.session_state[_payload_key(name)] = _json_block(trace.get(name, default))
    st.session_state[_payload_key("report_markdown")] = trace.get("report_markdown", "")


def _ensure_payload_state() -> None:
    for name, _, _, default in JSON_PAYLOADS:
        st.session_state.setdefault(_payload_key(name), _json_block(default))
    st.session_state.setdefault(_payload_key("report_markdown"), "")


def _parse_role_payloads() -> tuple[dict[str, Any] | None, list[str]]:
    parsed: dict[str, Any] = {}
    errors: list[str] = []

    for name, label, expected_type, default in JSON_PAYLOADS:
        raw = st.session_state.get(_payload_key(name), "").strip()
        if not raw:
            parsed[name] = default
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"{label} 不是合法 JSON：{exc.msg}")
            continue
        if not isinstance(value, expected_type):
            errors.append(f"{label} 需要是 {expected_type.__name__}")
            continue
        parsed[name] = value

    parsed["report_markdown"] = st.session_state.get(_payload_key("report_markdown"), "")
    if errors:
        return None, errors
    return parsed, []


def _step_states(trace: dict[str, Any] | None) -> list[dict[str, str]]:
    if trace is None:
        return [{**step, "status": "waiting"} for step in WORKFLOW_STEPS]
    if trace.get("workflow_steps"):
        return trace["workflow_steps"]
    return [{**step, "status": "completed"} for step in WORKFLOW_STEPS]


def _workflow_counts(trace: dict[str, Any] | None) -> tuple[int, int, int]:
    steps = _step_states(trace)
    completed = sum(1 for step in steps if step["status"] == "completed")
    waiting = len(steps) - completed
    return completed, waiting, len(steps)


def _payload_counts(trace: dict[str, Any] | None) -> tuple[int, int]:
    if trace is None:
        return 0, len(EMPTY_ROLE_OUTPUTS)
    ready = 0
    for key, empty_value in EMPTY_ROLE_OUTPUTS.items():
        value = trace.get(key, empty_value)
        if isinstance(value, str):
            ready += int(bool(value.strip()))
        elif isinstance(value, (dict, list)):
            ready += int(bool(value))
        else:
            ready += int(value is not None)
    return ready, len(EMPTY_ROLE_OUTPUTS)


def _render_app_header(trace: dict[str, Any] | None) -> None:
    completed, waiting, total = _workflow_counts(trace)
    mode = trace.get("workflow_mode", "mock_demo_workflow") if trace else "not_started"
    framework = trace.get("workflow_framework", "-") if trace else "-"
    mode_display = _mode_label(mode)
    framework_display = _framework_label(framework)
    trace_state = "active" if trace else "waiting"
    trace_label = "记录已创建" if trace else "等待记录"

    with st.container(border=True):
        logo_col, title_col, status_col = st.columns([0.08, 0.48, 0.44], vertical_alignment="center")
        with logo_col:
            _html('<div class="aw-logo-standalone">AW</div>')
        with title_col:
            st.markdown('<div class="app-title">AlphaWorkbench</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="app-subtitle">角色 2 工作流串联与前端控制台</div>',
                unsafe_allow_html=True,
            )
        with status_col:
            _html(
                f'<div class="aw-header-actions">'
                f'<span class="aw-pill {trace_state}">{trace_label}</span>'
                f'<span class="aw-pill">运行模式 · {escape(mode_display)}</span>'
                f'<span class="aw-pill">工作流框架 · {escape(framework_display)}</span>'
                f'<span class="aw-pill">阶段 · {completed}/{total}</span>'
                f'</div>'
            )


def _render_summary_cards(trace: dict[str, Any] | None) -> None:
    completed, waiting, total = _workflow_counts(trace)
    payload_ready, payload_total = _payload_counts(trace)
    trace_value = "已创建" if trace else "等待"

    _html(
        f'<div class="aw-metrics-grid">'
        f'<div class="aw-metric-card"><div class="aw-metric-label">已接入阶段</div>'
        f'<div class="aw-metric-value">{completed}</div>'
        f'<div class="aw-metric-note">共 {total} 个流程阶段</div></div>'
        f'<div class="aw-metric-card waiting"><div class="aw-metric-label">等待输出</div>'
        f'<div class="aw-metric-value">{waiting}</div>'
        f'<div class="aw-metric-note">等待其他角色交付</div></div>'
        f'<div class="aw-metric-card payload"><div class="aw-metric-label">已接入输出</div>'
        f'<div class="aw-metric-value">{payload_ready}</div>'
        f'<div class="aw-metric-note">共 {payload_total} 个输出插槽</div></div>'
        f'<div class="aw-metric-card trace"><div class="aw-metric-label">研究路径记录</div>'
        f'<div class="aw-metric-value">{trace_value}</div>'
        f'<div class="aw-metric-note">用于保存研究路径</div></div>'
        f'</div>'
    )


def _render_status(trace: dict[str, Any] | None) -> None:
    chips = []
    for index, step in enumerate(_step_states(trace), start=1):
        status = step["status"]
        css = "status-chip completed" if status == "completed" else "status-chip waiting"
        label = "已接入" if status == "completed" else "等待"
        chips.append(f'<span class="{css}">{index}. {step["label"]} · {label}</span>')
    _html("".join(chips))


def _render_pipeline(trace: dict[str, Any] | None) -> None:
    cards = []
    for index, step in enumerate(_step_states(trace), start=1):
        status = step["status"]
        status_label = "已接入" if status == "completed" else "等待"
        cards.append(
            f'<div class="aw-step-card {status}">'
            f'<div class="aw-step-top">'
            f'<span class="aw-step-index">阶段 {index:02d}</span>'
            f'<span class="aw-step-status">{status_label}</span>'
            f'</div>'
        f'<div class="aw-step-title">{escape(step["label"])}</div>'
        f'<div class="aw-step-owner">{escape(_owner_label(step["owner"]))}</div>'
        f'</div>'
        )
    completed, _, total = _workflow_counts(trace)
    _html(
        f'<div class="aw-pipeline-wrap">'
        f'<div class="aw-pipeline-header">'
        f'<div class="aw-pipeline-title">端到端研究工作流</div>'
        f'<div class="aw-pipeline-caption">从左到右推进，已完成节点会依次变绿 · {completed}/{total}</div>'
        f'</div>'
        f'<div class="aw-pipeline-rail">{"".join(cards)}</div>'
        f'</div>'
    )


def _render_section_heading(label: str, title: str) -> None:
    _html(
        f"""
        <div class="aw-section-label">{escape(label)}</div>
        <div class="aw-section-title">{escape(title)}</div>
        """,
    )


def _render_empty_slot(title: str, owner: str) -> None:
    _html(
        f"""
        <div class="slot-panel">
            <div class="slot-title">{escape(title)}</div>
            <div class="slot-muted">等待 {escape(owner)} 输出。</div>
        </div>
        """,
    )


def _render_workflow_table(trace: dict[str, Any]) -> None:
    rows = [
        {
            "步骤": step["label"],
            "负责人": _owner_label(step["owner"]),
            "输出内容": _output_label(step["output_key"]),
            "状态": "已接入" if step["status"] == "completed" else "等待输出",
        }
        for step in _step_states(trace)
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _render_intake_form(input_text: str, save_trace: bool) -> None:
    with st.form("role_output_intake"):
        _render_section_heading("输出接入", "角色输出接入")
        role2_tab, role3_tab, role4_tab, role5_tab, role6_tab = st.tabs(
            ["角色 2 配置", "角色 3 Idea", "角色 4 因子", "角色 5 回测", "角色 6 审计报告"]
        )

        with role2_tab:
            st.text_area(
                "研究配置 JSON",
                key=_payload_key("research_spec"),
                height=180,
            )
            st.text_area("用户修改记录 JSON", key=_payload_key("user_edits"), height=140)

        with role3_tab:
            st.text_area("投资思想 JSON", key=_payload_key("idea_spec"), height=340)

        with role4_tab:
            st.text_area("候选因子 JSON", key=_payload_key("factor_specs"), height=260)
            st.text_area(
                "因子编译结果 JSON",
                key=_payload_key("compiled_factors"),
                height=180,
            )

        with role5_tab:
            st.text_area(
                "回测结果 JSON",
                key=_payload_key("backtest_result"),
                height=240,
            )
            st.text_area("回测解释 JSON", key=_payload_key("explanation"), height=180)

        with role6_tab:
            st.text_area("审计报告 JSON", key=_payload_key("audit_report"), height=220)
            st.text_area(
                "最终报告 Markdown",
                key=_payload_key("report_markdown"),
                height=220,
            )

        submitted = st.form_submit_button("更新接入记录", type="primary", use_container_width=True)

    if not submitted:
        return

    role_outputs, errors = _parse_role_payloads()
    if errors:
        for error in errors:
            st.error(error)
        return

    st.session_state["trace"] = build_integration_trace(
        input_text=input_text,
        role_outputs=role_outputs,
        save_trace=save_trace,
    )
    st.success("接入记录已更新")


def _render_idea(trace: dict[str, Any]) -> None:
    idea = trace.get("idea_spec") or {}
    if not idea:
        _render_empty_slot("IdeaSpec", "角色 3")
        return

    _render_section_heading("投资思想", "投资思想")
    st.write(idea.get("core_hypothesis") or idea.get("idea_name") or "IdeaSpec 已接入")
    if idea.get("economic_mechanism"):
        st.markdown("**经济机制**")
        for item in idea["economic_mechanism"]:
            _html(f'<div class="aw-bullet">{escape(str(item))}</div>')
    if idea.get("risk_flags"):
        st.markdown("**风险提示**")
        for item in idea["risk_flags"]:
            _html(
                f'<div class="aw-risk-item">{escape(str(item))}</div>',
            )
    with st.expander("投资思想原始 JSON（IdeaSpec）"):
        st.code(_json_block(idea), language="json")


def _render_research_spec(trace: dict[str, Any]) -> None:
    research = trace.get("research_spec") or {}
    if not research:
        _render_empty_slot("ResearchSpec", "角色 2 / 用户确认")
        return

    _render_section_heading("研究配置", "研究配置")
    left, right = st.columns(2)
    with left:
        st.write(f"股票池：{research.get('universe', '-')}")
        st.write(f"调仓频率：{research.get('rebalance_frequency', '-')}")
        st.write(f"持有期：{research.get('holding_period', '-')}")
    with right:
        st.write(f"基准：{research.get('benchmark', '-')}")
        st.write(f"交易成本：{research.get('transaction_cost_bps', '-')} bps")
        st.write(f"过滤规则：{', '.join(research.get('filters', [])) or '-'}")
    with st.expander("研究配置原始 JSON（ResearchSpec）"):
        st.code(_json_block(research), language="json")


def _render_factors(trace: dict[str, Any]) -> None:
    factors = trace.get("factor_specs") or []
    if not factors:
        _render_empty_slot("FactorSpecs", "角色 4")
        return

    _render_section_heading("候选因子", "候选因子")
    tabs = st.tabs([factor.get("factor_name", factor.get("factor_id", "factor")) for factor in factors])
    for tab, factor in zip(tabs, factors):
        with tab:
            st.write(factor.get("plain_description", ""))
            if factor.get("latex_formula"):
                st.latex(factor["latex_formula"])
            if factor.get("required_fields"):
                st.markdown("**所需字段**")
                st.write("、".join(f"`{field}`" for field in factor["required_fields"]))
            if factor.get("risk_notes"):
                st.markdown("**风险提示**")
                for note in factor["risk_notes"]:
                    _html(
                        f'<div class="aw-risk-item">{escape(str(note))}</div>',
                    )
            if factor.get("formula_tree"):
                with st.expander("表达式树"):
                    st.code(_json_block(factor["formula_tree"]), language="json")


def _render_compiled_factors(trace: dict[str, Any]) -> None:
    compiled = trace.get("compiled_factors") or []
    if not compiled:
        _render_empty_slot("因子编译结果", "角色 4")
        return
    _render_section_heading("校验结果", "因子编译结果")
    st.dataframe(pd.DataFrame(compiled), hide_index=True, use_container_width=True)


def _render_backtest(trace: dict[str, Any]) -> None:
    result = trace.get("backtest_result") or {}
    factor_results = result.get("factor_results") or []
    if not factor_results:
        _render_empty_slot("BacktestResult", "角色 5")
        return

    _render_section_heading("回测结果", "回测结果")
    metrics = pd.DataFrame(factor_results)
    best = metrics.iloc[0]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("最佳因子", best.get("factor_name", best.get("factor_id", "-")))
    col2.metric("IC 均值", f"{best.get('ic_mean', 0):.3f}")
    col3.metric("多空收益", f"{best.get('long_short_return', 0):.2%}")
    col4.metric("最大回撤", f"{best.get('max_drawdown', 0):.2%}")

    nav_series = result.get("nav_series") or []
    if nav_series:
        nav = pd.DataFrame(nav_series).set_index("date")
        st.line_chart(nav)

    st.dataframe(metrics, hide_index=True, use_container_width=True)


def _render_explanation(trace: dict[str, Any]) -> None:
    explanation = trace.get("explanation") or {}
    if not explanation:
        _render_empty_slot("回测解释", "角色 5")
        return
    _render_section_heading("结果解释", "回测解释")
    st.write(explanation.get("summary", "Explanation 已接入"))
    for item in explanation.get("observations", []):
        _html(f'<div class="aw-bullet">{escape(str(item))}</div>')
    with st.expander("回测解释原始 JSON"):
        st.code(_json_block(explanation), language="json")


def _render_audit_and_report(trace: dict[str, Any]) -> None:
    audit = trace.get("audit_report") or {}
    if audit:
        _render_section_heading("审计结果", "审计结果")
        st.write(f"审计等级：`{audit.get('overall_level', '-')}`")
        for check in audit.get("checks", []):
            message = f"{check.get('item', 'check')}：{check.get('message', '')}"
            _html(
                f'<div class="aw-risk-item">{escape(message)}</div>',
            )
        with st.expander("审计报告原始 JSON"):
            st.code(_json_block(audit), language="json")
    else:
        _render_empty_slot("AuditReport", "角色 6")

    report_markdown = trace.get("report_markdown") or ""
    if report_markdown:
        _render_section_heading("研究报告", "研究报告")
        st.markdown(report_markdown)
    else:
        _render_empty_slot("最终报告 Markdown", "角色 6")


def _render_trace(trace: dict[str, Any]) -> None:
    if trace.get("trace_path"):
        st.success(f"研究路径记录已保存：{trace['trace_path']}")
    with st.expander("完整研究路径记录"):
        st.code(_json_block(trace), language="json")


def _render_empty_state() -> None:
    _html(
        """
        <div class="slot-panel">
            <div class="slot-title">等待创建记录</div>
            <div class="slot-muted">先构建空白集成记录，或运行模拟全流程。</div>
        </div>
        """,
    )


st.set_page_config(page_title="AlphaWorkbench", page_icon="AW", layout="wide")
st.markdown(PAGE_STYLE, unsafe_allow_html=True)
_ensure_payload_state()

if "trace" not in st.session_state:
    st.session_state["trace"] = None

with st.sidebar:
    st.markdown("## AlphaWorkbench")
    st.caption("角色 2 工作流控制台")
    input_text = st.text_area("研究输入", value=DEFAULT_INPUT, height=180)
    save_trace = st.toggle("保存研究路径记录", value=False)

    if st.button("构建空白集成记录", type="primary", use_container_width=True):
        trace = build_empty_integration_trace(input_text)
        if save_trace:
            trace = build_integration_trace(input_text=input_text, save_trace=True)
        st.session_state["trace"] = trace
        _set_payloads_from_trace(trace)

    if st.button("运行模拟全流程", use_container_width=True):
        trace = run_demo_workflow(input_text, save_trace=save_trace)
        st.session_state["trace"] = trace
        _set_payloads_from_trace(trace)

    if st.button("重置", use_container_width=True):
        st.session_state["trace"] = None
        _set_payloads_from_trace(build_empty_integration_trace(""))
        st.rerun()

trace = st.session_state["trace"]

_render_app_header(trace)
_render_summary_cards(trace)
_render_pipeline(trace)
st.divider()

if trace is None:
    left, right = st.columns([0.48, 0.52], gap="large")
    with left:
        _render_empty_state()
    with right:
        _render_intake_form(input_text, save_trace)
else:
    intake_col, state_col = st.columns([0.58, 0.42], gap="large")
    with intake_col:
        _render_intake_form(input_text, save_trace)
    with state_col:
        _render_section_heading("接入状态", "接入状态")
        _render_workflow_table(trace)

    st.divider()
    idea_col, research_col = st.columns(2, gap="large")
    with idea_col:
        _render_idea(trace)
    with research_col:
        _render_research_spec(trace)

    st.divider()
    factor_col, compiled_col = st.columns([0.64, 0.36], gap="large")
    with factor_col:
        _render_factors(trace)
    with compiled_col:
        _render_compiled_factors(trace)

    st.divider()
    backtest_col, explanation_col = st.columns([0.62, 0.38], gap="large")
    with backtest_col:
        _render_backtest(trace)
    with explanation_col:
        _render_explanation(trace)

    st.divider()
    _render_audit_and_report(trace)

    st.divider()
    _render_trace(trace)
