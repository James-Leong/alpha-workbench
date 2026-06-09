# Role 5: 回测与结果解释 — 工作总结

## 功能清单

Role 5 负责因子回测、Mercury 远端交易模拟、结果可视化和 LLM 解释。全部功能已从 `role5/` 迁移到主 `alpha_workbench/` 包中。

### 1. 因子回测引擎

| 功能 | 模块 | 说明 |
|---|---|---|
| IC / RankIC 计算 | `backtest/metrics.py` | Pearson IC 和 Spearman RankIC，含 ICIR、t 统计量、IC 为正比例 |
| 分层收益 | `backtest/hybrid_engine.py` | 按因子值分 N 层（默认 5 层），计算各层年化收益和累计收益曲线 |
| 多空组合 | `backtest/hybrid_engine.py` | 做多最高层 / 做空最低层，计算年化收益、夏普、最大回撤 |
| 换手率 | `backtest/hybrid_engine.py` | 相邻期持仓变化比例 |
| 批量回测 | `backtest/factor_backtest.py` | 多因子并行回测，结果排序，mock fallback |

### 2. 交易级回测

| 功能 | 模块 | 说明 |
|---|---|---|
| HTTP 客户端 | `backtest/mercury_adapter.py` | httpx 客户端，支持 Bearer Token 认证 |
| 健康检查 | `health_check()` / `ready_check()` | 检测 Mercury 服务可用性 |
| 创建回测 | `create_backtest()` | POST `/api/v1/backtests` |
| 查询结果 | `get_backtest()` | GET `/api/v1/backtests/{job_id}` |
| 异步等待 | `create_and_wait()` | 创建并轮询直到完成 |

默认服务地址：`http://quant.futuri.top`（可通过 `MERCURY_BASE_URL` 环境变量覆盖）。

### 3. LLM 回测解释

| 功能 | 模块 | 说明 |
|---|---|---|
| API 调用 | `backtest/llm_explainer.py` | DeepSeek V3.2 via 华为云 MaaS，支持流式响应 |
| Mock fallback | `llm_explainer.py:_explain_mock()` | 基于规则的自动分析，无需 API |
| 结构化输出 | `schemas/backtest_schemas.py:BacktestExplanationResult` | 7 个分析维度 + 质量评分 |

### 4. 调仓与订单

| 功能 | 模块 | 说明 |
|---|---|---|
| 选股 | `backtest/rebalance.py:FactorRebalancer` | TopN / 分位数 / 阈值 选股 |
| 加权 | `backtest/rebalance.py` | 等权 / 因子加权 / 排名加权 |
| 订单生成 | `rebalance.py:generate_orders()` | 权重变化 → 买卖订单 |
| Mercury 转换 | `rebalance.py:MercuryOrderConverter` | 内部 Order → Mercury RunSpec JSON |

### 5. 可视化

| 图表 | 模块 |
|---|---|
| IC 序列图（柱状图 + MA 线） | `backtest/plotter.py:plot_ic_series()` |
| 分层累计收益图 | `backtest/plotter.py:plot_layer_cumreturns()` |
| 多空净值曲线 + 回撤 | `backtest/plotter.py:plot_long_short_nav()` |
| IC 分布直方图 | `backtest/plotter.py:plot_ic_distribution()` |
| 综合仪表板 | `backtest/plotter.py:create_dashboard()` |

### 6. 因子引擎

| 功能 | 模块 |
|---|---|
| 表达式树求值 | `factor_engine/expression_evaluator.py` |
| 因子计算（编译 + 执行） | `factor_engine/factor_calculator.py`（整合 `compiler.py` 验证） |

---

## 上下游对接

### Role 4 → Role 5（因子输入）

**推荐方式：CSV 文件**

```csv
date,stock_code,factor_value
2024-01-02,000001.XSHE,0.0234
2024-01-02,000002.XSHE,-0.0156
```

`data/csv_loader.py:load_role4_factor_output(csv_path)` 加载并转为 DataFrame(index=date, columns=stock_code)。

