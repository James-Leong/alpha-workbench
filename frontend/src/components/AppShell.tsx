import { BarChart3, LogOut, Plus, Settings, Sparkles } from "lucide-react";
import { NavLink } from "react-router-dom";
import type { User } from "../types";

export function AppShell({
  user,
  onLogout,
  children
}: {
  user: User;
  onLogout: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">AW</div>
          <div>
            <strong>AlphaWorkbench</strong>
            <span>因子研究工作台</span>
          </div>
        </div>
        <nav>
          <NavLink to="/dashboard">
            <BarChart3 size={18} /> 研究台
          </NavLink>
          <NavLink to="/research/new">
            <Plus size={18} /> 新建研究
          </NavLink>
          <NavLink to="/settings">
            <Settings size={18} /> 账号设置
          </NavLink>
        </nav>
        <div className="sidebar-footer">
          <div className="user-card">
            <Sparkles size={17} />
            <div>
              <strong>{user.username}</strong>
              <span>{user.email}</span>
            </div>
          </div>
          <button className="ghost-button" type="button" onClick={onLogout}>
            <LogOut size={17} /> 退出
          </button>
        </div>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}
