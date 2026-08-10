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
        # Prefer H.264 (avc1) explicitly over AV1/VP9: confirmed live that
        # yt-dlp's plain "bestvideo[ext=mp4]" can resolve to an AV1-in-mp4
        # stream (itag 399) even when an H.264-in-mp4 one (itag 137) is
        # also available -- AV1 format availability/negotiation is flakier
        # server-side, and OpenCV's bundled ffmpeg (used downstream for
        # face-tracking) doesn't reliably decode AV1. H.264 is universally
        # supported by every tool in this pipeline. Falls through to any
        # codec, then to a fully unrestricted "best" if H.264 isn't offered
        # for this particular video.
        "format": (
            "bestvideo[vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]"
            "/bestvideo[height<=1080]+bestaudio"
            "/best[height<=1080]/best"
        ),
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
            try:
                info = ydl.extract_info(url, download=True)
            except yt_dlp.utils.DownloadError:
                _log_available_formats(ydl_opts, url)
                raise
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


def _log_available_formats(ydl_opts: dict[str, Any], url: str) -> None:
    """On a download failure, log what formats YouTube actually offered for
    this request -- without this, "Requested format not available" gives no
    way to tell whether that's a real format-selector bug (like the AV1
    issue this function was added to help catch) or YouTube just not
    returning anything for this IP/session, short of reproducing it by hand
    with a separate script every time."""
    try:
        probe_opts = {**ydl_opts, "format": None, "simulate": True, "quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(probe_opts) as probe:
            info = probe.extract_info(url, download=False)
        formats = info.get("formats", []) if info else []
        summary = [
            f"{f.get('format_id')}:{f.get('ext')}:{f.get('vcodec')}:{f.get('height')}p"
            for f in formats
        ]
        log.error("download failed; %d formats were actually available: %s", len(formats), summary)
    except Exception:  # noqa: BLE001
        log.exception("download failed, and the diagnostic re-probe also failed")
