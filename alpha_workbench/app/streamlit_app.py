"""Streamlit demo for AlphaWorkbench."""

from __future__ import annotations

import json
from typing import Any

import plotly.graph_objects as go

import time

import pandas as pd
import streamlit as st

from alpha_workbench.agents.backtest_explainer import explain_backtest
from alpha_workbench.agents.factor_generator import generate_factors
from alpha_workbench.agents.idea_extractor import extract_idea
from alpha_workbench.agents.audit_agent import run_audit
from alpha_workbench.agents.report_agent import generate_report
from alpha_workbench.app.research_config import apply_research_config_edits
from alpha_workbench.app.status import backtest_source_summary, group_charts_by_factor
from alpha_workbench.backtest.engine import run_backtest
from alpha_workbench.factor_engine.compiler import compile_factors
from alpha_workbench.memory.research_trace import save_research_trace
from alpha_workbench.schemas.specs import build_research_trace
from alpha_workbench.workflows.demo_workflow import build_research_spec, DEFAULT_INPUT


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


class _TraceEncoder(json.JSONEncoder):
    """JSON encoder that handles Plotly Figures and non-serializable objects in trace dicts."""

    def default(self, o: Any) -> Any:
        if isinstance(o, go.Figure):
            return json.loads(o.to_json())
        try:
            return super().default(o)
        except TypeError:
            return str(o)


def _json_block(value: dict[str, Any] | list[dict[str, Any]]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, cls=_TraceEncoder)


