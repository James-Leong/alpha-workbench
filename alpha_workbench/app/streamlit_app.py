"""Streamlit demo for AlphaWorkbench."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from alpha_workbench.workflows.demo_workflow import DEFAULT_INPUT, run_demo_workflow


PAGE_STYLE = """
<style>
    .block-container {
        padding-top: 1.25rem;
        padding-bottom: 2rem;
        max-width: 1280px;
    }
    .app-title {
        font-size: 2.1rem;
        font-weight: 760;
        letter-spacing: 0;
        margin: 0;
    }
    .app-subtitle {
        color: #5f6b7a;
        font-size: 0.98rem;
        margin-top: 0.25rem;
        margin-bottom: 1rem;
    }
    .status-chip {
        display: inline-flex;
        align-items: center;
        border: 1px solid #d8dee8;
        border-radius: 999px;
        padding: 0.2rem 0.65rem;
        margin: 0.15rem 0.25rem 0.15rem 0;
        font-size: 0.82rem;
        color: #304054;
        background: #ffffff;
    }
    .status-chip.active {
        border-color: #1f7a4d;
        color: #145c39;
        background: #eef8f2;
    }
    .agent-card {
        border: 1px solid #dde3ea;
        border-radius: 8px;
        padding: 0.9rem 1rem;
        background: #ffffff;
        margin-bottom: 0.75rem;
    }
    .agent-name {
        font-weight: 700;
        color: #172033;
        margin-bottom: 0.25rem;
    }
    .agent-note {
        color: #526173;
        font-size: 0.92rem;
        line-height: 1.45;
    }
    .small-muted {
        color: #6b7584;
        font-size: 0.86rem;
    }
    .section-label {
        color: #526173;
        font-size: 0.82rem;
        font-weight: 700;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }
</style>
"""


def _json_block(value: dict[str, Any] | list[dict[str, Any]]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _run_research(input_text: str, save_trace: bool) -> dict[str, Any]:
    with st.spinner("AI 研究工作流正在生成 baseline..."):
        return run_demo_workflow(input_text, save_trace=save_trace)


def _render_status(trace: dict[str, Any] | None) -> None:
    steps = [
        "输入",
        "思想提炼",
        "研究配置",
        "因子生成",
        "回测解释",
        "审计报告",
    ]
    active_count = len(steps) if trace else 1
    chips = []
    for index, step in enumerate(steps, start=1):
        css = "status-chip active" if index <= active_count else "status-chip"
        chips.append(f'<span class="{css}">{index}. {step}</span>')
    st.markdown("".join(chips), unsafe_allow_html=True)


def _render_chat_trace(trace: dict[str, Any]) -> None:
    idea = trace["idea_spec"]
    research = trace["research_spec"]
    explanation = trace["explanation"]
    audit = trace["audit_report"]

    with st.chat_message("user"):
        st.write(trace["input_text"])

    with st.chat_message("assistant"):
        st.markdown("**IdeaExtractionAgent**")
        st.write(idea["core_hypothesis"])
        st.caption("已提炼投资假设、经济机制、所需数据和风险点。")

    with st.chat_message("assistant"):
        st.markdown("**ResearchSpec Builder**")
        st.write(
            f"股票池：{research['universe']}；调仓：{research['rebalance_frequency']}；"
            f"持有期：{research['holding_period']}；交易成本：{research['transaction_cost_bps']} bps。"
        )

    with st.chat_message("assistant"):
        st.markdown("**FactorGenerationAgent**")
        factor_names = "、".join(factor["factor_name"] for factor in trace["factor_specs"])
        st.write(f"已生成候选因子：{factor_names}。")

    with st.chat_message("assistant"):
        st.markdown("**BacktestExplanationAgent**")
        st.write(explanation["summary"])

    with st.chat_message("assistant"):
        st.markdown("**AuditAgent**")
        st.write(f"当前审计等级：`{audit['overall_level']}`。")
        for check in audit["checks"]:
            st.write(f"- {check['item']}：{check['message']}")


def _render_research_config(trace: dict[str, Any]) -> None:
    idea = trace["idea_spec"]
    research = trace["research_spec"]

    st.markdown('<div class="section-label">Human-in-the-loop Checkpoint</div>', unsafe_allow_html=True)
    st.subheader("研究配置确认")
    st.write(idea["core_hypothesis"])

    left, right = st.columns(2)
    with left:
        st.text_input("股票池", value=research["universe"], disabled=True)
        st.text_input("持有期", value=research["holding_period"], disabled=True)
        st.text_input("基准", value=research["benchmark"], disabled=True)
    with right:
        st.text_input("调仓频率", value=research["rebalance_frequency"], disabled=True)
        st.number_input("交易成本 bps", value=research["transaction_cost_bps"], disabled=True)
        st.text_input("样本区间", value=f"{research['sample_window']['start']} 至 {research['sample_window']['end']}", disabled=True)

    with st.expander("查看完整 ResearchSpec"):
        st.code(_json_block(research), language="json")


def _render_factor_lab(trace: dict[str, Any]) -> None:
    st.subheader("候选因子实验台")
    factors = trace["factor_specs"]

    tabs = st.tabs([factor["factor_name"] for factor in factors])
    for tab, factor in zip(tabs, factors):
        with tab:
            st.write(factor["plain_description"])
            st.latex(factor["latex_formula"])
            st.markdown("**所需字段**")
            st.write("、".join(f"`{field}`" for field in factor["required_fields"]))
            st.markdown("**风险提示**")
            for note in factor["risk_notes"]:
                st.warning(note)
            with st.expander("表达式树"):
                st.code(_json_block(factor["formula_tree"]), language="json")


def _render_backtest(trace: dict[str, Any]) -> None:
    st.subheader("回测结果")
    metrics = pd.DataFrame(trace["backtest_result"]["factor_results"])
    best = metrics.iloc[0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("最佳因子", best["factor_name"])
    col2.metric("IC 均值", f"{best['ic_mean']:.3f}")
    col3.metric("多空收益", f"{best['long_short_return']:.2%}")
    col4.metric("最大回撤", f"{best['max_drawdown']:.2%}")

    nav = pd.DataFrame(trace["backtest_result"]["nav_series"]).set_index("date")
    st.line_chart(nav)

    display = metrics[
        [
            "factor_name",
            "ic_mean",
            "ic_positive_ratio",
            "long_short_return",
            "max_drawdown",
            "turnover",
        ]
    ].rename(
        columns={
            "factor_name": "因子",
            "ic_mean": "IC均值",
            "ic_positive_ratio": "IC为正比例",
            "long_short_return": "多空收益",
            "max_drawdown": "最大回撤",
            "turnover": "换手率",
        }
    )
    st.dataframe(display, width="stretch", hide_index=True)


def _render_report(trace: dict[str, Any]) -> None:
    st.subheader("研究报告")
    st.markdown(trace["report_markdown"])

    if "trace_path" in trace:
        st.success(f"Research Trace 已保存：{trace['trace_path']}")

    with st.expander("完整 Research Trace"):
        st.code(_json_block(trace), language="json")


def _render_empty_state() -> None:
    st.markdown(
        """
        <div class="agent-card">
            <div class="agent-name">等待输入</div>
            <div class="agent-note">
                输入一段投资想法后，系统会依次生成投资思想、研究配置、候选因子、
                回测解释和轻量审计报告。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="AlphaWorkbench", page_icon="AW", layout="wide")
