# Role3 Idea Agent 开发说明

## 1. 模块定位

Role3 是 AlphaWorkbench 中的“研报解析与 Idea Agent”模块，负责把自然语言投资想法或研报 PDF 文本转化为结构化 `IdeaSpec`。

本阶段 Role3 只在 `role3/` 文件夹内独立开发，不嵌入主流程，不修改 Streamlit UI，不修改 `alpha_workbench/` 主包，不影响其他同学模块。

Role3 的核心不是文本摘要，而是金融投研语义抽取。它需要从输入内容中识别：

- 投资假设
- 经济机制
- 所需数据概念
- 未来函数与数据风险
- 证据片段
- 后续因子构造方向

最终输出必须是稳定 JSON envelope，以便后续 Role4、Role5、Role6 可以读取。

---

## 2. 开发边界

### 允许修改

```text
role3/
```

建议文件结构：

```text
role3/
  __init__.py
  idea_extractor.py
  workflow.py
  prompt_templates.py
  validators.py
  fallback.py
  finance_taxonomy.py
  pdf_parser.py
  huawei_api.py
  run_role3_huawei.py
  examples/
    sample_input_text.txt
    sample_idea_spec.json
  tests/
    test_mock_path.py
    test_validator.py
    test_response_parser.py
    test_workflow.py
```

### 暂时不要修改

```text
alpha_workbench/
docs/
README.md
scripts/
app/
workflows/
```

### 暂时不要做

- 不接入主流程
- 不接入 Streamlit UI
- 不修改全局 workflow
- 不修改主包 agent
- 不引入重型依赖
- 不依赖真实网络完成测试

---

## 3. 固定对外接口

Role3 对外入口固定为：

```python
def extract_idea(
    input_text: str,
    source_meta: dict | None = None,
    *,
    api_url: str | None = None,
    token: str | None = None
) -> dict:
    ...
```

参数说明：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `input_text` | `str` | 原始输入内容，可以是自然语言文本，也可以是 PDF 文件路径 |
| `source_meta` | `dict | None` | 来源元信息，例如 `{"source_type": "text"}` 或 `{"source_type": "pdf"}` |
| `api_url` | `str | None` | 模型调用地址，仅在 Role3 内部使用 |
| `token` | `str | None` | 模型认证 token，仅在 Role3 内部使用 |

要求：

- 函数必须始终返回 dict。
- 任何异常都应 fallback，不应直接抛给调用方。
- 不传 `api_url` 或 `token` 时，返回 mock 结果。
- 返回结构必须稳定。

---

## 4. 固定输出结构

Role3 输出采用“外层 envelope + 内层 idea_spec”的结构。

```python
{
    "idea_spec": {
        "idea_id": "earnings_surprise_revision",
        "idea_name": "盈利超预期与预期修正",
        "core_hypothesis": "单季度盈利超预期且公告前股价未充分反应的公司，未来可能获得相对超额收益。",
        "economic_mechanism": [
            "盈利公告带来基本面信息冲击",
            "市场对业绩改善可能存在反应不足",
            "分析师预期可能随业绩披露发生修正"
        ],
        "required_data_concepts": [
            "实际单季度净利润",
            "市场一致预期净利润",
            "财报公告日",
            "公告前20日收益率",
            "未来持有期收益率"
        ],
        "risk_flags": [
            "公告日处理不当可能产生未来函数",
            "一致预期数据可能不可得",
            "公告前收益率窗口需要严格滞后",
            "行业和市值暴露可能影响回测解释"
        ],
        "evidence": [
            "用户原始输入或研报关键片段"
        ],
        "summary": "基于盈利超预期和公告前价格反应不足构建的基本面选股假设。",
        "factor_directions": [
            "盈利超预期强度",
            "公告前价格反应调整",
            "盈利预测修正强度",
            "行业中性化后的盈利冲击"
        ],
        "uncertainties": [
            "市场一致预期数据口径未明确",
            "公告日与可交易日之间存在时点差异"
        ],
        "suggested_research_spec": {
            "universe": "CSI500_or_sample_universe",
            "rebalance_frequency": "monthly",
            "holding_period": 20,
            "transaction_cost_bps": 20,
            "groups": 5
        }
    },
    "is_mock": true,
    "is_fallback": false,
    "source_meta": {
        "source_type": "text"
    },
    "raw_model_response": null,
    "missing_fields": []
}
```

