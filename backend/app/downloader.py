"""yt-dlp wrapper -- downloads source video + metadata, free/local."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yt_dlp

from .config import settings

log = logging.getLogger("clipforge.downloader")


def download_source(url: str, project_id: str) -> dict[str, Any]:
    """Download a YouTube (or any yt-dlp-supported) URL to data/sources/<id>.mp4.

    Returns metadata dict: {path, title, duration}.
    """
    out_dir = settings.DATA_DIR / "sources"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(out_dir / f"{project_id}.%(ext)s")

    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": out_template,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "writesubtitles": False,
        "socket_timeout": 30,
        "retries": 3,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
        if not path.exists():
            # merge_output_format may have changed the extension
            path = path.with_suffix(".mp4")

    return {
        "path": str(path),
        "title": info.get("title") or "Untitled",
        "duration": float(info.get("duration") or 0.0),
    }
