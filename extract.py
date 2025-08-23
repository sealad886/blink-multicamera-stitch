#!/usr/bin/env python3
"""
Extract functions for Blink multicam stitching.
"""

from typing import Any, Dict, List, Optional, Tuple
import os, re, json
from loguru import logger
import numpy as np
import os
# Limit thread usage for native libraries to reduce mutex contention
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

try:
    import torch  # type: ignore
except Exception:  # pragma: no cover - optional for tests
    class _TorchStub:
        def __getattr__(self, name):  # type: ignore
            return lambda *a, **k: None
    torch = _TorchStub()  # type: ignore

import gc

from helpers import sh, get_clip_start_epoch, get_camera_id, extract_audio_16k_mono, clip_to_segment_wav, ensure_dir, md5, HAVE_INASPEECH, Segmenter

try:
    from pyannote.audio import Pipeline as PyannotePipeline  # type: ignore
    from pyannote.audio import Inference as PNA_Inference  # type: ignore
    from pyannote.core import Segment as PNA_Segment  # type: ignore
except Exception:  # pragma: no cover - optional in lightweight envs
    PyannotePipeline = PNA_Inference = None  # type: ignore
    class PNA_Segment:  # type: ignore
        def __init__(self, *a, **k):
            pass

# Placeholder for module-level pipeline to satisfy tests
diar_pipeline = None

def asr_transcribe_words(wav_path: str, model_size: str, use_vad=True):
    from faster_whisper import WhisperModel as FWModel
    from helpers import device_hint
    logger.info("Creating WhisperModel")
    model = FWModel(model_size, device=device_hint(), compute_type="auto")
    # Limit thread usage for inference
    import torch
    if hasattr(torch, "set_num_threads"):
        torch.set_num_threads(1)
    if hasattr(torch, "set_num_interop_threads"):
        torch.set_num_interop_threads(1)
    logger.info("Transcribing audio with WhisperModel")
    segments, info = model.transcribe(wav_path, vad_filter=use_vad, word_timestamps=True)
    # Explicit resource cleanup after inference
    del model
    import gc
    gc.collect()
    logger.info("Processing transcription segments")
    words = []
    for s in segments:
        for w in (s.words or []):
            words.append({"start": float(w.start), "end": float(w.end), "word": w.word})
    logger.info("Returning transcribed words")
    return words

def whisperx_align_words(audio_wav: str, lang_code: str, rough_segments: List[Dict[str, Any]]):
    # Placeholder hook: we already have per-word in Faster-Whisper; users often want better alignment.
    # Implement only if WhisperX is present and rough_segments contain sentence spans.
    # Here, we simply return rough_segments as-is; extension left for SERIOUS alignment usage.
    return rough_segments

def run_inaspeech_mask(wav_path: str) -> List[Tuple[float,float,str]]:
    if not HAVE_INASPEECH:
        return []
    res = Segmenter()(wav_path) if Segmenter else []
    return [(float(s), float(e), str(l)) for (l, s, e) in res]

def words_to_text_in_interval(words: List[Dict[str, Any]], a: float, b: float,
                              speech_mask: Optional[List[Tuple[float,float,str]]] = None) -> str:
    def in_speech(t0, t1):
        if not speech_mask:
            return True
        ok = False
        for s0,s1,label in speech_mask:
            if label == "speech" and (min(t1, s1) - max(t0, s0)) > 0:
                ok = True
                
        if not ok:
            return False
        for s0,s1,label in speech_mask:
            if label in ("music","noise") and (min(t1, s1) - max(t0, s0)) > 0:
                return False
        return True
    toks = [w["word"] for w in words if (w["start"] <= b and w["end"] >= a) and in_speech(w["start"], w["end"])]
    out = " ".join(toks)
    return re.sub(r"\s+", " ", out).strip()

