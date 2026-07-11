# AlphaWorkbench Codex 因子研发与真实数据管线设计 v3

本文档重新设计 AlphaWorkbench 从研报解析到真实股票数据因子研发的完整链路。核心调整是：平台不再假设复杂因子都能用有限表达式树覆盖，而是采用“双轨因子实现”：

- 简单/标准化因子：使用结构化表达式树或受限 DAG，便于解释、审计和快速回测。
- 复杂/研究型因子：当前版本只使用本地 Codex CLI 生成 Python 因子插件，再经过沙箱、测试、PIT 审计、人工或自动注册后进入回测。

最终目标不是让 LLM 在业务运行时直接 `exec` 任意 Python，而是把 Python 因子代码作为可版本化、可测试、可审计的工程产物管理。

## 0. 当前实现状态（2026-07-11）

| 模块 | 状态 | 当前可验证结果 | 后续缺口 |
| --- | --- | --- | --- |
| 因子插件契约与运行时 | 已完成 | manifest、AST、FactorContext、受限子进程 runner、多截点 lookahead perturbation audit | 后续可替换为远端容器执行 |
| 插件注册 | 已完成 | 校验通过后按 factor/version/source hash 原子 promotion，重复注册幂等 | 生产环境人工审批界面 |
| CodexExecProvider | 已完成 | 检测 `codex-cli 0.144.1`，bubblewrap 隔离 job、最小环境、结构化输出，真实 repair 验收通过 | 将 Codex JSONL 事件流接入 API 进度 |
| Codex 真实生成验收 | 已完成 | 真实 Codex 产物通过 manifest、AST、生成 pytest、PIT smoke，输出 80x20 因子矩阵 | 将 Codex JSONL 事件流接入 API 进度 |
| Data SDK | 部分完成 | Provider 协议、InMemoryProvider、SQLiteStore、UqerProvider 惰性适配、PIT fixture | UQER 字段映射、分页/重试、Parquet 分区与 catalog |
| 回测接入 | 已完成（fixture） | strict factor data 模式，`uses_synthetic_factor_data=false`，因子/行情 provenance 分离 | 使用真实股票快照做同一验收 |
| API/Trace | 部分完成 | ResearchSpec 可选 `expression/codex`，Trace 保存 brief、manifest、validation、lookahead audit、promotion、hash | 前端模式选择、`needs_review` 状态、插件审核页 |

当前里程碑证明的是：Codex 生成的代码可以被受控地验证并计算，且不会再由回测器静默替换成 synthetic factor signal。它尚不等于“真实股票数据接入完成”；真实数据阶段必须在 UQER 字段映射与本地快照完成后单独验收。

## 1. 目标

### 1.1 产品目标

AlphaWorkbench 应支持以下研究闭环：

```text
研报 PDF / 文本想法
-> 研报解析与证据提取
-> IdeaSpec
-> ResearchSpec 人工确认
-> Factor Coding Brief
-> 代码 Agent 生成因子插件 / 或生成表达式 DAG
-> 数据 SDK 准备真实股票数据
-> 因子计算
-> 回测
-> 审计
-> 报告与 Research Trace
```

### 1.2 工程目标

- 能用真实股票数据构建因子，不再依赖 synthetic factor data。
- 底层可使用 `uqer` 获取数据，但项目核心只依赖自有 `data_sdk`。
- 本地数据以 parquet/sqlite 存储，支持缓存、复现和数据源切换。
- 支持代码 Agent 生成因子代码，但代码必须进入受控插件机制。
- 每个阶段都有可运行测试和可观察产物。

## 2. 关键设计决策

### 2.1 Python 因子代码允许存在

允许 Python 写复杂因子，但必须满足：

- 因子代码存放在插件目录，而不是数据库里的临时代码字符串。
- 插件必须声明 manifest：字段、lookback、频率、PIT 要求、参数、风险。
- 插件只能通过平台提供的 `FactorContext` 读取数据，不能直接 import `uqer`。
- 插件必须通过单元测试、样例数据 smoke test 和未来函数检查。
- 插件注册后才允许进入回测。

### 2.2 Code Agent 是开发者，不是运行时执行器

