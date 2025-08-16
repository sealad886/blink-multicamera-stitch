#!/usr/bin/env python3
"""
Clustering functions for Blink multicam stitching.
"""

from typing import Any, Dict, List, Optional
import os, numpy as np
from loguru import logger
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import normalize
from sklearn.neighbors import NearestNeighbors
from .helpers import ensure_dir, HAVE_HDBSCAN, clip_to_segment_wav, sh, torch

try:
    import hdbscan
    HAVE_HDBSCAN = True
except ImportError:
    hdbscan = None
    pass

try:
    import librosa
    HAVE_LIBROSA = True
except ImportError:
    librosa = None
    pass

# Limit thread usage for native libraries to reduce mutex contention
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
if hasattr(torch, "set_num_threads"):
    torch.set_num_threads(1)
if hasattr(torch, "set_num_interop_threads"):
    torch.set_num_interop_threads(1)

def auto_eps_knn(Xn: np.ndarray, k: int = 5, quantile: float = 0.90) -> float:
    logger.info("Starting NearestNeighbors.fit")
    nbrs = NearestNeighbors(n_neighbors=min(k, len(Xn))).fit(Xn)
    logger.info("Finished NearestNeighbors.fit")
    dists, _ = nbrs.kneighbors(Xn)
    kth = dists[:, -1]
    logger.info("Computed kth distances, quantile next")
    return float(np.quantile(kth, quantile))

def run_dbscan(Xn: np.ndarray, eps: float, min_samples: int) -> np.ndarray:
    logger.info("Creating DBSCAN model")
    model = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine", n_jobs=-1)
    logger.info("Fitting DBSCAN model")
    result = model.fit_predict(Xn)
    logger.info("DBSCAN fit_predict complete")
    return result

def run_hdbscan(Xn: np.ndarray, min_cluster_size: int) -> np.ndarray:
    if not HAVE_HDBSCAN:
        raise RuntimeError("hdbscan not installed.")
    logger.info("Creating HDBSCAN model")
    model = hdbscan.HDBSCAN(metric="euclidean", min_cluster_size=min_cluster_size)
    logger.info("Fitting HDBSCAN model")
    result = model.fit_predict(Xn)
    logger.info("HDBSCAN fit_predict complete")
    return result

def external_verifier_score(cmd_tmpl: str, wav1: str, wav2: str) -> float:
    cmd = cmd_tmpl.format(wav1=wav1, wav2=wav2).split()
    p = sh(cmd)
    return float(p.stdout.strip().split()[0])

def ecapa_embed_and_score(wav_a: str, wav_b: str) -> float:
    from speechbrain.inference.classifiers import EncoderClassifier  # lazy
    logger.info("Loading EncoderClassifier")
    classifier = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb")
    import soundfile as sf
    logger.info("Reading wav_a and wav_b with soundfile")
    wa, fsa = sf.read(wav_a); wb, fsb = sf.read(wav_b)
    def prep(w, fs):
        logger.info(f"Preparing audio, fs={fs}")
        if fs != 16000 and HAVE_LIBROSA:
            logger.info("Resampling with librosa")
            w = librosa.resample(w, orig_sr=fs, target_sr=16000)
        if w.ndim > 1: w = w.mean(axis=1)
        logger.info("Converting to torch tensor")
        # Ensure minimal thread contention during tensor ops
        if hasattr(torch, "set_num_threads"):
            torch.set_num_threads(1)
        if hasattr(torch, "set_num_interop_threads"):
            torch.set_num_interop_threads(1)
        return torch.tensor(w[None, :], dtype=torch.float32)
    logger.info("Encoding batch for wa")
    ea = classifier.encode_batch(prep(wa, fsa)).mean(1)
    logger.info("Encoding batch for wb")
    eb = classifier.encode_batch(prep(wb, fsb)).mean(1)
    logger.info("Normalizing embeddings")
    # Normalize embeddings with minimal thread contention
    ea = torch.nn.functional.normalize(ea, dim=-1)
    eb = torch.nn.functional.normalize(eb, dim=-1)
    logger.info("Computing similarity score")
    # Compute similarity score with minimal thread contention
    score = float(torch.sum(ea * eb).item())
    # Explicit resource cleanup
    import gc
    gc.collect()
    return score

def refine_by_verification(turns: List[Dict[str, Any]],
                           labels: np.ndarray,
                           seg_cache_dir: str,
                           score_mode: str,
                           score_threshold: float,
                           max_pairs: int,
                           external_cmd: Optional[str]) -> np.ndarray:
    from collections import defaultdict
    clusters = defaultdict(list)
    for i, lab in enumerate(labels):
        if lab == -1: continue
        clusters[int(lab)].append(i)
    if not clusters: return labels

    X = np.vstack([np.array(t["emb"], dtype=np.float32) for t in turns])
    Xn = normalize(X)
    centroids = {c: normalize(np.mean(Xn[idxs], axis=0, keepdims=True))[0] for c, idxs in clusters.items()}

    def cos(a,b): return float(np.dot(a,b))
    cand = []
    keys = sorted(centroids.keys())
    for i in range(len(keys)):
        for j in range(i+1, len(keys)):
            c1, c2 = keys[i], keys[j]
            s = cos(centroids[c1], centroids[c2])
            if s >= 0.6:
                cand.append((c1,c2,s))
    cand.sort(key=lambda x: -x[2])

    parent = {k:k for k in keys}
    def find(x):
        while parent[x]!=x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a,b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[rb] = ra

    ensure_dir(seg_cache_dir)
    rng = np.random.default_rng(42)
    for c1,c2,_ in cand:
        a, b = clusters[c1], clusters[c2]
        if not a or not b: continue
        pairs = [(int(rng.choice(a)), int(rng.choice(b))) for _ in range(max_pairs)]
        scores = []
        for (i,j) in pairs:
            ti, tj = turns[i], turns[j]
            wi = os.path.join(seg_cache_dir, f"seg_{i}.wav")
            wj = os.path.join(seg_cache_dir, f"seg_{j}.wav")
            if not os.path.exists(wi): clip_to_segment_wav(ti["clip_path"], ti["start"], ti["end"], wi)
            if not os.path.exists(wj): clip_to_segment_wav(tj["clip_path"], tj["start"], tj["end"], wj)
            s = ecapa_embed_and_score(wi, wj) if score_mode=="ecapa" else external_verifier_score(external_cmd, wi, wj)
            scores.append(s)
        if np.mean(scores) >= score_threshold:
            union(c1, c2)

    root_to_new = {}
    next_id = 0
    new_labels = labels.copy()
    for old in keys:
        r = find(old)
        if r not in root_to_new:
            root_to_new[r] = next_id; next_id += 1
    for i, lab in enumerate(labels):
        if lab == -1: continue
        r = find(lab)
        new_labels[i] = root_to_new[r]
    return new_labels
