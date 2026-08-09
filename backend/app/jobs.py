"""
Simple in-process job pipeline. This is a single-node, self-hosted
tool -- a thread pool + SQLite status column is enough; no Redis/Celery
needed. Each stage updates the project/clip row so the frontend can
poll status.
"""
from __future__ import annotations

import logging
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import clipper, db, downloader, scorer, transcriber

log = logging.getLogger("clipforge.jobs")

_executor = ThreadPoolExecutor(max_workers=2)


def submit(project_id: str, url: str, aspect: str, burn_captions: bool) -> None:
    _executor.submit(_run_pipeline, project_id, url, aspect, burn_captions)


def _run_pipeline(project_id: str, url: str, aspect: str, burn_captions: bool) -> None:
    try:
        db.update_project(project_id, status="downloading")
        meta = downloader.download_source(url, project_id)
        db.update_project(
            project_id,
            title=meta["title"],
            source_path=meta["path"],
            duration=meta["duration"],
        )

        db.update_project(project_id, status="transcribing")
        transcript = transcriber.transcribe(meta["path"])
        db.update_project(project_id, transcript=transcript)

        db.update_project(project_id, status="scoring")
        candidates = scorer.score_transcript(transcript)
        if not candidates:
            db.update_project(project_id, status="done", error="No clip-worthy moments found above the score threshold")
            return

        db.update_project(project_id, status="rendering")
        for cand in candidates:
            clip_id = db.create_clip(
                project_id,
                cand["start"],
                cand["end"],
                aspect=aspect,
                title=cand["title"],
                hook_text=cand["hook_text"],
                scores=cand["scores"],
                total_score=cand["total_score"],
            )
            try:
                db.update_clip(clip_id, status="rendering")
                out_path = clipper.render_clip(
                    meta["path"],
                    transcript,
                    project_id,
                    clip_id,
                    cand["start"],
                    cand["end"],
                    aspect=aspect,
                    burn_captions=burn_captions,
                )
                db.update_clip(clip_id, status="done", output_path=out_path)
            except Exception as exc:  # noqa: BLE001
                log.exception("clip render failed for %s", clip_id)
                db.update_clip(clip_id, status="error", error=str(exc))

        db.update_project(project_id, status="done")
    except Exception as exc:  # noqa: BLE001
        log.error("pipeline failed for project %s:\n%s", project_id, traceback.format_exc())
        db.update_project(project_id, status="error", error=str(exc))