st.markdown(PAGE_STYLE, unsafe_allow_html=True)

if "trace" not in st.session_state:
    st.session_state["trace"] = None

with st.sidebar:
    st.markdown("## AlphaWorkbench")
    st.caption("AI research copilot")
    input_text = st.text_area("投资想法 / 研报摘要", value=DEFAULT_INPUT, height=180)
    save_trace = st.toggle("保存 Research Trace", value=False)

    run_clicked = st.button("生成研究 baseline", type="primary", width="stretch")
    if run_clicked:
        st.session_state["trace"] = _run_research(input_text, save_trace)

    if st.button("重置会话", width="stretch"):
        st.session_state["trace"] = None
        st.rerun()

trace = st.session_state["trace"]

top_left, top_right = st.columns([0.68, 0.32])
with top_left:
    st.markdown('<p class="app-title">AlphaWorkbench</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="app-subtitle">研报驱动的人机协同量化因子研究工作台</p>',
        unsafe_allow_html=True,
    )
with top_right:
    st.markdown("")
    if trace:
        st.success("Baseline 已生成")
    else:
        st.info("等待研究输入")

_render_status(trace)

st.divider()

if trace is None:
    col1, col2 = st.columns([0.58, 0.42])
    with col1:
        _render_empty_state()
    with col2:
        st.markdown("#### 默认演示主题")
        st.write(DEFAULT_INPUT)
        st.markdown("#### 研究输出")
        st.write("系统将生成投资思想、研究配置、候选因子、基础回测、审计提示和研究报告。")
else:
    main_col, side_col = st.columns([0.62, 0.38], gap="large")
    with main_col:
        _render_chat_trace(trace)
    with side_col:
        _render_research_config(trace)

    st.divider()
    _render_factor_lab(trace)

    st.divider()
    _render_backtest(trace)

    st.divider()
    _render_report(trace)