def _run_research(input_text: str, save_trace: bool) -> dict[str, Any]:
    """Run workflow and render each agent's output progressively."""
    st.chat_message("user").write(input_text)

    # Step 1: Idea Extraction
    with st.chat_message("assistant"):
        st.markdown("**IdeaExtractionAgent**")
        with st.spinner("正在提取投资思想..."):
            idea_spec = extract_idea(input_text)
        st.write(idea_spec["core_hypothesis"])
        st.caption("已提炼投资假设、经济机制、所需数据和风险点。")

    # Step 2: Research Spec (with inline config display)
    with st.chat_message("assistant"):
        st.markdown("**ResearchSpec Builder**")
        with st.spinner("正在构建研究配置..."):
            research_spec = build_research_spec(idea_spec)
        st.markdown("**研究配置确认**")
        rs = research_spec
        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown(f"- **股票池：** `{rs.get('universe', '—')}`")
            st.markdown(f"- **持有期：** `{rs.get('holding_period', '—')}`")
            st.markdown(f"- **基准：** `{rs.get('benchmark', '沪深300')}`")
        with col_r:
            st.markdown(f"- **调仓频率：** `{rs.get('rebalance_frequency', '—')}`")
            st.markdown(f"- **交易成本：** `{rs.get('transaction_cost_bps', 10)} bps`")
            st.markdown(f"- **初始资金：** `{rs.get('initial_cash', 1000000):,.0f}`")
            sw = rs.get("sample_window", {})
            st.markdown(f"- **样本区间：** `{sw.get('start', '—')}` ~ `{sw.get('end', '—')}`")
        with st.expander("查看完整 ResearchSpec"):
            st.code(_json_block(research_spec), language="json")

    # Step 3: Factor Generation
    with st.chat_message("assistant"):
        st.markdown("**FactorGenerationAgent**")
        with st.spinner("正在生成候选因子..."):
            factor_specs = generate_factors(idea_spec, research_spec)
        factor_names = "、".join(f["factor_name"] for f in factor_specs)
        st.write(f"已生成候选因子：{factor_names}。")

    # Step 4: Backtest
    with st.chat_message("assistant"):
        st.markdown("**BacktestEngine**")
        with st.spinner("正在执行回测..."):
            compiled_factors = compile_factors(factor_specs)
            backtest_result = run_backtest(factor_specs, research_spec)
        best = backtest_result["factor_results"][0]
        st.write(
            f"最佳因子：**{best['factor_name']}**，"
            f"IC 均值：{best['ic_mean']:.4f}，"
            f"夏普：{best.get('sharpe_ratio', 0):.2f}，"
            f"最大回撤：{best['max_drawdown']:.2%}"
        )
        if backtest_result.get("mercury_results"):
            st.caption("包含 交易级回测结果")

    # Step 5: LLM Explanation
    with st.chat_message("assistant"):
        st.markdown("**BacktestExplanationAgent**")
        placeholder = st.empty()
        placeholder.info("⏳ DeepSeek API 正在生成分析报告（约需1分钟）...")
        start = time.time()
        explanation = explain_backtest(backtest_result)
        elapsed = time.time() - start
        placeholder.empty()
        if explanation.get("is_fallback"):
            st.caption("LLM 不可用，当前为规则生成的分析")
        else:
            st.caption(f"DeepSeek API 生成完成（{elapsed:.0f}秒）")
        with st.expander("总体评价", expanded=True):
            st.write(explanation.get("summary", ""))
        with st.expander("IC 分析"):
            st.write(explanation.get("ic_analysis", ""))
        with st.expander("风险评估"):
            st.write(explanation.get("risk_assessment", ""))
        with st.expander("改进建议"):
            st.write(explanation.get("recommendations", ""))

    # Step 6: Audit
    with st.chat_message("assistant"):
        st.markdown("**AuditAgent**")
        with st.spinner("正在执行审计..."):
            partial_trace = {
                "input_text": input_text,
                "idea_spec": idea_spec,
                "research_spec": research_spec,
                "factor_specs": factor_specs,
                "compiled_factors": compiled_factors,
                "backtest_result": backtest_result,
                "explanation": explanation,
            }
            audit_report = run_audit(partial_trace)
        st.write(f"当前审计等级：`{audit_report['overall_level']}`。")
        for check in audit_report["checks"]:
            st.write(f"- {check['item']}：{check['message']}")

    # Build full trace
    trace = build_research_trace(
        input_text=input_text,
        idea_spec=idea_spec,
        research_spec=research_spec,
        factor_specs=factor_specs,
        backtest_result=backtest_result,
        explanation=explanation,
        audit_report=audit_report,
        report_markdown="",
    )
    trace["compiled_factors"] = compiled_factors
    with st.chat_message("assistant"):
        st.markdown("**ReportAgent**")
        with st.spinner("正在生成研究报告..."):
            trace["report_markdown"] = generate_report(trace)
        st.success("研究报告生成完成")
    if save_trace:
        trace["trace_path"] = save_research_trace(trace)

    return trace


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
        st.markdown("**研究配置确认**")
        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown(f"- **股票池：** `{research.get('universe', '—')}`")
            st.markdown(f"- **持有期：** `{research.get('holding_period', '—')}`")
            st.markdown(f"- **基准：** `{research.get('benchmark', '沪深300')}`")
        with col_r:
            st.markdown(f"- **调仓频率：** `{research.get('rebalance_frequency', '—')}`")
            st.markdown(f"- **交易成本：** `{research.get('transaction_cost_bps', 10)} bps`")
            st.markdown(f"- **初始资金：** `{research.get('initial_cash', 1000000):,.0f}`")
            sw = research.get("sample_window", {})
            st.markdown(f"- **样本区间：** `{sw.get('start', '—')}` ~ `{sw.get('end', '—')}`")
        with st.expander("查看完整 ResearchSpec"):
            st.code(_json_block(research), language="json")

    with st.chat_message("assistant"):
        st.markdown("**FactorGenerationAgent**")
        factor_names = "、".join(factor["factor_name"] for factor in trace["factor_specs"])
        st.write(f"已生成候选因子：{factor_names}。")

    with st.chat_message("assistant"):
        st.markdown("**BacktestEngine**")
        br = trace["backtest_result"]
        best = br["factor_results"][0]
        source_summary = backtest_source_summary(br)
        st.caption(f"回测来源：{source_summary['label']}")
        st.write(f"最佳因子：**{best['factor_name']}**，IC 均值：{best['ic_mean']:.4f}，夏普：{best.get('sharpe_ratio', 0):.2f}，最大回撤：{best['max_drawdown']:.2%}")
        mercury = br.get("mercury_results", {})
        if mercury:
            fid, s = next(iter(mercury.items()))
            st.markdown("---")
            st.markdown(f"**交易级回测** — {fid}")
            mcols = st.columns(5)
            mcols[0].metric("总收益", f"{s.get('total_return', 0):.2%}")
            mcols[1].metric("年化收益", f"{s.get('annualized_return', 0):.2%}")
            mcols[2].metric("夏普比率", f"{s.get('sharpe', 0):.2f}")
            mcols[3].metric("最大回撤", f"{s.get('max_drawdown', 0):.2%}")
            mcols[4].metric("年化波动", f"{s.get('annualized_volatility', 0):.2%}")
            mcols2 = st.columns(5)
            mcols2[0].metric("交易天数", s.get("trading_days", "—"))
            mcols2[1].metric("交易笔数", s.get("total_trades", "—"))
            mcols2[2].metric("总换手率", f"{s.get('total_turnover', 0):.2f}")
            mcols2[3].metric("日胜率", f"{s.get('win_rate', 0):.2%}")
            mcols2[4].metric("最终净值", f"{s.get('final_unit_nav', 0):.4f}")

    with st.chat_message("assistant"):
        st.markdown("**BacktestExplanationAgent**")
        if explanation.get("is_fallback"):
            st.caption("LLM 不可用，当前为规则生成的分析")
        with st.expander("总体评价", expanded=True):
            st.write(explanation.get("summary", ""))
        with st.expander("IC 分析"):
            st.write(explanation.get("ic_analysis", ""))
        with st.expander("风险评估"):
            st.write(explanation.get("risk_assessment", ""))
        with st.expander("改进建议"):
            st.write(explanation.get("recommendations", ""))

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
        st.number_input("初始资金", value=float(research.get("initial_cash", 1000000)), disabled=True)
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
    backtest_result = trace["backtest_result"]
    metrics_list = backtest_result.get("factor_results", [])

    if not metrics_list:
        st.info("暂无回测数据。")
        return

    best = metrics_list[0]

    # --- KPI cards ---
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("最佳因子", best.get("factor_name", "-"))
    col2.metric("IC 均值", f"{best.get('ic_mean', 0):.4f}")
    col3.metric("Rank IC", f"{best.get('rank_ic_mean', 0):.4f}")
    col4.metric("多空夏普", f"{best.get('sharpe_ratio', 0):.2f}")
    col5.metric("最大回撤", f"{best.get('max_drawdown', 0):.2%}")

    # --- Factor comparison table ---
    if len(metrics_list) > 0:
        display = pd.DataFrame(metrics_list)
        keep_cols = [
            "factor_name", "engine", "ic_mean", "rank_ic_mean", "icir", "rank_icir",
            "ic_positive_ratio", "long_short_return", "sharpe_ratio",
            "max_drawdown", "annual_volatility",
        ]
        avail_cols = [c for c in keep_cols if c in display.columns]
        if avail_cols:
            display = display[avail_cols].rename(
                columns={
                    "factor_name": "因子",
                    "engine": "来源",
                    "ic_mean": "IC均值",
                    "rank_ic_mean": "RankIC均值",
                    "icir": "ICIR",
                    "rank_icir": "RankICIR",
                    "ic_positive_ratio": "IC为正比例",
                    "long_short_return": "多空收益",
                    "sharpe_ratio": "夏普",
                    "max_drawdown": "最大回撤",
                    "annual_volatility": "年化波动",
                }
            )
            st.dataframe(display, width="stretch", hide_index=True)

    # --- Plotly charts ---
    charts = backtest_result.get("charts", {})
    if charts:
        with st.expander("回测图表", expanded=True):
            chart_groups = [group for group in group_charts_by_factor(charts, metrics_list) if group["charts"]]
            tabs = st.tabs([group["factor_name"] for group in chart_groups])
            for tab, group in zip(tabs, chart_groups):
                with tab:
                    if group.get("engine"):
                        st.caption(f"来源：{group['engine']}")
                    for chart in group["charts"]:
                        st.markdown(f"**{chart['label']}**")
                        st.plotly_chart(chart["figure"], width='stretch', key=chart["key"])
    else:
        # Fallback: simple line chart from nav_series if available
        nav = backtest_result.get("nav_series", [])
        if nav:
            nav_df = pd.DataFrame(nav).set_index("date")
            st.line_chart(nav_df)



