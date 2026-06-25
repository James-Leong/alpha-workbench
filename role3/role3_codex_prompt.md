# Codex Task Prompt: Implement Role3 Idea Agent in `role3/` Only

你是一个资深 Python 工程师与量化金融系统开发者。请根据本 Prompt 在当前仓库中实现 Role3：研报解析与 Idea Agent 模块。注意：本次任务只允许修改或新增 `role3/` 文件夹内的文件，暂时不要嵌入 AlphaWorkbench 主流程，不要修改 `alpha_workbench/`、`app/`、`workflows/`、`README.md` 等全局文件。

## 1. 背景

AlphaWorkbench 是一个研报驱动的人机协同量化因子研究平台。Role3 的职责是将自然语言投资想法或研报 PDF 文本提炼为结构化 `IdeaSpec`，为后续 ResearchSpec、FactorSpec、回测和审计模块提供稳定输入。

Role3 不是普通文本摘要模块，而是金融投研语义抽取模块。它需要把输入文本转化为可检验、可编辑、可追踪、可审计的投资思想结构。

## 2. 本次实现边界

只在 `role3/` 目录内开发。

允许新增或修改：

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
  tests/
```

禁止修改：

```text
alpha_workbench/
docs/
README.md
scripts/
tests/   # 根目录 tests 暂时不动，Role3 测试放在 role3/tests/
```

禁止把 Role3 接入主流程。不要修改 Streamlit UI，不要修改全局 workflow，不要修改主包 agent 入口。

## 3. 对外固定接口

必须保留并实现以下函数签名：

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

参数含义：

- `input_text`：原始输入内容，可以是自然语言投资想法，也可以是 PDF 文件路径字符串。
- `source_meta`：来源元信息，默认可以省略。
- `api_url`：模型调用地址，只在 Role3 内部使用。
- `token`：认证 token，只在 Role3 内部使用。

无论真实模型是否可用，函数都必须返回固定 envelope，不允许直接抛出异常给调用方。

## 4. 固定输出 Envelope

`extract_idea()` 必须返回 JSON-compatible dict，结构如下：

```python
{
    "idea_spec": {
        "idea_id": str,
        "idea_name": str,
        "core_hypothesis": str,
        "economic_mechanism": list[str],
        "required_data_concepts": list[str],
        "risk_flags": list[str],
        "evidence": list[str],
        "summary": str,
        "factor_directions": list[str],
        "uncertainties": list[str],
        "suggested_research_spec": dict
    },
    "is_mock": bool,
    "is_fallback": bool,
    "source_meta": dict,
    "raw_model_response": object,
    "missing_fields": list[str]
}
```

`idea_spec` 内部字段可以后续扩展，但以上字段必须保证存在。缺失时使用默认值并记录到 `missing_fields`。

## 5. 金融语义要求

Role3 需要从输入中提炼以下金融研究信息：

1. 核心投资假设  
   例如：单季度盈利超预期且公告前价格未充分反应的公司，未来可能获得相对超额收益。

2. 经济机制  
   例如：
   - 盈利公告形成基本面信息冲击
   - 分析师盈利预测可能发生上修
   - 投资者对业绩改善存在反应不足
   - 公告前价格未充分上涨意味着预期尚未完全反映

3. 所需数据概念  
   例如：
   - 实际单季度净利润
   - 市场一致预期净利润
   - 财报公告日
   - 公告前 20 个交易日收益率
   - 未来持有期收益率
   - 行业分类
   - 市值

4. 风险与不确定性  
   例如：
   - 财报公告日处理不当可能产生未来函数
   - 一致预期数据可能不可得，需要使用 proxy 字段
   - 公告前收益率窗口必须严格早于公告日
   - 行业和市值暴露可能造成伪 alpha
   - 单季度利润可能受非经常性损益影响

5. 证据片段  
   对自然语言输入，至少把原始输入的关键片段放入 `evidence`。  
   对 PDF 输入，尽量返回抽取文本中的关键段落；如果当前只实现简单 PDF 解析，也可以返回截断后的文本片段。

6. 后续因子方向  
   `factor_directions` 给 Role4 使用，例如：
   - 盈利超预期强度
   - 公告前价格反应调整
   - 盈利预测修正强度
   - 行业中性化后的盈利冲击

禁止输出确定性收益承诺，禁止生成实盘交易建议。应使用“可能”“有待回测验证”“潜在”等谨慎表述。

## 6. 推荐文件职责

### 6.1 `role3/fallback.py`

实现：

```python
def mock_idea_spec(input_text: str, source_meta: dict | None = None) -> dict:
    ...
```

要求：

- 返回固定 envelope。
- 默认主题使用“盈利超预期与预期修正”。
- `is_mock=True`
- `is_fallback=False`
- `raw_model_response=None`
- `missing_fields=[]`

### 6.2 `role3/validators.py`

实现：

```python
REQUIRED_IDEA_FIELDS = [...]

def validate_idea_spec(idea_spec: dict) -> tuple[dict, list[str]]:
    ...
```

要求：

- 检查必填字段。
- 缺失字段用默认值补齐。
- 字符串列表字段如果模型返回字符串，需要自动包成 list。
- `suggested_research_spec` 缺失时补默认研究设置。
- 返回补齐后的 `idea_spec` 和 `missing_fields`。

### 6.3 `role3/finance_taxonomy.py`

实现一个金融概念映射词表，例如：

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
    ...
}
```

