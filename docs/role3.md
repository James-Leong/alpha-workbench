# Role3 开发进度（Idea Agent）

更新日期：2026-06-14

概述：Role3 负责研报解析与 IdeaSpec 提取。为便于独立开发，已在仓库根创建 `role3/` 包，相关功能将来再迁移回主包 `alpha_workbench/`。

已完成

- 阅读并理解 `docs/team_work_plan.md` 中 Role3 的职责与接口要求。

- 在仓库根创建 `role3/` 开发包并添加：
  - `role3/idea_extractor.py` （尝试调用华为模型，失败回退到 mock）
  - `role3/huawei_api.py` （开发用的 Huawei helper）
  - `role3/workflow.py` （基于 Agno 的 Role 3 工作流包装）
  - `role3/run_role3_huawei.py` （可执行示例脚本）
- 添加了全局示例脚本：`scripts/run_role3_huawei.py`（演示如何使用 `alpha_workbench/agents/huawei_api.py`）
- 现在 `role3/run_role3_huawei.py` 已切换为运行 Agno workflow，CLI 输出的是稳定 trace。

待办（建议优先级）

1. 在本地运行并验证示例脚本（`role3/run_role3_huawei.py` 或 `scripts/run_role3_huawei.py`），确保能正确处理模型返回与错误回退。
2. 为 `role3` 增加单元测试，覆盖：mock 路径、API 返回解析、异常回退。
3. 按需把 `alpha_workbench/agents/idea_extractor.py` 暂时切换为调用 `role3.extract_idea()`（带回退），并运行集成测试。
4. 撰写迁移文档 `docs/role3_integration.md`，说明如何将 role3 功能逐步迁移回 `alpha_workbench/`（接口、测试、部署注意事项）。
5. 提交 feature 分支（建议 `feature/role3`）并创建 PR，标注安全提示（不要提交 token）。

运行示例（在仓库根目录）

PowerShell:
```
$env:HUAWEI_TOKEN="<your_token>"
python .\role3\run_role3_huawei.py --url "https://<模型调用URL>" --input "一句投资想法"
```

cmd:
```
set HUAWEI_TOKEN=<your_token>
python role3\run_role3_huawei.py --url "https://<模型调用URL>" --input "一句投资想法"
```

安全与注意事项

- 不要把 token 或敏感凭据提交到仓库；建议使用环境变量或安全凭据管理。  
- 若在公司网络或防火墙下，确认能访问模型调用 URL。  
- 模型返回格式可能不一致，请根据实际 API 文档调整 `payload` 与解析逻辑。

联系人 / 下一步

- 如果你需要，我可以：
  - 现在运行一次本地验证（需要提供模型 URL 或确认可访问公网）；
  - 添加单元测试和 CI 步骤；
  - 将 `idea_extractor` 的调用路径在主包中做成可选切换并提交 PR。

## 固定输入与输出规范

为保证各模块并行开发，Role3 的输入与输出从现在开始固定。后续只允许修改中间处理逻辑，不允许改动输入参数名、返回字段名和返回结构层级。

### 输入（Input）
- **固定函数签名**：`extract_idea(input_text: str, source_meta: dict|None = None, *, api_url: str|None = None, token: str|None = None) -> dict`
- **参数名固定**：
  - `input_text`：原始输入内容，字符串。
  - `source_meta`：来源元信息字典，默认可省略。
  - `api_url`：模型调用地址，仅用于中间处理层。
  - `token`：认证 token，仅用于中间处理层。
- **输入内容类型**：自然语言文本（字符串）或 PDF 文件路径（字符串）。
- **示例 1（纯文本）**：

```json
"单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。"
```

- **示例 2（PDF 路径）**：

```json
"/path/to/report.pdf"
```

- **可选的 source_meta**：

```json
{"source_type": "text"}  // 或 {"source_type": "pdf", "pages": [1,2]}
```

### 输出（Output — 固定 Envelope）
- **类型**：JSON 兼容的 Python dict，固定为“外层 envelope + 内层 `idea_spec`”结构。
- **外层固定字段**：
  - `idea_spec`：核心 IdeaSpec 对象，dict。
  - `is_mock`：是否为 mock 输出，bool。
  - `is_fallback`：是否为回退输出，bool。
  - `source_meta`：原样返回的来源元信息，dict。
  - `raw_model_response`：模型原始响应或解析前响应，任何类型。
  - `missing_fields`：可选，模型返回缺失字段列表，list[str]。

- **内层 `idea_spec` 字段**（暂不强制固定，仅作为当前推荐字段）：
  - `idea_id` (str)
  - `idea_name` (str)
  - `core_hypothesis` (str)
  - `economic_mechanism` (list[str])
  - `required_data_concepts` (list[str])
  - `risk_flags` (list[str])
  - `evidence` (list[str])
  - `summary` (str)

- **说明**：后续如果角色 3 需要在中间处理阶段增加或减少 `idea_spec` 字段，可以调整模型输出和解析逻辑，但不要改动外层 envelope 的字段名和结构层级。

- **示例输出**：

```json
{
  "idea_spec": {
    "idea_id": "earnings_surprise_revision",
    "idea_name": "盈利超预期与预期修正",
    "core_hypothesis": "单季度盈利超预期且公告前无明显股价反应可能产生后续超额收益",
    "economic_mechanism": ["信息冲击", "分析师预期修正", "投资者反应滞后"],
    "required_data_concepts": ["实际盈利", "市场预期盈利", "财报公告日", "公告前价格反应"],
    "risk_flags": ["未来函数：公告日处理不当", "一致预期数据缺失"],
    "evidence": ["公司财报第3页盈利数据段落", "公告前20日价格无明显异常"],
    "summary": "基于盈利超预期并且公告前无明显价格反应的选股假设。"
  },
  "is_mock": false,
  "is_fallback": false,
  "source_meta": {"source_type": "text"},
  "raw_model_response": {"...": "..."}
}
```

### 兼容与注意事项
- 模型返回需严格校验外层 envelope 结构；内层 `idea_spec` 字段可随实现阶段调整。
- 若缺少推荐字段，可返回 `missing_fields` 键或使用默认值，避免让 UI 崩溃。
- 外部调用失败时返回固定 envelope，并在返回中标注 `is_fallback: true`。
- 若输入为 PDF，建议先在前端或 `parsers/pdf_parser.py` 中做文本抽取并传入文本以获得更稳定的结果。

相关实现：`role3/idea_extractor.py`（开发中）和主包中的 `alpha_workbench/agents/idea_extractor.py`（保留 mock 接口）。

### Agno 工作流入口
- 入口函数：`role3.workflow.run_role3_workflow(input_text, source_meta=None, api_url=None, token=None) -> dict`
- 返回值：Role 3 trace，包含 `workflow_mode`、`input_text`、`source_meta`、`idea_result`，以及 Agno / fallback 元信息。
- CLI 入口：`role3/run_role3_huawei.py`
- 运行方式不变，仍然用 `--url` 和 `--input` 传参；中间处理层现在由 Agno workflow 负责串联。
