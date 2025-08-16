#!/usr/bin/env python3
"""
Helper functions for Blink multicam stitching.
"""

def set_openmp_env():
    """
    Set environment variables to resolve OpenMP mutex blocking issues.
    Should be called before any imports that may trigger OpenMP.
    """
    import os
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"


import os, re, sys, json, math, glob, time, hashlib, shutil, argparse, subprocess, random
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
from functools import partial

import numpy as np
import pandas as pd

import torch
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import normalize
from sklearn.neighbors import NearestNeighbors

from faster_whisper import WhisperModel as FWModel
from pyannote.audio import Pipeline as PyannotePipeline
from pyannote.audio import Model as PNA_Model
from pyannote.audio import Inference as PNA_Inference
from pyannote.core import Segment as PNA_Segment

# Optional deps (lazy)
HAVE_HDBSCAN = False
HAVE_SPEECHBRAIN = False
HAVE_INASPEECH = False
HAVE_WHISPERX = False
HAVE_OPENSMILE = False
HAVE_LIBROSA = False

try:
    import hdbscan as _hdbscan  # type: ignore
    HAVE_HDBSCAN = True
except Exception:
    _hdbscan = None
    pass

try:
    import speechbrain as _speechbrain  # type: ignore
    HAVE_SPEECHBRAIN = True
except Exception:
    _speechbrain = None
    pass

try:
    from inaSpeechSegmenter import Segmenter  # type: ignore
    HAVE_INASPEECH = True
except Exception:
    Segmenter = None
    pass

try:
    import whisperx  # type: ignore
    HAVE_WHISPERX = True
except Exception:
    whisperx = None
    pass

try:
    import opensmile
    HAVE_OPENSMILE = True
except Exception:
    opensmile = None
    pass

try:
    import librosa
    HAVE_LIBROSA = True
except Exception:
    librosa = None
    pass

def sh(cmd: List[str], check=True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=check)

def device_hint() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"

def md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:12]

def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def ffprobe_meta(path: str) -> dict:
    p = sh(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path])
    return json.loads(p.stdout)

def parse_filename_ts(path: str, pattern: Optional[str], ts_format: Optional[str]) -> Optional[float]:
    if not pattern or not ts_format:
        return None
    bn = os.path.basename(path)
    m = re.search(pattern, bn)
    if not m:
        return None
    ts = m.groupdict().get("ts")
    if not ts:
        return None
    import datetime as dt
    try:
        return dt.datetime.strptime(ts, ts_format).timestamp()
    except Exception:
        return None

def get_clip_start_epoch(path: str, time_source: str, filename_regex: Optional[str], ts_format: Optional[str]) -> float:
    if time_source == "filename":
        t = parse_filename_ts(path, filename_regex, ts_format)
        if t is not None:
            return t
        time_source = "ffprobe"
    if time_source == "ffprobe":
        try:
            meta = ffprobe_meta(path)
            tags = meta.get("format", {}).get("tags", {})
            ct = tags.get("creation_time")
            if ct:
                import datetime as dt
                return dt.datetime.fromisoformat(ct.replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
        time_source = "mtime"
    return os.path.getmtime(path)

def get_camera_id(path: str, camera_from: str, filename_regex: Optional[str]) -> str:
    if camera_from == "parentdir":
        return os.path.basename(os.path.dirname(path)) or "camera"
    bn = os.path.basename(path)
    if camera_from == "regex" and filename_regex:
        m = re.search(filename_regex, bn)
        if m and "camera" in m.groupdict():
            return m.group("camera")
    if camera_from == "filename":
        return os.path.splitext(bn)[0]
    return "camera"

def extract_audio_16k_mono(in_mp4: str, out_wav: str):
    sh(["ffmpeg", "-y", "-i", in_mp4, "-ac", "1", "-ar", "16000", "-vn", out_wav])

def clip_to_segment_wav(src_mp4: str, start: float, end: float, out_wav: str):
    dur = max(0.05, end - start)
    sh(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src_mp4, "-ac", "1", "-ar", "16000", "-vn", out_wav])