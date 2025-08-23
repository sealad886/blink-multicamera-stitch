#!/usr/bin/env python3
"""Automatic alignment and stream selection for Blink multicamera exports."""

from __future__ import annotations

from typing import Dict, List, Tuple
import os
import re
import numpy as np
from loguru import logger

from helpers import sh, get_clip_start_epoch, ensure_dir

try:  # optional dependency
    import cv2  # type: ignore
    HAVE_CV2 = True
except Exception:  # pragma: no cover - cv2 may not be installed
    cv2 = None  # type: ignore
    HAVE_CV2 = False


def audio_clarity_score(path: str) -> float:
    """Return an estimate of audio clarity using ffmpeg's volumedetect."""
    p = sh([
        "ffmpeg",
        "-i",
        path,
        "-af",
        "volumedetect",
        "-vn",
        "-sn",
        "-dn",
        "-f",
        "null",
        "-",
    ], check=False)
    m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", p.stderr)
    return -float(m.group(1)) if m else float("-inf")


def video_view_score(path: str, samples: int = 5) -> float:
    """Score how well the speaker is framed; larger face area is better."""
    if not HAVE_CV2:
        return 0.0
    try:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return 0.0
        face_cascade = cv2.CascadeClassifier(
            os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        )
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        step = max(total // samples, 1)
        scores: List[float] = []
        for i in range(0, total, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
            if len(faces):
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                scores.append(float(w * h))
        cap.release()
        return float(np.mean(scores)) if scores else 0.0
    except Exception:  # pragma: no cover - best effort when cv2 misbehaves
        return 0.0


def select_best_streams(clips: List[str]) -> Tuple[str, str]:
    """Return (best_video, best_audio) from the provided clip paths."""
    best_audio = max(clips, key=audio_clarity_score)
    best_video = max(clips, key=video_view_score)
    logger.info(f"Selected best audio {best_audio} and best video {best_video}")
    return best_video, best_audio


def synthesize_best(
    clips: List[str],
    out_path: str,
    time_source: str = "ffprobe",
    filename_regex: str | None = None,
    ts_format: str | None = None,
) -> Dict[str, float | str]:
    """Align clips and mux the best audio with the best video."""
    ensure_dir(os.path.dirname(out_path) or ".")
    best_video, best_audio = select_best_streams(clips)
    tv = get_clip_start_epoch(best_video, time_source, filename_regex, ts_format)
    ta = get_clip_start_epoch(best_audio, time_source, filename_regex, ts_format)
    offset = ta - tv
    cmd = ["ffmpeg", "-y"]
    if offset >= 0:
        cmd += ["-i", best_video, "-itsoffset", f"{offset}", "-i", best_audio]
    else:
        cmd += ["-itsoffset", f"{-offset}", "-i", best_video, "-i", best_audio]
    cmd += [
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-shortest",
        out_path,
    ]
    sh(cmd)
    return {"video": best_video, "audio": best_audio, "offset": offset, "output": out_path}


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Auto-select best audio and video from Blink clips")
    ap.add_argument("clips", nargs="+", help="Input MP4 clips")
    ap.add_argument("--out", required=True, help="Output stitched MP4")
    ap.add_argument("--time-source", default="ffprobe")
    ap.add_argument("--filename-regex", default=None)
    ap.add_argument("--ts-format", default=None)
    args = ap.parse_args()
    info = synthesize_best(
        args.clips,
        args.out,
        time_source=args.time_source,
        filename_regex=args.filename_regex,
        ts_format=args.ts_format,
    )
    print(json.dumps(info, indent=2))