外层字段必须固定：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `idea_spec` | `dict` | 核心投资思想结构 |
| `is_mock` | `bool` | 是否为 mock 输出 |
| `is_fallback` | `bool` | 是否由异常回退产生 |
| `source_meta` | `dict` | 来源元信息 |
| `raw_model_response` | `object` | 模型原始返回或错误信息 |
| `missing_fields` | `list[str]` | 模型输出缺失字段 |

---

## 5. 金融语义抽取要求

Role3 需要把模糊的投资想法转化为可回测假设。

示例输入：

```text
单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。
```

Role3 应抽取为：

### 5.1 核心假设

```text
单季度盈利超预期且公告前价格未充分反应的公司，未来可能获得相对超额收益。
```

### 5.2 经济机制

```text
盈利公告带来基本面信息冲击；
市场对业绩改善可能存在反应不足；
分析师盈利预测可能发生上修；
公告前价格未充分上涨意味着预期尚未完全反映。
```

### 5.3 所需数据

```text
实际单季度净利润；
市场一致预期净利润；
财报公告日；
公告前 20 个交易日收益率；
未来持有期收益率；
行业分类；
市值。
```

### 5.4 风险提示

```text
财报公告日处理不当可能产生未来函数；
一致预期数据可能不可得，需要使用 proxy 字段；
公告前收益率窗口必须严格早于公告日；
行业和市值暴露可能造成伪 alpha；
单季度利润可能受非经常性损益影响。
```

### 5.5 因子方向

```text
盈利超预期强度；
公告前价格反应调整；
盈利预测修正强度；
行业中性化后的盈利冲击。
```

注意：Role3 不能输出确定性收益承诺，不能生成实盘交易建议。表达应保持研究假设口径，例如“可能”“潜在”“有待回测验证”。

---

## 6. 文件实现说明

### 6.1 `fallback.py`

职责：提供稳定 mock 输出。

建议实现：

```python
def mock_idea_spec(input_text: str, source_meta: dict | None = None) -> dict:
    ...
```

要求：

- 不调用外部模型。
- 返回固定 envelope。
- 默认主题为“盈利超预期与预期修正”。
- 把输入文本截断后放入 `evidence`。
- `is_mock=True`
- `is_fallback=False`

---

### 6.2 `validators.py`

职责：校验并补齐 `idea_spec`。

建议常量：

```python
REQUIRED_IDEA_FIELDS = [
    "idea_id",
    "idea_name",
    "core_hypothesis",
    "economic_mechanism",
    "required_data_concepts",
    "risk_flags",
    "evidence",
    "summary",
    "factor_directions",
    "uncertainties",
    "suggested_research_spec",
]
```

建议函数：

```python
def validate_idea_spec(idea_spec: dict) -> tuple[dict, list[str]]:
    ...
```

要求：

- 缺字段时补默认值。
- 字符串字段误返回为 list 时可转为字符串。
- list 字段误返回为字符串时包成 list。
- `missing_fields` 记录被补齐的字段。
- 不直接抛异常给上游。

---

### 6.3 `finance_taxonomy.py`

职责：提供简单金融概念词表与规则识别。

建议实现：

```python
FINANCE_CONCEPT_MAP = {
    "盈利超预期": {
        "canonical_name": "earnings_surprise",
        "required_fields": [
            "actual_quarterly_profit",
            "expected_quarterly_profit",
            "announcement_date"
        ],
        "risk_flags": [
            "expectation_data_unavailable",
            "announcement_date_lookahead"
        ]
    },
    "公告前股价没有明显上涨": {
        "canonical_name": "pre_announcement_price_reaction",
        "required_fields": [
            "pre_announcement_return_20d",
            "announcement_date"
        ],
        "risk_flags": [
            "window_must_end_before_announcement"
        ]
    },
    "盈利预测修正": {
        "canonical_name": "earnings_forecast_revision",
        "required_fields": [
            "analyst_forecast_before",
            "analyst_forecast_after"
        ],
        "risk_flags": [
            "analyst_forecast_timestamp_required"
        ]
    }
}
```

