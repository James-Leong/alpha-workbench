export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    completed: "已完成",
    running: "生成中",
    failed: "失败"
  };
  return labels[status] ?? status;
}
