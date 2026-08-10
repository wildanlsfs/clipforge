import { useState } from "react";

const STEPS = [
  {
    title: "Paste a URL",
    body: "Drop in any YouTube link. Pick an aspect ratio (9:16 for Reels/Shorts/TikTok is the usual choice) and whether you want captions burned in, then hit Generate clips.",
  },
  {
    title: "It transcribes locally",
    body: "The source video downloads, then Whisper transcribes it word-by-word on the server — no audio ever leaves the box for this step.",
  },
  {
    title: "Moments get scored",
    body: "Each candidate segment is rated on 8 dimensions (hook, shock, humor, controversy, insight, emotion, energy, arc completion) — by an LLM if one's configured, otherwise a free built-in heuristic. Only strong scorers survive.",
  },
  {
    title: "Clips render",
    body: "Surviving segments get auto-reframed to follow the speaker's face, captions burn in if enabled, and finished MP4s show up below — ready to preview and download.",
  },
];

const FAQ: { q: string; a: string }[] = [
  {
    q: "A project failed with “Sign in to confirm you’re not a bot”",
    a: "YouTube is blocking the server's IP — common on VPS/cloud hosting, much less common on a home connection. The server admin needs to set a YTDLP_COOKIES environment variable with an exported YouTube cookies.txt. This is a server-side config issue, not something fixable from this page.",
  },
  {
    q: "A project finished with “No clip-worthy moments found”",
    a: "The scorer only keeps segments that score well across all 8 dimensions — short, flat, or low-energy source videos can legitimately produce nothing. Try a livelier or longer source.",
  },
  {
    q: "What's the difference between LLM and heuristic scoring?",
    a: "If the server has an LLM endpoint configured (shown by the absence of the amber warning banner above), an actual model reads the transcript and judges each moment. Without one, a free built-in heuristic scores on simpler signals like question density and pacing — no external cost, somewhat less discerning.",
  },
  {
    q: "Why does a clip have no burned-in captions even though I checked the box?",
    a: "Caption burning needs ffmpeg built with libass on the server. If that's missing, rendering itself would actually fail rather than silently skip captions — if you're seeing a render error, that's likely why.",
  },
  {
    q: "Can I use a video I already have, not YouTube?",
    a: "Not yet — currently only URLs that yt-dlp can resolve (YouTube and a number of other sites it supports) work. Direct file upload isn't built.",
  },
];

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <path d="M5 7.5L10 12.5L15 7.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-neutral-800 last:border-b-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 py-3 text-left text-sm font-medium text-neutral-200 hover:text-white"
      >
        {q}
        <ChevronIcon open={open} />
      </button>
      {open && <p className="pb-3 text-sm text-neutral-400">{a}</p>}
    </div>
  );
}

const SEEN_KEY = "clipforge_tutorial_seen";

export default function Tutorial() {
  const [open, setOpen] = useState(() => {
    try {
      return !localStorage.getItem(SEEN_KEY);
    } catch {
      return true;
    }
  });

  const toggle = () => {
    setOpen((o) => {
      const next = !o;
      try {
        if (next) localStorage.removeItem(SEEN_KEY);
        else localStorage.setItem(SEEN_KEY, "1");
      } catch {
        // localStorage unavailable (private browsing etc.) -- not worth failing over
      }
      return next;
    });
  };

  return (
    <div className="mb-8">
      <button
        onClick={toggle}
        className="flex items-center gap-1.5 text-sm font-medium text-neutral-400 hover:text-neutral-200"
      >
        <span className="flex h-5 w-5 items-center justify-center rounded-full border border-neutral-700 text-xs">?</span>
        How it works
        <ChevronIcon open={open} />
      </button>

      {open && (
        <div className="mt-3 rounded-2xl border border-neutral-800 bg-neutral-900/50 p-5">
          <ol className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <li key={s.title}>
                <div className="mb-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-accent/20 text-xs font-semibold text-accent">
                  {i + 1}
                </div>
                <p className="text-sm font-semibold text-neutral-100">{s.title}</p>
                <p className="mt-1 text-xs leading-relaxed text-neutral-400">{s.body}</p>
              </li>
            ))}
          </ol>

          <div className="mt-6 border-t border-neutral-800 pt-4">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-neutral-500">
              Common issues
            </p>
            <div>
              {FAQ.map((item) => (
                <FaqItem key={item.q} q={item.q} a={item.a} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
