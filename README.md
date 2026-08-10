# ClipForge

Paste a YouTube URL → get back auto-reframed, captioned, vertical clips
picked for virality. Self-hosted, no subscription, no per-clip fee.

Built after studying [OpenClip](https://github.com/aionixOS/Openclip),
[Chopify](https://github.com/mehbul/chopify), and
[AutoClip](https://github.com/artbyjazi/autoclip) — same idea, own
implementation:

| From | Idea reused |
|---|---|
| OpenClip | web UI + SQLite project/clip history, local-first design |
| Chopify | 8-dimension virality rubric (hook/shock/humor/controversy/insight/emotion/energy/arc), burnt-in word-by-word captions |
| AutoClip | FastAPI + Docker Compose architecture, any-OpenAI-compatible-endpoint LLM config, word-index-not-timestamp trick for reliable LLM output |

## How it works

```
YouTube URL
   │  yt-dlp
   ▼
source video ──────────────────────────────┐
   │  faster-whisper (local, free)         │
   ▼                                        │
word-level transcript                       │
   │  LLM (optional) or heuristic scorer    │
   ▼                                        │
ranked clip candidates (start/end + scores) │
   │  OpenCV face-tracked crop ─────────────┘
   ▼
vertical clip (silent)
   │  ffmpeg + libass burnt-in captions
   ▼
final MP4 ── served to the web UI for preview/download
```

Everything runs locally in the container except two things: the YouTube
download itself, and (optionally) a call to an LLM API for ranking clips.
**The LLM is optional.** With no key configured, ClipForge falls back to a
built-in heuristic scorer (question/superlative density, pause-bounded
sentence completeness, speaking-rate energy) — zero external cost, works
out of the box.

When you do want LLM ranking, point it at **any OpenAI-compatible
endpoint** — 9router, OpenRouter, Groq, a local Ollama/vLLM proxy,
whatever you already have — via `LLM_BASE_URL` / `LLM_API_KEY`. There's no
hardcoded OpenAI or Anthropic dependency.

## Stack

- **Backend**: FastAPI (Python 3.11), SQLite, yt-dlp, faster-whisper, OpenCV
  (YuNet face detection with Haar-cascade fallback), ffmpeg/libass
- **Frontend**: React + Vite + Tailwind, served by nginx (also reverse-proxies
  `/api` to the backend so the app is a single origin)
- **Packaging**: two Dockerfiles + one `docker-compose.yml`, ready to hand to
  Coolify as a "Docker Compose" resource

## Local development

```bash
cp .env.example .env        # fill in LLM_* if you want LLM ranking; optional
docker compose up --build
# frontend: http://localhost:3000
```

First run will download the faster-whisper model (~500MB for `small`) and the
YuNet face model on image build — subsequent runs are fast.

### Running without Docker (dev loop)

```bash
# backend
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ffmpeg -version   # must be installed on the host, with libass -- see note below
uvicorn app.main:app --reload --port 8000

# frontend (separate shell)
cd frontend
npm install
BACKEND_URL=http://localhost:8000 npm run dev   # http://localhost:5173
```

> **macOS + Homebrew note:** Homebrew's plain `ffmpeg` formula deliberately
> excludes libass (no caption burning) and libfreetype (no `drawtext`
> either) — confirmed by hitting this directly: caption burning failed with
> a filter error against a stock `brew install ffmpeg`. Install
> `brew install ffmpeg-full` instead (keg-only, won't conflict with a
> regular `ffmpeg` other projects may depend on) and point the backend at
> it: `FFMPEG_BIN=/usr/local/opt/ffmpeg-full/bin/ffmpeg`. Not an issue in
> Docker — Debian's apt `ffmpeg` package includes libass by default.

## Configuration reference

| Env var | Default | Notes |
|---|---|---|
| `LLM_BASE_URL` | *(empty)* | e.g. your 9router `.../v1` endpoint. Empty = heuristic scorer only. |
| `LLM_API_KEY` | *(empty)* | key for the above |
| `LLM_MODEL` | `gpt-4o-mini` | any model name your endpoint accepts |
| `WHISPER_MODEL_SIZE` | `small` | `tiny`/`base`/`small`/`medium`/`large-v3` — bigger = more accurate, slower |
| `WHISPER_DEVICE` | `cpu` | set `cuda` if you attach a GPU-enabled base image |
| `MIN_CLIP_SECONDS` / `MAX_CLIP_SECONDS` | `20` / `90` | candidate clip length bounds |
| `MAX_CLIPS_PER_VIDEO` | `6` | cap on rendered clips per source video |
| `CORS_ORIGINS` | `*` | tighten this once you have a real domain |

## Deploying to Coolify

See [`DEPLOY_COOLIFY.md`](./DEPLOY_COOLIFY.md).

## Current scope / roadmap

Shipped: download, local transcription, LLM-or-heuristic virality scoring,
face-tracked reframing to 9:16/1:1/4:5/16:9, burnt-in word-by-word captions,
project/clip history, web UI.

Not yet built (flagged so expectations are clear, happy to add on request):
multi-speaker diarization / active-speaker switching between multiple faces,
layout classification (tutorial vs. podcast vs. panel), multiple caption
style presets, in-browser clip trimming before export, direct posting to
social platforms.

## License

MIT
