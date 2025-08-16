#!/usr/bin/env python3
"""
Deduplication functions for Blink multicam stitching.
"""

from typing import Any, Dict, List
import numpy as np

def iou_time(a0,a1,b0,b1) -> float:
    inter = max(0.0, min(a1,b1) - max(a0,b0))
    union = (a1-a0) + (b1-b0) - inter
    return inter / max(union, 1e-6)

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = a / max(1e-6, np.linalg.norm(a)); b = b / max(1e-6, np.linalg.norm(b))
    return float(np.dot(a,b))

def hard_dedupe(turns: List[Dict[str, Any]], iou_thresh: float, emb_cos_thresh: float) -> List[Dict[str, Any]]:
    turns = sorted(turns, key=lambda t: (t["abs_start"], t["camera"]))
    keep = [True]*len(turns)
    X = np.vstack([np.array(t["emb"], dtype=np.float32) for t in turns])
    for i in range(len(turns)):
        if not keep[i] or turns[i]["spk_global"] is None: continue
        for j in range(i+1, len(turns)):
            if not keep[j]: continue
            if turns[i]["spk_global"] != turns[j]["spk_global"]: continue
            if turns[j]["abs_start"] > turns[i]["abs_end"] + 1.0: break
            iou = iou_time(turns[i]["abs_start"], turns[i]["abs_end"], turns[j]["abs_start"], turns[j]["abs_end"])
            if iou >= iou_thresh:
                sim = cosine(X[i], X[j])
                if sim >= emb_cos_thresh:
                    di = turns[i]["abs_end"] - turns[i]["abs_start"]
                    dj = turns[j]["abs_end"] - turns[j]["abs_start"]
                    if di >= dj: keep[j] = False
                    else:
                        keep[i] = False
                        break
    return [t for k,t in zip(keep, turns) if k]