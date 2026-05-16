# AlphaWorkbench 小组分工与开发指南

本文档用于将 AlphaWorkbench 的 demo 开发任务拆分给 6 位同学。目标是让每个人都有清晰的模块边界、可执行步骤、阶段性交付物，并且都能参与到大模型相关工作中。

## 总体目标

本项目要完成一个 demo 级但流程完整的“研报 / 投资想法 → 投资思想 → 候选因子 → 回测 → 审计报告 → 研究路径沉淀”的人机协同量化因子研究平台。

Demo 主流程固定为：

```text
输入研报 PDF / 输入自然语言投资想法
→ 系统提炼投资思想
→ 生成可编辑 IdeaSpec
→ 生成可编辑 ResearchSpec
→ 发散候选因子族
→ 编译/计算因子
→ 基础回测
→ 回测解释与轻量审计
→ 输出研究报告
→ 保存 Research Trace
```

MVP 建议聚焦一个主题：

```text
单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。
```

## 分工总览

| 角色 | 模块边界 | 主要交付 | 大模型相关任务 | 依赖关系 | 可否并行 |
| --- | --- | --- | --- | --- | --- |
| 角色 1：产品、流程与演示 | 需求、验收、演示脚本、答辩材料 | demo 脚本、验收清单、展示逻辑 | 设计 Agent 输出评价标准、Prompt 场景、失败案例总结 | 需要了解所有模块进度 | 可并行，负责协调 |
| 角色 2：UI 与交互 | Streamlit 主界面和流程串联 | 可演示 Web UI、编辑页面、结果展示 | 展示 AI 输出、区分 AI 生成和用户修改 | 依赖各模块接口和 mock 数据 | 可先用 mock 并行 |
| 角色 3：研报解析与 Idea Agent | 文本/PDF 输入到 IdeaSpec | IdeaSpec、PDF 解析、思想提炼 Agent | 设计 Idea Extraction Prompt，生成结构化 IdeaSpec | 输出给角色 2、4、6 | 可独立并行 |
| 角色 4：因子生成与编译 | IdeaSpec/ResearchSpec 到 FactorSpec 和可执行因子 | 候选因子、LaTeX 公式、表达式树、编译器 | 设计 Factor Generation Prompt，约束 LLM 输出 | 输入来自角色 3，输出给角色 5 | 可先用固定 IdeaSpec 并行 |
| 角色 5：数据、回测与结果解释 | 样例数据、因子回测、结果解释 | 回测指标、图表数据、LLM 解释 | 设计 Backtest Explanation Prompt | 输入来自角色 4，输出给角色 2、6 | 可先用固定因子并行 |
| 角色 6：轻量审计、记忆与报告 Agent | Research Trace、审计、最终报告 | 审计报告、研究路径 JSON、报告生成 | 设计 Audit Prompt 和 Report Prompt | 汇总角色 3、4、5 输出 | 可先定义结构并行 |

## 协作原则

- 先跑通固定样例，再逐步接入 Agent 和可编辑配置。
- 大模型不直接生成任意可执行代码，优先生成结构化 JSON、YAML、受限 DSL、LaTeX 公式或自然语言解释。
- 所有中间结果都应可查看、可编辑、可保存。
- 每个模块先提供 mock 数据或固定输出，避免互相等待。
- 每位同学都要维护自己模块的最小 demo、输入输出格式和说明文档。

## 并行开发规范

不同同学可以并行开展工作，前提是先约定好目录边界、接口格式和 mock 输出。建议第一天先完成接口冻结，后续每个人在自己的模块内推进。

### 接口先行

第一轮不要先追求复杂实现，而是每个模块先提交下面 3 件事：

- 一个 `mock_xxx()` 函数，返回固定样例输出。
- 一个 `run_xxx(input)` 函数，作为后续真实实现的稳定入口。
- 一个示例 JSON 文件或文档片段，说明输入输出字段。

推荐函数边界：

```python
extract_idea(input_text: str, source_meta: dict | None = None) -> dict
build_research_spec(idea_spec: dict, user_rules: dict | None = None) -> dict
generate_factors(idea_spec: dict, research_spec: dict) -> list[dict]
compile_factor(factor_spec: dict) -> object
run_backtest(factor_specs: list[dict], research_spec: dict) -> dict
explain_backtest(backtest_results: dict) -> dict
run_audit(trace: dict) -> dict
save_research_trace(trace: dict) -> str
```