Code Agent 的职责：

- 根据 Factor Coding Brief 生成或修改插件文件。
- 编写测试。
- 根据测试失败自动修复。
- 输出 diff、说明和风险提示。

Code Agent 不负责：

- 在生产回测路径中直接执行任意代码。
- 直接访问 UQER、网络、凭证或生产数据。
- 绕过测试和注册流程。

### 2.3 UQER 是 provider，不是业务依赖

正确依赖方向：

```text
workflow / factor / backtest
-> data_sdk.service
-> data_sdk.storage
-> data_sdk.providers.uqer_provider
-> uqer
```

禁止：

```text
factor.py -> uqer.DataAPI
workflow.py -> uqer.DataAPI
backtest.py -> uqer.DataAPI
```

## 3. 总体架构

```text
frontend
  |
api/routers/research.py
  |
workflows/
  research_workflow.py
  code_factor_workflow.py
  real_data_workflow.py
  |
agents/
  idea_extractor.py
  factor_generator.py
  code_agent_orchestrator.py
  |
  code_agent/
  providers/
    codex_exec_provider.py
  sandbox.py
  patch_parser.py
  validation.py
  |
factor_plugins/
  generated/
  promoted/
  |
factor_runtime/
  context.py
  plugin_loader.py
  runner.py
  validators.py
  |
data_sdk/
  service.py
  registry.py
  providers/
    base.py
    uqer_provider.py
    mock_provider.py
  storage/
    parquet_store.py
    sqlite_store.py
    manifest.py
  quality.py
  |
backtest/
  engine.py
```

## 4. 核心对象

### 4.1 ParsedReport

研报解析结果，作为 Idea Agent 的输入和审计证据。

```json
{
  "source_type": "pdf",
  "filename": "report.pdf",
  "parser": "pymupdf",
  "text_chars": 120000,
  "sections": [
    {
      "section_id": "s1",
      "title": "投资逻辑",
      "text": "...",
      "page_start": 3,
      "page_end": 5
    }
  ],
  "evidence": [
    {
      "source": "pdf",
      "page": 4,
      "text": "盈利超预期且市场反应不足..."
    }
  ],
  "parse_quality": {
    "is_fallback": false,
    "warnings": []
  }
}
```

### 4.2 Factor Coding Brief

给 Code Agent 的任务说明，不直接让它自由发挥。

```json
{
  "factor_id": "earnings_surprise_underreaction",
  "idea_summary": "盈利超预期且公告前反应不足",
  "hypothesis": "公告后可能存在滞后定价",
  "required_fields": [
    "net_profit_q",
    "expected_net_profit_q",
    "announce_date",
    "adj_close",
    "industry"
  ],
  "data_policy": {
    "point_in_time_required": true,
    "signal_effective_rule": "next_trade_date_after_announce",
    "allow_consensus_proxy": true
  },
  "implementation_target": "python_plugin",
  "plugin_contract": {
    "entrypoint": "calculate(ctx, params)",
    "return_shape": "wide_dataframe",
    "forbidden": ["uqer", "requests", "subprocess", "open", "eval", "exec"]
  },
  "test_requirements": [
    "must run on mock PIT fixture",
    "must not use report_period as trade_date",
    "must produce DataFrame indexed by trade_date and columns by symbol"
  ]
}
```

### 4.3 Factor Plugin Manifest

每个 Python 因子插件必须带 manifest。

```json
{
  "factor_id": "earnings_surprise_underreaction",
  "factor_name": "盈利超预期低反应",
  "version": "0.1.0",
  "entrypoint": "factor:calculate",
  "required_fields": [
    "net_profit_q",
    "expected_net_profit_q",
    "announce_date",
    "adj_close",
    "industry"
  ],
  "lookback_days": 40,
  "frequency": "daily",
  "point_in_time": true,
  "parameters": {
    "pre_window": 20,
    "pre_return_weight": 0.5
  },
  "data_policy": {
    "signal_effective_rule": "next_trade_date_after_announce",
    "allow_proxy_fields": ["expected_net_profit_q"]
  },
  "risk_notes": [
    "expected_net_profit_q 可能使用去年同期利润 proxy",
    "公告日对齐错误会产生未来函数"
  ],
  "status": "generated"
}
```

