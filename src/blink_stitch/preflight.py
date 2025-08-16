#!/usr/bin/env python3
"""
Preflight and survey functions for Blink multicam stitching.
"""

from typing import Any, Dict, List
import numpy as np
from .helpers import ffprobe_meta, get_camera_id

def survey(paths: List[str], cfg: Dict[str, Any]) -> Dict[str, Any]:
    durations = []
    cameras = set()
    sample_rates = set()
    problems = []
    for p in paths[:200]:  # sample first 200 for speed
        try:
            m = ffprobe_meta(p)
            fmt = m.get("format", {})
            dur = float(fmt.get("duration", 0.0))
            durations.append(dur)
            cams = get_camera_id(p, cfg["camera_from"], cfg["filename_regex"])
            cameras.add(cams)
            # audio stream sr if present
            for s in m.get("streams", []):
                if s.get("codec_type") == "audio":
                    sr = int(s.get("sample_rate", 0) or 0)
                    if sr: sample_rates.add(sr)
        except Exception as e:
            problems.append(f"{p}: {e}")
    est_total = sum(durations) * (len(paths)/max(1,len(durations)))
    seconds = int(est_total)
    return {
        "files": len(paths),
        "cameras": sorted(cameras),
        "dur_sample": durations[:5],
        "dur_median": float(np.median(durations)) if durations else 0.0,
        "dur_est_total_s": seconds,
        "sample_rates": sorted(sample_rates),
        "problems": problems[:5],
    }

def print_plan(sv: Dict[str, Any], cfg: Dict[str, Any]):
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()
    tbl = Table(title="Preflight Survey", box=box.SIMPLE_HEAVY)
    tbl.add_column("Field", style="bold")
    tbl.add_column("Value")
    tbl.add_row("Files found", str(sv["files"]))
    tbl.add_row("Cameras", ", ".join(sv["cameras"]) or "n/a")
    tbl.add_row("Median clip dur (s)", f"{sv['dur_median']:.2f}")
    hrs = sv["dur_est_total_s"] / 3600.0
    tbl.add_row("Estimated total audio (h)", f"{hrs:.2f}")
    tbl.add_row("Audio sample rates", ", ".join(map(str, sv["sample_rates"])) or "n/a")
    adjust = []
    if cfg["workers"] > 1:
        adjust.append("Clustering/dedupe will run single-process (auto).")
    if cfg["cluster_mode"] == "hdbscan" and not cfg.get("HAVE_HDBSCAN", False):
        adjust.append("HDBSCAN not installed; falling back to DBSCAN.")
    if cfg["verify"] == "ecapa" and not cfg.get("HAVE_SPEECHBRAIN", False):
        adjust.append("SpeechBrain not installed; disabling verification.")
    if cfg["filter_music_tv"] and not cfg.get("HAVE_INASPEECH", False):
        adjust.append("inaSpeechSegmenter not installed; music/TV filtering disabled.")
    if cfg["whisperx"] and not cfg.get("HAVE_WHISPERX", False):
        adjust.append("WhisperX not installed; word-level alignment disabled.")
    tbl.add_row("Auto adjustments", "\n".join(adjust) or "None")
    console.print(tbl)
