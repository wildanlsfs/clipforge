"""
Local transcription via faster-whisper (CTranslate2). Runs entirely on
CPU by default -- no external API, no per-minute billing. Word-level
timestamps are kept so captions can be burned in word-by-word and so
clip boundaries snap to word edges instead of arbitrary cut points.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from .config import settings

log = logging.getLogger("clipforge.transcriber")

_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from faster_whisper import WhisperModel

                log.info(
                    "loading whisper model=%s device=%s compute=%s",
                    settings.WHISPER_MODEL_SIZE,
                    settings.WHISPER_DEVICE,
                    settings.WHISPER_COMPUTE_TYPE,
                )
                _model = WhisperModel(
                    settings.WHISPER_MODEL_SIZE,
                    device=settings.WHISPER_DEVICE,
                    compute_type=settings.WHISPER_COMPUTE_TYPE,
                )
    return _model


def transcribe(video_path: str) -> dict[str, Any]:
    """Returns {language, segments: [{start, end, text, words: [{start,end,word}]}]}"""
    model = _get_model()
    segments_iter, info = model.transcribe(
        video_path,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    segments = []
    for seg in segments_iter:
        words = [
            {"start": w.start, "end": w.end, "word": w.word.strip()}
            for w in (seg.words or [])
        ]
        segments.append(
            {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
                "words": words,
            }
        )

    return {"language": info.language, "segments": segments}
