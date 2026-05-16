"""Lightweight audit agent for demo traces."""

from __future__ import annotations

from typing import Any


def mock_run_audit(trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall_level": "medium",
        "checks": [
            {
                "item": "未来函数",
                "level": "medium",
                "message": "必须确认财报公告日和一致预期截面时间，demo 暂用 announcement_lag 规则标记。",
            },
            {
                "item": "数据 proxy",
                "level": "medium",
                "message": "一致预期净利润在 MVP 中可用历史同期利润 proxy，但报告中必须显式披露。",
            },
            {
                "item": "样本稳健性",
                "level": "low",
                "message": "当前为小样例 mock 回测，不能作为真实收益结论。",
            },
        ],
        "next_actions": [
            "接入真实公告日字段。",
            "替换一致预期 proxy。",
            "增加分年度和分行业稳健性检验。",
        ],
        "is_mock": True,
    }


def run_audit(trace: dict[str, Any]) -> dict[str, Any]:
    return mock_run_audit(trace)
