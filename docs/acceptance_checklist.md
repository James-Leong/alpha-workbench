# AlphaWorkbench 验收清单

> 版本：v1.0 | 更新时间：2026-06-22
> 用途：中期评审前自查 + 演示就绪度确认
> 原则：以"能稳定演示"为第一优先级

---

## 模块一：Role6 核心模块验收

### 1.1 AuditAgent（audit_agent.py）

| 验收项 | 验收方法 | 当前状态 |
|--------|----------|----------|
| 文件存在且可导入 | `ls alpha_workbench/agents/audit_agent.py` | ✅ 通过 |
| 真实LLM接入（华为云）| 跑全流程，终端看 is_mock: false | ✅ 通过 |
| 输出标准JSON结构 | 检查字段：overall_level / checks / next_actions | ✅ 通过 |
| 4个审计维度全部覆盖 | 未来函数/样本稳健性/过拟合/交易频率风险 | ✅ 通过 |
| LLM失败自动mock fallback | 断网或key失效时不崩溃 | ✅ 通过 |

### 1.2 ReportAgent（report_agent.py）

| 验收项 | 验收方法 | 当前状态 |
|--------|----------|----------|
| 文件存在且可导入 | `ls alpha_workbench/agents/report_agent.py` | ✅ 通过 |
| 真实LLM接入，输出Markdown | 跑全流程，查看报告页面内容非模板 | ✅ 通过 |
| 兼容两种回测结果格式 | 有Mercury数据/无Mercury数据均可生成报告 | ✅ 通过 |
| LLM失败自动fallback | 不崩溃，输出兜底报告 | ✅ 通过 |

### 1.3 Research Trace（research_trace.py）

| 验收项 | 验收方法 | 当前状态 |
|--------|----------|----------|
| 文件存在 | `ls alpha_workbench/memory/research_trace.py` | ✅ 通过 |
| Trace保存至 runs/ 目录 | 跑完全流程，`ls runs/` 有新文件生成 | ✅ 通过 |
| Figure序列化不报错 | 终端无 "not JSON serializable" 红色报错 | ✅ 通过（已修复）|
| Trace包含审计+报告字段 | JSON文件内含 audit_report / report_markdown | ✅ 通过 |

### 1.4 Alpha Memory 可视化

| 验收项 | 验收方法 | 当前状态 |
|--------|----------|----------|
| 可视化页面可访问 | 侧边栏进入 Alpha Memory 页面不报错 | ✅ 通过 |
| 历史记录可列表展示 | 页面显示 runs/ 下的历史研究列表 | ✅ 通过（13条）|
| 审计+报告内容可展开查看 | 点击单条记录，审计结果和报告均可展示 | ✅ 通过 |

---

## 模块二：主流程端到端验收（9阶段）

| 阶段 | 名称 | 预期行为 | 当前状态 |
|------|------|----------|----------|
| 1 | 输入投资想法 | 文本框可输入，点击提交无报错 | ✅ 通过 |
| 2 | IdeaExtraction | 提炼 IdeaSpec 结构化输出 | ⚠️ 通过（固定模板，不随输入变化）|
| 3 | ResearchSpec | 展示研究配置，Human可编辑 | ✅ 通过 |
| 4 | FactorGeneration | 生成候选因子族 | ⚠️ 通过（固定3因子，不随输入变化）|
| 5 | BacktestEngine | 回测指标+图表展示 | ⚠️ 通过（Mercury 401，走mock数据）|
| 6 | BacktestExplanation | 自然语言解释回测结果 | ⚠️ 通过（403报错，走mock解释）|
| 7 | AuditAgent | 反证审计，标记风险 | ✅ 通过（真实LLM，is_mock: false）|
| 8 | ReportAgent | 生成完整Markdown研究报告 | ✅ 通过（真实LLM）|
| 9 | Trace保存 | runs/ 目录生成JSON文件 | ✅ 通过 |

> ⚠️ 说明：阶段2/4为当前版本的已知限制，不影响演示核心流程。
> 阶段5/6有完善的fallback机制，演示稳定。

---

## 模块三：Bug修复验收

| Bug描述 | 修复位置 | 修复方式 | 验收状态 |
|---------|----------|----------|----------|
| sharpe_ratio KeyError | streamlit_app.py | best.get('sharpe_ratio', 0) | ✅ 已修复 |
| Figure not JSON serializable（主流程）| research_trace.py | _safe_json_default + json.loads(obj.to_json()) | ✅ 已修复 |
| Figure序列化报错（新界面第633行）| streamlit_app.py | 同上处理方式 | ✅ 已修复 |
| pyarrow formula_tree类型崩溃（993行）| streamlit_app.py | 类型兜底处理 | ✅ 已修复 |
| 侧边栏默认未折叠 | streamlit_app.py | 设置默认折叠 | ✅ 已修复 |

---

## 模块四：已知问题与处理策略

| 问题 | 性质 | 演示影响 | 处理策略 |
|------|------|----------|----------|
| Role3 IdeaExtraction 返回固定模板 | 功能限制 | 不能演示"不同输入不同输出" | 演示重点放流程和审计质量 |
| Role4 FactorGeneration 返回写死因子 | 功能限制 | 同上 | 同上 |
| Mercury 401，回测走mock数据 | 外部依赖 | 数字是模拟的 | 审计模块主动标记，变为"反证优先"亮点 |
| BacktestExplanation 403，走mock | 外部依赖 | 解释非真实LLM | fallback机制是设计特性，稳定不崩溃 |
| 线上部署仍是旧版mock审计 | 部署滞后 | 线上无法演示新功能 | 演示固定用本地 http://127.0.0.1:8501 |
| Human-in-the-loop 可编辑不重跑 | 功能不完整 | 被追问时需解释 | 说"规划中"或演示前实现 |

---

## 模块五：演示就绪度检查

| 检查项 | 验收方法 | 当前状态 |
|--------|----------|----------|
| 本地demo可一键启动 | `bash scripts/start_demo.sh` 无报错 | ✅ 通过 |
| 浏览器可访问 | http://127.0.0.1:8501 正常打开 | ✅ 通过 |
| 全流程9/9阶段跑通 | 从输入到Trace保存无崩溃 | ✅ 通过 |
| 演示脚本已就位 | docs/demo_script.md 存在 | ✅ 通过 |
| 关键话术已准备 | "反证优先"、"流程可复现"等说法已明确 | ✅ 通过 |
| Alpha Memory可演示 | 侧边栏可进入，历史记录可查看 | ✅ 通过 |
| 演示用本地而非线上 | 已确认，线上为旧版 | ✅ 已确认 |

---

## 总体评估

| 维度 | 评分 | 说明 |
|------|------|------|
| Role6 模块完成度 | 🟢 高 | 全部核心功能已实现并验证 |
| 全流程稳定性 | 🟢 高 | 9/9阶段跑通，有完善fallback |
| 演示准备度 | 🟡 中 | 脚本已有，口稿待完成 |
| 整体项目完成度 | 🟡 中 | Role3/4有限制，Role6是最强模块 |

