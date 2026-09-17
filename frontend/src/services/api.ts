const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) }, ...options });
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

export type Summary = { total_projects: number; investigation_signals: number; critical_signals: number; open_investigations: number; data_quality_issues: number; label: string; official: boolean | null };
export type Project = { id: number; work_id: string; state: string; district: string; constituency: string; work_description: string; work_type: string; sanctioned_amount: number; expenditure: number; physical_progress: number; start_date?: string; completion_date?: string; status: string; contractor: string; implementing_agency: string; is_synthetic: boolean };
export type Signal = { id: number; signal_id: string; work_id: string; detector_type: string; priority: string; anomaly_score: number; title: string; observed_evidence: Record<string, unknown>; baseline: Record<string, unknown>; explanation: string; possible_explanation: string[]; recommended_verification: string[]; status: string; source: Record<string, unknown>; metadata_json: Record<string, unknown> };
export type Investigation = { id: number; investigation_id: string; work_id: string; priority: string; status: string; notes: string };
export type MP = { id: number; state: string; pc: string; constituency: string; mp_name: string; party: string; associated_area: string };
export type DataSource = { source: string; type: string; status: string; official: boolean; record_count: number };
export type Evidence = { work_id: string; source_data: Project; signals: Signal[]; evidence_links: Array<{ label: string; value: string; source: string; explanation: string }> };

export const api = {
  summary: () => request<Summary>("/dashboard/summary"),
  projects: () => request<Project[]>("/projects"),
  alerts: () => request<Signal[]>("/alerts"),
  signal: (id: string) => request<Signal>(`/alerts/${id}`),
  projectSignals: (id: string) => request<Signal[]>(`/projects/${id}/signals`),
  evidence: (id: string) => request<unknown>(`/projects/${id}/evidence`),
  sources: () => request<DataSource[]>("/data-sources"),
  quality: () => request<Signal[]>("/data-quality"),
  network: () => request<{ nodes: Array<Record<string, string>>; edges: Array<Record<string, string>>; label: string }>("/network"),
  investigations: () => request<Investigation[]>("/investigations"),
  updateSignal: (id: string, status: string) => request<Signal>(`/alerts/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }),
  updateInvestigation: (id: string, status: string) => request<Investigation>(`/investigations/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  analyze: () => request<{ signals_created: number }>("/analyze", { method: "POST" }),
  mps: () => request<MP[]>("/admin/mps"),
  createMp: (mp: Omit<MP, "id">) => request<MP>("/admin/mps", { method: "POST", body: JSON.stringify(mp) }),
  updateMp: (id: number, mp: Omit<MP, "id">) => request<MP>(`/admin/mps/${id}`, { method: "PUT", body: JSON.stringify(mp) }),
  deleteMp: (id: number) => request<{ deleted: boolean }>(`/admin/mps/${id}`, { method: "DELETE" }),
  importMps: (mps: Array<Omit<MP, "id">>) => request<{ imported: number }>("/admin/import/mps", { method: "POST", body: JSON.stringify(mps) }),
  exportMps: () => request<MP[]>("/admin/export/mps"),
  createProject: (project: Omit<Project, "id">) => request<Project>("/admin/projects", { method: "POST", body: JSON.stringify(project) }),
  updateProject: (id: number, project: Omit<Project, "id">) => request<Project>(`/admin/projects/${id}`, { method: "PUT", body: JSON.stringify(project) }),
  deleteProject: (id: number) => request<{ deleted: boolean }>(`/admin/projects/${id}`, { method: "DELETE" }),
  exportProjects: () => request<Project[]>("/admin/export/projects"),
};