### 4.4 FactorContext

插件唯一允许访问数据的接口。

```python
class FactorContext:  # 当前 MVP
    def field(self, name: str) -> pd.DataFrame: ...
    @property
    def trading_dates(self) -> pd.DatetimeIndex: ...
    @property
    def symbols(self) -> list[str]: ...

class ExtendedFactorContext(FactorContext):  # 后续阶段
    def event_field(self, name: str) -> pd.DataFrame: ...
    def event_window_return(
        self,
        price_field: str,
        event_date_field: str,
        start_offset: int,
        end_offset: int,
    ) -> pd.DataFrame: ...
    def point_in_time_fill(self, value_field: str, effective_date_field: str) -> pd.DataFrame: ...
    def winsorize(self, df: pd.DataFrame, limits=(0.01, 0.99)) -> pd.DataFrame: ...
    def group_zscore(self, df: pd.DataFrame, by: str) -> pd.DataFrame: ...
    def neutralize(self, df: pd.DataFrame, exposures: list[str]) -> pd.DataFrame: ...
    def quality_report(self) -> dict: ...
```

这样复杂因子可以用 Python 表达，但所有数据访问、事件窗口和中性化都由平台统一实现。

## 5. 数据 SDK 设计

### 5.1 Provider 接口

```python
class DataProvider:
    name: str

    def fetch_trade_calendar(self, start: str, end: str, exchange: str) -> pd.DataFrame: ...
    def fetch_universe(self, universe: str, date: str | None) -> pd.DataFrame: ...
    def fetch_market_daily(self, symbols: list[str], start: str, end: str, fields: list[str]) -> pd.DataFrame: ...
    def fetch_financial_pit(self, symbols: list[str], start: str, end: str, fields: list[str]) -> pd.DataFrame: ...
    def fetch_consensus_forecast(self, symbols: list[str], start: str, end: str, fields: list[str]) -> pd.DataFrame: ...
    def fetch_industry(self, symbols: list[str], start: str, end: str) -> pd.DataFrame: ...
```

第一阶段只实现 `MockProvider`，第二阶段再实现 `UqerProvider`。这样可以先验证工程链路，不被外部数据源阻塞。

### 5.2 本地存储

parquet 保存大表：

```text
data/cache/parquet/
  market_daily/year=2024/month=01/part.parquet
  financial_pit/year=2024/month=01/part.parquet
  industry/year=2024/month=01/part.parquet
  factor_values/factor_id=xxx/year=2024/month=01/part.parquet
```

sqlite 保存 manifest 和 catalog：

```text
data/cache/alpha_data.sqlite3
```

表：

- `dataset_manifest`
- `field_registry`
- `universe_membership`
- `data_quality_report`
- `factor_plugin_registry`
- `factor_run_manifest`

### 5.3 标准字段

第一版字段注册表只覆盖盈利超预期因子：

| 标准字段 | 含义 | 频率 | PIT | 数据集 |
| --- | --- | --- | --- | --- |
| `adj_close` | 后复权收盘价 | daily | 否 | market_daily |
| `net_profit_q` | 单季度净利润 | quarterly/event | 是 | financial_pit |
| `net_profit_q_yoy_base` | 去年同期单季度净利润 | quarterly/event | 是 | financial_pit |
| `expected_net_profit_q` | 预期净利润 | event | 是 | consensus_forecast / proxy |
| `announce_date` | 公告日 | event | 是 | financial_pit |
| `industry` | 行业 | daily | 否 | industry |
| `market_cap` | 市值 | daily | 否 | market_daily |

字段注册表必须记录 provider 字段映射，但上层代码只使用标准字段。

## 6. Code Agent 集成设计

### 6.1 Provider 抽象

```python
class CodeAgentProvider:
    def generate_plugin(self, brief: dict, workspace: Path) -> dict: ...
    def fix_plugin(self, failure_report: dict, workspace: Path) -> dict: ...
    def review_plugin(self, diff: str, workspace: Path) -> dict: ...
```

