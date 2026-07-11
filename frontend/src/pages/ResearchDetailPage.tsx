import { marked } from "marked";
import katex from "katex";
import "katex/dist/katex.min.css";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import { statusLabel } from "../components/status";
import type { ProgressEvent, ResearchProjectDetail, ResearchSpecUpdate } from "../types";

type Stage = {
  title: string;
  subtitle: string;
  status?: string;
  content: React.ReactNode;
};

function textValue(value: unknown, fallback = "暂无内容") {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value, null, 2);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asString(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  return String(value);
}

function ProgressTimeline({ events, status }: { events: ProgressEvent[]; status: string }) {
  const normalizedStatus = status || "pending";

  const title: Record<string, string> = {
    completed: "研究完成",
    running: "正在生成研究结果",
    failed: "研究失败",
    pending: "等待开始"
  };

  const summary: Record<string, { step: string; message: string }> = {
    completed: { step: "完成", message: "研究任务已结束，下方为完整结果与报告。" },
    failed: { step: "失败", message: "研究任务执行失败，请检查输入或查看日志。" },
    running: { step: "准备中", message: "正在创建研究任务。" },
    pending: { step: "等待中", message: "等待任务开始。" }
  };

  const hasEvents = events.length > 0;

  return (
    <section className="run-panel compact">
      <div>
        <h2>{title[normalizedStatus] ?? "研究进度"}</h2>
        <p>系统会按阶段提炼想法、生成候选因子、执行回测并整理报告。</p>
      </div>
      {hasEvents ? (
        <ol className="timeline">
          {events.map((event, index) => (
            <li className={event.status} key={`${event.step}-${index}`}>
              <span className="timeline-dot" />
              <div>
                <strong>{event.step}</strong>
                <p>{event.message}</p>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="run-summary">{summary[normalizedStatus]?.message ?? summary.pending.message}</p>
      )}
    </section>
  );
}

function KeyValueList({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, value]) => value !== undefined && value !== null);
  if (!entries.length) {
    return <p className="muted-text">暂无结构化内容。</p>;
  }
  return (
    <dl className="kv-list">
      {entries.slice(0, 8).map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{textValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function BulletList({ items }: { items: unknown[] }) {
  if (!items.length) return null;
  return (
    <ul className="bullet-list">
      {items.map((item, index) => {
        if (typeof item === "string") {
          return <li key={index}>{item}</li>;
        }
        if (item && typeof item === "object" && !Array.isArray(item)) {
          const record = item as Record<string, unknown>;
          return (
            <li key={index}>
              {Object.entries(record).map(([k, v]) => (
                <span key={k} className="kv-inline">
                  <strong>{k}:</strong> {textValue(v)}
                </span>
              ))}
            </li>
          );
        }
        return <li key={index}>{textValue(item)}</li>;
      })}
    </ul>
  );
}

function TagList({ tags }: { tags: unknown[] }) {
  if (!tags.length) return null;
  return (
    <div className="tag-list">
      {tags.map((tag, index) => (
        <span className="tag" key={index}>
          {asString(tag)}
        </span>
      ))}
    </div>
  );
}

function LatexFormula({ formula }: { formula: string }) {
  const [html, setHtml] = useState<string>("");

  useEffect(() => {
    try {
      const rendered = katex.renderToString(formula, {
        throwOnError: false,
        displayMode: true,
      });
      setHtml(rendered);
    } catch {
      setHtml(`<code>${formula}</code>`);
    }
  }, [formula]);

  return (
    <div
      className="latex-container"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <details className="json-details">
      <summary>原始数据</summary>
      <pre className="json-box">{textValue(value)}</pre>
    </details>
  );
}

function CodeBlock({ code }: { code: string }) {
  return <pre className="code-box"><code>{code}</code></pre>;
}

function EmptyBlock({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-block">
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

function IdeaSpecView({ idea }: { idea: Record<string, unknown> }) {
  return (
    <div className="idea-view">
      <p className="lead">{asString(idea.core_hypothesis || idea.idea_name)}</p>
      {Boolean(idea.summary) && <p className="idea-summary">{asString(idea.summary)}</p>}
      {Boolean(idea.economic_mechanism) && asArray(idea.economic_mechanism).length > 0 && (
        <>
          <h4>经济机制</h4>
          <BulletList items={asArray(idea.economic_mechanism)} />
        </>
      )}
      {Boolean(idea.required_data_concepts) && asArray(idea.required_data_concepts).length > 0 && (
        <>
          <h4>所需数据</h4>
          <TagList tags={asArray(idea.required_data_concepts)} />
        </>
      )}
      {Boolean(idea.factor_directions) && asArray(idea.factor_directions).length > 0 && (
        <>
          <h4>因子方向</h4>
          <TagList tags={asArray(idea.factor_directions)} />
        </>
      )}
      {Boolean(idea.risk_flags) && asArray(idea.risk_flags).length > 0 && (
        <>
          <h4>风险提示</h4>
          <ul className="risk-list">
            {asArray(idea.risk_flags).map((flag, index) => (
              <li key={index}>{asString(flag)}</li>
            ))}
          </ul>
        </>
      )}
      {Boolean(idea.uncertainties) && asArray(idea.uncertainties).length > 0 && (
        <>
          <h4>不确定性</h4>
          <BulletList items={asArray(idea.uncertainties)} />
        </>
      )}
      {Boolean(idea.evidence) && asArray(idea.evidence).length > 0 && (
        <>
          <h4>证据片段</h4>
          <ul className="evidence-list">
            {asArray(idea.evidence).map((ev, index) => {
              const record = asRecord(ev);
              return (
                <li key={index}>
                  <span className="tag">{asString(record.source || "source")}</span>
                  <p>{asString(record.text)}</p>
                </li>
              );
            })}
          </ul>
        </>
      )}
      {Boolean(idea.suggested_research_spec) && (
        <>
          <h4>推荐研究配置</h4>
          <JsonBlock value={idea.suggested_research_spec} />
        </>
      )}
      <JsonBlock value={idea} />
    </div>
  );
}

function FactorSpecView({ factor }: { factor: Record<string, unknown> }) {
  return (
    <article className="factor-card">
      <strong>{asString(factor.factor_name || factor.factor_id)}</strong>
      <p>{asString(factor.plain_description || factor.description || factor.rationale)}</p>
      {Boolean(factor.latex_formula) && (
        <LatexFormula formula={asString(factor.latex_formula)} />
      )}
      {Boolean(factor.required_fields) && asArray(factor.required_fields).length > 0 && (
        <div className="factor-meta">
          <span className="meta-label">所需字段</span>
          <TagList tags={asArray(factor.required_fields)} />
        </div>
      )}
      {Boolean(factor.risk_notes) && asArray(factor.risk_notes).length > 0 && (
        <div className="factor-meta">
          <span className="meta-label">风险提示</span>
          <BulletList items={asArray(factor.risk_notes)} />
        </div>
      )}
      {Boolean(factor.formula_tree) && <JsonBlock value={factor.formula_tree} />}
    </article>
  );
}

function AuditResultView({ audit }: { audit: Record<string, unknown> }) {
  const level = asString(audit.overall_level || "unknown").toLowerCase();
  const checks = asArray(audit.checks);
  const nextActions = asArray(audit.next_actions);

  return (
    <div className="audit-view">
      <div className="audit-summary">
        <span className={`audit-level audit-level-${level}`}>
          {level === "high" ? "高风险" : level === "medium" ? "中风险" : "低风险"}
        </span>
      </div>
      {checks.length > 0 && (
        <div className="audit-check-list">
          {checks.map((check, index) => {
            const record = asRecord(check);
            const checkLevel = asString(record.level || "low").toLowerCase();
            return (
              <div className={`audit-check audit-check-${checkLevel}`} key={index}>
                <div className="audit-check-header">
                  <span className={`audit-level audit-level-${checkLevel}`}>
                    {checkLevel === "high" ? "高" : checkLevel === "medium" ? "中" : "低"}
                  </span>
                  <strong>{asString(record.item)}</strong>
                </div>
                <p>{asString(record.message)}</p>
              </div>
            );
          })}
        </div>
      )}
      {nextActions.length > 0 && (
        <>
          <h4>建议行动</h4>
          <ol className="next-actions">
            {nextActions.map((action, index) => (
              <li key={index}>{asString(action)}</li>
            ))}
          </ol>
        </>
      )}
      <JsonBlock value={audit} />
    </div>
  );
}

function formatPercent(value: unknown): string {
  const num = typeof value === "number" ? value : parseFloat(asString(value));
  if (Number.isNaN(num)) return "-";
  return `${(num * 100).toFixed(2)}%`;
}

function formatNumber(value: unknown, digits = 3): string {
  const num = typeof value === "number" ? value : parseFloat(asString(value));
  if (Number.isNaN(num)) return "-";
  return num.toFixed(digits);
}

function SimpleLineChart({ data }: { data: { date: string; value: number }[] }) {
  if (!data.length) return null;
  const width = 600;
  const height = 200;
  const padding = 24;
  const values = data.map((d) => d.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const points = data.map((d, index) => {
    const x = padding + (index / (data.length - 1 || 1)) * (width - padding * 2);
    const y = height - padding - ((d.value - min) / range) * (height - padding * 2);
    return `${x},${y}`;
  });

  return (
    <div className="line-chart">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet">
        <polyline
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2"
          points={points.join(" ")}
        />
        <circle cx={points[0].split(",")[0]} cy={points[0].split(",")[1]} r="3" fill="var(--accent)" />
        <circle
          cx={points[points.length - 1].split(",")[0]}
          cy={points[points.length - 1].split(",")[1]}
          r="3"
          fill="var(--accent)"
        />
      </svg>
    </div>
  );
}

function BacktestResultView({ result }: { result: Record<string, unknown> }) {
  const factorResults = asArray(result.factor_results);
  const navSeries = asArray(result.nav_series) as { date: string; value: number }[];
  const mercuryResults = asRecord(result.mercury_results || {});

  if (!factorResults.length) {
    return <p className="muted-text">暂无回测结果。</p>;
  }

  const best = asRecord(factorResults[0]);

  return (
    <div className="backtest-view">
      <div className="metric-grid">
        <div className="metric-card-small">
          <span className="metric-label">最佳因子</span>
          <strong>{asString(best.factor_name || best.factor_id)}</strong>
        </div>
        <div className="metric-card-small">
          <span className="metric-label">IC 均值</span>
          <strong>{formatNumber(best.ic_mean)}</strong>
        </div>
        <div className="metric-card-small">
          <span className="metric-label">多空收益</span>
          <strong>{formatPercent(best.long_short_return)}</strong>
        </div>
        <div className="metric-card-small">
          <span className="metric-label">最大回撤</span>
          <strong>{formatPercent(best.max_drawdown)}</strong>
        </div>
      </div>

      {navSeries.length > 0 && <SimpleLineChart data={navSeries} />}

      <h4>全部因子结果</h4>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>因子</th>
              <th>IC 均值</th>
              <th>多空收益</th>
              <th>最大回撤</th>
              <th>夏普</th>
            </tr>
          </thead>
          <tbody>
            {factorResults.map((factor, index) => {
              const record = asRecord(factor);
              return (
                <tr key={index}>
                  <td>{asString(record.factor_name || record.factor_id)}</td>
                  <td>{formatNumber(record.ic_mean)}</td>
                  <td>{formatPercent(record.long_short_return)}</td>
                  <td>{formatPercent(record.max_drawdown)}</td>
                  <td>{formatNumber(record.sharpe_ratio)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {Object.keys(mercuryResults).length > 0 && (
        <>
          <h4>Mercury 交易级结果</h4>
          <div className="mercury-list">
            {Object.entries(mercuryResults).map(([factorId, mercury]) => {
              const record = asRecord(mercury);
              return (
                <details className="json-details" key={factorId}>
                  <summary>{factorId}</summary>
                  <pre className="json-box">{textValue(record)}</pre>
                </details>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function ExplanationView({ explanation }: { explanation: Record<string, unknown> }) {
  const observations = asArray(explanation.observations);
  return (
    <div className="explanation-view">
      <p className="lead">{asString(explanation.summary || "解释已生成。")}</p>
      {observations.length > 0 && <BulletList items={observations} />}
      <JsonBlock value={explanation} />
    </div>
  );
}

function ResearchConfigView({
  projectId,
  research,
  status,
  onSaved,
  onStart,
}: {
  projectId: string;
  research: Record<string, unknown>;
  status: string;
  onSaved: (project: ResearchProjectDetail) => void;
  onStart: (project: ResearchProjectDetail) => void;
}) {
  const sw = asRecord(research.sample_window);
  const editable = status === "pending";

  const [universe, setUniverse] = useState(asString(research.universe));
  const [rebalanceFrequency, setRebalanceFrequency] = useState(asString(research.rebalance_frequency));
  const [holdingPeriod, setHoldingPeriod] = useState(asString(research.holding_period));
  const [benchmark, setBenchmark] = useState(asString(research.benchmark));
  const [transactionCostBps, setTransactionCostBps] = useState(
    typeof research.transaction_cost_bps === "number" ? research.transaction_cost_bps : 10
  );
  const [initialCash, setInitialCash] = useState(
    typeof research.initial_cash === "number" ? research.initial_cash : 1000000
  );
  const [sampleStart, setSampleStart] = useState(asString(sw.start));
  const [sampleEnd, setSampleEnd] = useState(asString(sw.end));
  const [filters, setFilters] = useState(() => asArray(research.filters).map(asString).join(", "));
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  async function saveSpec(): Promise<ResearchProjectDetail | null> {
    setSaving(true);
    setError("");
    setSuccess(false);

    const payload: ResearchSpecUpdate = {
      universe: universe.trim(),
      rebalance_frequency: rebalanceFrequency.trim(),
      holding_period: holdingPeriod.trim(),
      transaction_cost_bps: Number(transactionCostBps),
      benchmark: benchmark.trim(),
      initial_cash: Number(initialCash),
      sample_window_start: sampleStart.trim(),
      sample_window_end: sampleEnd.trim(),
      factor_execution_mode: "codex",
      filters: filters
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };

    try {
      const updated = await api.updateResearchSpec(projectId, payload);
      setSuccess(true);
      onSaved(updated);
      return updated;
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    await saveSpec();
  }

  async function handleStart() {
    setStarting(true);
    setError("");
    try {
      const saved = await saveSpec();
      if (!saved) {
        setStarting(false);
        return;
      }
      const updated = await api.startResearchProject(projectId);
      onStart(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "启动失败");
    } finally {
      setStarting(false);
    }
  }

  return (
    <form className="research-config-form" onSubmit={handleSubmit}>
      <div className="config-grid">
        <label>
          股票池
          <input
            value={universe}
            onChange={(event) => setUniverse(event.target.value)}
            disabled={!editable || saving || starting}
          />
        </label>
        <label>
          调仓频率
          <input
            value={rebalanceFrequency}
            onChange={(event) => setRebalanceFrequency(event.target.value)}
            disabled={!editable || saving || starting}
            placeholder="daily / weekly / monthly"
          />
        </label>
        <label>
          持有期
          <input
            value={holdingPeriod}
            onChange={(event) => setHoldingPeriod(event.target.value)}
            disabled={!editable || saving || starting}
            placeholder="20D"
          />
        </label>
        <label>
          基准
          <input
            value={benchmark}
            onChange={(event) => setBenchmark(event.target.value)}
            disabled={!editable || saving || starting}
          />
        </label>
        <label>
          交易成本（bps）
          <input
            type="number"
            step="0.1"
            value={transactionCostBps}
            onChange={(event) => setTransactionCostBps(Number(event.target.value))}
            disabled={!editable || saving || starting}
          />
        </label>
        <label>
          初始资金
          <input
            type="number"
            step="10000"
            value={initialCash}
            onChange={(event) => setInitialCash(Number(event.target.value))}
            disabled={!editable || saving || starting}
          />
        </label>
        <label>
          样本开始
          <input
            value={sampleStart}
            onChange={(event) => setSampleStart(event.target.value)}
            disabled={!editable || saving || starting}
            placeholder="YYYY-MM-DD"
          />
        </label>
        <label>
          样本结束
          <input
            value={sampleEnd}
            onChange={(event) => setSampleEnd(event.target.value)}
            disabled={!editable || saving || starting}
            placeholder="YYYY-MM-DD"
          />
        </label>
      </div>
      <label>
        过滤规则（逗号分隔）
        <input
          value={filters}
          onChange={(event) => setFilters(event.target.value)}
          disabled={!editable || saving || starting}
          placeholder="remove_ST, remove_new_listed"
        />
      </label>
      <div className="readonly-strip">
        <span>因子实现</span>
        <strong>Codex 生成 Python 插件，经沙箱验证后执行</strong>
      </div>

      {!editable && (
        <p className="form-hint">研究已开始执行或已完成，配置不可修改。</p>
      )}
      {error && <p className="form-error">{error}</p>}
      {success && <p className="form-success">配置已保存。</p>}

      {editable && (
        <div className="config-actions">
          <button className="primary-button" type="submit" disabled={saving || starting}>
            {saving ? "保存中..." : "保存配置"}
          </button>
          <button
            className="primary-button"
            type="button"
            disabled={saving || starting}
            onClick={handleStart}
          >
            {starting ? "启动中..." : "确认配置并继续"}
          </button>
        </div>
      )}
    </form>
  );
}

function MercuryStatusView({ result }: { result: Record<string, unknown> }) {
  const status = asRecord(result.mercury_status);
  const mercuryResults = asRecord(result.mercury_results || {});
  const attempts = asRecord(status.attempts);

  if (!Object.keys(status).length && !Object.keys(mercuryResults).length) {
    return (
      <EmptyBlock
        title="暂无 Mercury 输出"
        detail="当前 trace 没有 Mercury 尝试记录。新任务会保存 Mercury 状态、成功摘要或本地 fallback 原因。"
      />
    );
  }

  return (
    <div className="artifact-stack">
      <div className="summary-line">
        <span>Mercury</span>
        <strong>
          {Object.keys(mercuryResults).length
            ? `${Object.keys(mercuryResults).length} 个因子返回交易级结果`
            : status.fallback
              ? "已回退到本地因子分析"
              : "等待交易级结果"}
        </strong>
      </div>
      <KeyValueList data={{
        enabled: status.enabled,
        base_url: status.base_url,
        attempted: status.attempted,
        success_count: status.success_count,
        attempt_count: status.attempt_count,
      }} />
      {asArray(status.notes).length > 0 && <BulletList items={asArray(status.notes)} />}
      {Object.keys(mercuryResults).length > 0 && <JsonBlock value={mercuryResults} />}
      {Object.keys(attempts).length > 0 && <JsonBlock value={attempts} />}
    </div>
  );
}

function FactorDataPreviewTable({ preview }: { preview: Record<string, unknown> }) {
  const records = asArray(preview.records).map(asRecord);
  if (!records.length) {
    return null;
  }
  const columns = Object.keys(records[0]);
  return (
    <div className="table-wrap">
      <table className="data-table compact">
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{column}</th>)}
          </tr>
        </thead>
        <tbody>
          {records.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => <td key={column}>{textValue(row[column], "-")}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CodexArtifactsView({ trace }: { trace: Record<string, unknown> }) {
  const codeAgent = asRecord(trace.code_agent);
  const sources = asArray(trace.factor_plugin_sources).map(asRecord);
  const previews = asArray(trace.factor_data_previews).map(asRecord);
  const manifests = asArray(trace.factor_data_manifests).map(asRecord);
  const validations = asArray(trace.codegen_validation_reports).map(asRecord);
  const errors = asArray(trace.pipeline_errors);

  if (!Object.keys(codeAgent).length && !sources.length && !previews.length) {
    return (
      <EmptyBlock
        title="暂无 Codex 因子产物"
        detail="当前任务没有保存因子代码或数据预览。新任务默认使用 Codex 模式后会在这里展示插件源码、校验结果和样例数据。"
      />
    );
  }

  return (
    <div className="artifact-stack">
      <div className="summary-line">
        <span>实现模式</span>
        <strong>{asString(trace.factor_implementation_mode || "codex")}</strong>
      </div>
      {Object.keys(codeAgent).length > 0 && <KeyValueList data={codeAgent} />}
      {errors.length > 0 && <BulletList items={errors} />}
      {sources.map((source, index) => (
        <section className="artifact-section" key={asString(source.factor_id || index)}>
          <div className="artifact-heading">
            <strong>{asString(source.factor_id || `factor_${index + 1}`)}</strong>
            <span>{asString(source.source_sha256).slice(0, 12)}</span>
          </div>
          <CodeBlock code={asString(source.code)} />
        </section>
      ))}
      {previews.map((preview, index) => (
        <section className="artifact-section" key={asString(preview.factor_id || index)}>
          <div className="artifact-heading">
            <strong>因子数据样例：{asString(preview.factor_id)}</strong>
            <span>{asArray(preview.shape).join(" x ")}</span>
          </div>
          <FactorDataPreviewTable preview={preview} />
        </section>
      ))}
      {manifests.length > 0 && <JsonBlock value={manifests} />}
      {validations.length > 0 && <JsonBlock value={validations} />}
    </div>
  );
}

function buildStages(
  projectId: string,
  project: ResearchProjectDetail | null,
  onSaved: (project: ResearchProjectDetail) => void,
  onStart: (project: ResearchProjectDetail) => void
): Stage[] {
  const trace = project?.trace ?? {};
  const idea = asRecord(trace.idea_spec);
  const research = asRecord(trace.research_spec);
  const compiled = asArray(trace.compiled_factors);
  const factors = asArray(trace.factor_specs);
  const explanation = asRecord(trace.explanation);
  const audit = asRecord(trace.audit_report);
  const backtest = asRecord(trace.backtest_result);
  const status = project?.status ?? "pending";
  const ideaReady = Object.keys(idea).length > 0;
  const researchReady = Object.keys(research).length > 0;
  const completed = status === "completed";

  return [
    {
      title: "1. 智能研读",
      subtitle: "从原始想法中提炼投资假设、适用场景和潜在风险。",
      status: ideaReady ? "completed" : "running",
      content: ideaReady ? (
        <IdeaSpecView idea={idea} />
      ) : (
        <EmptyBlock title="正在研读输入" detail="系统正在提炼投资假设，并生成可编辑的研究配置。" />
      )
    },
    {
      title: "2. 研究配置",
      subtitle: "确认股票池、调仓频率、交易成本和回测约束。",
      status: researchReady ? (status === "pending" ? "running" : "completed") : "pending",
      content: researchReady ? (
        <ResearchConfigView
          projectId={projectId}
          research={research}
          status={status}
          onSaved={onSaved}
          onStart={onStart}
        />
      ) : (
        <EmptyBlock title="等待研读完成" detail="研究配置会在智能研读完成后出现。" />
      )
    },
    {
      title: "3. 候选因子",
      subtitle: "生成可比较的因子表达、公式和业务解释。",
      status: factors.length ? "completed" : status === "running" ? "running" : "pending",
      content: (
        <div className="factor-list">
          {factors.length ? (
            factors.map((factor, index) => {
              const item = asRecord(factor);
              return <FactorSpecView factor={item} key={String(item.factor_id || index)} />;
            })
          ) : (
            <p className="muted-text">暂无候选因子。</p>
          )}
        </div>
      )
    },
    {
      title: "4. 表达式校验",
      subtitle: "检查候选因子是否能被受限表达式引擎解析。",
      status: compiled.length ? "completed" : status === "running" ? "running" : "pending",
      content: (
        <div className="factor-list">
          {compiled.length ? (
            compiled.map((item, index) => {
              const record = asRecord(item);
              return (
                <article className={`factor-card compact ${record.status === "compiled" ? "valid" : "invalid"}`} key={index}>
                  <strong>{textValue(record.factor_id || record.factor_name, `因子 ${index + 1}`)}</strong>
                  <p>{textValue(record.status || record.error || record.message)}</p>
                </article>
              );
            })
          ) : (
            <p className="muted-text">暂无校验结果。</p>
          )}
        </div>
      )
    },
    {
      title: "5. Codex 因子产物",
      subtitle: "展示生成的插件源码、沙箱校验和因子数据样例。",
      status: asArray(trace.factor_plugin_sources).length || asArray(trace.factor_data_previews).length
        ? "completed"
        : status === "running"
          ? "running"
          : "pending",
      content: <CodexArtifactsView trace={trace} />
    },
    {
      title: "6. 回测摘要",
      subtitle: "汇总 IC、分层、多空和净值表现等关键结果。",
      status: Object.keys(backtest).length ? "completed" : status === "running" ? "running" : "pending",
      content: <BacktestResultView result={Object.keys(backtest).length ? backtest : {}} />
    },
    {
      title: "7. Mercury 交易回测",
      subtitle: "展示 Mercury 服务调用状态、交易级结果或本地 fallback 原因。",
      status: Object.keys(asRecord(backtest.mercury_status)).length || Object.keys(asRecord(backtest.mercury_results)).length
        ? "completed"
        : status === "running"
          ? "running"
          : "pending",
      content: <MercuryStatusView result={backtest} />
    },
    {
      title: "8. 结果解释",
      subtitle: "解释回测表现、异常波动和下一步验证方向。",
      status: Object.keys(explanation).length ? "completed" : completed ? "completed" : "pending",
      content: <ExplanationView explanation={explanation} />
    },
    {
      title: "9. 研究审计",
      subtitle: "检查未来函数、样本偏差、字段可得性和稳健性风险。",
      status: Object.keys(audit).length ? "completed" : completed ? "completed" : "pending",
      content: <AuditResultView audit={audit} />
    }
  ];
}

function shouldPollProject(project: ResearchProjectDetail | null): boolean {
  if (!project) return true;
  if (project.status === "running") return true;
  if (project.status === "pending") {
    return project.progress_events.some((event) => event.status === "running");
  }
  return false;
}

export function ResearchDetailPage() {
  const { id = "" } = useParams();
  const [project, setProject] = useState<ResearchProjectDetail | null>(null);
  const [error, setError] = useState("");
  const [railCollapsed, setRailCollapsed] = useState(false);
  const statusRef = useRef(project?.status);
  const pollRef = useRef(true);

  useEffect(() => {
    statusRef.current = project?.status;
    pollRef.current = shouldPollProject(project);
  }, [project?.status]);

  useEffect(() => {
    if (!id) {
      return;
    }
    let disposed = false;
    let interval: number | undefined;
    let loading = false;

    async function load() {
      if (loading) {
        return;
      }
      loading = true;
      try {
        const next = await api.getProject(id);
        if (disposed) {
          return;
        }
        setProject(next);
        statusRef.current = next.status;
        pollRef.current = shouldPollProject(next);
      } catch (err) {
        if (!disposed) {
          setError(err instanceof Error ? err.message : "加载失败");
        }
      } finally {
        loading = false;
      }
    }

    // Poll while the project is running so the UI updates as the workflow progresses.
    interval = window.setInterval(() => {
      if (pollRef.current || statusRef.current === "running") {
        load();
      }
    }, 1500);

    load();
    return () => {
      disposed = true;
      if (interval) {
        window.clearInterval(interval);
      }
    };
  }, [id]);

  const stages = useMemo(
    () => buildStages(id, project, setProject, setProject),
    [id, project]
  );
  const visibleStages = useMemo(
    () => stages.filter((stage) => (stage.status ?? "pending") !== "pending"),
    [stages]
  );

  if (error) {
    return <div className="panel form-error">{error}</div>;
  }
  if (!project) {
    return <div className="panel loading-panel">正在加载研究详情...</div>;
  }

  const hasReport = Boolean(project.report_markdown?.trim());
  const reportHtml = marked.parse(project.report_markdown || "");

  return (
    <div className="research-workspace">
      <header className="research-header">
        <div>
          <span className={`status-pill ${project.status}`}>{statusLabel(project.status)}</span>
          <h1>{project.title}</h1>
          <p>{project.idea_text}</p>
        </div>
      </header>

      <div className={`research-layout ${railCollapsed ? "rail-collapsed" : ""}`}>
        <main className="research-main">
          {visibleStages.map((stage) => (
            <section className={`work-section ${stage.status ?? "pending"}`} key={stage.title}>
              <div className="work-section-heading">
                <span className="work-step-dot" />
                <div>
                  <h2>{stage.title}</h2>
                  <p>{stage.subtitle}</p>
                </div>
              </div>
              <div className="work-section-body">{stage.content}</div>
            </section>
          ))}

          {hasReport && (
            <section className="work-section completed">
              <div className="work-section-heading">
                <span className="work-step-dot" />
                <div>
                  <h2>10. 研究报告</h2>
                  <p>汇总投资假设、因子定义、回测结论和风险提示。</p>
                </div>
              </div>
              <article className="markdown-body" dangerouslySetInnerHTML={{ __html: reportHtml }} />
            </section>
          )}
        </main>

        <aside className="research-rail">
          <button
            aria-label={railCollapsed ? "展开右侧进度栏" : "折叠右侧进度栏"}
            className="icon-button rail-toggle"
            title={railCollapsed ? "展开右侧进度栏" : "折叠右侧进度栏"}
            type="button"
            onClick={() => setRailCollapsed((value) => !value)}
          >
            {railCollapsed ? <PanelRightOpen size={17} /> : <PanelRightClose size={17} />}
          </button>
          {!railCollapsed && (
            <ProgressTimeline events={project.progress_events} status={project.status} />
          )}
        </aside>
      </div>
    </div>
  );
}