**备选方式：内存传递**

```python
factor_data_dict = {
    "factor_id_1": pd.DataFrame(...),
    "factor_id_2": pd.DataFrame(...),
}
result = run_backtest(factor_specs, research_spec,
                      factor_data_dict=factor_data_dict, price_data=price_data)
```

**Demo 回退**：role4 未就绪时，`sample_data.py` 自动生成随机因子数据，结果标记 `is_mock: true`。

### Role 5 → Role 6（审计/报告输入）

`run_backtest()` 返回的 dict 结构：

```python
{
    "research_universe": "sample_universe",
    "factor_results": [
        {
            "factor_id": str,
            "factor_name": str,
            "ic_mean": float, "ic_std": float, "icir": float,
            "ic_positive_ratio": float, "ic_tstat": float,
            "rank_ic_mean": float, "rank_ic_std": float, "rank_icir": float,
            "rank_ic_positive_ratio": float, "rank_ic_tstat": float,
            "long_short_return": float, "sharpe_ratio": float,
            "max_drawdown": float, "annual_volatility": float,
            "layer_returns": {"L1": 0.05, "L2": 0.03, ...},
        }
    ],
    "mercury_results": {"factor_id": {...}},
    "is_mock": bool,
}
```

`explain_backtest()` 返回：

```python
{
    "summary": str, "ic_analysis": str, "layer_analysis": str,
    "long_short_analysis": str, "turnover_analysis": str,
    "risk_assessment": str, "recommendations": str,
    "is_fallback": bool,
}
```

### Role 5 → 前端（Streamlit）

工作流：`Streamlit → run_demo_workflow() → run_backtest() → explain_backtest() → trace dict`

`backtest_result` 中的 `charts` 字段包含 Plotly Figure 对象，前端使用 `st.plotly_chart()` 渲染。metrics 字段直接渲染为 table 和 metric cards。

---

## Mercury 配置

### 环境变量（`.env` 文件）

```bash
MERCURY_BASE_URL=http://quant.futuri.top    # 默认值，可不配
MERCURY_API_TOKEN=your_token_here           # 必填
```

### 代码配置

```python
from alpha_workbench.backtest.mercury_adapter import create_mercury_adapter, MercuryConfig

# 方式 1: 便捷函数（从环境变量读取）
adapter = create_mercury_adapter(api_token="xxx")

# 方式 2: 配置对象
config = MercuryConfig(api_token="xxx")
adapter = MercuryAdapter(config)
```

### Token 格式兼容

支持三种输入格式，自动归一化：
- `sk-xxx`（裸 token）
- `Bearer sk-xxx`
- `Authorization: Bearer sk-xxx`

---

## 待修复：前端研究配置未传递到回测引擎

前端 `_render_research_config` 展示的股票池、调仓频率等配置，目前**仅做展示**，未实际传入 `BacktestInput` 或 `MercuryRunConfig`。

### 现状对照

| 前端字段 | `research_spec` 来源 | 回测实际使用情况 |
|---|---|---|
| `universe`（股票池） | `sample_universe` | ❌ 仅做标签回传；引擎硬编码 50 只 sample stocks |
| `holding_period`（持有期） | `20D` | ❌ 未传入 `BacktestInput`，也未传给 Mercury |
| `rebalance_frequency`（调仓频率） | `monthly` | ❌ Mercury 策略硬编码 `"weekly"` |
| `transaction_cost_bps`（交易成本） | `10` | ❌ Mercury 使用 `BacktestInput.commission_rate` 默认值（千分之一 = 10bps，数值碰巧一致） |
| `sample_window`（样本区间） | `2024-01-01 ~ 2024-06-30` | ❌ 使用 `sample_data` 随机生成 120 天，与区间无关 |
| `backtest.groups`（分层数） | `5` | ✅ 用于本地 IC / 分层收益计算 |

### 根因

