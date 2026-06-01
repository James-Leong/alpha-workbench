"""Research report generator with real LLM and mock fallback."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


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

    best = factor_results[0]

    # 兼容两种字段名
    factor_name = best.get("factor_name", best.get("factor_id", "未知因子"))
    ic_mean = best.get("ic_mean", best.get("ic", {}).get("ic_mean", 0))
    long_short_return = best.get("long_short_return",
                                  best.get("long_short", {}).get("annual_return", 0))
    max_drawdown = best.get("max_drawdown",
                             best.get("long_short", {}).get("max_drawdown", 0))

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
    idea = trace["idea_spec"]
    audit = trace["audit_report"]
    factor_results = _get_factor_results(trace)

    if factor_results:
        best = factor_results[0]
        factor_name = best.get("factor_name", best.get("factor_id", "未知因子"))
        ic_mean = best.get("ic_mean", 0)
        long_short_return = best.get("long_short_return", 0)
        max_drawdown = best.get("max_drawdown", 0)
        factor_line = f"{factor_name}"
        metrics_line = (
            f"IC 均值：{ic_mean:.3f}；"
            f"多空年化收益：{long_short_return:.2%}；"
            f"最大回撤：{max_drawdown:.2%}。"
        )
    else:
        factor_line = "暂无因子数据"
        metrics_line = "暂无回测数据"

    return "\n".join([
        "# AlphaWorkbench Demo 研究报告",
        "",
        f"## 投资思想\n{idea['core_hypothesis']}",
        "",
        f"## 当前最佳候选因子\n{factor_line}",
        "",
        f"## 样例回测结论\n{metrics_line}",
        "",
        f"## 审计等级\n{audit.get('overall_level', '未知')}",
        "",
        "## 说明\n本报告由 mock demo 生成，只用于展示研发流程，不构成投资建议。",
    ])


def generate_report(trace: dict[str, Any]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.modelarts-maas.com/v2")
    model = os.getenv("MODEL_NAME", "deepseek-v3.2")

    if not api_key or api_key.strip() == "这里填你的完整token":
        return _mock_generate_report(trace)

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        prompt = _build_report_prompt(trace)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=600,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"[ReportAgent] LLM调用失败，使用mock fallback: {e}")
        return _mock_generate_report(trace)
