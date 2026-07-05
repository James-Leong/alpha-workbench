import { ArrowRight, Clock, FileText, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { statusLabel } from "../components/status";
import type { ResearchProjectSummary } from "../types";

export function DashboardPage() {
  const [projects, setProjects] = useState<ResearchProjectSummary[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.listProjects().then(setProjects).catch((err) => setError(err.message));
  }, []);

  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <span className="eyebrow">研究工作台</span>
          <h1>管理你的因子研究</h1>
          <p>从投资想法开始，沉淀研究记录、回测摘要和最终报告，方便后续复盘与分叉探索。</p>
        </div>
        <Link className="primary-button hero-action" to="/research/new">
          <Plus size={18} /> 新建研究
        </Link>
      </section>
      <section className="grid-two">
        <div className="stat-card">
          <Clock size={20} />
          <strong>{projects.length}</strong>
          <span>历史研究</span>
        </div>
        <div className="stat-card">
          <FileText size={20} />
          <strong>报告</strong>
          <span>研究结论归档</span>
        </div>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>最近研究</h2>
          <span>{error || "按更新时间排序"}</span>
        </div>
        <div className="project-list">
          {projects.length === 0 && (
            <div className="empty-state">还没有研究记录。新建一条研究，开始整理你的第一个因子想法。</div>
          )}
          {projects.map((project) => (
            <Link className="project-row" to={`/research/${project.id}`} key={project.id}>
              <div>
                <strong>{project.title}</strong>
                <p>{project.summary || project.idea_text}</p>
              </div>
              <span className={`status-pill ${project.status}`}>{statusLabel(project.status)}</span>
              <ArrowRight size={18} />
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
