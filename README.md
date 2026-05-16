# AlphaWorkbench

AlphaWorkbench 是一个研报驱动的人机协同量化因子研究平台，面向金融研究员和量化研究学习者。

项目目标不是完美复现研报中的某个唯一因子，而是从研报或自然语言投资想法中提炼投资思想，生成可编辑的研究配置，发散候选因子，完成基础回测与审计，并沉淀可追踪的研究路径。

> 平台给 baseline，研究员找 alpha；流程可复现，研究可分叉。

## 核心流程

```text
研报 PDF / 自然语言投资想法
→ IdeaSpec 投资思想提炼
→ ResearchSpec 研究配置编辑
→ FactorSpec 候选因子生成
→ 因子计算与基础回测
→ 回测解释与轻量审计
→ Research Trace 研究路径沉淀
```

Demo 阶段聚焦“盈利超预期 / 单季度净利润超预期 / 盈利预测修正”这一类基本面因子思想。

## 功能特性

- 支持自然语言投资想法输入，后续扩展研报 PDF 解析。
- 使用 LLM 提炼投资思想并生成结构化 `IdeaSpec`。
- 支持研究员编辑股票池、字段口径、过滤规则、交易成本等 `ResearchSpec`。
- 生成候选因子族，并用自然语言、LaTeX 公式和表达式树三层表示 `FactorSpec`。
- 基于样例数据完成 IC、分层收益、多空收益、净值曲线等基础回测。
- 生成回测解释、轻量审计报告和 `Research Trace`。

## 技术栈

- 界面：Streamlit
- 核心计算：Python、Pandas、NumPy
- Agent 框架：Agno
- Agent 编排：Agno Workflow + 普通 Python 函数
- 大模型：优先使用云端 API，并保留 mock fallback 以保证 demo 稳定
- 数据：优先使用本地 CSV 样例数据；AKShare、TuShare、Wind、内部数据作为后续扩展
- 存储：demo 阶段使用本地 JSON / Markdown 保存研究路径和报告
- 环境管理：uv

## 快速开始

Linux / macOS：

```bash
./scripts/start_demo.sh
```

Windows：

```bat
scripts\start_demo.bat
```

手动启动：

```bash
uv sync
uv run alpha-workbench-demo
uv run streamlit run alpha_workbench/app/streamlit_app.py
```

如果暂时不安装依赖，也可以先用当前 Python 环境验证 mock 链路：

```bash
python -m alpha_workbench
```

## 系统架构

AlphaWorkbench 在 demo 阶段使用 Agno 作为 Agent 框架。系统应实现为确定性的研究工作流，而不是自由对话式的多 Agent 聊天。

```text
Streamlit UI
  ↓
Agno Workflow
  ↓
Agno Agents + Python functions
  ↓
Pydantic schemas
  ↓
CSV sample data + JSON/Markdown traces
```

### Agent 层

面向大模型的模块实现为 Agno Agents：

- `IdeaExtractionAgent`：提炼投资假设，输出 `IdeaSpec`。
- `FactorGenerationAgent`：生成候选因子族，输出 `FactorSpec`。
- `BacktestExplanationAgent`：解释 IC、分层收益、净值曲线、回撤和换手率。
- `AuditAgent`：检查数据可得性、proxy 使用、未来函数风险和稳健性问题。
- `ReportAgent`：基于完整研究路径生成最终研究报告。

Agent 应尽量返回结构化 Pydantic 对象。自由文本只用于面向用户的解释和报告。

### Workflow 层

Agno Workflow 控制主研究链路：

```text
parse_input
→ extract_idea
→ edit_research_spec
→ generate_factors
→ validate_factor_specs
→ compile_factors
→ run_backtest
→ explain_backtest
→ run_audit
→ save_research_trace
→ generate_report
```

这样可以保证 demo 可复现、易调试。后续如果需要更灵活的 Agent 协作，可以再引入 Agno Teams；MVP 阶段优先使用 Workflow，因为本项目流程有明确的顺序步骤和输入输出。

### 计算层

确定性任务保留为普通 Python 代码：

- PDF / 文本解析
- schema 校验
- 因子表达式编译
- 因子计算
- 回测指标计算
- 图表数据生成
- 研究路径持久化

LLM Agents 负责生成和解释结构化研究对象；Python 代码负责校验、计算、审计和保存。

## 项目结构

```text
alpha-workbench/
  README.md
  AGENTS.md
  scripts/
    start_demo.sh
    start_demo.bat
  docs/
    team_work_plan.md
  alpha_workbench/
    app/
    agents/
    schemas/
    parsers/
    data/
    factor_engine/
    backtest/
    memory/
    reports/
    configs/
    workflows/
  tests/
```

## 文档

- [项目分工与开发指南](docs/team_work_plan.md)
- [项目原始飞书文档](https://wcn56p71ygrh.feishu.cn/wiki/CjfXwPywlin5jvk7ZGkcOGs7nVh?from=from_copylink)

## 参考来源

- [Agno 官方文档](https://docs.agno.com/index)：Agno 是用于构建 Agent 平台的 SDK。
- [Agno SDK 介绍](https://docs.agno.com/sdk/introduction)：Agno 提供 `Agent`、`Team`、`Workflow` 三类核心原语，其中 Workflow 适合确定性的步骤式执行。
- [Agno Agents](https://docs.agno.com/agents/overview)：Agent 是使用工具完成任务的 AI 程序，可扩展 memory、knowledge、storage、human-in-the-loop 和 guardrails。
- [Agno Workflows](https://docs.agno.com/workflows/overview)：Workflow 通过定义好的步骤编排 agents、teams 和 functions，适合可重复任务。
- [Agno Input & Output](https://docs.agno.com/input-output/overview)：Agno 支持使用 Pydantic 模型进行结构化输入和输出。

## 当前状态

当前项目处于启动阶段。优先目标是跑通一条固定 demo 链路：

```text
一句投资想法 → 固定 IdeaSpec → 3 个候选因子 → 基础回测图 → 轻量审计报告
```

详细分工、并行开发规范、接口约定和阶段目标见 `docs/team_work_plan.md`。