本次开发只实现 `CodexExecProvider`，通过本地 `codex exec` 调用。测试使用注入式 fake runner 或 fake provider，不提供可在业务运行时选择的 Mock/Claude/其他 Provider。

Provider 必须隐藏具体工具差异，workflow 只依赖 `CodeAgentProvider`。

### 6.2 生成工作区

每次代码生成使用隔离目录：

```text
runs/codegen/{run_id}/
  workspace/
    alpha_workbench/factor_plugins/generated/{factor_id}/
      manifest.json
      factor.py
      tests/test_factor.py
  logs/
    prompt.md
    agent_output.json
    pytest.log
    review.json
```

生成通过后，插件可以复制或移动到：

```text
alpha_workbench/factor_plugins/promoted/{factor_id}/
```

是否自动 promoted 由配置决定。默认建议：demo 环境可自动 promoted，生产环境必须人工确认。

### 6.3 代码约束

插件代码允许：

- `pandas`
- `numpy`
- 平台提供的 `FactorContext`
- 标准类型和简单工具函数

插件代码禁止：

- `uqer`
- `requests`
- `socket`
- `subprocess`
- `os.system`
- 文件写入
- 任意网络访问
- `eval`
- `exec`
- 动态 import

AST 扫描只承担快速拒绝和可解释性检查，不作为安全边界。生成测试和因子计算必须在 bubblewrap 隔离进程中运行，隐藏宿主 home、清空业务环境变量、禁用网络，并设置超时及资源上限。

### 6.4 验证流水线

```text
生成插件
-> 格式检查
-> AST 安全扫描
-> manifest 校验
-> mock PIT fixture 单元测试
-> 因子 smoke calculation
-> lookahead audit
-> backtest smoke test
-> 注册或等待人工确认
```

任一环节失败：

1. 生成 failure report。
2. 调用 `fix_plugin()` 最多 N 次。
3. 仍失败则项目状态为 `needs_review`，前端展示失败原因。

## 7. 盈利超预期插件示例

Code Agent 生成的目标代码应接近：

```python
def calculate(ctx, params):
    pre_window = int(params.get("pre_window", 20))
    weight = float(params.get("pre_return_weight", 0.5))

    profit = ctx.field("net_profit_q")
    expected = ctx.field("expected_net_profit_q")
    pre_ret = ctx.event_window_return(
        price_field="adj_close",
        event_date_field="announce_date",
        start_offset=-pre_window,
        end_offset=-1,
    )

    surprise = (profit - expected) / (expected.abs() + 1.0)
    raw = surprise - weight * pre_ret
    return ctx.group_zscore(ctx.winsorize(raw), by="industry")
```

这个代码不直接关心 UQER，不处理 parquet 路径，不直接做公告日展开。所有这些由 `FactorContext` 和 `data_sdk` 处理。

## 8. Workflow v2

### 8.1 创建项目

```text
POST /api/research/projects
-> 解析 PDF/text
-> extract_idea()
-> build_research_spec()
-> 保存 pending trace
```

可验证：

- trace 有 `idea_spec`
- trace 有 `research_spec`
- PDF 输入有 `parsed_report`
- 项目状态为 `pending`

### 8.2 启动研究

```text
POST /api/research/projects/{id}/start
-> generate_factor_coding_brief()
-> code_agent.generate_plugin()
-> validate_plugin()
-> prepare_real_data()
-> run_factor_plugin()
-> run_backtest()
-> audit
-> report
```

可验证：

- trace 有 `factor_plugin_manifest`
- trace 有 `codegen_validation_report`
- trace 有 `data_quality_report`
- trace 有 `factor_data_manifest`
- backtest 不使用 synthetic factor data

### 8.3 Fallback 策略

配置：

```env
FACTOR_CODE_AGENT=codex
FACTOR_CODE_TIMEOUT_SECONDS=600
FACTOR_CODE_JOBS_DIR=./data/factor_code_jobs
FACTOR_PLUGIN_REGISTRY_DIR=./data/factor_plugins
```

Fallback：

