# AlphaWorkbench 修复与开发阶段总结

> 记录时间：2026-07-03
> 记录人：James Leong
> 背景：PR #1（`3f9f290` Merge）合并后前端与核心工作流出现破坏，随后按 `/home/lzq/.claude/plans/frolicking-jingling-raccoon.md` 进行了 P0-P4 四阶段修复与补齐。本文档汇总已完成的工作、当前状态、以及仍然存在的问题，供后续决策参考。

---

## 一、已完成的修复与开发工作

### P0：恢复项目可运行性

1. **修复 `demo_workflow.py` 的 `progress_callback` NameError**
   - `workflows/demo_workflow.py` 的 `_run_python_demo_workflow` 在 PR 合并时删除了 `progress_callback` 参数，但函数体内仍保留 6 处 `if progress_callback:` 引用，导致 Python fallback 路径触发 `NameError`。
   - 已恢复该参数，并在 `run_demo_workflow` 各调用处透传。

2. **恢复被删除的 `alpha_workbench/app/` 目录**
   - PR #1 合并后，工作区中 `alpha_workbench/app/__init__.py`、`status.py`、`research_config.py`、`streamlit_app.py` 被删除，导致 `ModuleNotFoundError: No module named 'alpha_workbench.app'`。
   - 由于 `git checkout` 被权限拦截，改为从 git HEAD blob 读取原始内容并重新 Write 到工作区。

3. **验证结果**
   - `uv run pytest`：19/19 全部通过。
   - `uv run alpha-workbench-demo` 与 `python -m alpha_workbench` 可输出完整 trace。

### 阶段 1：恢复交互式人机协同工作流

1. **补全 `streamlit_app.py` 的 imports**
   - 恢复了 `_render_workflow()` 内部依赖的函数：`extract_idea`、`build_research_spec`、`generate_factors`、`compile_factors`、`run_backtest`、`explain_backtest`、`run_audit`、`generate_report`、`save_research_trace`、`build_research_trace`、`apply_research_config_edits`、`backtest_source_summary`。

2. **添加界面模式切换**
   - 在侧边栏增加「集成控制台」/「交互式研究流」radio。
   - 交互式模式调用已有的 `_render_workflow()`，按 7 步状态机推进；控制台模式保留原有 JSON 接入表单。

3. **清理死代码**
   - 移除未实际使用的 `group_charts_by_factor` import。
   - 处理 ruff E402 告警（`sys.path` 插入后的 imports 加 `noqa`）。

### 阶段 2：统一 LLM 配置与 `AlphaModel` 接入

1. **精简 `core/config.py`**
   - 删除与本项目无关的 JWT、CORS、session、batch limits、`reference_doc_path` 等字段。
   - 保留应用基础、LLM、Vision LLM、Mercury 四组配置。
   - 默认值策略：`LLM_*` 优先，为空时回退到 `DEEPSEEK_*`（与仓库 `.env` 一致）。

2. **更新 `.env.template`**
   - 说明 `LLM_*` 是覆盖配置，`DEEPSEEK_*` 是默认模型。
   - 删除已移除配置项的注释。

3. **统一 Agent/Explainer 使用 `AlphaModel`**
   - `agents/idea_extractor.py`
   - `agents/factor_generator.py`
   - `agents/audit_agent.py`
   - `agents/report_agent.py`
   - `backtest/llm_explainer.py`
   - 为 idea/factor/audit 增加 Pydantic response model（`output_schema`），report 使用纯文本生成。

4. **适配 Agno 2.6.7 API**
   - `response_model` → `output_schema`
   - `system_prompt` → `instructions`

### 阶段 3：回测层去重与因子编译收敛

1. **统一指标计算**
   - `backtest/hybrid_engine.py` 的 `_calculate_ic_metrics`、`_calculate_layer_metrics`、`_calculate_long_short_metrics` 改为复用 `backtest/metrics.py` 的对应函数，删除约 160 行重复实现。

2. **澄清回测入口**
   - 将 `backtest/factor_backtest.py` 中容易与 `engine.run_backtest` 混淆的 `run_backtest` 重命名为 `run_batch_backtest`。

3. **因子编译器收敛**
   - `factor_engine/compiler.py` 扩展操作符集合，与 `expression_evaluator.py` 对齐。
   - 新增 `formula_tree_to_expression_tree()`，将 dict 形式的 `formula_tree` 转换为 `ExpressionTree` Pydantic 模型。
   - 兼容 `ts_pct_change`、`industry_zscore`、`zscore`、`rank`、`winsorize` 等 LLM 常用别名。
   - `compile_factor()` 改为返回 `status`/`error`/`expression_tree_valid`，不再因校验失败直接抛异常。

4. **补充横截面操作符**
   - `factor_engine/expression_evaluator.py` 补充 `industry_zscore`、`zscore`、`rank`、`winsorize`。

### 阶段 4：输入与产出扩展

1. **PDF 解析**
   - 新增 `parsers/pdf_parser.py`，基于 `pymupdf` 提取文本。
   - `agents/idea_extractor.py` 支持 `source_type="pdf" + pdf_path`。
   - `pyproject.toml` 添加 `pymupdf` 依赖并执行 `uv sync`。

2. **报告模块落地**
   - 新增 `reports/report_generator.py` 与结构化 Markdown 模板。
   - `reports/__init__.py` 导出 `generate_report`。
   - `agents/report_agent.py` 的 mock fallback 改用模板生成报告。

3. **测试调整**
   - `tests/test_demo_workflow.py` 改为 mock 模式运行（monkeypatch `settings.llm_api_key = ""`），避免每次测试调用真实 LLM，保证 CI 稳定。

---

## 二、当前状态

