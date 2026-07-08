"""Alpha Memory — historical research trace browser.

Absorbed from origin/main and adapted to the product package.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st


RUNS_DIR = Path(__file__).resolve().parents[3] / "runs"


def _parse_trace_time(filename: str) -> str:
    """Parse filename like research_trace_YYYYMMDD_HHMMSS.json into readable time."""
    try:
        stem = filename.replace("research_trace_", "").replace(".json", "")
        dt = datetime.strptime(stem, "%Y%m%d_%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return filename


def _level_color(level: str) -> str:
    level = str(level).lower()
    if level == "high":
        return "🔴"
    if level == "medium":
        return "🟡"
    return "🟢"


def load_traces() -> list[dict[str, Any]]:
    """Load all research traces from the runs directory."""
    if not RUNS_DIR.exists():
        return []
    files = sorted(RUNS_DIR.glob("research_trace_*.json"), reverse=True)
    traces = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            data["_filename"] = f.name
            data["_time"] = _parse_trace_time(f.name)
            traces.append(data)
        except Exception:
            continue
    return traces


def main() -> None:
    st.set_page_config(page_title="Alpha Memory", page_icon="🧠", layout="wide")
    st.title("Alpha Memory")
    st.caption("历史研究记录浏览")

    traces = load_traces()
    if not traces:
        st.info("暂无历史研究记录。请先运行完整研究流程并保存 trace。")
        return

    st.write(f"共找到 {len(traces)} 条记录")

    for trace in traces:
        idea_spec = trace.get("idea_spec") or {}
        audit_report = trace.get("audit_report") or {}
        overall_level = audit_report.get("overall_level", "unknown")
        is_mock = audit_report.get("is_mock", True)

        title = idea_spec.get("idea_name") or idea_spec.get("core_hypothesis") or trace.get("input_text", "")[:40]
        subtitle = f"{trace['_time']} · 审计等级: {_level_color(overall_level)} {overall_level} · {'mock' if is_mock else '真实 LLM'}"

        with st.expander(f"{title} — {subtitle}"):
            left, right = st.columns(2)
            with left:
                st.markdown("**审计结果**")
                checks = audit_report.get("checks", [])
                if checks:
                    for check in checks:
                        item = check.get("item", "未知")
                        level = check.get("level", "low")
                        message = check.get("message", "")
                        st.markdown(f"- {_level_color(level)} **{item}** ({level}): {message}")
                else:
                    st.write("无审计记录")

                next_actions = audit_report.get("next_actions", [])
                if next_actions:
                    st.markdown("**建议行动**")
                    for action in next_actions:
                        st.markdown(f"- {action}")
            with right:
                st.markdown("**研究报告**")
                report = trace.get("report_markdown", "")
                if report:
                    st.markdown(report)
                else:
                    st.write("无报告")


main()