- Code Agent 不可用：按 `ResearchSpec.factor_execution.fallback_to_expression` 决定回退表达式路径或失败，不伪造 Codex 成功。
- UQER 不可用：阶段测试使用 deterministic PIT fixture，trace 明确标记 `data_provider=deterministic_pit_fixture` 和 `uses_mock_market_data=true`。
- 插件失败：回到表达式树候选因子或标记 `needs_review`，不静默伪装成真实成功。

## 9. 阶段计划与验收

### 阶段 0：设计冻结

目标：冻结接口和目录，不写真实 provider。

交付：

- 本设计文档。
- `FactorPlugin` manifest JSON Schema。
- `CodeAgentProvider` 协议。
- `DataProvider` 协议。

验证：

```bash
uv run pytest tests/test_contracts.py
```

验收标准：

- schema 能校验合法/非法 manifest。
- provider 协议有最小 mock 实现。

### 阶段 1：插件运行时骨架

目标：不用 Code Agent，手写一个固定插件，验证插件机制。

交付：

- `factor_runtime/context.py`
- `factor_runtime/plugin_loader.py`
- `factor_plugins/promoted/earnings_surprise_underreaction/`
- mock PIT fixture

验证：

```bash
uv run pytest tests/test_factor_plugin_runtime.py
```

验收标准：

- 能加载 manifest。
- 能调用 `calculate(ctx, params)`。
- 输出宽表 `DataFrame(index=trade_date, columns=symbol)`。
- 插件不能 import 禁止模块。

### 阶段 2：Data SDK + 本地缓存

目标：不接 UQER，用 MockProvider 写入 parquet/sqlite，再从本地读出供插件计算。

交付：

- `data_sdk/providers/mock_provider.py`
- `data_sdk/storage/parquet_store.py`
- `data_sdk/storage/sqlite_store.py`
- `data_sdk/service.py`

验证：

```bash
uv run pytest tests/test_data_sdk.py
```

验收标准：

- 第一次请求写入 parquet。
- 第二次请求命中缓存，不调用 provider。
- manifest 记录字段、日期范围、行数、hash。
- `MarketDataService` 返回标准字段。

### 阶段 3：真实数据路径接入回测

目标：仍使用 MockProvider，但完整走“真实数据路径”，不再 synthetic factor data。

交付：

- `real_data_workflow.py`
- `run_factor_plugin()` 生成 `factor_data_dict`
- `run_backtest()` 接收真实 `factor_data_dict`

验证：

```bash
uv run pytest tests/test_real_data_workflow.py
```

验收标准：

- trace 中 `uses_synthetic_factor_data=false`。
- trace 中有 `factor_data_manifest`。
- trace 中有 `data_quality_report`。
- 回测结果来自插件计算的因子值。

### 阶段 4：Code Agent 测试替身

目标：用测试替身验证代码生成工作区和修复流程，不将测试替身暴露为业务 Provider。

交付：

- `code_agent/providers/mock_provider.py`
- `runs/codegen/{run_id}` 工作区
- validation pipeline

验证：

```bash
uv run pytest tests/test_code_agent_workflow.py
```

验收标准：

- Brief 能生成插件文件。
- 失败测试能生成 failure report。
- mock fix 能修复一个故意错误。
- 通过后可注册插件。

### 阶段 5：Codex Provider

目标：接入至少一种真实代码 Agent，但仍只在隔离工作区生成代码。

交付：

- `CodexExecProvider`
- provider 配置
- agent prompt 模板
- 生成日志持久化

验证：

```bash
uv run pytest tests/test_code_agent_provider_contract.py
uv run pytest tests/test_code_agent_workflow.py --run-external-code-agent
```

验收标准：

- 没有外部工具时测试默认跳过，不影响 CI。
- 配置外部工具后能生成插件。
- 生成插件必须通过阶段 4 的同一套验证流水线。
- provider 不允许直接修改项目主目录，只能写 codegen workspace。

### 阶段 6：UQER Provider

目标：接入真实 UQER 数据源，但 workflow 不感知 UQER。

交付：

- `data_sdk/providers/uqer_provider.py`
- 标准字段映射
- 分月拉取和缓存
- 数据质量报告

验证：

```bash
uv run pytest tests/test_uqer_provider_contract.py
uv run pytest tests/test_real_data_workflow.py --run-uqer
```

验收标准：

