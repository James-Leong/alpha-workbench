import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { AuthFrame } from "./LoginPage";
import type { User } from "../types";

export function RegisterPage({ onAuthenticated }: { onAuthenticated: (user: User) => void }) {
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const user = await api.register(email, username, password);
      onAuthenticated(user);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败");
    }
  }

  return (
    <AuthFrame eyebrow="因子研究工作台" title="创建账号">
      <form className="auth-form" onSubmit={submit}>
        <label>
          邮箱
          <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
        </label>
        <label>
          用户名
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          密码
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            minLength={8}
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button" type="submit">
          注册并进入
        </button>
        <p className="auth-hint">
          已有账号？<Link to="/login">返回登录</Link>
        </p>
      </form>
    </AuthFrame>
  );
}
