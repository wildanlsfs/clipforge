"""
Burns word-by-word "pop" captions (CapCut-style) using libass. We
generate an .ass subtitle file with one word visible at a time -- far
simpler and more reliable to generate correctly than per-word karaoke
tags inside a single line, while looking effectively identical on
screen. Requires ffmpeg built with --enable-libass (the Docker image
installs it explicitly).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,Arial Black,{fontsize},&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,1,0,0,0,100,100,0,0,1,{outline},2,2,40,40,{marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(words: list[dict[str, Any]], out_path: str, video_w: int = 1080, video_h: int = 1920) -> str:
    fontsize = max(28, video_w // 14)
    outline = max(2, fontsize // 14)
    marginv = int(video_h * 0.18)

    lines = [ASS_HEADER.format(w=video_w, h=video_h, fontsize=fontsize, outline=outline, marginv=marginv)]
    for w in words:
        start, end = w["start"], w["end"]
        if end <= start:
            end = start + 0.15
        text = w["word"].strip().replace("\n", " ").upper()
        if not text:
            continue
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Word,,0,0,0,,{text}\n")

    Path(out_path).write_text("".join(lines), encoding="utf-8")
    return out_path


def burn_captions(video_path: str, ass_path: str, out_path: str) -> str:
    # escape for ffmpeg filter arg: colons and backslashes need escaping in the path
    escaped = ass_path.replace("\\", "\\\\").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"ass={escaped}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
