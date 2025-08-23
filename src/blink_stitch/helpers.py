#!/usr/bin/env python3
"""
Helper functions for Blink multicam stitching.
"""
import os

def set_openmp_env():
    """
    Set environment variables to resolve OpenMP mutex blocking issues.
    Should be called before any imports that may trigger OpenMP.
    """
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"


# Ensure OpenMP / MKL env vars are set immediately on module import so that
# any subsequent top-level native-library imports (torch, numpy, pyannote, ...)
# do not trigger mutex/thread contention during import-time initialization.
set_openmp_env()

import re, json, hashlib, subprocess
import logging
from pathlib import Path
from typing import List, Optional, Iterable

import torch

# Optional deps (lazy)
HAVE_HDBSCAN = False
HAVE_SPEECHBRAIN = False
HAVE_INASPEECH = False
HAVE_WHISPERX = False
HAVE_OPENSMILE = False
HAVE_LIBROSA = False

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

# Media discovery helpers
# Small, deterministic helpers to locate media files (video/audio) in mixed layouts.
# Kept minimal and conservative; returns absolute (resolved) paths to match common usage.
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".mpg", ".mpeg", ".ts"}
AUDIO_EXTS = {".wav", ".mp3", ".aac", ".m4a", ".flac", ".ogg"}

def normalize_ext(path_or_name: str) -> str:
    """
    Return the lowercased extension (including the leading dot) for a filename or path.
    Examples: "FOO.MP4" -> ".mp4", "audio.wav" -> ".wav", "noext" -> ""
    """
    return Path(path_or_name).suffix.lower()

def discover_media_paths(paths: List[str], recursive: bool = True, exts: Optional[Iterable[str]] = None) -> List[str]:
    """
    Discover media file paths from a list of files or directories.

    - paths: iterable of file or directory paths (strings).
    - recursive: if True, directories are traversed recursively (Path.rglob); otherwise only top-level (Path.glob).
    - exts: optional iterable of extensions (with or without a leading dot); case-insensitive.
            If not provided, defaults to VIDEO_EXTS | AUDIO_EXTS.

    Returns:
        A deterministic, sorted list of absolute paths (as strings). Non-existing paths are skipped
        and logged at debug level.
    """
    logger = logging.getLogger(__name__)
    # prepare chosen extension set (normalize to leading-dot, lowercase)
    # Note: exts coming from CLI/config may include values like "mp4" or ".MP4".
    # Normalize here to a set of lower-case extensions with a leading dot so
    # callers may pass either form. This mirrors behavior expected by tests.
    if exts is None:
        chosen = set(VIDEO_EXTS) | set(AUDIO_EXTS)
    else:
        chosen = set()
        for e in exts:
            ee = e.lower()
            if not ee.startswith("."):
                ee = "." + ee
            chosen.add(ee)

    results = set()
    for p in paths:
        pth = Path(p)
        if not pth.exists():
            logger.debug("discover_media_paths: skipping non-existing path: %s", p)
            continue
        if pth.is_file():
            if normalize_ext(pth.name) in chosen:
                results.add(str(pth.resolve()))
            continue
        if pth.is_dir():
            if recursive:
                # Recursive traversal: walk all descendants but skip hidden files/dirs and symbolic links
                iterator = pth.rglob("*")
                for child in iterator:
                    try:
                        # skip symlinks to avoid loops and hidden files/dirs (any path component starting with '.')
                        if child.is_symlink():
                            continue
                        if any(part.startswith(".") for part in child.parts):
                            continue
                    except Exception:
                        # best-effort: if parts inspection fails, skip the entry
                        continue
                    if child.is_file() and normalize_ext(child.name) in chosen:
                        results.add(str(child.resolve()))
            else:
                # Non-recursive discovery semantics (conservative) — per-input behaviour:
                # - collect top-level media files for this input directory (skip hidden and symlinks)
                # - if any top-level media found, prefer top-level files only
                #   and, if any top-level audio (.wav/.flac) present, prefer audio-only
                # - if no top-level media found, fall back to scanning immediate subdirectories
                top_files = []
                for child in pth.glob("*"):
                    if child.name.startswith(".") or child.is_symlink():
                        continue
                    if child.is_file() and normalize_ext(child.name) in chosen:
                        top_files.append(child)
                if top_files:
                    # If any top-level audio exists prefer audio-only results for shallow scans
                    audio_exts = {".wav", ".flac"}
                    top_audio = [f for f in top_files if normalize_ext(f.name) in audio_exts]
                    selected = top_audio if top_audio else top_files
                    for f in selected:
                        results.add(str(f.resolve()))
                else:
                    # Fallback: look in immediate subdirectories (one-level deep), applying same hidden/symlink rules
                    for child in pth.iterdir():
                        if child.is_symlink() or child.name.startswith("."):
                            continue
                        if child.is_dir():
                            for sub in child.glob("*"):
                                if sub.name.startswith(".") or sub.is_symlink():
                                    continue
                                if sub.is_file() and normalize_ext(sub.name) in chosen:
                                    results.add(str(sub.resolve()))

    return sorted(results)