### Mock 优先

为了让 UI 和各模块并行，所有模块必须先支持固定样例：

- 角色 3 在没有 LLM API 时返回固定的盈利超预期 IdeaSpec。
- 角色 4 在没有 LLM API 时返回 3-5 个固定候选因子。
- 角色 5 在没有真实数据时返回固定回测结果或使用小样例 CSV。
- 角色 6 在没有完整 trace 时返回固定审计报告。
- 角色 2 先接入 mock，再替换为真实函数。

### 集成节奏

- 第 1 次集成：只用 mock 串通页面，不要求真实 LLM 和真实回测。
- 第 2 次集成：接入 Idea Agent 和候选因子生成。
- 第 3 次集成：接入真实样例数据回测和结果解释。
- 第 4 次集成：接入审计、Research Trace 和报告生成。
- 最终演示：固定样例 + 可选真实调用，确保网络或 API 不稳定时也能展示。

### 分支与提交建议

- 每位同学使用独立分支，例如 `feature/ui`、`feature/idea-agent`、`feature/factor-engine`。
- 公共 schema 变更需要先在群里同步字段变化，再修改代码。
- 不要在自己的分支中大幅改动别人的负责目录。
- 每次合并前至少保证自己的 mock 函数可运行。
- 大模型 Prompt、示例输入和示例输出要随代码一起提交，便于复现。

## 推荐开发阶段

### 阶段 1：最小闭环

目标：不用追求全自动，先让固定样例跑通。

交付：

- 输入一句投资想法。
- 生成固定 IdeaSpec。
- 生成 3 个候选因子。
- 跑出基础回测图。
- 页面能串起完整流程。

### 阶段 2：Agent 与可编辑配置

目标：从固定模板升级为 Agent 自动提炼 + 用户可修改。

交付：

- 文本或 PDF 输入。
- LLM 生成 IdeaSpec。
- 用户可编辑 ResearchSpec。
- LLM 生成候选因子解释和结构化因子定义。
- 回测结果可展示。

### 阶段 3：解释、审计与研究路径

目标：让系统可解释、可追踪、可审计。

交付：

- LLM 解释回测结果。
- 轻量审计报告。
- Research Trace JSON。
- 最终研究报告页面。

### 阶段 4：展示打磨

目标：形成完整比赛作品。

交付：

- 可演示 Web UI。
- 项目技术报告。
- 演示脚本。
- 答辩 PPT 素材。

## 角色 1：产品、流程与演示负责人

### 主要职责

- 负责整体 demo 流程设计和项目验收标准。
- 固定比赛演示主题、输入样例和讲解脚本。
- 维护项目文档、阶段目标和最终答辩材料。
- 协调各模块输入输出格式，保证最终系统能串起来。

### 大模型相关工作

- 设计“好输出”的评价标准，例如 IdeaSpec 是否符合投研逻辑、因子解释是否合理、审计报告是否可信。
- 设计用于演示的 Prompt 场景和用户问题。
- 收集每个 Agent 的优秀输出和失败案例，形成答辩中的对比材料。

### 工作步骤

1. 明确 demo 主线：盈利超预期因子研究。
2. 写出完整演示脚本，包括输入、系统输出、用户修改、回测展示、审计报告。
3. 定义验收清单：哪些页面必须可用，哪些数据必须能展示，哪些结果可以 mock。
4. 和其他同学确认统一的数据结构：IdeaSpec、ResearchSpec、FactorSpec、Research Trace。
5. 每个阶段结束时组织一次集成检查，确认当前版本能否演示。

### 阶段目标

- 阶段 1：完成 demo 流程图、输入样例、验收清单。
- 阶段 2：完成 Agent 输出质量评价表。
- 阶段 3：完成最终演示脚本和报告大纲。
- 阶段 4：完成答辩 PPT 内容和项目亮点总结。

### 交付物

- `docs/demo_script.md`
- `docs/acceptance_checklist.md`
- `docs/presentation_outline.md`
- Agent 输出评价表

## 角色 2：UI 与交互负责人

### 主要职责

