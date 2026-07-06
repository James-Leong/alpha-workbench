import type {
  ResearchProjectDetail,
  ResearchProjectSummary,
  ResearchRunProgress,
  ResearchSpecUpdate,
  User
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

let csrfToken = "";

type ApiOptions = {
  method?: string;
  body?: unknown;
  csrf?: boolean;
};

async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json"
  };
  if (options.csrf && csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    credentials: "include",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `请求失败：${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function rememberUser(user: User): User {
  csrfToken = user.csrf_token;
  return user;
}

export const api = {
  apiBaseUrl: API_BASE_URL,
  async me(): Promise<User> {
    return rememberUser(await apiRequest<User>("/api/auth/me"));
  },
  async register(email: string, username: string, password: string): Promise<User> {
    return rememberUser(
      await apiRequest<User>("/api/auth/register", {
        method: "POST",
        body: { email, username, password }
      })
    );
  },
  async login(email: string, password: string): Promise<User> {
    return rememberUser(
      await apiRequest<User>("/api/auth/login", {
        method: "POST",
        body: { email, password }
      })
    );
  },
  async logout(): Promise<void> {
    await apiRequest<void>("/api/auth/logout", { method: "POST", csrf: true });
    csrfToken = "";
  },
  async listProjects(): Promise<ResearchProjectSummary[]> {
    return apiRequest<ResearchProjectSummary[]>("/api/research/projects");
  },
  async createProject(title: string, inputText: string): Promise<ResearchProjectDetail> {
    return apiRequest<ResearchProjectDetail>("/api/research/projects", {
      method: "POST",
      csrf: true,
      body: { title, input_text: inputText }
    });
  },
  async getProject(id: string): Promise<ResearchProjectDetail> {
    return apiRequest<ResearchProjectDetail>(`/api/research/projects/${id}`);
  },
  async updateResearchSpec(
    id: string,
    researchSpec: Partial<ResearchSpecUpdate>
  ): Promise<ResearchProjectDetail> {
    return apiRequest<ResearchProjectDetail>(`/api/research/projects/${id}/research-spec`, {
      method: "PATCH",
      csrf: true,
      body: researchSpec,
    });
  },
  async getProjectProgress(id: string): Promise<ResearchRunProgress> {
    return apiRequest<ResearchRunProgress>(`/api/research/projects/${id}/progress`);
  },
  githubLoginUrl(): string {
    return `${API_BASE_URL}/api/auth/github/login`;
  }
};
