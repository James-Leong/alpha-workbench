"""Lightweight schema helpers for the demo.

The MVP keeps schemas as plain dictionaries so the mock workflow can run before
all dependencies are installed. The same field names can later be promoted to
Pydantic models without changing module interfaces.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_IDEA_SPEC: dict[str, Any] = {
    "idea_name": "盈利超预期后的滞后定价",
    "core_hypothesis": "单季度净利润显著超预期且公告前股价未充分上涨的公司，未来一个月可能获得超额收益。",
    "economic_mechanism": [
        "盈利信息改善会推动分析师和投资者上修预期。",
        "如果公告前价格反应不足，公告后可能存在滞后定价。",
        "行业中性化后可以降低行业景气度共振带来的干扰。",
    ],
    "required_data_concepts": [
        "单季度净利润",
        "一致预期净利润或历史可比利润",
        "公告日前收益率",
        "行业分类",
        "未来收益率",
    ],
    "risk_flags": [
        "一致预期数据在 demo 中可能需要 proxy。",
        "公告日和财报可得时间必须避免未来函数。",
        "小样本回测结果只用于流程展示，不代表真实投资建议。",
    ],
    "evidence": [
        {
            "source": "user_input",
            "text": "单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。",
        }
    ],
    "is_mock": True,
}


DEFAULT_RESEARCH_SPEC: dict[str, Any] = {
    "universe": "沪深300样例股票池",
    "rebalance_frequency": "monthly",
    "holding_period": "20 trading days",
    "neutralization": ["industry"],
    "filters": ["exclude_suspended", "exclude_st"],
    "transaction_cost_bps": 10,
    "benchmark": "沪深300",
    "sample_window": {
        "start": "2021-01-01",
        "end": "2023-12-31",
    },
    "data_policy": {
        "announcement_lag": "use_public_announcement_date",
        "forecast_proxy_allowed": True,
    },
    "is_mock": True,
}


def clone_default_idea_spec() -> dict[str, Any]:
    return deepcopy(DEFAULT_IDEA_SPEC)


def clone_default_research_spec() -> dict[str, Any]:
    return deepcopy(DEFAULT_RESEARCH_SPEC)


def build_research_trace(
    *,
    input_text: str,
    idea_spec: dict[str, Any],
    research_spec: dict[str, Any],
    factor_specs: list[dict[str, Any]],
    backtest_result: dict[str, Any],
    explanation: dict[str, Any],
    audit_report: dict[str, Any],
    report_markdown: str,
) -> dict[str, Any]:
    return {
        "project": "AlphaWorkbench",
        "trace_version": "0.1",
        "input_text": input_text,
        "idea_spec": idea_spec,
        "research_spec": research_spec,
        "factor_specs": factor_specs,
        "backtest_result": backtest_result,
        "explanation": explanation,
        "audit_report": audit_report,
        "report_markdown": report_markdown,
    }