- 使用 Streamlit 实现 demo 主界面。
- 串联输入、IdeaSpec 编辑、ResearchSpec 编辑、候选因子、回测结果、审计报告和研究记录。
- 保证非编程用户也能看懂系统流程。

### 大模型相关工作

- 设计 AI 输出的展示方式，例如投资思想卡片、候选因子卡片、风险提示卡片。
- 做可编辑界面，让用户能修改 LLM 生成的 IdeaSpec 和 ResearchSpec。
- 在界面中标明哪些内容来自 AI，哪些内容来自用户修改。

### 工作步骤

1. 创建 Streamlit 页面骨架。
2. 先用 mock 数据串通 6 个页面：输入、思想提炼、研究配置、因子发散、回测结果、审计报告。
3. 为 IdeaSpec 和 ResearchSpec 做表单或 JSON 编辑区。
4. 接入其他模块提供的函数接口。
5. 增加流程状态展示，让用户知道当前处于哪一步。
6. 最后做演示打磨，包括默认按钮、一键运行、示例输入、错误提示。

### 阶段目标

- 阶段 1：完成 Streamlit 页面骨架和 mock 全流程。
- 阶段 2：接入 IdeaSpec、ResearchSpec 和候选因子生成结果。
- 阶段 3：展示审计报告、回测解释和 Research Trace。
- 阶段 4：完成 UI 打磨，保证演示稳定。

### 交付物

- `alpha_workbench/app/streamlit_app.py`
- 页面状态管理逻辑
- mock 数据展示页面
- 最终 demo UI

## 角色 3：研报解析与 Idea Agent 负责人

### 主要职责

- 支持用户输入自然语言投资想法或上传研报 PDF。
- 从输入中提炼核心投资思想、经济机制、所需数据、风险点。
- 输出结构化 IdeaSpec。

### 大模型相关工作

- 设计 Idea Extraction Prompt。
- 让 LLM 输出稳定的结构化 JSON / YAML，而不是散乱文本。
- 为每个投资思想标注证据来源、默认假设和不确定点。

### 工作步骤

1. 先支持自然语言输入，不依赖 PDF。
2. 定义 IdeaSpec 字段，例如 `idea_name`、`core_hypothesis`、`economic_mechanism`、`required_data_concepts`、`risk_flags`。
3. 写固定模板版本，保证没有 LLM 时也能返回盈利超预期 IdeaSpec。
4. 接入 LLM，根据用户输入生成 IdeaSpec。
5. 增加 PDF 解析能力，优先支持文本型 PDF；复杂 PDF 可允许人工复制关键段落。
6. 为输出增加证据片段和风险提示。

### 阶段目标

- 阶段 1：固定输入生成固定 IdeaSpec。
- 阶段 2：LLM 根据自然语言生成 IdeaSpec。
- 阶段 3：支持 PDF 文本提取和证据标注。
- 阶段 4：优化 Prompt，使输出稳定适合展示。

### 交付物

- `alpha_workbench/agents/idea_extractor.py`
- `alpha_workbench/parsers/pdf_parser.py`
- `alpha_workbench/schemas/idea_spec.py`
- Idea Extraction Prompt
- 示例 IdeaSpec JSON

## 角色 4：因子生成与编译负责人

### 主要职责

- 根据 IdeaSpec 和 ResearchSpec 生成候选因子族。
- 将候选因子表达为自然语言解释、LaTeX 公式和受限表达式树三层结构。
- 避免让大模型直接生成任意 Python 代码。
- 将结构化因子定义编译为可执行计算函数。

### 大模型相关工作

- 设计 Factor Generation Prompt。
- 让 LLM 生成候选因子的名称、逻辑解释、字段依赖、公式结构和风险说明。
- 约束 LLM 输出到系统支持的操作符集合。

### 工作步骤

1. 定义 FactorSpec 字段，例如 `factor_id`、`factor_name`、`plain_description`、`latex_formula`、`required_fields`、`field_definitions`、`formula_tree`、`risk_notes`。
2. 先手写 3-5 个盈利超预期候选因子。
3. 定义支持的操作符，例如 `subtract`、`multiply`、`zscore`、`industry_zscore`、`winsorize`、`rank`。
4. 编写编译器，把表达式树转换为 Pandas 计算逻辑。
5. 接入 LLM，让其生成三层 FactorSpec：给用户看的自然语言、给展示看的 LaTeX、给系统执行的表达式树。
6. 增加字段检查和错误提示。

