"""
Smart reframing: landscape source -> vertical (or square) output that
follows the speaker instead of a dumb center-crop.

Approach (kept deliberately simple/robust over "clever"):
  1. Sample frames across the clip with OpenCV, detect faces with YuNet
     (falls back to Haar cascade if the YuNet ONNX model isn't present
     -- e.g. offline Docker build without the model baked in).
  2. Track the largest/most-central face's x-position over time,
     exponentially smoothed so the crop pans instead of jittering.
  3. Re-render every frame center-cropped around that moving x position
     with OpenCV, then mux the trimmed original audio back on with
     ffmpeg (which also does the final encode).
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger("clipforge.reframer")

ASPECTS = {"9:16": (9, 16), "1:1": (1, 1), "16:9": (16, 9), "4:5": (4, 5)}

_YUNET_PATH = Path(__file__).parent / "models" / "face_detection_yunet.onnx"
_face_detector = None
_haar = None


def _get_face_detector(frame_w: int, frame_h: int):
    global _face_detector, _haar
    if _YUNET_PATH.exists():
        if _face_detector is None:
            _face_detector = cv2.FaceDetectorYN.create(
                str(_YUNET_PATH), "", (frame_w, frame_h), score_threshold=0.7
            )
        else:
            _face_detector.setInputSize((frame_w, frame_h))
        return ("yunet", _face_detector)

    if _haar is None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _haar = cv2.CascadeClassifier(cascade_path)
    return ("haar", _haar)


def _detect_face_center(frame: np.ndarray) -> Optional[tuple[float, float]]:
    h, w = frame.shape[:2]
    kind, detector = _get_face_detector(w, h)

    if kind == "yunet":
        _, faces = detector.detect(frame)
        if faces is None or len(faces) == 0:
            return None
        # pick the largest face (by bbox area)
        best = max(faces, key=lambda f: f[2] * f[3])
        x, y, fw, fh = best[:4]
        return ((x + fw / 2) / w, (y + fh / 2) / h)

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(40, 40))
    if len(faces) == 0:
        return None
    x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
    return ((x + fw / 2) / w, (y + fh / 2) / h)


def _sample_centers(cap: cv2.VideoCapture, start_f: int, end_f: int, fps: float, sample_every_s: float = 0.5):
    step = max(1, int(fps * sample_every_s))
    samples: list[tuple[int, float]] = []
    for f in range(start_f, end_f, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ok, frame = cap.read()
        if not ok:
            continue
        center = _detect_face_center(frame)
        samples.append((f, center[0] if center else 0.5))
    return samples


def _smooth_centers(samples: list[tuple[int, float]], total_frames: int, alpha: float = 0.12) -> np.ndarray:
    if not samples:
        return np.full(total_frames, 0.5)
    xs = np.array([s[0] for s in samples], dtype=np.float64)
    ys = np.array([s[1] for s in samples], dtype=np.float64)
    frame_idx = np.arange(total_frames)
    interp = np.interp(frame_idx, xs, ys, left=ys[0], right=ys[-1])

    smoothed = np.empty_like(interp)
    smoothed[0] = interp[0]
    for i in range(1, len(interp)):
        smoothed[i] = alpha * interp[i] + (1 - alpha) * smoothed[i - 1]
    return smoothed


def render_reframed(
    source_path: str,
    start_s: float,
    end_s: float,
    out_path: str,
    aspect: str = "9:16",
    target_short_side: int = 1080,
) -> str:
    aw, ah = ASPECTS.get(aspect, (9, 16))
    cap = cv2.VideoCapture(source_path)
    if not cap.isOpened():
        raise RuntimeError(f"could not open source video: {source_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    start_f = max(0, int(start_s * fps))
    end_f = min(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), int(end_s * fps))
    total_frames = max(1, end_f - start_f)

    # crop full height, narrower width to hit target aspect (assumes landscape source)
    crop_h = src_h
    crop_w = int(crop_h * aw / ah)
    if crop_w > src_w:
        crop_w = src_w
        crop_h = int(crop_w * ah / aw)

    out_w = target_short_side if aw < ah else int(target_short_side * aw / ah)
    out_h = int(target_short_side * ah / aw) if aw < ah else target_short_side

    samples = _sample_centers(cap, start_f, end_f, fps)
    centers = _smooth_centers(samples, total_frames)

    silent_path = str(Path(out_path).with_suffix(".silent.mp4"))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(silent_path, fourcc, fps, (out_w, out_h))

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    for i in range(total_frames):
        ok, frame = cap.read()
        if not ok:
            break
        cx = centers[i] * src_w
        x0 = int(np.clip(cx - crop_w / 2, 0, src_w - crop_w))
        y0 = int((src_h - crop_h) / 2)
        cropped = frame[y0 : y0 + crop_h, x0 : x0 + crop_w]
        resized = cv2.resize(cropped, (out_w, out_h), interpolation=cv2.INTER_AREA)
        writer.write(resized)

    writer.release()
    cap.release()

    # mux trimmed original audio back on + final encode to a widely-compatible mp4
    cmd = [
        "ffmpeg", "-y",
        "-i", silent_path,
        "-ss", str(start_s), "-to", str(end_s), "-i", source_path,
        "-map", "0:v:0", "-map", "1:a:0?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-shortest",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    Path(silent_path).unlink(missing_ok=True)
    return out_path