def _render_report(trace: dict[str, Any]) -> None:
    st.subheader("研究报告")
    st.markdown(trace["report_markdown"])

    if "trace_path" in trace:
        st.success(f"Research Trace 已保存：{trace['trace_path']}")

    with st.expander("完整 Research Trace"):
        st.code(_json_block(trace), language="json")


def _render_data_source(trace: dict[str, Any]) -> None:
    """Show data source indicators: Mercury / Local / Mock."""
    br = trace.get("backtest_result", {})
    summary = backtest_source_summary(br)
    chips = [f'<span class="status-chip active">{chip}</span>' for chip in summary["chips"]]
    if chips:
        st.markdown("".join(chips), unsafe_allow_html=True)


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


def _render_workflow() -> None:
    """Progressive workflow with human-in-the-loop config checkpoint.

    Renders agent outputs as chat messages, pausing at Step 2 for user
    to review and edit the research config before backtest execution.
    """
    wf = st.session_state

    # User message (re-rendered on each phase)
    st.chat_message("user").write(wf.wf_data["input_text"])

    # === Step 1: Idea Extraction ===
    if "idea_spec" not in wf.wf_data:
        with st.chat_message("assistant"):
            st.markdown("**IdeaExtractionAgent**")
            with st.spinner("正在提取投资思想..."):
                wf.wf_data["idea_spec"] = extract_idea(wf.wf_data["input_text"])
            st.write(wf.wf_data["idea_spec"]["core_hypothesis"])
            st.caption("已提炼投资假设、经济机制、所需数据和风险点。")
        wf.wf_step = 2
        st.rerun()

    with st.chat_message("assistant"):
        st.markdown("**IdeaExtractionAgent**")
        st.write(wf.wf_data["idea_spec"]["core_hypothesis"])
        st.caption("已提炼投资假设、经济机制、所需数据和风险点。")

    # === Step 2: Research Config + Human-in-the-loop Checkpoint ===
    if "research_spec" not in wf.wf_data:
        rs_raw = build_research_spec(wf.wf_data["idea_spec"])
        with st.chat_message("assistant"):
            st.markdown("**ResearchSpec Builder**")
            st.markdown("**研究配置确认（可编辑）**")
            col_l, col_r = st.columns(2)
            with col_l:
                universe = st.text_input("股票池", value=rs_raw.get("universe", ""), key="wf_universe")
                holding = st.text_input("持有期", value=str(rs_raw.get("holding_period", "")), key="wf_holding")
                benchmark = st.text_input("基准", value=rs_raw.get("benchmark", "沪深300"), key="wf_bench")
            with col_r:
                rebalance = st.text_input("调仓频率", value=rs_raw.get("rebalance_frequency", ""), key="wf_rebal")
                cost = st.number_input("交易成本 bps", value=int(rs_raw.get("transaction_cost_bps", 10)), key="wf_cost")
                initial_cash = st.number_input(
                    "初始资金",
                    min_value=10000.0,
                    value=float(rs_raw.get("initial_cash", 1000000)),
                    step=100000.0,
                    key="wf_initial_cash",
                )
                sw = rs_raw.get("sample_window", {})
                sample_start = st.text_input("样本开始", value=sw.get("start", ""), key="wf_sample_start")
                sample_end = st.text_input("样本结束", value=sw.get("end", ""), key="wf_sample_end")
            st.info("请确认以上研究配置，点击下方按钮继续执行回测")
            if st.button("确认配置，继续回测", type="primary"):
                updated_research_spec = apply_research_config_edits(
                    rs_raw,
                    universe=universe,
                    holding_period=holding,
                    benchmark=benchmark,
                    rebalance_frequency=rebalance,
                    transaction_cost_bps=int(cost),
                    sample_start=sample_start,
                    sample_end=sample_end,
                )
                updated_research_spec["initial_cash"] = float(initial_cash)
                updated_research_spec.setdefault("backtest", {})
                updated_research_spec["backtest"]["initial_cash"] = float(initial_cash)
                wf.wf_data["research_spec"] = updated_research_spec
                wf.wf_step = 3
                st.rerun()
        return  # Pause — wait for user to click confirm

    # Step 2 display (read-only after confirmed)
    with st.chat_message("assistant"):
        st.markdown("**ResearchSpec Builder**")
        rs = wf.wf_data["research_spec"]
        st.markdown("**研究配置确认**")
        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown(f"- **股票池：** `{rs.get('universe', '—')}`")
            st.markdown(f"- **持有期：** `{rs.get('holding_period', '—')}`")
            st.markdown(f"- **基准：** `{rs.get('benchmark', '沪深300')}`")
        with col_r:
            st.markdown(f"- **调仓频率：** `{rs.get('rebalance_frequency', '—')}`")
            st.markdown(f"- **交易成本：** `{rs.get('transaction_cost_bps', 10)} bps`")
            st.markdown(f"- **初始资金：** `{rs.get('initial_cash', 1000000):,.0f}`")
            sw = rs.get("sample_window", {})
            st.markdown(f"- **样本区间：** `{sw.get('start', '—')}` ~ `{sw.get('end', '—')}`")

    # === Step 3: Factor Generation ===
    if "factor_specs" not in wf.wf_data:
        with st.chat_message("assistant"):
            st.markdown("**FactorGenerationAgent**")
            with st.spinner("正在生成候选因子..."):
                wf.wf_data["factor_specs"] = generate_factors(wf.wf_data["idea_spec"], wf.wf_data["research_spec"])
            factor_names = "、".join(f["factor_name"] for f in wf.wf_data["factor_specs"])
            st.write(f"已生成候选因子：{factor_names}。")
        wf.wf_step = 4
        st.rerun()

    with st.chat_message("assistant"):
        st.markdown("**FactorGenerationAgent**")
        factor_names = "、".join(f["factor_name"] for f in wf.wf_data["factor_specs"])
        st.write(f"已生成候选因子：{factor_names}。")

    # === Step 4: Backtest (Mercury first, local fallback if needed) ===
    if "backtest_result" not in wf.wf_data:
        with st.chat_message("assistant"):
            st.markdown("**BacktestEngine**")
            with st.spinner("正在执行 Mercury 回测，失败时自动切换本地 fallback..."):
                wf.wf_data["compiled_factors"] = compile_factors(wf.wf_data["factor_specs"])
                wf.wf_data["backtest_result"] = run_backtest(wf.wf_data["factor_specs"], wf.wf_data["research_spec"])
            br = wf.wf_data["backtest_result"]
            best = br["factor_results"][0]
            source_summary = backtest_source_summary(br)
            st.caption(f"回测来源：{source_summary['label']}")
            st.write(f"最佳因子：**{best['factor_name']}**，IC 均值：{best['ic_mean']:.4f}，夏普：{best.get('sharpe_ratio', 0):.2f}，最大回撤：{best['max_drawdown']:.2%}")

            # --- Inline Mercury result (only the best factor) ---
            mercury = br.get("mercury_results", {})
            if mercury:
                fid, s = next(iter(mercury.items()))
                st.markdown("---")
                st.markdown(f"**交易级回测** — {fid}")
                mcols = st.columns(5)
                mcols[0].metric("总收益", f"{s.get('total_return', 0):.2%}")
                mcols[1].metric("年化收益", f"{s.get('annualized_return', 0):.2%}")
                mcols[2].metric("夏普比率", f"{s.get('sharpe', 0):.2f}")
                mcols[3].metric("最大回撤", f"{s.get('max_drawdown', 0):.2%}")
                mcols[4].metric("年化波动", f"{s.get('annualized_volatility', 0):.2%}")
                mcols2 = st.columns(5)
                mcols2[0].metric("交易天数", s.get("trading_days", "—"))
                mcols2[1].metric("交易笔数", s.get("total_trades", "—"))
                mcols2[2].metric("总换手率", f"{s.get('total_turnover', 0):.2f}")
                mcols2[3].metric("日胜率", f"{s.get('win_rate', 0):.2%}")
                mcols2[4].metric("最终净值", f"{s.get('final_unit_nav', 0):.4f}")
        wf.wf_step = 5
        st.rerun()

    with st.chat_message("assistant"):
        st.markdown("**BacktestEngine**")
        br = wf.wf_data["backtest_result"]
        best = br["factor_results"][0]
        source_summary = backtest_source_summary(br)
        st.caption(f"回测来源：{source_summary['label']}")
        st.write(f"最佳因子：**{best['factor_name']}**，IC 均值：{best['ic_mean']:.4f}，夏普：{best.get('sharpe_ratio', 0):.2f}，最大回撤：{best['max_drawdown']:.2%}")
        mercury = br.get("mercury_results", {})
        if mercury:
            fid, s = next(iter(mercury.items()))
            st.markdown("---")
            st.markdown(f"**交易级回测** — {fid}")
            mcols = st.columns(5)
            mcols[0].metric("总收益", f"{s.get('total_return', 0):.2%}")
            mcols[1].metric("年化收益", f"{s.get('annualized_return', 0):.2%}")
            mcols[2].metric("夏普比率", f"{s.get('sharpe', 0):.2f}")
            mcols[3].metric("最大回撤", f"{s.get('max_drawdown', 0):.2%}")
            mcols[4].metric("年化波动", f"{s.get('annualized_volatility', 0):.2%}")
            mcols2 = st.columns(5)
            mcols2[0].metric("交易天数", s.get("trading_days", "—"))
            mcols2[1].metric("交易笔数", s.get("total_trades", "—"))
            mcols2[2].metric("总换手率", f"{s.get('total_turnover', 0):.2f}")
            mcols2[3].metric("日胜率", f"{s.get('win_rate', 0):.2%}")
            mcols2[4].metric("最终净值", f"{s.get('final_unit_nav', 0):.4f}")

    # === Step 5: LLM Explanation ===
    if "explanation" not in wf.wf_data:
        with st.chat_message("assistant"):
            st.markdown("**BacktestExplanationAgent**")
            placeholder = st.empty()
            placeholder.info("⏳ DeepSeek API 正在生成分析报告（约需1分钟）...")
            start = time.time()
            wf.wf_data["explanation"] = explain_backtest(wf.wf_data["backtest_result"])
            elapsed = time.time() - start
            placeholder.empty()
            if wf.wf_data["explanation"].get("is_fallback"):
                st.caption("LLM 不可用，当前为规则生成的分析")
            else:
                st.caption(f"DeepSeek API 生成完成（{elapsed:.0f}秒）")
            with st.expander("总体评价", expanded=True):
                st.write(wf.wf_data["explanation"].get("summary", ""))
            with st.expander("IC 分析"):
                st.write(wf.wf_data["explanation"].get("ic_analysis", ""))
            with st.expander("风险评估"):
                st.write(wf.wf_data["explanation"].get("risk_assessment", ""))
            with st.expander("改进建议"):
                st.write(wf.wf_data["explanation"].get("recommendations", ""))
        wf.wf_step = 6
        st.rerun()

    explanation = wf.wf_data["explanation"]
    with st.chat_message("assistant"):
        st.markdown("**BacktestExplanationAgent**")
        if explanation.get("is_fallback"):
            st.caption("LLM 不可用，当前为规则生成的分析")
        with st.expander("总体评价", expanded=True):
            st.write(explanation.get("summary", ""))
        with st.expander("IC 分析"):
            st.write(explanation.get("ic_analysis", ""))
        with st.expander("风险评估"):
            st.write(explanation.get("risk_assessment", ""))
        with st.expander("改进建议"):
            st.write(explanation.get("recommendations", ""))

    # === Step 6: Audit ===
    if "audit_report" not in wf.wf_data:
        with st.chat_message("assistant"):
            st.markdown("**AuditAgent**")
            with st.spinner("正在执行审计..."):
                partial_trace = {
                    "input_text": wf.wf_data["input_text"],
                    "idea_spec": wf.wf_data["idea_spec"],
                    "research_spec": wf.wf_data["research_spec"],
                    "factor_specs": wf.wf_data["factor_specs"],
                    "compiled_factors": wf.wf_data["compiled_factors"],
                    "backtest_result": wf.wf_data["backtest_result"],
                    "explanation": wf.wf_data["explanation"],
                }
                wf.wf_data["audit_report"] = run_audit(partial_trace)
            st.write(f"当前审计等级：`{wf.wf_data['audit_report']['overall_level']}`。")
            for check in wf.wf_data["audit_report"]["checks"]:
                st.write(f"- {check['item']}：{check['message']}")
        wf.wf_step = 7
        st.rerun()

    audit = wf.wf_data["audit_report"]
    with st.chat_message("assistant"):
        st.markdown("**AuditAgent**")
        st.write(f"当前审计等级：`{audit['overall_level']}`。")
        for check in audit["checks"]:
            st.write(f"- {check['item']}：{check['message']}")

    # === Step 7: Report + Finalize ===
    if "report_markdown" not in wf.wf_data:
        with st.chat_message("assistant"):
            st.markdown("**ReportAgent**")
            with st.spinner("正在生成研究报告..."):
                trace = build_research_trace(
                    input_text=wf.wf_data["input_text"],
                    idea_spec=wf.wf_data["idea_spec"],
                    research_spec=wf.wf_data["research_spec"],
                    factor_specs=wf.wf_data["factor_specs"],
                    backtest_result=wf.wf_data["backtest_result"],
                    explanation=wf.wf_data["explanation"],
                    audit_report=wf.wf_data["audit_report"],
                    report_markdown="",
                )
                trace["compiled_factors"] = wf.wf_data["compiled_factors"]
                trace["report_markdown"] = generate_report(trace)
            st.success("研究报告生成完成")

        if wf.wf_data.get("save_trace"):
            trace["trace_path"] = save_research_trace(trace)

        st.session_state["trace"] = trace
        st.session_state.wf_step = 0
        st.session_state.wf_data = {}
        st.rerun()


