"""
blink_stitch package init.

Expose a small public API surface while keeping implementation inside modules.
"""
from . import main as main

from sklearn.cluster import DBSCAN
from sklearn.preprocessing import normalize
from sklearn.neighbors import NearestNeighbors

from faster_whisper import WhisperModel as FWModel
from pyannote.audio import Pipeline as PyannotePipeline
from pyannote.audio import Model as PNA_Model
from pyannote.audio import Inference as PNA_Inference
from pyannote.core import Segment as PNA_Segment


__all__ = ["main"]
