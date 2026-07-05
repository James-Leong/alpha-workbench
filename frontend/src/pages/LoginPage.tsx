import { Github } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { User } from "../types";

export function LoginPage({ onAuthenticated }: { onAuthenticated: (user: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const user = await api.login(email, password);
      onAuthenticated(user);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    }
  }

  return (
    <AuthFrame eyebrow="因子研究工作台" title="登录 AlphaWorkbench">
      <form className="auth-form" onSubmit={submit}>
        <label>
          邮箱
          <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
        </label>
        <label>
          密码
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button" type="submit">
          登录
        </button>
        <a className="github-button" href={api.githubLoginUrl()}>
          <Github size={18} /> 使用 GitHub 登录
        </a>
        <p className="auth-hint">
          还没有账号？<Link to="/register">创建账号</Link>
        </p>
      </form>
    </AuthFrame>
  );
}

export function AuthFrame({
  eyebrow,
  title,
  children
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <main className="auth-page">
      <section className="auth-hero">
        <span>{eyebrow}</span>
        <h1>把投资想法整理成可追踪的研究记录。</h1>
        <p>面向研究员的因子研究空间，集中管理研究输入、回测摘要和报告沉淀。</p>
      </section>
      <section className="auth-card">
        <h2>{title}</h2>
        {children}
      </section>
    </main>
  );
}