可选函数：

```python
def infer_finance_concepts(text: str) -> dict:
    ...
```

要求：

- 使用规则匹配即可。
- 不需要复杂机器学习。
- 用于增强 mock、prompt 或 fallback 结果。
- 保持可解释。

---

### 6.4 `prompt_templates.py`

职责：构造 Idea Extraction Prompt。

建议函数：

```python
def build_idea_extraction_prompt(input_text: str, source_meta: dict | None = None) -> str:
    ...
```

Prompt 内容必须要求：

- 只输出 JSON。
- 输出外层包含 `idea_spec`。
- 不要输出 Markdown。
- 不要输出代码块。
- 不给实盘交易建议。
- 不承诺收益。
- 明确标注数据需求、风险、不确定性和证据。
- 以金融投研语义抽取为目标，而不是摘要。

---

### 6.5 `pdf_parser.py`

职责：轻量 PDF 文本抽取。

建议函数：

```python
def maybe_parse_pdf(input_text: str, source_meta: dict | None = None) -> tuple[str, dict]:
    ...
```

要求：

- 如果 `source_meta["source_type"] == "pdf"` 或输入以 `.pdf` 结尾，则尝试解析。
- 优先尝试 `pymupdf` 或 `pypdf`。
- 如果没有依赖或解析失败，不中断流程。
- 解析失败时返回原始 `input_text`，并在 `source_meta` 中写入 `pdf_parse_error`。
- 当前阶段不做 OCR。

---

### 6.6 `huawei_api.py`

职责：封装模型调用。

建议函数：

```python
def call_huawei_model(prompt: str, api_url: str, token: str) -> object:
    ...
```

要求：

- 不硬编码 token。
- 不打印 token。
- API 错误向上抛出，由 `idea_extractor.py` 统一 fallback。
- 可以使用 `requests`，但要设置 timeout。
- 返回原始响应对象或 JSON。

---

### 6.7 `idea_extractor.py`

职责：实现主入口 `extract_idea()`。

推荐流程：

```text
1. 标准化 source_meta
2. 调用 maybe_parse_pdf
3. 如果没有 api_url 或 token，返回 mock_idea_spec
4. 构造 prompt
5. 调用模型
6. 解析模型返回
7. 校验 idea_spec
8. 返回固定 envelope
9. 若任一步异常，fallback 到 mock，并标注 is_fallback=True
```

需要实现稳健响应解析：

```python
def parse_model_response(raw_response: object) -> dict:
    ...
```

需支持：

- raw response 是 dict
- raw response 是 JSON 字符串
- raw response 是 Markdown code fence 包裹的 JSON
- raw response 外层直接是 idea_spec
- raw response 外层是 `{"idea_spec": ...}`

---

### 6.8 `workflow.py`

职责：Role3 独立 workflow。

建议函数：

```python
def run_role3_workflow(
    input_text: str,
    source_meta: dict | None = None,
    api_url: str | None = None,
    token: str | None = None
) -> dict:
    ...
```

返回：

```python
{
    "workflow_mode": "role3_idea_extraction",
    "input_text": input_text,
    "source_meta": source_meta,
    "idea_result": {...},
    "workflow_meta": {
        "agent": "IdeaExtractionAgent",
        "version": "0.1.0",
        "scope": "role3_only"
    }
}
```

要求：

- Agno 可用时可以轻量包装。
- Agno 不可用时普通 Python 实现即可。
- 不要让 Agno 成为硬依赖。
- 不接入主流程。

---

### 6.9 `run_role3_huawei.py`

职责：CLI 调试入口。

推荐命令：

```bash
python role3/run_role3_huawei.py --input "单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。"
```

可选参数：

```bash
--url
--token
--source-type text
--source-type pdf
```

要求：

- 如果不传 `--token`，尝试读取环境变量 `HUAWEI_TOKEN`。
- 输出 JSON。
- 不打印 token。
- 不要求真实 API 才能运行；无 API 时应输出 mock。

