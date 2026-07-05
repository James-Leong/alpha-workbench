import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api/client";
import { AppShell } from "./components/AppShell";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { NewResearchPage } from "./pages/NewResearchPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ResearchDetailPage } from "./pages/ResearchDetailPage";
import { SettingsPage } from "./pages/SettingsPage";
import type { User } from "./types";

function RequireAuth({
  user,
  children
}: {
  user: User | null;
  children: React.ReactNode;
}) {
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  async function logout() {
    await api.logout();
    setUser(null);
    navigate("/login");
  }

  if (loading) {
    return <div className="boot-screen">AlphaWorkbench 正在载入...</div>;
  }

  return (
    <Routes>
      <Route path="/" element={<Navigate to={user ? "/dashboard" : "/login"} replace />} />
      <Route path="/login" element={<LoginPage onAuthenticated={setUser} />} />
      <Route path="/register" element={<RegisterPage onAuthenticated={setUser} />} />
      <Route
        path="/dashboard"
        element={
          <RequireAuth user={user}>
            <AppShell user={user as User} onLogout={logout}>
              <DashboardPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/research/new"
        element={
          <RequireAuth user={user}>
            <AppShell user={user as User} onLogout={logout}>
              <NewResearchPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/research/:id"
        element={
          <RequireAuth user={user}>
            <AppShell user={user as User} onLogout={logout}>
              <ResearchDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/settings"
        element={
          <RequireAuth user={user}>
            <AppShell user={user as User} onLogout={logout}>
              <SettingsPage user={user as User} />
            </AppShell>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
