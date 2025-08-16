#!/usr/bin/env python3
"""
Annotation functions for Blink multicam stitching.
"""

from typing import Any, Dict, List
import os, json, math, numpy as np, pandas as pd
from helpers import ensure_dir, HAVE_OPENSMILE, opensmile, HAVE_LIBROSA, librosa

def compute_paralinguistics(turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Attach paralinguistic features per turn using opensmile (eGeMAPS LLDs) aggregated.
    Also compute rough SNR and intonation/inflection heuristics from F0 statistics.
    Requires opensmile. If missing, annotate minimal features.
    """
    if not HAVE_OPENSMILE:
        for t in turns:
            t["paralinguistics"] = {"note": "opensmile not installed; minimal features only"}
        return turns

    # Group by clip to avoid reloading audio repeatedly
    from collections import defaultdict
    by_clip: Dict[str,List[int]] = defaultdict(list)
    for i,t in enumerate(turns):
        by_clip[t["clip_path"]].append(i)

    smile_lld = opensmile.Smile(
        feature_set=opensmile.FeatureSet.eGeMAPSv02,
        feature_level=opensmile.FeatureLevel.LowLevelDescriptors,
    )

    for clip_path, idxs in by_clip.items():
        # process once per clip
        lld = smile_lld.process_file(clip_path)  # time-indexed LLD dataframe
        # time index (MultiIndex file,time) -> seconds array
        if isinstance(lld.index, pd.MultiIndex):
            times = [float(t) for _, t in lld.index]
        else:
            # fallback 10ms hop assumption
            times = [i*0.01 for i in range(len(lld))]

        # map column names of interest
        cols = lld.columns
        def col_like(keys): return [c for c in cols if any(k.lower() in c.lower() for k in keys)]
        f0_cols = col_like(["F0", "f0"])
        loud_cols = col_like(["loudness"])
        jitter_cols = col_like(["jitter"])
        shimmer_cols = col_like(["shimmer"])
        mfcc_cols = col_like(["mfcc"])

        arr = lld.to_numpy(dtype=np.float32)

        # helper to slice by time
        t_np = np.array(times, dtype=np.float32)
        def slice_stats(a,b, col_idx):
            mask = (t_np >= a) & (t_np <= b)
            if not np.any(mask) or len(col_idx)==0:
                return None
            sub = arr[mask][:, col_idx]
            return sub

        for i in idxs:
            t = turns[i]
            s, e = t["start"], t["end"]
            # F0 & loudness stats
            f0_sub = slice_stats(s,e,[cols.get_loc(c) for c in f0_cols])
            loud_sub = slice_stats(s,e,[cols.get_loc(c) for c in loud_cols])
            jit_sub = slice_stats(s,e,[cols.get_loc(c) for c in jitter_cols])
            shm_sub = slice_stats(s,e,[cols.get_loc(c) for c in shimmer_cols])
            mfcc_sub= slice_stats(s,e,[cols.get_loc(c) for c in mfcc_cols])

            def stats(mat):
                if mat is None or mat.size==0:
                    return {}
                v = np.nan_to_num(mat, nan=np.nan)
                mean = float(np.nanmean(v))
                std  = float(np.nanstd(v))
                p95  = float(np.nanpercentile(v,95))
                p05  = float(np.nanpercentile(v,5))
                return {"mean":mean,"std":std,"p95":p95,"p05":p05}

            f0_stats = stats(f0_sub)
            loud_stats = stats(loud_sub)
            jitter_stats = stats(jit_sub)
            shimmer_stats= stats(shm_sub)

            # intonation/inflection proxy: slope of F0 over time (linear fit on mean of f0 cols)
            inflection = None
            if f0_sub is not None and f0_sub.size>0:
                f0_trace = np.nanmean(f0_sub, axis=1)
                tt = t_np[(t_np>=s)&(t_np<=e)]
                if len(tt)>=2:
                    A = np.vstack([tt, np.ones_like(tt)]).T
                    m, c = np.linalg.lstsq(A, f0_trace, rcond=None)[0]
                    inflection = {"slope_hz_per_s": float(m), "range_hz": float(np.nanmax(f0_trace)-np.nanmin(f0_trace))}
            # MFCC summary (voice "fingerprint" features – good for cloning packs)
            mfcc_means = None
            if mfcc_sub is not None and mfcc_sub.size>0:
                mfcc_means = np.nanmean(mfcc_sub, axis=0).tolist()

            # rough SNR proxy: loudness in-turn vs adjacent 0.5s margins if available
            snr = None
            if loud_sub is not None and loud_sub.size>0:
                L_in = float(np.nanmean(loud_sub))
                pre = slice_stats(max(0.0,s-0.5), s, [cols.get_loc(c) for c in loud_cols])
                post= slice_stats(e, e+0.5, [cols.get_loc(c) for c in loud_cols])
                L_out = float(np.nanmean(np.vstack([x for x in [pre,post] if x is not None])) if (pre is not None or post is not None) else np.nan)
                if not math.isnan(L_in) and not math.isnan(L_out):
                    snr = float(L_in - L_out)  # in arbitrary loudness units

            # fast heuristics for mood tags (keep simple, transparent)
            mood = []
            if f0_stats.get("std",0)>15 and loud_stats.get("mean",0)>0: mood.append("energetic/excited")
            if f0_stats.get("std",0)<5 and loud_stats.get("mean",0)<0: mood.append("calm/flat")
            if (t["text"].count("!")>=1) or (f0_stats.get("p95",0)-f0_stats.get("p05",0)>60): mood.append("emphatic")

            t["paralinguistics"] = {
                "f0": f0_stats,
                "loudness": loud_stats,
                "jitter": jitter_stats,
                "shimmer": shimmer_stats,
                "inflection": inflection,
                "mfcc_means": mfcc_means,
                "snr_proxy": snr,
                "mood_tags": mood,
            }
    return turns