---

## 7. 错误处理策略

Role3 的错误处理原则：

```text
外部 API 失败 → fallback mock
模型返回格式错误 → fallback mock
PDF 解析失败 → 保留原输入，继续流程
字段缺失 → validators 补齐，记录 missing_fields
token 缺失 → mock，不报错
api_url 缺失 → mock，不报错
```

fallback 返回时：

```python
result["is_fallback"] = True
result["raw_model_response"] = {"error": str(error)}
```

---

## 8. 单元测试要求

测试放在：

```text
role3/tests/
```

至少覆盖：

### 8.1 Mock 路径

```python
def test_extract_idea_without_api_returns_mock():
    ...
```

检查：

- 返回 dict
- 有 `idea_spec`
- `is_mock=True`
- `is_fallback=False`
- 外层字段完整

### 8.2 Validator

```python
def test_validate_idea_spec_fill_missing_fields():
    ...
```

检查：

- 缺失字段被补齐
- `missing_fields` 正确记录
- list 字段类型正确

### 8.3 模型响应解析

```python
def test_parse_model_response_json_string():
    ...

def test_parse_model_response_markdown_code_fence():
    ...
```

检查：

- JSON 字符串可解析
- Markdown code fence 可解析
- 直接返回 idea_spec 时可包成 envelope

### 8.4 Workflow

```python
def test_run_role3_workflow():
    ...
```

检查：

- 有 `workflow_mode`
- 有 `idea_result`
- `workflow_meta.scope == "role3_only"`

### 8.5 Fallback

```python
def test_extract_idea_api_error_fallback(monkeypatch):
    ...
```

检查：

- 模拟 API 报错
- `is_fallback=True`
- 仍返回完整 envelope

测试不得依赖真实网络或真实模型 API。

---

## 9. 验收命令

无 API 情况下应可运行：

```bash
python role3/run_role3_huawei.py --input "单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。"
```

预期输出包含：

```json
{
  "workflow_mode": "role3_idea_extraction",
  "idea_result": {
    "idea_spec": {
      "idea_id": "earnings_surprise_revision",
      "idea_name": "盈利超预期与预期修正"
    },
    "is_mock": true,
    "is_fallback": false
  }
}
```

测试命令：

```bash
python -m pytest role3/tests
```

---

## 10. 迁移预留

本阶段不接入总流程，但代码设计要方便后续迁移。

后续可迁移路径：

```text
role3/idea_extractor.py
→ alpha_workbench/agents/idea_extractor.py

role3/pdf_parser.py
→ alpha_workbench/parsers/pdf_parser.py

role3/workflow.py
→ alpha_workbench/workflows/role3_workflow.py

role3/tests/
→ tests/test_role3_*.py
```

迁移前不要改变接口结构：

```python
extract_idea(input_text, source_meta=None, *, api_url=None, token=None) -> dict
```

---

## 11. 最小完成标准

本阶段 Role3 完成标准：

- `extract_idea()` 可独立运行。
- 没有模型 API 时返回稳定 mock。
- 有模型 API 时尝试调用并解析。
- 调用失败时 fallback。
- 输出 envelope 结构固定。
- `idea_spec` 字段完整。
- 支持轻量 PDF 路径识别。
- 有基础单元测试。
- CLI 可打印 workflow trace。
- 所有修改限定在 `role3/` 文件夹内。

---

## 12. Codex 执行建议

建议 Codex 按以下顺序实现：

1. 创建或整理 `role3/fallback.py`
2. 创建 `role3/validators.py`
3. 创建 `role3/finance_taxonomy.py`
4. 创建 `role3/prompt_templates.py`
5. 创建或完善 `role3/pdf_parser.py`
6. 完善 `role3/huawei_api.py`
7. 重写或完善 `role3/idea_extractor.py`
8. 完善 `role3/workflow.py`
9. 完善 `role3/run_role3_huawei.py`
10. 添加 `role3/tests/`
11. 运行 `python -m pytest role3/tests`
12. 确认没有修改 `role3/` 以外文件

本阶段目标是独立、稳定、可测试，而不是完整系统集成。
