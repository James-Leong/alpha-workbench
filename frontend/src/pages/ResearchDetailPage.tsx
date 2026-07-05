import { marked } from "marked";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import { statusLabel } from "../components/status";
import type { ProgressEvent, ResearchProjectDetail } from "../types";

type Stage = {
  title: string;
  subtitle: string;
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

function ProgressTimeline({ events, status }: { events: ProgressEvent[]; status: string }) {
  const visibleEvents = events.length
    ? events
    : [{ step: "准备中", status: "running", message: "正在创建研究任务。" }];
  return (
    <section className="run-panel">
      <div>
        <span className={`status-pill ${status}`}>{statusLabel(status)}</span>
        <h2>{status === "running" ? "正在生成研究结果" : "研究进度"}</h2>
        <p>系统会按阶段提炼想法、生成候选因子、执行回测并整理报告。</p>
      </div>
      <ol className="timeline">
        {visibleEvents.map((event, index) => (
          <li className={event.status} key={`${event.step}-${index}`}>
            <span className="timeline-dot" />
            <div>
              <strong>{event.step}</strong>
              <p>{event.message}</p>
            </div>
          </li>
        ))}
      </ol>
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

function buildStages(trace: Record<string, unknown>, metrics: Record<string, unknown>): Stage[] {
  const idea = asRecord(trace.idea_spec);
  const research = asRecord(trace.research_spec);
  const compiled = asArray(trace.compiled_factors);
  const factors = asArray(trace.factor_specs);
  const explanation = asRecord(trace.explanation);
  const audit = asRecord(trace.audit_report);
  const backtest = asRecord(trace.backtest_result);

  return [
    {
      title: "1. 智能研读",
      subtitle: "从原始想法中提炼投资假设、适用场景和潜在风险。",
      content: <KeyValueList data={idea} />
    },
    {
      title: "2. 研究配置",
      subtitle: "确认股票池、调仓频率、交易成本和回测约束。",
      content: <KeyValueList data={research} />
    },
    {
      title: "3. 候选因子",
      subtitle: "生成可比较的因子表达、公式和业务解释。",
      content: (
        <div className="factor-list">
          {factors.length ? (
            factors.map((factor, index) => {
              const item = asRecord(factor);
              return (
                <article className="factor-card" key={String(item.factor_id || index)}>
                  <strong>{textValue(item.factor_name || item.factor_id, `候选因子 ${index + 1}`)}</strong>
                  <p>{textValue(item.description || item.rationale || item.economic_logic)}</p>
                  <code>{textValue(item.formula_latex || item.formula || item.expression, "")}</code>
                </article>
              );
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
      content: (
        <div className="factor-list">
          {compiled.length ? (
            compiled.map((item, index) => {
              const record = asRecord(item);
              return (
                <article className="factor-card compact" key={index}>
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
      title: "5. 回测摘要",
      subtitle: "汇总 IC、分层、多空和净值表现等关键结果。",
      content: <KeyValueList data={Object.keys(metrics).length ? metrics : backtest} />
    },
    {
      title: "6. 结果解释",
      subtitle: "解释回测表现、异常波动和下一步验证方向。",
      content: <KeyValueList data={explanation} />
    },
    {
      title: "7. 研究审计",
      subtitle: "检查未来函数、样本偏差、字段可得性和稳健性风险。",
      content: <KeyValueList data={audit} />
    }
  ];
}

export function ResearchDetailPage() {
  const { id = "" } = useParams();
  const [project, setProject] = useState<ResearchProjectDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let disposed = false;
    let timer: number | undefined;

    async function load() {
      try {
        const next = await api.getProject(id);
        if (disposed) {
          return;
        }
        setProject(next);
        if (next.status === "running") {
          timer = window.setTimeout(load, 1500);
        }
      } catch (err) {
        if (!disposed) {
          setError(err instanceof Error ? err.message : "加载失败");
        }
      }
    }

    load();
    return () => {
      disposed = true;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [id]);

  const stages = useMemo(
    () => buildStages(project?.trace ?? {}, project?.metrics_summary ?? {}),
    [project]
  );

  if (error) {
    return <div className="panel form-error">{error}</div>;
  }
  if (!project) {
    return <div className="panel loading-panel">正在加载研究详情...</div>;
  }

  const reportHtml = marked.parse(project.report_markdown || "研究报告将在流程完成后生成。");

  return (
    <div className="page-stack">
      <section className="detail-header">
        <span className={`status-pill ${project.status}`}>{statusLabel(project.status)}</span>
        <h1>{project.title}</h1>
        <p>{project.idea_text}</p>
      </section>

      <ProgressTimeline events={project.progress_events} status={project.status} />

      <section className="stage-grid">
        {stages.map((stage) => (
          <article className="stage-card" key={stage.title}>
            <div className="stage-card-heading">
              <h2>{stage.title}</h2>
              <p>{stage.subtitle}</p>
            </div>
            {stage.content}
          </article>
        ))}
      </section>

      <section className="report-panel">
        <div className="stage-card-heading">
          <h2>8. 研究报告</h2>
          <p>汇总投资假设、因子定义、回测结论和风险提示。</p>
        </div>
        <article dangerouslySetInnerHTML={{ __html: reportHtml }} />
      </section>
    </div>
  );
}
