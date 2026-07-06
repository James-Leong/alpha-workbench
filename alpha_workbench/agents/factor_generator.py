"""Factor generation agent with real LLM and mock fallback."""

from __future__ import annotations

from typing import Any

from agno.agent import Agent
from pydantic import BaseModel, Field

from alpha_workbench.agents.core.model import AlphaModel
from alpha_workbench.core.config import settings


class FactorSpecModel(BaseModel):
    """候选因子结构化输出（与现有 mock 格式保持一致）。"""

    factor_id: str = Field(..., description="因子唯一标识")
    factor_name: str = Field(..., description="因子名称")
    plain_description: str = Field(..., description="自然语言解释")
    latex_formula: str = Field(..., description="LaTeX 公式")
    formula_tree: dict[str, Any] = Field(..., description="受限表达式树")
    required_fields: list[str] = Field(..., description="所需字段")
    risk_notes: list[str] = Field(default_factory=list, description="风险提示")


class FactorSpecsResponse(BaseModel):
    """LLM 返回的候选因子列表包装。"""

    factors: list[FactorSpecModel] = Field(..., description="候选因子列表")


def _supported_operators() -> str:
    return (
        "abs, add, subtract, multiply, divide, ref, "
        "industry_zscore, zscore, rank, winsorize, "
        "ts_mean, ts_std, ts_max, ts_min, ts_sum, ts_rank, "
        "ts_corr, ts_delta, ts_delay, ts_zscore, ts_pct_change, pct_change"
    )


def _build_prompt(idea_spec: dict[str, Any], research_spec: dict[str, Any]) -> str:
    hypothesis = idea_spec.get("core_hypothesis", "")
    mechanisms = "\n".join(idea_spec.get("economic_mechanism", []))
    return f"""你是一位量化因子研究专家。请基于以下投资思想，生成 3-5 个候选因子。

【投资假设】
{hypothesis}

【经济机制】
{mechanisms}

【研究配置】
- 股票池：{research_spec.get("universe", "未知")}
- 调仓频率：{research_spec.get("rebalance_frequency", "未知")}
- 持有期：{research_spec.get("holding_period", "未知")}

请输出以下 JSON 结构（不要输出其他内容）：
{{
  "factors": [
    {{
      "factor_id": "唯一英文标识",
      "factor_name": "因子中文名",
      "plain_description": "自然语言解释",
      "latex_formula": "LaTeX 公式字符串",
      "formula_tree": {{"op": "操作符", "args": [...]}},
      "required_fields": ["字段1", "字段2"],
      "risk_notes": ["风险1", "风险2"]
    }},
    ...
  ]
}}

约束：
1. formula_tree 只能使用以下操作符：{_supported_operators()}
2. 不要直接生成可执行 Python 代码。
3. 必须标注数据 proxy、未来函数风险。
4. 输出必须是合法 JSON。"""


def mock_generate_factors(
    idea_spec: dict[str, Any],
    research_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "factor_id": "earnings_surprise_adj_001",
            "factor_name": "行业中性盈利超预期",
            "plain_description": "衡量单季度净利润相对历史同期的超预期程度，并做行业中性化处理。",
            "latex_formula": r"z_{industry}\left(\frac{NP_q - NP_{q,y-1}}{|NP_{q,y-1}| + 1}\right)",
            "formula_tree": {
                "op": "industry_zscore",
                "args": [
                    {
                        "op": "divide",
                        "args": [
                            {"op": "subtract", "args": ["quarter_net_profit", "quarter_net_profit_yoy_base"]},
                            {"op": "add", "args": [{"op": "abs", "args": ["quarter_net_profit_yoy_base"]}, 1]},
                        ],
                    }
                ],
            },
            "required_fields": ["quarter_net_profit", "quarter_net_profit_yoy_base", "industry"],
            "risk_notes": ["历史同期利润为 proxy，后续可替换为一致预期净利润。"],
            "is_mock": True,
        },
        {
            "factor_id": "pre_announcement_underreaction_002",
            "factor_name": "公告前低反应修正",
            "plain_description": "盈利超预期越强，且公告前 20 日涨幅越低，因子分数越高。",
            "latex_formula": r"Surprise - 0.5 \times Ret_{[-20,-1]}",
            "formula_tree": {
                "op": "subtract",
                "args": [
                    {"op": "ref", "args": ["earnings_surprise_score"]},
                    {"op": "multiply", "args": [0.5, "pre_announcement_return_20d"]},
                ],
            },
            "required_fields": ["earnings_surprise_score", "pre_announcement_return_20d"],
            "risk_notes": ["公告前收益窗口必须严格早于公告日。"],
            "is_mock": True,
        },
        {
            "factor_id": "quality_surprise_combo_003",
            "factor_name": "质量增强盈利超预期",
            "plain_description": "在盈利超预期基础上叠加经营质量，降低一次性损益扰动。",
            "latex_formula": r"0.7 \times Surprise + 0.3 \times CFOQuality",
            "formula_tree": {
                "op": "add",
                "args": [
                    {"op": "multiply", "args": [0.7, "earnings_surprise_score"]},
                    {"op": "multiply", "args": [0.3, "operating_cashflow_quality"]},
                ],
            },
            "required_fields": ["earnings_surprise_score", "operating_cashflow_quality"],
            "risk_notes": ["经营现金流披露频率和利润披露频率可能不完全一致。"],
            "is_mock": True,
        },
    ]


def generate_factors(
    idea_spec: dict[str, Any],
    research_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate candidate factors using AlphaModel when API key is available."""
    if not settings.llm_api_key:
        return mock_generate_factors(idea_spec, research_spec)

    try:
        agent = Agent(
            model=AlphaModel(),
            output_schema=FactorSpecsResponse,
            instructions="你是一位专业的量化因子研究专家。请基于投资思想生成候选因子，只输出合法 JSON。",
        )
        response = agent.run(_build_prompt(idea_spec, research_spec))
        result = response.content if hasattr(response, "content") else response
        if isinstance(result, FactorSpecsResponse):
            factors = [f.model_dump() for f in result.factors]
        elif isinstance(result, dict):
            factors = [f.model_dump() if isinstance(f, BaseModel) else f for f in result.get("factors", [])]
        else:
            return mock_generate_factors(idea_spec, research_spec)
        for f in factors:
            f["is_mock"] = False
            f["is_fallback"] = False
        return factors
    except Exception as e:
        print(f"[FactorGenerator] LLM调用失败，使用mock fallback: {e}")
        return mock_generate_factors(idea_spec, research_spec)
