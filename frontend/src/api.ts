export interface Clip {
  id: string;
  project_id: string;
  start_s: number;
  end_s: number;
  aspect: string;
  title: string | null;
  hook_text: string | null;
  scores: Record<string, number> | null;
  total_score: number | null;
  output_path: string | null;
  status: string;
  error: string | null;
}

export interface Project {
  id: string;
  source_url: string;
  title: string | null;
  status: string;
  error: string | null;
  duration: number | null;
  created_at: number;
  clips: Clip[];
}

const BASE = "/api";

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${body}`);
  }
  return res.json();
}

export const api = {
  health: () => req<{ status: string; llm_enabled: boolean }>("/health"),
  listProjects: () => req<Project[]>("/projects"),
  getProject: (id: string) => req<Project>(`/projects/${id}`),
  createProject: (url: string, aspect: string, burnCaptions: boolean, cookies?: string) =>
    req<{ id: string }>("/projects", {
      method: "POST",
      body: JSON.stringify({
        url,
        aspect,
        burn_captions: burnCaptions,
        cookies: cookies?.trim() || null,
      }),
    }),
  deleteProject: (id: string) => req(`/projects/${id}`, { method: "DELETE" }),
  downloadUrl: (clipId: string) => `${BASE}/clips/${clipId}/download`,
};
