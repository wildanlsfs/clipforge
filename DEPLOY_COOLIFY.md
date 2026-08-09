# Deploying ClipForge to Coolify

ClipForge ships as a plain `docker-compose.yml` with two services
(`backend`, `frontend`) — this maps directly onto Coolify's **Docker
Compose** resource type. No Coolify API access needed; this is all done
through the dashboard.

## 1. Push the code somewhere Coolify can pull from

Coolify deploys from a git remote (GitHub, GitLab, Gitea, or a plain git
URL). From inside `clipforge/`:

```bash
git init                      # already done if you got this from me pre-initialized
git add -A
git commit -m "Initial ClipForge build"
git remote add origin <your-repo-url>
git branch -M main
git push -u origin main
```

If you'd rather not use GitHub, Coolify also supports deploying from a
private git server it can reach, or pasting a public repo URL directly.

## 2. Create the resource in Coolify

1. **Projects → (your project) → + New Resource → Docker Compose**
2. Point it at your git repo, branch `main`, and the root of the repo
   (where `docker-compose.yml` lives).
3. Coolify will auto-detect `docker-compose.yml`. Leave the two services
   (`backend`, `frontend`) as detected.

## 3. Environment variables

In the resource's **Environment Variables** tab, set (all optional except
none are strictly required — the app runs with defaults / heuristic
scoring if you skip the LLM ones):

```
LLM_BASE_URL=https://<your-9router-endpoint>/v1
LLM_API_KEY=<your-9router-key>
LLM_MODEL=<model name your 9router endpoint accepts>
WHISPER_MODEL_SIZE=small
```

Coolify injects these into the compose file's `${VAR}` references
automatically — that's what the `${LLM_BASE_URL:-}` syntax in
`docker-compose.yml` is for.

> Don't have the exact 9router base URL/key on hand — check whatever
> dashboard/docs came with that proxy for the `base_url` and API key it
> expects; it's a drop-in for `OPENAI_BASE_URL`/`OPENAI_API_KEY`-style
> config, which is exactly what `LLM_BASE_URL`/`LLM_API_KEY` map to here.

## 4. Domain & port

- Only `frontend` needs a public domain — it's the one with `ports: -
  "3000:80"` in the compose file. In Coolify's **Domains** tab for the
  `frontend` service, set your domain and target port **80** (the
  container's internal nginx port, not host port 3000 — Coolify's proxy
  talks to the container directly).
- Leave `backend` domain-less. It's reached only via `frontend`'s nginx
  proxy (`/api/*` → `http://backend:8000`) over the internal compose
  network — it doesn't need to be internet-facing, which is the safer
  default since it has no auth layer of its own yet.

## 5. Persistent storage

The compose file already declares a named volume, `clipforge_data`,
mounted at `/data` in the backend container — this holds the SQLite DB,
downloaded source videos, and rendered clips. Coolify persists named
volumes across redeploys automatically; no extra action needed. If disk
fills up, `data/sources/*` (raw downloads) is the safe thing to prune
first — clips in `data/clips/*` are the actual deliverables.

## 6. First deploy

Click **Deploy**. First build will be slow (~5-10 min): it compiles
opencv-python-headless, faster-whisper's dependencies, downloads the
YuNet face model, and builds the frontend. Subsequent deploys reuse
Docker layer cache and are much faster unless `requirements.txt` /
`package.json` changed.

## 7. Sizing

- **CPU**: transcription and OpenCV reframing are CPU-bound. 2 vCPU
  minimum; 4 vCPU makes a real difference on longer source videos.
- **RAM**: 2GB minimum with `WHISPER_MODEL_SIZE=small`; bump to 4GB if you
  switch to `medium`/`large-v3`.
- **No GPU required.** Everything defaults to CPU (`int8` compute type for
  Whisper) so this runs fine on a standard Coolify VPS.

## Troubleshooting

- **Build fails fetching the YuNet model** — the Dockerfile's `curl` step
  for the face model has `|| echo ...` so a network hiccup during build
  won't fail the whole image; reframing just falls back to OpenCV's
  bundled Haar cascade (a bit less accurate, still works).
- **"No clip-worthy moments found"** — the scorer only keeps candidates
  scoring ~55%+ across all 8 dimensions. Very short or low-energy source
  videos may legitimately produce nothing; try a livelier source or lower
  `MIN_CLIP_SECONDS`.
- **Captions not rendering** — confirm the backend image built with
  `libass` (it's installed via `apt-get install ffmpeg` in the provided
  Dockerfile, which pulls in libass on Debian's ffmpeg package; don't swap
  the base image without checking this).
