#!/usr/bin/env python3
"""
Data structures for Blink multicam stitching.
"""

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

@dataclass
class Turn:
    start: float
    end: float
    abs_start: float
    abs_end: float
    clip: str
    clip_path: str
    camera: str
    spk_local: str
    text: str
    emb: List[float]
    spk_global: Optional[str] = None