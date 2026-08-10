from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import db, jobs
from .config import settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("clipforge.main")

app = FastAPI(title="ClipForge", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()
    log.info("ClipForge ready. LLM scoring enabled=%s", settings.LLM_ENABLED)


class CreateProjectRequest(BaseModel):
    url: str = Field(..., description="YouTube (or yt-dlp supported) URL")
    aspect: str = Field("9:16", pattern="^(9:16|1:1|16:9|4:5)$")
    burn_captions: bool = True
    cookies: str | None = Field(
        None,
        description=(
            "Optional: raw Netscape-format cookies.txt content from the "
            "caller's own browser, so multiple people sharing one instance "
            "each authenticate YouTube downloads as themselves. Used only "
            "for this job's download, never stored in the database. Falls "
            "back to the server's YTDLP_COOKIES env var if omitted."
        ),
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "llm_enabled": settings.LLM_ENABLED}


@app.post("/api/projects")
def create_project(req: CreateProjectRequest):
    if not req.url.strip():
        raise HTTPException(400, "url is required")
    project_id = db.create_project(req.url.strip())
    jobs.submit(project_id, req.url.strip(), req.aspect, req.burn_captions, cookies=req.cookies)
    return {"id": project_id}


@app.get("/api/projects")
def list_projects():
    return db.list_projects()


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "project not found")
    project.pop("transcript", None)  # can be large; omit from list/detail payloads
    project["clips"] = db.list_clips(project_id)
    return project


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "project not found")
    db.delete_project(project_id)
    return {"ok": True}


@app.get("/api/clips/{clip_id}/download")
def download_clip(clip_id: str):
    clip = db.get_clip(clip_id)
    if not clip or not clip.get("output_path"):
        raise HTTPException(404, "clip not found or not rendered yet")
    path = Path(clip["output_path"])
    if not path.exists():
        raise HTTPException(404, "clip file missing on disk")
    return FileResponse(path, media_type="video/mp4", filename=f"{clip.get('title') or clip_id}.mp4")
