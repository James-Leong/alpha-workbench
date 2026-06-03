# 数据接口说明

本文只整理项目里当前真正对外可调用的 HTTP 数据接口，代码实现来自 [src/service/mod.rs](../src/service/mod.rs) 和 `src/service/` 下的子模块。

本地开发默认服务地址通常是：

```text
http://127.0.0.1:8080
```

测试环境默认服务地址通常是：

```text
http://10.24.51.212:18081
```

如果测试环境由于代理无法访问，可以使用 `dev212.datayes.com` 替代 `host` ，由用户手动修改 `/etc/hosts` 文件。

容器内默认绑定地址是：

```text
0.0.0.0:8080
```

## 1. 存活检查接口

| 项目 | 内容 |
| --- | --- |
| 名称 | 存活检查 `Liveness Probe` |
| URL | `GET /healthz` |
| 说明 | 检查 HTTP 进程是否存活。适合 Docker / 进程探活。 |

调用示例：

```bash
curl http://127.0.0.1:8080/healthz
```

返回值示例：

```json
{
  "status": "ok",
  "bind": "0.0.0.0:8080",
  "run_root": "runs",
  "cache_root": "cache",
  "metadata_root": "runs/jobs"
}
```

## 2. 就绪检查接口

| 项目 | 内容 |
| --- | --- |
| 名称 | 就绪检查 `Readiness Probe` |
| URL | `GET /readyz` |
| 说明 | 检查运行目录、metadata 目录和数据库配置文件路径是否可用。适合部署前置检查。 |

调用示例：

```bash
curl http://127.0.0.1:8080/readyz
```

成功返回示例：

```json
{
  "status": "ready",
  "bind": "0.0.0.0:8080",
  "run_root": "runs",
  "cache_root": "cache",
  "metadata_root": "runs/jobs"
}
```

如果未就绪，返回 `503 Service Unavailable`，响应体形如：

```json
{
  "error": "not_ready",
  "message": "<具体失败原因>"
}
```

## 3. 指标接口

| 项目 | 内容 |
| --- | --- |
| 名称 | 指标导出 `Metrics` |
| URL | `GET /metrics` |
| 说明 | 暴露 Prometheus 文本格式指标。HTTP 请求指标由 `axum-prometheus` 输出，业务耗时指标由服务侧额外记录。 |

调用示例：

```bash
curl http://127.0.0.1:8080/metrics
```

返回内容是 Prometheus exposition text，例如：

```text
# TYPE axum_http_requests_total counter
# TYPE mercury_backtest_jobs_total counter
```

## 4. 创建回测任务接口

| 项目 | 内容 |
| --- | --- |
| 名称 | 创建回测任务 `Create Backtest` |
| URL | `POST /api/v1/backtests` |
| 说明 | 接收一个 `RunSpec` JSON。顶层为 `run` + `inputs[]`；`inputs[]` 中最多一个交易生产输入（`strategy` / `order` / `transaction`），可同时携带任意数量 assertion 输入（`position` / `valuation` / `cash` / `indicator`）。服务端会校验参数、编译 `SimulationPlan`、生成 `DataRequirement`、准备 Parquet cache / execution view、执行回测并把结果写入 `runs/<job_id>/`。响应头会自动带回 `x-request-id`。 |

调用示例（使用下方请求体）：

```bash
curl -X POST http://127.0.0.1:8080/api/v1/backtests \
  -H 'Content-Type: application/json' \
  --data '<json-body>'
```

策略录入示例：

```json
{
  "run": {
    "start_date": "20240102",
    "end_date": "20260320",
    "initial_cash": 1000000.0,
    "transaction_cost_bps": 5.0
  },
  "inputs": [
    {
      "kind": "strategy",
      "name": "weekly_equal_weight_cn_equity",
      "language": "python-restricted",
      "version": 1,
      "ops": [
        {
          "op": "load_universe",
          "assets": ["000001", "600000", "上海机场", "中国石油"]
        },
        {
          "op": "schedule",
          "schedule": "weekly"
        },
        {
          "op": "weight",
          "weighting": "equal"
        },
        {
          "op": "order_target_percent"
        }
      ]
    }
  ]
}
```

