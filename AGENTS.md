# AlphaWorkbench 开发协作说明

本文档给参与开发的同学和 AI coding agent 使用，用于统一项目结构、运行方式和协作边界。

## 环境管理

本项目使用 `uv` 管理 Python 虚拟环境和依赖。

常用命令：

```bash
./scripts/start_demo.sh
uv sync --all-groups
uv sync --extra dev
uv run alpha-workbench-demo
uv run streamlit run alpha_workbench/app/streamlit_app.py
uv run pytest
uv run ruff check .
```

如果只是快速验证当前 mock demo，也可以先运行：

```bash
python -m alpha_workbench
```

Windows 一键启动：

```bat
scripts\start_demo.bat
```

## 项目边界

- `alpha_workbench/app/`：Streamlit UI 和页面状态管理。
- `alpha_workbench/agents/`：LLM Agent 的 prompt、mock fallback 和结构化输出入口。
- `alpha_workbench/schemas/`：IdeaSpec、ResearchSpec、FactorSpec、ResearchTrace 等公共结构。
- `alpha_workbench/factor_engine/`：因子表达式校验、编译和后续真实计算。
- `alpha_workbench/backtest/`：样例数据、回测指标和图表数据。
- `alpha_workbench/memory/`：Research Trace 保存、读取和轻量记忆。
- `alpha_workbench/reports/`：最终研究报告生成。
- `alpha_workbench/workflows/`：串联完整研究流程。
- `tests/`：最小回归测试，至少保证 mock 全流程可运行。
- `scripts/`：跨平台启动脚本，Linux/macOS 使用 `start_demo.sh`，Windows 使用 `start_demo.bat`。

## 前端交互原则

- 页面应体现 AI 应用的研究流，而不是简单 JSON 调试页。
- 主流程按“输入 -> AI 研读 -> 人工确认配置 -> 因子实验 -> 回测审计 -> 报告沉淀”组织。
- JSON、表达式树、Research Trace 默认放在详情区，主界面优先展示研究员能直接理解的摘要、指标和风险。
- UI 改动必须保留 mock 全流程可运行，不依赖真实 API 才能演示。

## 开发原则

- 先保证 mock 全流程稳定，再替换真实 Agent、真实数据和真实回测。
- 每个模块都必须保留 `mock_xxx()` 或稳定 fallback，避免 API、网络、数据源不可用时 demo 中断。
- LLM 不直接生成任意可执行 Python 代码，优先输出结构化 JSON、受限表达式树、LaTeX 公式和自然语言解释。
- 公共 schema 变更需要同步 README、分工文档和测试样例。
- 各负责人尽量只修改自己负责目录；跨模块改动先说明接口原因。
- Demo 默认主题固定为“盈利超预期因子研究”，便于集成和答辩演示。

## Agent 输出规范

Agent 输出应满足：

- 字段稳定，可被 UI、回测和报告模块直接消费。
- 包含 `is_mock` 或 `is_fallback` 标记，方便展示当前是否调用真实模型。
- 对不确定数据、proxy 字段、未来函数风险和样本偏差给出提示。
- 可保存为 Research Trace，支持复现和后续分叉研究。

## 提交前检查

提交前至少运行：

```bash
uv run alpha-workbench-demo
uv run pytest
```

如果本地尚未安装依赖，至少运行：

```bash
python -m alpha_workbench
python -m py_compile alpha_workbench/__main__.py
```
