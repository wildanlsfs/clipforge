"""yt-dlp wrapper -- downloads source video + metadata, free/local."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yt_dlp

from .config import settings

log = logging.getLogger("clipforge.downloader")


def download_source(url: str, project_id: str, cookies: str | None = None) -> dict[str, Any]:
    """Download a YouTube (or any yt-dlp-supported) URL to data/sources/<id>.mp4.

    `cookies`, if given, is the raw content of a Netscape-format cookies.txt
    export from the *requesting user's own browser* -- multiple people can
    share one ClipForge instance and each authenticate downloads as
    themselves rather than one shared server-wide identity. It's written to
    a per-project temp file only for the duration of this download and
    deleted immediately after (success or failure) -- never persisted to
    the database or kept around longer than the single yt-dlp call needs
    it. Falls back to the server-wide YTDLP_COOKIES env var if the caller
    didn't supply their own.
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

    per_request_cookie_path: Path | None = None
    if cookies and cookies.strip():
        per_request_cookie_path = settings.TMP_DIR / f"{project_id}_cookies.txt"
        per_request_cookie_path.write_text(cookies, encoding="utf-8")
        ydl_opts["cookiefile"] = str(per_request_cookie_path)
    else:
        fallback = settings.cookies_path()
        if fallback:
            ydl_opts["cookiefile"] = fallback
        else:
            log.warning(
                "no cookies (per-request or YTDLP_COOKIES fallback) -- YouTube "
                "frequently blocks unauthenticated requests from datacenter/VPS "
                "IPs with a 'Sign in to confirm you're not a bot' error"
            )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
            if not path.exists():
                # merge_output_format may have changed the extension
                path = path.with_suffix(".mp4")
    finally:
        if per_request_cookie_path is not None:
            per_request_cookie_path.unlink(missing_ok=True)

    return {
        "path": str(path),
        "title": info.get("title") or "Untitled",
        "duration": float(info.get("duration") or 0.0),
    }
