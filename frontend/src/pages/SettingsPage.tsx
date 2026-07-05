import type { User } from "../types";

export function SettingsPage({ user }: { user: User }) {
  return (
    <div className="page-stack">
      <section className="panel wide-panel">
        <span className="eyebrow">账号</span>
        <h1>账号设置</h1>
        <div className="settings-list">
          <div>
            <span>用户名</span>
            <strong>{user.username}</strong>
          </div>
          <div>
            <span>邮箱</span>
            <strong>{user.email}</strong>
          </div>
          <div>
            <span>认证方式</span>
            <strong>账号密码 / GitHub</strong>
          </div>
        </div>
      </section>
    </div>
  );
}