### 阶段目标

- 阶段 1：手写 3 个候选因子并能计算。
- 阶段 2：LLM 生成候选因子解释和结构化 FactorSpec。
- 阶段 3：表达式树可编译，字段检查可用。
- 阶段 4：输出适合 UI 展示的因子卡片。

### 交付物

- `alpha_workbench/agents/factor_generator.py`
- `alpha_workbench/factor_engine/compiler.py`
- `alpha_workbench/factor_engine/operators.py`
- `alpha_workbench/schemas/factor_spec.py`
- Factor Generation Prompt
- 示例 FactorSpec JSON

## 角色 5：数据、回测与结果解释负责人

### 主要职责

- 准备 demo 样例数据。
- 实现因子计算后的基础回测。
- 输出 IC、RankIC、分层收益、多空收益、Top 组合净值、最大回撤、换手率等指标。
- 将回测指标转成适合展示的数据结构。

### 大模型相关工作

- 设计 Backtest Explanation Prompt。
- 使用 LLM 把回测指标解释成投研语言。
- 让 LLM 总结因子表现、潜在问题和下一步研究建议。

### 工作步骤

1. 准备最小样例数据，包括日期、股票代码、收益率、行业、市值、财务字段。
2. 实现因子分组和未来收益计算。
3. 实现 IC / RankIC。
4. 实现分层收益和多空组合收益。
5. 实现基础图表所需数据输出。
6. 接入 LLM，根据指标生成自然语言解释。
7. 对接 UI 展示结果。

### 阶段目标

- 阶段 1：固定因子能跑出一张回测图。
- 阶段 2：多个候选因子能批量回测。
- 阶段 3：LLM 能解释回测结果。
- 阶段 4：回测结果展示稳定，适合答辩演示。

### 交付物

- `alpha_workbench/data/sample/`
- `alpha_workbench/backtest/factor_backtest.py`
- `alpha_workbench/backtest/metrics.py`
- 回测结果 JSON
- Backtest Explanation Prompt

## 角色 6：轻量审计、记忆与报告 Agent 负责人

### 主要职责

- 负责轻量审计，不做复杂工业级风控系统。
- 保存 Research Trace，记录一次研究从输入到结果的完整路径。
- 生成最终研究报告。
- 该模块优先级低于主闭环，但要体现项目的“可解释、可追踪、可审计”亮点。

### 大模型相关工作

- 设计 Audit Prompt 和 Report Generation Prompt。
- 使用 LLM 将规则检查、回测解释和研究路径整理成报告。
- 让审计报告指出风险，而不是只做正向总结。

### 工作步骤

1. 定义 Research Trace 结构，记录输入、IdeaSpec、ResearchSpec、FactorSpec、回测结果、审计结果和用户修改。
2. 先实现规则化审计，包括未来函数风险提示、字段替代说明、交易成本提示、参数稳定性提示。
3. 将审计结果交给 LLM 生成自然语言报告。
4. 保存 `research_trace.json`。
5. 输出最终研究报告 Markdown。
6. 对接 UI 的审计与报告页面。

### 阶段目标

- 阶段 1：先不阻塞主流程，只定义 Research Trace 数据结构。
- 阶段 2：保存一次完整研究路径 JSON。
- 阶段 3：生成轻量审计报告。
- 阶段 4：生成最终项目演示报告。

### 交付物

- `alpha_workbench/agents/audit_agent.py`
- `alpha_workbench/memory/alpha_memory.py`
- `alpha_workbench/reports/report_generator.py`
- `research_trace.json` 示例
- Audit Prompt
- Report Generation Prompt

## 模块接口约定

为降低集成成本，各模块优先以 Python dict / JSON 作为边界。

### IdeaSpec

```yaml
idea_id: earnings_surprise_revision
idea_name: 盈利超预期与预期修正
core_hypothesis: 盈利超预期可能带来后续超额收益
economic_mechanism:
  - 盈利信息冲击
  - 分析师预期修正
  - 投资者反应不足
required_data_concepts:
  - 实际盈利
  - 市场预期盈利
  - 财报公告日
  - 公告前价格反应
risk_flags:
  - 一致预期数据可能不可得
  - 公告日处理不当会产生未来函数
```