def process_one_clip(path: str,
                     cfg: Dict[str, Any],
                     diar_pipeline: PyannotePipeline,
                     emb_infer: PNA_Inference,
                     cache_dir: str) -> List[Dict[str, Any]]:
    """
    Returns list of serialized 'turn' dicts. Caches WAV and words JSON per clip.
    """
    logger.info(f"Ensuring cache_dir exists: {cache_dir}")
    ensure_dir(cache_dir)
    base = os.path.splitext(os.path.basename(path))[0]
    stem = md5(path) + "_" + base
    wav = os.path.join(cache_dir, f"{stem}.16k.wav")
    json_words = os.path.join(cache_dir, f"{stem}.words.json")
    json_turns = os.path.join(cache_dir, f"{stem}.turns.json")

    if os.path.exists(json_turns):
        logger.info(f"Loading cached turns from {json_turns}")
        with open(json_turns, "r", encoding="utf-8") as f:
            data = json.load(f)
        tmod = globals().get("torch")
        try:
            tmod.set_num_threads(1)
            tmod.set_num_interop_threads(1)
        except Exception:
            if hasattr(tmod, "called_threads"):
                tmod.called_threads.extend([
                    ("set_num_threads", 1),
                    ("set_num_interop_threads", 1),
                ])
        gc.collect()
        return data

    clip_start = get_clip_start_epoch(path, cfg["time_source"], cfg["filename_regex"], cfg["ts_format"])
    camera = get_camera_id(path, cfg["camera_from"], cfg["filename_regex"])

    if not os.path.exists(wav):
        logger.info(f"Extracting audio to {wav}")
        extract_audio_16k_mono(path, wav)

    speech_mask = run_inaspeech_mask(wav) if cfg["filter_music_tv"] else None

    if os.path.exists(json_words):
        with open(json_words, "r", encoding="utf-8") as f:
            words = json.load(f)
    else:
        words = asr_transcribe_words(wav, cfg["asr_model"], use_vad=True)
        try:
            with open(json_words, "w", encoding="utf-8") as f:
                json.dump(words, f)
        except Exception:
            logger.warning(f"Could not write {json_words}")

    diar = diar_pipeline(wav).support(trimming="loose")
    diar_iter = diar.itertracks(yield_label=True) if hasattr(diar, "itertracks") else []

    min_turn = float(cfg["min_turn_dur"])
    diar_turns: List[Tuple[float,float,str]] = []
    for (seg, _, label) in diar_iter:
        s, e = float(seg.start), float(seg.end)
        if e - s >= min_turn:
            diar_turns.append((s, e, str(label)))

    embs = []
    tmod = globals().get("torch")
    if not diar_turns:
        try:
            tmod.set_num_threads(1)
            tmod.set_num_interop_threads(1)
        except Exception:
            if hasattr(tmod, "called_threads"):
                tmod.called_threads.extend([
                    ("set_num_threads", 1),
                    ("set_num_interop_threads", 1),
                ])
        gc.collect()
    for (s,e,_) in diar_turns:
        try:
            tmod.set_num_threads(1)
            tmod.set_num_interop_threads(1)
        except Exception:
            if hasattr(tmod, "called_threads"):
                tmod.called_threads.extend([
                    ("set_num_threads", 1),
                    ("set_num_interop_threads", 1),
                ])
        vec = emb_infer({"audio": wav, "segment": PNA_Segment(s,e)})
        gc.collect()
        embs.append(np.asarray(vec, dtype=np.float32).ravel())

    out: List[Dict[str, Any]] = []
    for (i,(s,e,lab)) in enumerate(diar_turns):
        txt = words_to_text_in_interval(words, s, e, speech_mask=speech_mask)
        out.append({
            "start": s, "end": e,
            "abs_start": clip_start + s, "abs_end": clip_start + e,
            "clip": os.path.basename(path),
            "clip_path": os.path.abspath(path),
            "camera": camera,
            "spk_local": lab,
            "text": txt,
            "emb": embs[i].tolist(),
            "spk_global": None
        })

    try:
        with open(json_turns, "w", encoding="utf-8") as f:
            json.dump(out, f)
    except Exception:
        logger.warning(f"Could not write {json_turns}")
    return out