- 无 UQER token 时测试跳过或 fallback mock。
- 有 token 时能拉取交易日历、行情、财务 PIT、行业数据。
- UQER 原始字段不会泄漏到插件和 workflow。
- parquet 缓存命中后不再访问 UQER。

### 阶段 7：前端和审计闭环

目标：用户能看到代码生成、测试、数据质量、真实回测结果。

交付：

- 前端展示 Code Agent 状态。
- 前端展示插件 manifest 和 validation report。
- 前端展示数据来源、proxy、PIT 检查。
- AuditAgent 检查代码插件和数据对齐风险。

验证：

```bash
uv run pytest tests/test_api_research.py
uv run pytest tests/test_research_trace_contract.py
```

验收标准：

- pending -> start -> completed 状态完整。
- 失败时进入 `needs_review` 或 `failed`，且 UI 有明确原因。
- Research Trace 可复现一次完整代码因子研发过程。

## 10. API 变更

新增或扩展字段：

```json
{
  "trace": {
    "parsed_report": {},
    "factor_coding_brief": {},
    "factor_plugin_manifest": {},
    "codegen_validation_report": {},
    "data_requirement_plan": {},
    "data_quality_report": {},
    "factor_data_manifest": {},
    "uses_real_data": true,
    "uses_synthetic_factor_data": false,
    "code_agent_provider": "codex_exec",
    "data_provider": "deterministic_pit_fixture",
    "data_store": "sqlite",
    "uses_mock_market_data": true
  }
}
```

新增状态建议：

- `pending`：等待确认配置。
- `running`：执行中。
- `needs_review`：代码生成或验证失败，需要人工处理。
- `completed`：完成。
- `failed`：系统性失败。

## 11. 最小可演示路径

当前第一条可演示路径不依赖 UQER，但会调用真实本地 Codex：

```text
文本输入
-> IdeaSpec
-> ResearchSpec
-> CodexExecProvider 生成盈利超预期插件
-> deterministic PIT fixture 生成标准字段
-> 插件计算因子
-> 回测
-> 报告
```

验收时必须证明：

- 因子值来自插件代码，不是 synthetic factor data。
- 数据来自 `DataService`/fixture，不能由插件内部构造或直接查询 provider。
- trace 保存了插件 manifest、数据质量和验证报告。

第二条演示路径把 fixture 替换为本地真实股票快照：

```text
同一份 Codex 插件
-> SQLite/Parquet 本地快照
-> 同一套回测
```

第三条演示路径接入 UQER：

```text
同一插件
-> UqerProvider 刷新本地 SQLite/Parquet 快照
-> 本地缓存读取
-> 因子计算和回测
```

## 12. 风险与控制

| 风险 | 控制 |
| --- | --- |
| Code Agent 生成不可控代码 | AST 扫描、禁用模块、沙箱、测试、人工确认 |
| 未来函数 | FactorContext 统一 PIT 对齐，lookahead audit 强制执行 |
| UQER 不稳定 | 本地 SQLite/Parquet 快照、fixture 验证路径、manifest 记录来源 |
| 代码生成结果不可复现 | 保存 prompt、brief、diff、测试日志、插件版本 |
| 插件绕过数据 SDK | 禁止 import provider，插件只能使用 `ctx.field()` |
| 阶段过大无法验收 | 每阶段独立测试，外部工具测试默认 opt-in |

## 13. 下一阶段任务

1. 为 `UqerProvider` 实现价格、交易日历、财报 PIT 和行业字段映射，并以 fixture 契约做一致性测试。
2. 增加 Parquet 时间分区与 SQLite catalog，保存 provider、查询指纹、schema、覆盖区间和完整性状态。
3. 把本地真实股票快照接入 `run_factor_plugin_pipeline()`，验收 `uses_synthetic_factor_data=false` 且 `uses_mock_market_data=false`。
4. 将 Codex `--json` 事件流映射为 API progress events，并增加 `needs_review` 状态与人工审批界面。
5. 将当前 bubblewrap 受限子进程执行器抽象为可选远端容器执行器。

本次范围内不增加 Claude、Codex SDK、Codex MCP 或其他代码 Agent Provider。
