import { FormEvent, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

const DEFAULT_IDEA =
  "单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。";

type InputMode = "text" | "pdf";

export function NewResearchPage() {
  const [title, setTitle] = useState("盈利超预期因子研究");
  const [inputText, setInputText] = useState(DEFAULT_IDEA);
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<InputMode>("text");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setRunning(true);
    setError("");
    try {
      const project =
        mode === "pdf" && file
          ? await api.createProject(title, "", file)
          : await api.createProject(title, inputText);
      navigate(`/research/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "研究创建失败");
    } finally {
      setRunning(false);
    }
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    setFile(selected);
  }

  function clearFile() {
    setFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function switchMode(nextMode: InputMode) {
    setMode(nextMode);
    if (nextMode === "text") {
      clearFile();
    } else {
      setInputText("");
    }
  }

  return (
    <div className="page-stack">
      <section className="panel wide-panel">
        <span className="eyebrow">新建研究</span>
        <h1>描述你的投资想法</h1>
        <p>系统会先提炼投资假设并生成研究配置，确认配置后再执行因子生成与回测。</p>
        <form className="research-form" onSubmit={submit}>
          <label>
            研究标题
            <input value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>

          <div className="input-mode-switch">
            <label className={mode === "text" ? "active" : ""}>
              <input
                type="radio"
                name="input-mode"
                checked={mode === "text"}
                onChange={() => switchMode("text")}
              />
              文本输入
            </label>
            <label className={mode === "pdf" ? "active" : ""}>
              <input
                type="radio"
                name="input-mode"
                checked={mode === "pdf"}
                onChange={() => switchMode("pdf")}
              />
              上传研报 PDF
            </label>
          </div>

          {mode === "text" ? (
            <label>
              投资想法
              <textarea
                value={inputText}
                onChange={(event) => setInputText(event.target.value)}
                rows={8}
              />
            </label>
          ) : (
            <label>
              上传研报 PDF
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf"
                onChange={handleFileChange}
              />
              {file ? (
                <p className="file-hint">
                  已选择：{file.name}（{Math.round(file.size / 1024)} KB）
                  <button type="button" className="text-button" onClick={clearFile}>
                    清除
                  </button>
                </p>
              ) : (
                <p className="file-hint">请选择一份 PDF 研报，系统将自动提取投资思想。</p>
              )}
            </label>
          )}

          {error && <p className="form-error">{error}</p>}
          <button
            className="primary-button"
            type="submit"
            disabled={running || (mode === "text" ? !inputText.trim() : !file)}
          >
            {running ? "正在创建研究任务..." : "创建研究任务"}
          </button>
        </form>
      </section>
    </div>
  );
}
