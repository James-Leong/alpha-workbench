"""Research report generator with real LLM and mock fallback."""

from __future__ import annotations

import logging
from typing import Any

from agno.agent import Agent

from alpha_workbench.agents.core.model import AlphaModel
from alpha_workbench.core.config import settings
from alpha_workbench.reports.report_generator import generate_report as generate_template_report

logger = logging.getLogger(__name__)


def _get_factor_results(trace: dict[str, Any]) -> list:
    """兼容两种回测结果格式"""
    backtest = trace.get("backtest_result", {})
    # 主流程格式
    if "factor_results" in backtest:
        return backtest["factor_results"]
    # mock_run_backtest 格式
    if "results" in backtest:
        return backtest["results"]
    return []


def _build_report_prompt(trace: dict[str, Any]) -> str:
    idea = trace["idea_spec"]
    factor_results = _get_factor_results(trace)
    audit = trace["audit_report"]

    if not factor_results:
        raise ValueError("没有找到回测结果")

    factor_lines = "\n".join([
        f"- {f.get('factor_name', f.get('factor_id', '未知'))}："
        f"IC均值={f.get('ic_mean', 0):.3f}，"
        f"多空收益={f.get('long_short_return', 0):.2%}，"
        f"最大回撤={f.get('max_drawdown', 0):.2%}"
        for f in factor_results
    ])

    audit_checks = "\n".join([
        f"- [{c['level'].upper()}] {c['item']}：{c['message']}"
        for c in audit.get("checks", [])
    ])

    return f"""你是一个量化研究报告撰写专家。请根据以下研究结果，生成一份简洁专业的研究报告。

【投资假说】
{idea['core_hypothesis']}

【经济逻辑】
{chr(10).join(idea.get('economic_mechanism', []))}

【候选因子回测结果】
{factor_lines}

【审计发现】
整体等级：{audit['overall_level']}
{audit_checks}

要求：
1. 用Markdown格式输出
2. 包含以下章节：投资思想、核心发现、风险提示、结论
3. 语言简洁专业，每个章节不超过3句话
4. 结尾必须注明：本报告基于模拟数据，不构成投资建议
5. 不要输出任何Markdown代码块标记，直接输出内容"""


def _mock_generate_report(trace: dict[str, Any]) -> str:
    """Mock fallback using the structured report template."""
    return generate_template_report(trace)


def generate_report(trace: dict[str, Any]) -> str:
    """Generate report using AlphaModel when API key is available, otherwise mock."""
    if not settings.llm_api_key:
        return _mock_generate_report(trace)

    try:
        agent = Agent(
            model=AlphaModel(),
            instructions="你是一位专业的量化研究报告撰写专家。请根据提供的研究结果生成简洁专业的 Markdown 研究报告。",
        )
        prompt = _build_report_prompt(trace)
        response = agent.run(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return content.strip()
    except Exception as e:
        logger.warning("ReportAgent LLM调用失败，使用mock fallback: %s", e)
        return _mock_generate_report(trace)
