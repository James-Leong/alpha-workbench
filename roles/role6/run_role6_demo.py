"""
Role 6 Demo 脚本
展示：审计Agent、报告Agent、Alpha Memory
"""

import json
import os
import sys
from pathlib import Path

# 确保项目根目录在路径里
sys.path.insert(0, str(Path(__file__).parent.parent))

from alpha_workbench.workflows.demo_workflow import run_demo_workflow
from alpha_workbench.memory.research_trace import save_research_trace

def print_section(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def print_step(step: int, desc: str):
    print(f"\n步骤 {step}: {desc}")
    print("-" * 40)

def demo_audit(trace: dict):
    """展示审计结果"""
    audit = trace["audit_report"]
    is_real = not audit.get("is_mock", True)

    print(f"{'✓ 真实 LLM 审计' if is_real else '⚠ Mock 审计（未配置API Key）'}")
    print(f"整体审计等级：{audit['overall_level'].upper()}")
    print()

    print("审计发现：")
    for check in audit["checks"]:
        level = check["level"].upper()
        icon = "🔴" if level == "HIGH" else "🟡" if level == "MEDIUM" else "🟢"
        print(f"  {icon} [{level}] {check['item']}")
        print(f"       {check['message'][:80]}...")

    print()
    print("建议行动：")
    for i, action in enumerate(audit["next_actions"], 1):
        print(f"  {i}. {action}")

def demo_report(trace: dict):
    """展示研究报告"""
    report = trace["report_markdown"]
    print(report)

def demo_memory():
    """展示 Alpha Memory 历史记录"""
    runs_dir = Path("runs")
    if not runs_dir.exists():
        print("暂无历史研究记录")
        return

    trace_files = sorted(runs_dir.glob("research_trace_*.json"), reverse=True)
    if not trace_files:
        print("暂无历史研究记录")
        return

    print(f"共找到 {len(trace_files)} 条历史研究记录：\n")
    for i, f in enumerate(trace_files, 1):
        # 读取文件基本信息
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            idea_name = data.get("idea_spec", {}).get("idea_name", "未知")
            input_text = data.get("input_text", "")[:40]
            audit_level = data.get("audit_report", {}).get("overall_level", "未知")
            print(f"  [{i}] {f.name}")
            print(f"       研究主题：{idea_name}")
            print(f"       输入：{input_text}...")
            print(f"       审计等级：{audit_level}")
            print()
        except Exception:
            print(f"  [{i}] {f.name}（读取失败）")

def main():
    print("=" * 60)
    print("  AlphaWorkbench - Role 6 完整演示")
    print("  审计Agent · 报告Agent · Alpha Memory")
    print("=" * 60)

    # 步骤1：运行完整工作流
    print_step(1, "运行完整研究工作流（含审计和报告）")
    print("输入：单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。")
    print("正在运行...")

    trace = run_demo_workflow(save_trace=True)
    print("✓ 工作流完成")

    # 步骤2：展示审计结果
    print_step(2, "AuditAgent 审计结果")
    demo_audit(trace)

    # 步骤3：展示研究报告
    print_step(3, "ReportAgent 生成的研究报告")
    demo_report(trace)

    # 步骤4：展示 Alpha Memory
    print_step(4, "Alpha Memory 历史研究记录")
    demo_memory()

    # 步骤5：展示接口数据
    print_step(5, "Role6 → Role2 接口数据预览")
    best_factor = trace["backtest_result"]["factor_results"][0]
    role6_summary = {
        "audit_level": trace["audit_report"]["overall_level"],
        "best_factor": best_factor["factor_name"],
        "ic_mean": best_factor["ic_mean"],
        "long_short_return": best_factor["long_short_return"],
        "report_length": len(trace["report_markdown"]),
        "trace_path": trace.get("trace_path", "未保存"),
    }
    print(json.dumps(role6_summary, ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("  Role 6 演示完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()
