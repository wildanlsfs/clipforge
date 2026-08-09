import { useEffect, useState, useCallback } from "react";
import { api, Project, Clip } from "./api";

const ACTIVE_STATUSES = new Set(["queued", "downloading", "transcribing", "scoring", "rendering"]);

const STATUS_LABEL: Record<string, string> = {
  queued: "Queued",
  downloading: "Downloading source",
  transcribing: "Transcribing (Whisper)",
  scoring: "Finding viral moments",
  rendering: "Rendering clips",
  done: "Done",
  error: "Error",
};

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-24 shrink-0 capitalize text-neutral-400">{label.replace("_", " ")}</span>
      <div className="h-1.5 flex-1 rounded-full bg-neutral-800">
        <div
          className="h-1.5 rounded-full bg-accent"
          style={{ width: `${Math.min(100, (value / 10) * 100)}%` }}
        />
      </div>
      <span className="w-6 text-right text-neutral-500">{value.toFixed(0)}</span>
    </div>
  );
}

function ClipCard({ clip }: { clip: Clip }) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-medium text-neutral-100">{clip.title || "Untitled clip"}</p>
          <p className="mt-1 text-xs text-neutral-500">
            {clip.start_s.toFixed(0)}s – {clip.end_s.toFixed(0)}s · {clip.aspect}
          </p>
        </div>
        {clip.total_score != null && (
          <span className="shrink-0 rounded-full bg-accent/20 px-2 py-1 text-xs font-semibold text-accent">
            {clip.total_score.toFixed(0)}/80
          </span>
        )}
      </div>

      {clip.hook_text && (
        <p className="mt-2 line-clamp-2 text-sm italic text-neutral-400">"{clip.hook_text}"</p>
      )}

      {clip.scores && (
        <div className="mt-3 space-y-1">
          {Object.entries(clip.scores).map(([k, v]) => (
            <ScoreBar key={k} label={k} value={v} />
          ))}
        </div>
      )}

      <div className="mt-3">
        {clip.status === "done" && clip.output_path ? (
          <div className="space-y-2">
            <video controls className="w-full max-h-72 rounded-lg bg-black" src={api.downloadUrl(clip.id)} />
            <a
              href={api.downloadUrl(clip.id)}
              download
              className="inline-block rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/80"
            >
              Download MP4
            </a>
          </div>
        ) : clip.status === "error" ? (
          <p className="text-sm text-red-400">Render failed: {clip.error}</p>
        ) : (
          <p className="text-sm text-neutral-500">Rendering…</p>
        )}
      </div>
    </div>
  );
}

function ProjectCard({ project, onDelete }: { project: Project; onDelete: (id: string) => void }) {
  const isActive = ACTIVE_STATUSES.has(project.status);
  return (
    <div className="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-semibold text-neutral-100">{project.title || project.source_url}</p>
          <p className="truncate text-xs text-neutral-500">{project.source_url}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-medium ${
              project.status === "done"
                ? "bg-green-500/20 text-green-400"
                : project.status === "error"
                ? "bg-red-500/20 text-red-400"
                : "bg-accent/20 text-accent"
            }`}
          >
            {isActive && (
              <span className="mr-1.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
            )}
            {STATUS_LABEL[project.status] || project.status}
          </span>
          <button
            onClick={() => onDelete(project.id)}
            className="rounded-lg px-2 py-1 text-xs text-neutral-500 hover:bg-neutral-800 hover:text-neutral-300"
          >
            Delete
          </button>
        </div>
      </div>

      {project.status === "error" && project.error && (
        <p className="mt-2 text-sm text-red-400">{project.error}</p>
      )}

      {project.clips?.length > 0 && (
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {project.clips.map((c) => (
            <ClipCard key={c.id} clip={c} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [url, setUrl] = useState("");
  const [aspect, setAspect] = useState("9:16");
  const [burnCaptions, setBurnCaptions] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [llmEnabled, setLlmEnabled] = useState<boolean | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await Promise.all(
        (await api.listProjects()).map((p) => api.getProject(p.id))
      );
      setProjects(list);
    } catch (e) {
      // transient network errors while polling shouldn't nuke the UI
      console.error(e);
    }
  }, []);

  useEffect(() => {
    api.health().then((h) => setLlmEnabled(h.llm_enabled)).catch(() => setLlmEnabled(false));
    refresh();
    const hasActive = () => projects.some((p) => ACTIVE_STATUSES.has(p.status));
    const interval = setInterval(() => {
      refresh();
    }, 3000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    setSubmitting(true);
    setErr(null);
    try {
      await api.createProject(url.trim(), aspect, burnCaptions);
      setUrl("");
      await refresh();
    } catch (e: any) {
      setErr(e.message || "Failed to submit");
    } finally {
      setSubmitting(false);
    }
  };

  const onDelete = async (id: string) => {
    await api.deleteProject(id);
    setProjects((p) => p.filter((x) => x.id !== id));
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">
          Clip<span className="text-accent">Forge</span>
        </h1>
        <p className="mt-1 text-neutral-400">
          Paste a YouTube URL → local Whisper transcription → viral-moment scoring → auto-reframed,
          captioned vertical clips. Self-hosted, no per-clip fees.
        </p>
        {llmEnabled === false && (
          <p className="mt-2 text-xs text-amber-400">
            No LLM endpoint configured — using the free heuristic scorer. Set LLM_BASE_URL / LLM_API_KEY
            to enable LLM-ranked clips.
          </p>
        )}
      </header>

      <form onSubmit={onSubmit} className="mb-8 rounded-2xl border border-neutral-800 bg-neutral-900/50 p-5">
        <label className="mb-1 block text-sm font-medium text-neutral-300">YouTube URL</label>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.youtube.com/watch?v=..."
          className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm outline-none focus:border-accent"
        />
        <div className="mt-3 flex flex-wrap items-center gap-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-neutral-400">Aspect ratio</label>
            <select
              value={aspect}
              onChange={(e) => setAspect(e.target.value)}
              className="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm"
            >
              <option value="9:16">9:16 (Reels/Shorts/TikTok)</option>
              <option value="1:1">1:1 (Square)</option>
              <option value="4:5">4:5 (Instagram)</option>
              <option value="16:9">16:9 (Landscape)</option>
            </select>
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm text-neutral-300">
            <input
              type="checkbox"
              checked={burnCaptions}
              onChange={(e) => setBurnCaptions(e.target.checked)}
              className="rounded border-neutral-700 bg-neutral-950"
            />
            Burn in captions
          </label>
          <button
            type="submit"
            disabled={submitting}
            className="ml-auto mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent/80 disabled:opacity-50"
          >
            {submitting ? "Submitting…" : "Generate clips"}
          </button>
        </div>
        {err && <p className="mt-2 text-sm text-red-400">{err}</p>}
      </form>

      <div className="space-y-5">
        {projects.length === 0 && (
          <p className="text-center text-neutral-500">No projects yet — paste a URL above to get started.</p>
        )}
        {projects.map((p) => (
          <ProjectCard key={p.id} project={p} onDelete={onDelete} />
        ))}
      </div>
    </div>
  );
}