`strategy` 输入中 `schedule` 支持的值：

| `schedule` 值 | 含义 | 触发条件 |
| --- | --- | --- |
| `"daily"` | 每日调仓 | 每个交易日 |
| `"weekly"` | 每周调仓 | ISO 周发生变化时（通常为周一或周一后的首个交易日） |
| `"monthly"` | 每月调仓 | 月份发生变化时 |
| `"quarterly"` | 每季调仓 | 季度发生变化时（Q1: 1-3 月，Q2: 4-6 月，Q3: 7-9 月，Q4: 10-12 月） |
| `"once"` | 仅建仓 | 首日建仓后不再调仓 |

订单录入示例：

```json
{
  "run": {
    "start_date": "20250102",
    "end_date": "20250110",
    "initial_cash": 1000000.0,
    "transaction_cost_bps": 0.0
  },
  "inputs": [
    {
      "kind": "order",
      "name": "explicit_orders_demo",
      "version": 1,
      "time_in_force": "day",
      "orders": [
        {
          "security_type": "stock",
          "date": "20250102",
          "sec_uiq_code": "000001.XSHE",
          "side": "buy",
          "quantity": 1000,
          "order_type": "market",
          "currency": "CNY",
          "submit_time": "20250102 09:30:00"
        },
        {
          "security_type": "fund",
          "date": "20250103",
          "sec_uiq_code": "110000.XSHE",
          "side": "buy",
          "quantity": 10000,
          "order_type": "market",
          "currency": "CNY",
          "submit_time": "20250103 09:30:00"
        }
      ]
    }
  ]
}
```

交易录入示例：

```json
{
  "run": {
    "start_date": "20250102",
    "end_date": "20250110",
    "initial_cash": 100000000.0,
    "transaction_cost_bps": 0.0
  },
  "inputs": [
    {
      "kind": "transaction",
      "name": "delivery_transactions_demo",
      "language": "delivery-transaction",
      "version": 1,
      "time_in_force": "day",
      "transactions": [
        {
          "security_type": "stock",
          "date": "20250102",
          "sec_uiq_code": "000001.XSHE",
          "direction": "long",
          "channel": null,
          "trans_currency_cd": "CNY",
          "transact_amount": 100000,
          "event_type": "buy",
          "transact_time": "20250102 15:00:00"
        },
        {
          "security_type": "stock",
          "date": "20250103",
          "sec_uiq_code": "000001.XSHE",
          "direction": "long",
          "channel": null,
          "trans_currency_cd": "CNY",
          "transact_amount": 100000,
          "event_type": "sell",
          "transact_price": 15.0,
          "settle_value": 1499950.0,
          "transact_time": "20250103 10:00:00"
        }
      ]
    }
  ]
}
```

说明：`settle_value` 为绝对值，commission 从 `|settle_value| - |transact_price × transact_amount|` 自动推导。
买入：|1000100 - 1000000| = 100 元佣金；卖出：|1499950 - 1500000| = 50 元佣金。

现金划转 / 盈亏录入示例：

```json
{
  "run": {
    "start_date": "20250303",
    "end_date": "20250317",
    "initial_cash": 100000000.0,
    "transaction_cost_bps": 0.0,
    "base_currency": "CNY"
  },
  "inputs": [
    {
      "kind": "transaction",
      "name": "cash_transfer_demo",
      "language": "delivery-transaction",
      "version": 1,
      "time_in_force": "day",
      "transactions": [
        {
          "security_type": "cash",
          "date": "20250305",
          "sec_uiq_code": "cash",
          "direction": "long",
          "channel": null,
          "trans_currency_cd": "CNY",
          "transact_amount": 5000000,
          "event_type": "credit",
          "transact_price": 1,
          "transact_time": "20250305 09:30:00"
        },
        {
          "security_type": "cash",
          "date": "20250310",
          "sec_uiq_code": "cash",
          "direction": "long",
          "channel": null,
          "trans_currency_cd": "CNY",
          "transact_amount": 2000000,
          "event_type": "debit",
          "transact_price": 1,
          "transact_time": "20250310 09:30:00"
        },
        {
          "security_type": "cash",
          "date": "20250312",
          "sec_uiq_code": "cash",
          "direction": "long",
          "channel": null,
          "trans_currency_cd": "CNY",
          "transact_amount": 300000,
          "event_type": "profit",
          "transact_price": 1,
          "transact_time": "20250312 09:30:00"
        }
      ]
    }
  ]
}
```

