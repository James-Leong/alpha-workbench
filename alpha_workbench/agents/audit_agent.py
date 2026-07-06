"""Audit agent — real LLM implementation with mock fallback."""

from __future__ import annotations

from typing import Any

from agno.agent import Agent
from pydantic import BaseModel, Field

from alpha_workbench.agents.core.model import AlphaModel
from alpha_workbench.core.config import settings


class AuditCheck(BaseModel):
    """单项审计发现。"""

    item: str = Field(..., description="问题名称，如未来函数、数据 proxy、样本稳健性")
    level: str = Field(..., description="风险等级：high / medium / low")
    message: str = Field(..., description="具体说明")


class AuditResult(BaseModel):
    """审计结果结构化输出。"""

    overall_level: str = Field(..., description="整体风险等级：high / medium / low")
    checks: list[AuditCheck] = Field(..., description="审计发现列表")
    next_actions: list[str] = Field(..., description="建议行动")


def _build_prompt(trace: dict[str, Any]) -> str:
    factor_specs = trace.get("factor_specs", [])
    factor_lines = []
    for f in factor_specs:
        name = f.get("factor_name", "未知因子")
        desc = f.get("plain_description", "")
        risks = f.get("risk_notes", [])
        risk_str = "；".join(risks) if risks else "无"
        factor_lines.append(f"- 因子名：{name}\n  描述：{desc}\n  已知风险：{risk_str}")
    factors_text = "\n".join(factor_lines) if factor_lines else "无因子信息"

    research_spec = trace.get("research_spec", {})
    sample_window = research_spec.get("sample_window", {})

    return f"""你是一个量化因子审计专家。请对以下因子研究进行风险审计，重点检查三类问题：
1. 未来函数风险：因子计算是否可能用到了未来才能知道的数据
2. 数据proxy风险：是否用了替代数据，是否需要披露
3. 样本稳健性：回测样本是否足够，结论是否可靠

【研究基本信息】
- 股票池：{research_spec.get("universe", "未知")}
- 回测区间：{sample_window.get("start", "?")} 至 {sample_window.get("end", "?")}
- 调仓频率：{research_spec.get("rebalance_frequency", "未知")}
- 是否模拟数据：{research_spec.get("is_mock", True)}

【候选因子列表】
{factors_text}

请用以下JSON格式输出审计结果，不要输出任何其他内容：
{{
  "overall_level": "high/medium/low之一",
  "checks": [
    {{"item": "问题名称", "level": "high/medium/low", "message": "具体说明"}},
    ...
  ],
  "next_actions": ["建议行动1", "建议行动2", ...]
}}"""


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
    """Run audit using AlphaModel when API key is available, otherwise mock."""
    if not settings.llm_api_key:
        return mock_run_audit(trace)

    try:
        agent = Agent(
            model=AlphaModel(),
            output_schema=AuditResult,
            instructions="你是一位专业的量化因子审计专家。请严格按要求的 JSON 结构输出审计结果。",
        )
        prompt = _build_prompt(trace)
        response = agent.run(prompt)
        result = response.content if hasattr(response, "content") else response
        if isinstance(result, AuditResult):
            data = result.model_dump()
        elif isinstance(result, dict):
            data = result
        else:
            return mock_run_audit(trace)
        data["is_mock"] = False
        data["is_fallback"] = False
        return data
    except Exception as e:
        print(f"[AuditAgent] LLM调用失败，使用mock fallback: {e}")
        return mock_run_audit(trace)
