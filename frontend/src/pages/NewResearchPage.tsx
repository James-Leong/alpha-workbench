import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

const DEFAULT_IDEA =
  "单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。";

export function NewResearchPage() {
  const [title, setTitle] = useState("盈利超预期因子研究");
  const [inputText, setInputText] = useState(DEFAULT_IDEA);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setRunning(true);
    setError("");
    try {
      const project = await api.createProject(title, inputText);
      navigate(`/research/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "研究创建失败");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="page-stack">
      <section className="panel wide-panel">
        <span className="eyebrow">新建研究</span>
        <h1>描述你的投资想法</h1>
        <p>系统会基于输入生成研究摘要、候选因子、回测结果和报告草稿。</p>
        <form className="research-form" onSubmit={submit}>
          <label>
            研究标题
            <input value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label>
            投资想法
            <textarea
              value={inputText}
              onChange={(event) => setInputText(event.target.value)}
              rows={8}
            />
          </label>
          {error && <p className="form-error">{error}</p>}
          <button className="primary-button" type="submit" disabled={running}>
            {running ? "正在生成研究结果..." : "生成研究结果"}
          </button>
        </form>
      </section>
    </div>
  );
}