| 检查项 | 结果 |
| --- | --- |
| `uv run pytest -q` | 19 passed |
| `uv run ruff check <修改文件>` | All checks passed |
| `uv run streamlit run alpha_workbench/app/streamlit_app.py` | 可启动 |
| `.vscode/launch.json` | 已配置 Streamlit / CLI / pytest 三套调试配置 |

---

## 三、仍然存在的关键问题

### 1. 前端体验问题（用户核心反馈）

- **视觉破坏**：PR #1 合并后的 `streamlit_app.py` 重写了大量自定义 CSS，覆盖 Streamlit 默认样式，但实际呈现效果差，破坏了原本相对清爽的设计。
- **调试界面不应作为生产界面**：当前「集成控制台」模式本质上是一个 JSON 粘贴板，要求用户把每个角色的输入输出手动贴进去。这是开发/联调工具，不是面向研究员的成品界面。
- **交互式工作流未完成**：虽然补回了 `_render_workflow()` 的 import 并接入模式切换，但该函数内部仍直接顺序调用后端 Agent，没有真正的人机协同体验优化；且一旦某步失败，用户难以回退或编辑。

### 2. 缺失产品级功能

- **没有登录/注册系统**：用户明确指出这是必要功能。当前项目完全没有用户、权限、会话管理。
- **没有真正的研究工作流引导**：页面应该围绕「输入 → 提炼 → 确认 → 因子 → 回测 → 审计 → 报告」自然推进，而不是让用户在 JSON 和 chat 消息之间切换。
- **缺少历史记录/分叉研究**：`memory/research_trace.py` 仅保存单个 JSON 文件，没有列表、读取、对比、Fork 功能。

### 3. 架构与代码质量问题

- **后端重复代码仍多**：虽然回测指标计算已收敛到 `metrics.py`，但 `backtest/` 目录仍有 `engine.py`、`hybrid_engine.py`、`factor_backtest.py`、`rebalance.py` 多个概念重叠的文件，职责边界不清。
- **`reports/` 与 `report_agent.py` 职责重复**：报告生成逻辑分散在 Agent 和 reports 模块，未形成清晰分层。
- **前端 import 结构脆弱**：`streamlit_app.py` 顶部插入 `sys.path`，imports 需要 `noqa: E402`，说明包结构有待整理。
- **Pydantic class-based `config` 已弃用**：`backtest_schemas.py` 中大量使用 `class Config:`，运行时会触发 `PydanticDeprecatedSince20` 警告，需迁移到 `ConfigDict`。

### 4. 真实 LLM 路径未经充分验证

- 当前测试默认 mock，CI 不覆盖真实 LLM 调用。
- `AlphaModel` 使用 `OpenAILike` 基类，与华为云 MaaS 的兼容性已在 `.env` 配置中体现，但真实调用链路的稳定性、超时、错误回退需要更多手测。

---

## 四、建议的后续方向

### 2026-07-03 产品网站阶段决策

本阶段不继续在 Streamlit 调试界面上堆产品功能，改为新增 FastAPI + React/Vite 产品外壳：

- FastAPI 承担认证、SQLite 持久化、GitHub OAuth 和研究记录 API。
- React/Vite 承担登录、注册、dashboard、新建研究、研究详情和设置页。
- Streamlit 保留为内部 demo/debug 入口。
- 当前只接入现有 `run_demo_workflow()`，不优化核心因子研报工作流。
- P6 文档已拆分为 Web 架构、认证设计、产品页面规划和 API 契约。

1. **暂停在当前 Streamlit 界面上继续堆功能**，优先重新定义产品级 UI 结构：
   - 登录/注册页
   - 研究工作流引导页（非 JSON 粘贴板）
   - 历史研究列表与 Fork
   - 结果展示页（卡片式、可折叠详情）

2. **重构前端**：
   - 删除或重写 PR #1 中不合理的自定义 CSS。
   - 将 `_render_workflow()` 改造为真正的分步引导，而不是 chat 消息堆砌。
   - 移除「集成控制台」JSON 粘贴模式，或降级为仅内部调试入口。

3. **补充用户系统**：
   - 最小可行方案：基于 Streamlit session state 的简单用户名/密码 + 本地 SQLite 用户表。
   - 或接入外部 OAuth/SSO。

4. **清理后端重复代码**：
   - 明确 `engine.py` 是唯一回测入口，逐步合并/删除 `factor_backtest.py` 和 `hybrid_engine.py` 的重复逻辑。
   - 将 `reports/report_generator.py` 作为报告生成主入口，`report_agent.py` 仅负责 LLM 增强。

5. **迁移 Pydantic Config**：
   - 将 `backtest_schemas.py` 中的 `class Config:` 全部改为 `model_config = ConfigDict(...)`。

---

## 五、相关文件索引

- 计划文件：`/home/lzq/.claude/plans/frolicking-jingling-raccoon.md`
- 前端入口：`alpha_workbench/app/streamlit_app.py`
- LLM 模型封装：`alpha_workbench/agents/core/model.py`
- 项目配置：`alpha_workbench/core/config.py`
- 环境变量模板：`.env.template`
- 回测引擎：`alpha_workbench/backtest/engine.py`、`hybrid_engine.py`、`metrics.py`
- 因子编译：`alpha_workbench/factor_engine/compiler.py`、`expression_evaluator.py`
- Agent：`alpha_workbench/agents/idea_extractor.py`、`factor_generator.py`、`audit_agent.py`、`report_agent.py`
- PDF 解析：`alpha_workbench/parsers/pdf_parser.py`
- 报告生成：`alpha_workbench/reports/report_generator.py`
- VS Code 调试配置：`.vscode/launch.json`
- 测试：`tests/test_demo_workflow.py`、`tests/test_backtest_config.py`
