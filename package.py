#!/usr/bin/env python3
"""
Packaging functions for Blink multicam stitching.
"""

from typing import Any, Dict, List, Tuple
import os, json, time, random
from helpers import ensure_dir, clip_to_segment_wav

def export_voicepack(turns: List[Dict[str, Any]], out_dir: str, per_speaker_clips: int = 8, clip_seconds: Tuple[float,float]=(2.5,6.0)) -> str:
    """
    Export per-speaker WAV snippets and a manifest.json with references to paralinguistic features
    and embeddings. Clips are drawn from deduped turns; diverse text prioritized.
    """
    ensure_dir(out_dir)
    from collections import defaultdict
    by_spk: Dict[str, List[int]] = defaultdict(list)
    for i,t in enumerate(turns):
        spk = t.get("spk_global")
        if not spk: continue
        if (t["abs_end"] - t["abs_start"]) >= clip_seconds[0]:
            by_spk[spk].append(i)

    manifest = {"schema":"voicepack/v1","generated_at": time.time(), "speakers":{}}
    rng = random.Random(42)
    for spk, idxs in by_spk.items():
        rng.shuffle(idxs)
        sel = idxs[:per_speaker_clips]
        spk_dir = os.path.join(out_dir, spk); ensure_dir(spk_dir)
        items = []
        for k, i in enumerate(sel):
            t = turns[i]
            dur = min(clip_seconds[1], t["end"] - t["start"])
            wav_out = os.path.join(spk_dir, f"{spk}_{k:02d}.wav")
            clip_to_segment_wav(t["clip_path"], t["start"], t["start"] + dur, wav_out)
            items.append({
                "wav": os.path.relpath(wav_out, out_dir),
                "text": t["text"],
                "abs_start": t["abs_start"], "abs_end": t["abs_end"],
                "paralinguistics": t.get("paralinguistics", {}),
                "embedding": t["emb"],  # pyannote vector; useful as fingerprint
            })
        manifest["speakers"][spk] = {"clips": items}
    man_path = os.path.join(out_dir, "manifest.json")
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return man_path