`engine.py` 构造 `BacktestInput` 时（约第 130 行）仅传入了 `factor_spec`、`factor_data`、`price_data`、`returns_data`、`n_quantiles`，未将 `research_spec` 中的配置字段传递下去：

```python
input_data = BacktestInput(
    factor_spec=factor_spec,
    factor_data=fdata,
    price_data=price_data_use,
    returns_data=rdata_use,
    n_quantiles=n_quantiles,  # ← 唯一从 research_spec 读取的字段
)
```

`HybridBacktestEngine._run_mercury_backtest()` 内部也硬编码了 `"schedule": "weekly"`、`initial_cash=1_000_000` 等，不读取外部配置。

### 修复方案

1. **`engine.py`** — 将 `research_spec` 的关键字段映射到 `BacktestInput`：
   ```python
   input_data = BacktestInput(
       ...,
       research_spec=ResearchSpec.from_dict(rs) if rs else None,
       start_date=parse_date(rs.get("sample_window", {}).get("start")),
       end_date=parse_date(rs.get("sample_window", {}).get("end")),
       commission_rate=rs.get("transaction_cost_bps", 10) / 10000,
   )
   ```

2. **`hybrid_engine.py:_run_mercury_backtest()`** — 从 `input_data.research_spec` 读取配置替代硬编码：
   - `schedule` 映射到 `research_spec.rebalance_frequency`（`monthly` → `monthly`，`weekly` → `weekly`）
   - `transaction_cost_bps` 从 `research_spec.transaction_cost_bps` 读取
   - `start_date/end_date` 从 `BacktestInput.start_date/end_date` 读取，替代 `factor_data.index[0]/[-1]`
   - `assets` 改为调用 `FactorRebalancer` 按因子值排名选股，替代 `all_stocks[:20]`

3. **`data/sample_data.py`** — `generate_sample_data()` 支持传入 `start_date/end_date` 参数，使生成的数据与 `research_spec.sample_window` 一致。

```
alpha_workbench/
├── backtest/
│   ├── engine.py              # 对外接口: run_backtest()（合约函数）
│   ├── hybrid_engine.py       # HybridBacktestEngine（本地 + Mercury）
│   ├── factor_backtest.py     # 批量回测 + mock fallback
│   ├── metrics.py             # IC/分层/多空/换手率 指标计算
│   ├── mercury_adapter.py     # Mercury HTTP 客户端
│   ├── rebalance.py           # 调仓选股 + Mercury Order 转换
│   ├── plotter.py             # Plotly 图表生成
│   └── llm_explainer.py       # LLM 解释器（DeepSeek + mock）
├── factor_engine/
│   ├── compiler.py            # 因子编译（表达式验证）
│   ├── expression_evaluator.py # 表达式树求值
│   └── factor_calculator.py   # 因子计算器
├── data/
│   ├── sample_data.py         # 样例数据生成
│   └── csv_loader.py          # CSV 加载（含 load_role4_factor_output）
├── schemas/
│   ├── backtest_schemas.py    # Pydantic 模型（FactorSpec, BacktestReport, etc.）
│   └── specs.py               # 工作流 dict 定义（IdeaSpec, ResearchSpec, ResearchTrace）
├── interfaces/
│   └── role_interfaces.py     # Role2/Role6 接口 Pydantic 模型
└── agents/
    └── backtest_explainer.py  # 解释 agent（调用 llm_explainer）
```

---

## 运行验证

```bash
# 快速检查导入
python -c "from alpha_workbench.backtest import run_backtest; print('OK')"

# 运行 demo 工作流（mock 模式，无须任何外部服务）
python -c "
from alpha_workbench.workflows.demo_workflow import run_demo_workflow
trace = run_demo_workflow()
print('Factors:', len(trace['factor_specs']))
print('Backtest results:', len(trace['backtest_result']['factor_results']))
print('Explanation summary:', trace['explanation']['summary'][:80])
"

# 启动 Streamlit 前端
streamlit run alpha_workbench/app/streamlit_app.py
```
