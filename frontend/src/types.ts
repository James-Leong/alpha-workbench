export type User = {
  id: number;
  email: string;
  username: string;
  csrf_token: string;
};

export type ResearchProjectSummary = {
  id: number;
  title: string;
  idea_text: string;
  status: string;
  summary: string;
  created_at: string;
  updated_at: string;
  latest_run_id?: number | null;
  current_step: string;
  progress_events: ProgressEvent[];
};

export type ResearchProjectDetail = ResearchProjectSummary & {
  report_markdown: string;
  metrics_summary: Record<string, unknown>;
  trace: Record<string, unknown>;
};

export type ProgressEvent = {
  step: string;
  status: string;
  message: string;
  time?: string;
};

export type ResearchSpecUpdate = {
  universe?: string;
  rebalance_frequency?: string;
  holding_period?: string;
  transaction_cost_bps?: number;
  benchmark?: string;
  initial_cash?: number;
  sample_window_start?: string;
  sample_window_end?: string;
  filters?: string[];
};

export type ResearchRunProgress = {
  project_id: number;
  run_id?: number | null;
  status: string;
  current_step: string;
  progress_events: ProgressEvent[];
};