st.set_page_config(page_title="AlphaWorkbench", page_icon="AW", layout="wide")
st.markdown(PAGE_STYLE, unsafe_allow_html=True)

if "trace" not in st.session_state:
    st.session_state["trace"] = None
if "wf_step" not in st.session_state:
    st.session_state.wf_step = 0
    st.session_state.wf_data = {}

with st.sidebar:
    st.markdown("## AlphaWorkbench")
    st.caption("AI research copilot")
    input_text = st.text_area("投资想法 / 研报摘要", value=DEFAULT_INPUT, height=180)
    save_trace = st.toggle("保存 Research Trace", value=False)

    run_clicked = st.button("生成研究 baseline", type="primary", width="stretch")

    if st.button("重置会话", width="stretch"):
        st.session_state["trace"] = None
        st.session_state.wf_step = 0
        st.session_state.wf_data = {}
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
    elif run_clicked:
        st.info("正在生成研究 Baseline ...")
    else:
        st.info("等待研究输入")

_render_status(trace)
if trace:
    _render_data_source(trace)

st.divider()

# === Workflow trigger ===
if run_clicked and st.session_state.wf_step == 0:
    st.session_state.wf_step = 1
    st.session_state.wf_data = {"input_text": input_text, "save_trace": save_trace}
    st.rerun()

# === Progressive workflow (state machine) ===
if st.session_state.wf_step > 0:
    try:
        _render_workflow()
    except Exception as e:
        st.error(f"工作流出错：{e}")
        st.session_state.wf_step = 0
        st.session_state.wf_data = {}

# === Post-workflow full view ===
if trace:
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

# === Pre-workflow empty state ===
elif st.session_state.wf_step == 0:
    col1, col2 = st.columns([0.58, 0.42])
    with col1:
        _render_empty_state()
    with col2:
        st.markdown("#### 默认演示主题")
        st.write(DEFAULT_INPUT)
        st.markdown("#### 研究输出")
        st.write("系统将生成投资思想、研究配置、候选因子、基础回测、审计提示和研究报告。")
