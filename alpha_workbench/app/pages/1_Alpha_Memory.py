"""Alpha Memory — 历史研究记录浏览页面"""
import json
from pathlib import Path
from datetime import datetime
import streamlit as st

RUNS_DIR = Path(__file__).parents[3] / "runs"

st.title("🧠 Alpha Memory")
st.caption("所有历史研究记录 · 可回溯 · 可对比")

def load_traces():
    files = sorted(RUNS_DIR.glob("research_trace_*.json"), reverse=True)
    traces = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            data["_filename"] = f.name
            traces.append(data)
        except Exception:
            continue
    return traces

def level_badge(level: str) -> str:
    color = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(str(level).lower(), "⚪")
    return f"{color} {level.upper()}"

traces = load_traces()

if not traces:
    st.warning("还没有任何研究记录，先跑一次完整流程吧。")
    st.stop()

st.markdown(f"**共找到 {len(traces)} 条历史记录**")
st.divider()

for i, trace in enumerate(traces):
    filename = trace.get("_filename", "")
    try:
        ts = filename.replace("research_trace_", "").replace(".json", "")
        dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        time_str = filename

    hypothesis = (
        trace.get("idea_spec", {}).get("core_hypothesis")
        or trace.get("input_text", "")
        or "无描述"
    )[:80]

    audit = trace.get("audit_report", {})
    overall_level = audit.get("overall_level", "未知")
    is_mock = audit.get("is_mock", True)
    audit_tag = "🤖 真实LLM" if not is_mock else "🔧 Mock"

    with st.expander(f"📄 {time_str}　|　{level_badge(overall_level)}　|　{audit_tag}　|　{hypothesis}…"):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 📊 审计结果")
            checks = audit.get("checks", [])
            if checks:
                for c in checks:
                    badge = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(c.get("level",""), "⚪")
                    st.markdown(f"{badge} **{c.get('item','')}**")
                    st.caption(c.get("message", ""))
            else:
                st.info("无审计数据")

            next_actions = audit.get("next_actions", [])
            if next_actions:
                st.markdown("**建议行动：**")
                for a in next_actions:
                    st.markdown(f"- {a}")

        with col2:
            st.markdown("#### 📝 研究报告")
            report = trace.get("report_markdown", "")
            if report:
                st.markdown(report)
            else:
                st.info("无报告数据")