可实现辅助函数：

```python
def infer_finance_concepts(text: str) -> dict:
    ...
```

要求：

- 根据关键词命中返回标准概念、建议数据字段、风险标记。
- 不需要复杂 NLP，规则匹配即可。
- 不要依赖外部服务。

### 6.4 `role3/prompt_templates.py`

实现：

```python
def build_idea_extraction_prompt(input_text: str, source_meta: dict | None = None) -> str:
    ...
```

Prompt 要求：

- 明确要求模型只输出 JSON。
- 要求输出 `idea_spec`。
- 要求包含核心假设、经济机制、所需数据、风险提示、证据、总结、因子方向、不确定性。
- 明确禁止实盘交易建议和收益承诺。
- 加入金融投研语义抽取要求，而不是普通摘要要求。

### 6.5 `role3/pdf_parser.py`

实现：

```python
def maybe_parse_pdf(input_text: str, source_meta: dict | None = None) -> tuple[str, dict]:
    ...
```

要求：

- 如果 `source_meta.source_type == "pdf"` 或 `input_text` 以 `.pdf` 结尾，则尝试解析 PDF。
- 优先使用可选依赖 `pymupdf` 或 `pypdf`。如果依赖不存在，不要报错中断，返回原始路径字符串并在 `source_meta` 中标注 `pdf_parse_error`。
- 当前阶段只做轻量文本抽取，不做 OCR。
- 不要引入重型依赖。

### 6.6 `role3/huawei_api.py`

保留或轻量完善现有模型调用函数。建议接口：

```python
def call_huawei_model(prompt: str, api_url: str, token: str) -> object:
    ...
```

要求：

- 不要硬编码 token。
- token 从参数或环境变量读取。
- API 报错时向上抛出异常，由 `idea_extractor.py` fallback。
- 不要打印敏感 token。

### 6.7 `role3/idea_extractor.py`

实现主入口：

```python
def extract_idea(...):
    ...
```

建议逻辑：

```text
normalize source_meta
→ maybe_parse_pdf
→ 如果没有 api_url 或 token，返回 mock_idea_spec
→ build prompt
→ call model
→ parse raw response
→ validate idea_spec
→ build envelope
→ 如果任一步失败，fallback 到 mock，并标注 is_fallback=True
```

需要实现稳健的 JSON 解析：

- raw response 可能是 dict
- raw response 可能是 JSON 字符串
- raw response 可能包在 Markdown code fence 中
- raw response 可能外层直接是 idea_spec，而不是 {"idea_spec": ...}

### 6.8 `role3/workflow.py`

实现：

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
    "idea_result": extract_idea(...),
    "workflow_meta": {
        "agent": "IdeaExtractionAgent",
        "version": "0.1.0",
        "scope": "role3_only"
    }
}
```

如果 Agno 可用，可以轻量包装；如果 Agno 不可用，普通 Python workflow 即可。不要让 Agno 成为运行 Role3 的硬依赖。

### 6.9 `role3/run_role3_huawei.py`

实现一个 CLI 示例：

```bash
python role3/run_role3_huawei.py --input "单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。"
```

可选参数：

```bash
--url
--token
--source-type text/pdf
```

要求：

- 如果不传 token，尝试读取环境变量 `HUAWEI_TOKEN`。
- 输出 JSON，便于调试。
- 不要打印 token。

## 7. 单元测试

在 `role3/tests/` 下新增测试。

至少包括：

```text
test_mock_path.py
test_validator.py
test_response_parser.py
test_workflow.py
```

测试要求：

1. 不传 api_url/token 时，`extract_idea()` 返回 mock envelope。
2. mock envelope 必须包含所有固定外层字段。
3. `idea_spec` 必须包含所有必填字段。
4. `validate_idea_spec()` 能补齐缺失字段。
5. 模型返回 JSON 字符串时可解析。
6. 模型返回 Markdown code fence 中的 JSON 时可解析。
7. workflow 返回 `workflow_mode`、`idea_result`。
8. API 异常时 `is_fallback=True`。

不要让测试依赖真实网络或真实模型 API。

## 8. 代码质量要求

- Python 代码使用类型标注。
- 不要引入复杂依赖。
- 不要提交 token、密钥或本地绝对路径。
- 不要在模块导入时调用 API。
- 所有外部调用必须在函数内部发生。
- 所有返回都必须 JSON-compatible。
- 失败时返回 fallback，不要让 UI 或调用方崩溃。
- 保持函数边界清晰，方便后续迁移回 `alpha_workbench/` 主包。

## 9. 验收标准

完成后应满足：

```bash
python role3/run_role3_huawei.py --input "单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。"
```

在没有模型 URL 和 token 的情况下，也能输出稳定 JSON：

```json
{
  "workflow_mode": "role3_idea_extraction",
  "idea_result": {
    "idea_spec": {
      "idea_id": "earnings_surprise_revision",
      "idea_name": "盈利超预期与预期修正",
      ...
    },
    "is_mock": true,
    "is_fallback": false,
    ...
  }
}
```

运行 Role3 测试应通过：

```bash
python -m pytest role3/tests
```

## 10. 特别注意

本次任务不是完整接入 AlphaWorkbench，而是把 Role3 做成一个独立、可测试、可 fallback 的子模块。请只在 `role3/` 文件夹内完成实现，不要动主流程。