返回值示例：

```json
{
  "job_id": "<job_id>",
  "status": "completed",
  "output_dir": "/home/lzq/datayes/mercury-quant/runs/<job_id>",
  "summary": {
    "start_date": "20240102",
    "end_date": "20260320",
    "total_return": 0.3323944975669013,
    "annualized_return": 0.14531735349114072,
    "annualized_volatility": 0.1740859447924518,
    "sharpe": 0.8347448937614724,
    "max_drawdown": -0.1679177733263003,
    "win_rate": 0.5196998123827392,
    "total_turnover": 1.4990000518628213,
    "initial_unit_nav": 1000000.0,
    "final_unit_nav": 1332394.4975669014,
    "total_asset": 1332394.4975669014,
    "total_debt": 0.0,
    "total_trades": 42
  },
  "metrics": {
    "total_ms": 15,
    "build_requirement_ms": 0,
    "prepare_data_ms": 0,
    "load_execution_view_ms": 7,
    "cache_hit": true,
    "connect_ms": 0,
    "resolve_assets_ms": 0,
    "load_bars_ms": 0,
    "source_fetch_count": 0,
    "prepare_partition_count": 5,
    "load_partition_count": 5,
    "cache_write_count": 0,
    "backtest_ms": 5,
    "persist_ms": 1
  }
}
```

校验失败时返回 `400 Bad Request`，响应体形如：

```json
{
  "error": "bad_request",
  "message": "<校验失败原因>"
}
```

服务内部错误返回 `500 Internal Server Error`，响应体形如：

```json
{
  "error": "internal_error",
  "message": "<内部错误摘要>"
}
```

`order` 输入当前支持：

- 股票 / 基金委托：`security_type=stock|fund`
- 买卖方向：`side=buy|sell`
- 委托类型：`order_type=market|limit`
- TIF：`time_in_force=day|ioc|fok`
- 股票数量必须为整数；A 股路径会继续按交易规则做整手约束
- `order` 输入会进入订单状态机、成交和 `SettlementEngine`

`transaction` 输入当前支持三类事件：

- 股票交易：`security_type=stock`，`event_type=buy|sell`
- 基金交易：`security_type=fund`，`event_type=buy|sell`
- 现金事件：`security_type=cash`，`event_type=credit|debit|profit|loss`

股票交易说明：

- `transact_amount` 表示股数
- `transact_price` 可选；若省略，则回测内核按该交易日收盘价成交
- 若显式提供 `transact_price`，则按该价格成交
- 若省略价格且当日没有可用收盘价，任务会报错
- 所有输入金额（`transact_amount`、`transact_price`、`commission`、`settle_value`、`transact_value`）均为**绝对值**，方向由 `event_type` 隐含（buy=扣现金/加仓位，sell=加现金/减仓位）
- `commission` 可选；若省略且提供了 `settle_value`，则从 `|settle_value| - |transact_value|` 自动推导佣金
- `settle_value` 可选；结算金额，用于从结算价推导佣金

现金事件建议约定：

- `sec_uiq_code="cash"`
- `transact_amount` 表示现金金额，始终为正数
- `transact_price=1`
- `credit/debit` 影响现金和份额
- `profit/loss` 只影响现金，不影响份额

所有输入金额均为**绝对值**，方向由 `event_type` 隐含（credit/profit 为流入，debit/loss 为流出）。

## 5. 查询回测任务接口

| 项目 | 内容 |
| --- | --- |
| 名称 | 查询回测任务 `Get Backtest` |
| URL | `GET /api/v1/backtests/{job_id}` |
| 说明 | 根据 `job_id` 查询已执行任务的落盘结果。成功时返回任务元数据、请求体、摘要和指标；如果任务不存在，返回 404。 |

