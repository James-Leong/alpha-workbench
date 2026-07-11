import {
  BarChart3,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Settings,
  Sparkles
} from "lucide-react";
import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
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
  const location = useLocation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const isResearchDetail =
    location.pathname.startsWith("/research/") && location.pathname !== "/research/new";

  return (
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="brand">
            <div className="brand-mark">AW</div>
            <div className="brand-copy">
              <strong>AlphaWorkbench</strong>
              <span>因子研究工作台</span>
            </div>
          </div>
          <button
            aria-label={sidebarCollapsed ? "展开左侧栏" : "折叠左侧栏"}
            className="icon-button sidebar-toggle"
            title={sidebarCollapsed ? "展开左侧栏" : "折叠左侧栏"}
            type="button"
            onClick={() => setSidebarCollapsed((value) => !value)}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </button>
        </div>
        <nav>
          <NavLink to="/dashboard">
            <BarChart3 size={18} /> <span>研究台</span>
          </NavLink>
          <NavLink to="/research/new">
            <Plus size={18} /> <span>新建研究</span>
          </NavLink>
          <NavLink to="/settings">
            <Settings size={18} /> <span>账号设置</span>
          </NavLink>
        </nav>
        <div className="sidebar-footer">
          <div className="user-card">
            <Sparkles size={17} />
            <div className="user-copy">
              <strong>{user.username}</strong>
              <span>{user.email}</span>
            </div>
          </div>
          <button
            aria-label="退出"
            className="ghost-button logout-button"
            title="退出"
            type="button"
            onClick={onLogout}
          >
            <LogOut size={17} /> <span>退出</span>
          </button>
        </div>
      </aside>
      <main className={`content ${isResearchDetail ? "content-full" : ""}`}>{children}</main>
    </div>
  );
}
