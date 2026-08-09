"""Per-clip render pipeline: reframe to vertical -> burn captions -> final mp4."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from . import captioner, reframer
from .config import settings


def _words_in_range(transcript: dict[str, Any], start_s: float, end_s: float) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for seg in transcript.get("segments", []):
        for w in seg.get("words") or []:
            if w["start"] >= start_s and w["end"] <= end_s + 0.25:
                words.append(
                    {"start": w["start"] - start_s, "end": w["end"] - start_s, "word": w["word"]}
                )
    return words


def render_clip(
    source_path: str,
    transcript: dict[str, Any],
    project_id: str,
    clip_id: str,
    start_s: float,
    end_s: float,
    aspect: str = "9:16",
    burn_captions: bool = True,
) -> str:
    clips_dir = settings.DATA_DIR / "clips" / project_id
    clips_dir.mkdir(parents=True, exist_ok=True)
    final_path = str(clips_dir / f"{clip_id}.mp4")

    with tempfile.TemporaryDirectory() as tmp:
        reframed_path = str(Path(tmp) / f"{clip_id}_reframed.mp4")
        reframer.render_reframed(source_path, start_s, end_s, reframed_path, aspect=aspect)

        if not burn_captions:
            Path(reframed_path).replace(final_path)
            return final_path

        words = _words_in_range(transcript, start_s, end_s)
        if not words:
            Path(reframed_path).replace(final_path)
            return final_path

        ass_path = str(Path(tmp) / f"{clip_id}.ass")
        aw, ah = reframer.ASPECTS.get(aspect, (9, 16))
        out_w = 1080 if aw < ah else int(1080 * aw / ah)
        out_h = int(1080 * ah / aw) if aw < ah else 1080
        captioner.build_ass(words, ass_path, video_w=out_w, video_h=out_h)
        captioner.burn_captions(reframed_path, ass_path, final_path)

    return final_path