调用示例：

```bash
curl http://127.0.0.1:8080/api/v1/backtests/<job_id>
```

返回值示例：

```json
{
  "job_id": "<job_id>",
  "status": "completed",
  "output_dir": "/home/lzq/datayes/mercury-quant/runs/<job_id>",
  "run_spec": {
    "run": {
      "start_date": "20240102",
      "end_date": "20260320",
      "initial_cash": 1000000.0,
      "transaction_cost_bps": 5.0
    },
    "inputs": [
      {
        "kind": "strategy",
        "name": "weekly_equal_weight_cn_equity",
        "language": "python-restricted",
        "version": 1,
        "ops": [
          {
            "op": "load_universe",
            "assets": ["000001", "600000", "上海机场", "中国石油"]
          },
          {
            "op": "schedule",
            "schedule": "weekly"
          },
          {
            "op": "weight",
            "weighting": "equal"
          },
          {
            "op": "order_target_percent"
          }
        ]
      }
    ]
  },
  "execution_view": {
    "view_id": "c3f0756556fea3f6",
    "cache_hit": true
  },
  "summary": {
    "start_date": "20240102",
    "end_date": "20260320",
    "total_return": 0.3323944975669013,
    "annualized_return": 0.14531735349114072,
    "annualized_volatility": 0.1740859447924518,
    "sharpe": 0.8347448937614724,
    "max_drawdown": -0.1679177733263003,
    "win_rate": 0.5196998123827392,
    "total_turnover": 1.4990000518628213,
    "initial_unit_nav": 1000000.0,
    "final_unit_nav": 1332394.4975669014,
    "total_asset": 1332394.4975669014,
    "total_debt": 0.0,
    "total_trades": 42
  },
  "metrics": {
    "total_ms": 15,
    "build_requirement_ms": 0,
    "prepare_data_ms": 0,
    "load_execution_view_ms": 7,
    "cache_hit": true,
    "connect_ms": 0,
    "resolve_assets_ms": 0,
    "load_bars_ms": 0,
    "source_fetch_count": 0,
    "prepare_partition_count": 5,
    "load_partition_count": 5,
    "cache_write_count": 0,
    "backtest_ms": 5,
    "persist_ms": 1
  }
}
```

如果任务不存在，返回 `404 Not Found`：

```json
{
  "error": "not_found",
  "message": "job not found: <job_id>"
}
```

## 6. 任务返回里的字段说明

`summary` 是回测结果摘要，常见字段包括：

- `start_date`：回测起始日期
- `end_date`：回测结束日期
- `trading_days`：实际交易日数量
- `initial_unit_nav`：初始单位净值（= 1.0）
- `final_unit_nav`：期末单位净值
- `total_asset`：期末总资产（元）
- `total_debt`：期末总负债（元，默认为 0）
- `total_return`：总收益率（= final_unit_nav / initial_unit_nav - 1）
- `annualized_return`：年化收益率
- `annualized_volatility`：年化波动率
- `sharpe`：夏普比率
- `max_drawdown`：最大回撤（基于单位净值序列）
- `win_rate`：日胜率
- `total_turnover`：总换手率
- `total_trades`：总成交笔数

`metrics` 是执行过程耗时：

- `build_requirement_ms`：`DataRequirement` 构建耗时
- `prepare_data_ms`：source -> cache -> execution view 准备耗时
- `load_execution_view_ms`：execution view 加载耗时
- `cache_hit`：本次任务是否命中缓存
- `connect_ms`：数据库连接耗时
- `resolve_assets_ms`：标的解析耗时
- `load_bars_ms`：行情加载耗时
- `source_fetch_count`：数据源查询次数
- `prepare_partition_count`：数据分区准备数量
- `load_partition_count`：数据分区加载数量
- `cache_write_count`：缓存写入次数
- `backtest_ms`：回测计算耗时
- `persist_ms`：结果落盘耗时
- `total_ms`：总耗时

## 7. 当前边界与后续演进