### ResearchSpec

```yaml
universe: CSI500_or_sample_universe
filters:
  - remove_ST
  - remove_new_listed_less_than_120_days
data_preference:
  profit_field: net_profit_after_deducting_non_recurring_items
  expectation_field: seasonal_profit_forecast_proxy
custom_rules:
  - pre_announcement_return_20d_adjustment
  - cash_flow_quality_filter
backtest:
  rebalance_frequency: monthly
  holding_period: 20
  transaction_cost_bps: 20
  groups: 5
```

### FactorSpec

FactorSpec 采用三层表达：

- `plain_description`：给研究员看的自然语言解释。
- `latex_formula`：给 UI、报告和答辩展示的数学公式。
- `formula_tree`：给系统执行、字段检查和审计使用的受限表达式树。

LaTeX 不替代表达式树。LaTeX 负责展示和沟通，表达式树负责执行和可审计。

```yaml
factor_id: earnings_surprise_adj_001
factor_name: 公告前涨幅调整后的盈利超预期
plain_description: >
  先计算公司盈利超预期程度，并在行业内标准化；
  再扣除公告前 20 日涨幅带来的提前反应影响。
latex_formula: >
  F_i =
  Z_{industry}(Surprise_i)
  - 0.5 \times Z_{industry}(PreRet20_i)
required_fields:
  - earnings_surprise
  - pre_announcement_return_20d
field_definitions:
  earnings_surprise: 实际单季度净利润相对预期利润的偏离
  pre_announcement_return_20d: 财报公告日前 20 个交易日收益率
formula_tree:
  op: subtract
  left:
    op: industry_zscore
    arg: earnings_surprise
  right:
    op: multiply
    left: 0.5
    right:
      op: industry_zscore
      arg: pre_announcement_return_20d
risk_notes:
  - 公告日前价格窗口必须严格滞后
  - 若一致预期不可得，需要标注 proxy 口径
```

### Research Trace

```yaml
trace_id: demo_earnings_surprise_001
input:
  source_type: natural_language
  content: 单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能有超额收益。
idea_spec: {}
research_spec: {}
factor_specs: []
backtest_results: {}
audit_results: {}
user_edits: []
final_report: ""
```

## 集成建议

- 每位同学先提供一个 `mock_xxx()` 函数，保证 UI 可以提前接入。
- 所有模块都保留固定样例输出，避免 LLM API 不稳定时 demo 崩溃。
- LLM 输出必须经过 JSON 解析和字段校验。
- 每个 Agent 都需要记录 prompt、输入、输出和错误信息。
- 最终演示时优先使用固定样例数据，减少外部数据源和网络依赖。

## 公共规范

### LLM 输出规范

- 所有 Agent 默认输出 JSON-compatible dict，不直接返回散乱长文本。
- LLM 原始输出要保存到日志或 trace 中，解析后的结构化结果用于系统后续流程。
- LLM 输出缺字段时，模块应使用默认值或返回清晰错误，不应让 UI 崩溃。
- Prompt 中必须明确禁止生成交易建议或实盘承诺。
- Prompt 中必须要求标注不确定性、数据替代和潜在风险。

### 命名规范

- Python 文件和函数使用 snake_case。
- schema 字段使用 snake_case。
- `id` 字段使用稳定英文，例如 `earnings_surprise_revision`。
- UI 展示名称使用中文，例如 `盈利超预期与预期修正`。

### 错误处理规范

- 外部 API 调用失败时返回 fallback mock 结果，并在结果中标注 `is_fallback: true`。
- 字段缺失时返回 `missing_fields`，不要直接抛给 UI。
- 回测无法运行时返回错误说明和可展示的诊断信息。
- 最终 demo 必须有一条完全离线可跑通的固定路径。

## 最小验收标准

到 demo 前，至少需要满足：

- 用户可以在页面输入一句投资想法。
- 系统可以生成 IdeaSpec。
- 用户可以修改部分 ResearchSpec。
- 系统可以展示 3 个以上候选因子。
- 至少 1 个因子可以完成基础回测。
- 页面可以展示回测图和指标。
- 系统可以生成一段回测解释和轻量审计报告。
- 系统可以保存或展示一次 Research Trace。
