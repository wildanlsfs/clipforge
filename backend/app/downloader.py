"""yt-dlp wrapper -- downloads source video + metadata, free/local."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yt_dlp

from .config import settings

log = logging.getLogger("clipforge.downloader")


def _extractor_args(player_clients: list[str]) -> dict[str, dict[str, list[str]]]:
    """Builds the yt-dlp extractor_args dict for a download attempt: which
    player client identities to try, plus (if configured) the PO-token
    provider's address so those clients get real video/audio formats back
    instead of the storyboard-only formats YouTube silently substitutes
    when it wants a token yt-dlp doesn't have. Requires the
    bgutil-ytdlp-pot-provider package (see requirements.txt) to be
    installed -- yt-dlp auto-detects it as a plugin, this just tells it
    where the companion HTTP server (docker-compose.yml's `pot-provider`
    service) is listening."""
    args: dict[str, dict[str, list[str]]] = {"youtube": {"player_client": player_clients}}
    if settings.POT_PROVIDER_URL.strip():
        args["youtubepot-bgutilhttp"] = {"base_url": [settings.POT_PROVIDER_URL.strip()]}
    return args


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

    # Format selector: Prefer H.264 (avc1) explicitly over AV1/VP9 (OpenCV
    # face-tracking compatibility), but fall back gracefully to any available video+audio
    # streams or best single stream.
    format_selector = (
        "bestvideo[vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]"
        "/bestvideo[height<=1080]+bestaudio"
        "/bestvideo+bestaudio"
        "/best[height<=1080]"
        "/best"
    )

    per_request_cookie_path: Path | None = None
    cookie_path_to_use: str | None = None

    if cookies and cookies.strip():
        per_request_cookie_path = settings.TMP_DIR / f"{project_id}_cookies.txt"
        per_request_cookie_path.write_text(cookies, encoding="utf-8")
        cookie_path_to_use = str(per_request_cookie_path)
    else:
        cookie_path_to_use = settings.cookies_path()
        if not cookie_path_to_use:
            log.warning(
                "no cookies (per-request or YTDLP_COOKIES fallback) -- YouTube "
                "frequently blocks unauthenticated requests from datacenter/VPS "
                "IPs with a 'Sign in to confirm you're not a bot' or format error"
            )

    # Common options shared by every attempt below. Notably includes
    # `proxy`, if configured: confirmed live that a *valid, logged-in*
    # cookie session still gets "Sign in to confirm you're not a bot"
    # 100% of the time from a flagged VPS IP while working fine from a
    # residential one, so cookies/client-spoofing alone can't fix that
    # class of block -- only routing off the flagged IP does.
    base_opts: dict[str, Any] = {
        "format": format_selector,
        "outtmpl": out_template,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "writesubtitles": False,
        "socket_timeout": 30,
        "retries": 3,
    }
    if settings.YTDLP_PROXY.strip():
        base_opts["proxy"] = settings.YTDLP_PROXY.strip()

    # Player client fallback strategies:
    # 'web_creator' (YouTube Studio) + 'web' + 'android' + 'ios' provides maximum compatibility
    # on datacenter/VPS IPs and with browser cookies.
    attempts: list[dict[str, Any]] = []

    if cookie_path_to_use:
        # Pass 1: Try with cookies + web_creator/web/android/ios clients
        attempts.append({
            **base_opts,
            "cookiefile": cookie_path_to_use,
            "extractor_args": _extractor_args(["web_creator", "web", "android", "ios"]),
        })

    # Pass 2 / Fallback: Unauthenticated pass with web_creator, android, ios clients
    # (Fixes cases where provided cookies were expired/invalid/blocked by YouTube)
    attempts.append({
        **base_opts,
        "extractor_args": _extractor_args(["web_creator", "android", "ios"]),
    })

    last_exc: Exception | None = None
    info: dict[str, Any] | None = None
    path: Path | None = None

    try:
        for idx, ydl_opts in enumerate(attempts):
            has_cookies = "cookiefile" in ydl_opts
            log.info("Attempting YouTube download (attempt %d/%d, cookies=%s)", idx + 1, len(attempts), has_cookies)
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    path = Path(ydl.prepare_filename(info))
                    if not path.exists():
                        # merge_output_format may have changed the extension
                        path = path.with_suffix(".mp4")
                    # If download succeeded, break out of retry loop
                    break
            except yt_dlp.utils.DownloadError as exc:
                last_exc = exc
                log.warning("yt-dlp download attempt %d failed: %s", idx + 1, exc)
                _log_available_formats(ydl_opts, url)

        if info is None or path is None:
            err_msg = str(last_exc) if last_exc else "Download failed"
            if "Requested format is not available" in err_msg or "Sign in to confirm" in err_msg or "Please sign in" in err_msg:
                proxy_hint = (
                    " Even valid cookies can't beat this from a flagged VPS/datacenter IP "
                    "-- if this keeps happening on every video, set YTDLP_PROXY to route "
                    "through a residential/mobile IP instead."
                    if not settings.YTDLP_PROXY.strip()
                    else ""
                )
                raise RuntimeError(
                    f"YouTube blocked format extraction or requires login on this server. "
                    f"If you provided cookies, they may be expired or invalid.{proxy_hint} "
                    f"Please update your YouTube cookies (cookies.txt) or try a different video URL. Original error: {err_msg}"
                ) from last_exc
            raise last_exc or RuntimeError("Download failed after all attempts")

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
    with a separate script every time.

    Confirmed live that setting format=None here still isn't enough: yt-dlp
    falls back to its own default selector and re-raises the exact same
    "Requested format not available" error if literally nothing is
    downloadable, which crashed this diagnostic itself instead of reporting
    anything useful. process=False sidesteps format *selection* entirely --
    it returns the raw extracted formats list without trying to pick one,
    so this can't fail the same way the real download attempt did."""
    try:
        probe_opts = {**ydl_opts, "simulate": True, "quiet": True, "no_warnings": True}
        probe_opts.pop("format", None)
        with yt_dlp.YoutubeDL(probe_opts) as probe:
            info = probe.extract_info(url, download=False, process=False)
        formats = info.get("formats", []) if info else []
        summary = [
            f"{f.get('format_id')}:{f.get('ext')}:{f.get('vcodec')}:{f.get('height')}p"
            for f in formats
        ]
        log.error("download failed; %d formats were actually available: %s", len(formats), summary)
    except Exception:  # noqa: BLE001
        log.exception("download failed, and the diagnostic re-probe also failed")