当前文档列出的接口，就是项目目前全部对外 HTTP 接口。

当前实现边界：

- `POST /api/v1/backtests` 仍然是同步执行链路
  服务会在同一条请求链路里完成 `DataRequirement -> cache / execution view -> 回测 -> 落盘`
- `GET /api/v1/backtests/{job_id}` 当前读取的是本地落盘任务元数据
  还不是独立的 metadata store
- `runs/<job_id>/` 下的结果来自当前最小 runner
  能用于联调和单机部署，但不代表最终平台化形态已经收敛
- `cache/` 当前只保留共享 Parquet 数据文件
  任务级 manifest 写在 `runs/<job_id>/summary.json`
- 共享 cache 当前采用 `instrument` 单文件和 `asset_class + 时间分区 + chunk` 的目录组织
  例如 `daily_bar/asset_class=E/frequency=daily/year=2025/chunk-000.parquet`

下一阶段的目标方向：

- 控制面先生成 `DataRequirement`
- `data-prep-worker` 负责 `source -> Parquet cache -> execution view`
- runner 只读取 execution view
- HTTP 接口演进为真正的异步 job API

相关但不属于 HTTP 数据接口的入口：

- [python/scripts/compile_strategy.py](../python/scripts/compile_strategy.py)
  把受限 Python 策略编译成 `RunSpec + Strategy IR`
- [skills/mercury-trade-replay-local/README.md](../skills/mercury-trade-replay-local/README.md)
  本地 agent skill 的安装、导出和 CLI 调用说明
- [skills/mercury-trade-replay-http/README.md](../skills/mercury-trade-replay-http/README.md)
  HTTP agent skill 的 `curl` 调用说明
- [etc/app.cfg](../etc/app.cfg)
  服务端开发路径使用的 MySQL 配置文件；本地安装包会生成用户级 `<MERCURY_QUANT_HOME>/db.cfg`

## 附录：curl 联调流程示例

下面是一套本地联调流程，覆盖：

- 服务健康检查
- 提交 `strategy` / `order` / `transaction` 回测任务
- 基于 `job_id` 查询结果并提取关键指标

附录只保留“流程步骤”。
请求参数、字段含义和完整示例请优先参考：

- [第 4 节：创建回测任务接口](#4-创建回测任务接口)（`POST /api/v1/backtests`）
- [第 5 节：查询回测任务接口](#5-查询回测任务接口)（`GET /api/v1/backtests/{job_id}`）

默认服务地址：`http://127.0.0.1:8080`

### A.0 准备变量

```bash
BASE_URL="http://127.0.0.1:8080"
```

### A.1 健康检查

```bash
curl -sS "$BASE_URL/healthz"
curl -sS "$BASE_URL/readyz"
```

### A.2 准备请求体

按 [第 4 节：创建回测任务接口](#4-创建回测任务接口) 的示例准备 `RunSpec`，构建 json 字符串。

- 在 `inputs[]` 中任选一个交易生产输入：`strategy`、`order` 或 `transaction`
- 本附录不重复展开参数字段

### A.3 创建回测任务

```bash
curl -X POST "$BASE_URL/api/v1/backtests" \
  -H "Content-Type: application/json" \
  --data '<json-body>'
```

### A.4 提取 job_id

从创建回测任务接口的返回数据中提取 `job_id` 。

### A.5 查询任务结果

```bash
curl "$BASE_URL/api/v1/backtests/$job_id"
```

### A.6 提取关键结果字段

```bash
jq '{
  summary: {
    final_unit_nav,
    total_asset,
    total_return,
    annualized_return,
    max_drawdown,
    trading_days
  },
  metrics: {
    total_ms,
    cache_hit,
    backtest_ms
  }
}' /tmp/backtest_get_resp.json
```

### A.7 常见错误排查

- `400` 且提示 `Failed to parse the request body as JSON`：通常是请求体为空或 JSON 格式错误
- `404`：`job_id` 不存在，或查询了错误环境（例如端口/地址不一致）
- `503`：服务未就绪，先检查 `/readyz` 和挂载目录、配置文件路径
