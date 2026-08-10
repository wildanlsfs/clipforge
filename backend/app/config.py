"""
Central configuration, entirely env-driven so the same image runs
locally (docker-compose) or on Coolify (env vars set in the UI).

LLM_* points at any OpenAI-compatible endpoint -- OpenRouter, Groq,
9router, a local vLLM/Ollama proxy, whatever. There is no hardcoded
OpenAI/Anthropic dependency and no paid API is required to run the
core pipeline (download/transcribe/reframe/caption all run locally).
The LLM is only used to *rank* transcript segments for virality; if
no key is configured the app falls back to a heuristic scorer.
"""
from __future__ import annotations

import os
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # --- storage ---
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/data"))
    TMP_DIR: Path = Path(os.getenv("TMP_DIR", "/data/tmp"))
    DB_PATH: Path = Path(os.getenv("DB_PATH", str(DATA_DIR / "clipforge.db")))

    # --- LLM (OpenAI-compatible; e.g. 9router) ---
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "").rstrip("/")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_ENABLED: bool = bool(LLM_BASE_URL and LLM_API_KEY)

    # --- whisper (local, free) ---
    WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "small")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")
    WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    # --- clip generation ---
    MIN_CLIP_SECONDS: int = int(os.getenv("MIN_CLIP_SECONDS", "20"))
    MAX_CLIP_SECONDS: int = int(os.getenv("MAX_CLIP_SECONDS", "90"))
    MAX_CLIPS_PER_VIDEO: int = int(os.getenv("MAX_CLIPS_PER_VIDEO", "6"))
    DEFAULT_ASPECT: str = os.getenv("DEFAULT_ASPECT", "9:16")

    # --- ffmpeg ---
    # Override if the system "ffmpeg" on PATH lacks libass (caption burning
    # will fail with a filter error otherwise). The Docker image's ffmpeg
    # (apt, Debian) has libass by default, so this is normally left alone;
    # it exists for local/native dev on machines with a stripped ffmpeg
    # build (e.g. Homebrew's plain `ffmpeg` formula, which excludes it --
    # use `ffmpeg-full` there instead and point this at its binary).
    FFMPEG_BIN: str = os.getenv("FFMPEG_BIN", "ffmpeg")

    # --- server ---
    CORS_ORIGINS: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
    ]
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "500"))

    def ensure_dirs(self) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.TMP_DIR.mkdir(parents=True, exist_ok=True)
        (self.DATA_DIR / "clips").mkdir(parents=True, exist_ok=True)
        (self.DATA_DIR / "sources").mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
