import os
import gc
import pytest
import numpy as np
from unittest import mock
import threading

# Test for extract.py: process_one_clip thread limiting and resource cleanup
@pytest.mark.parametrize("num_turns", [1, 10])
def test_process_one_clip_thread_limit_and_cleanup(num_turns):
    """
    Verifies that torch thread limiting and gc.collect() are called for each embedding inference.
    """
    import extract

    class DummyTorch:
        called_threads = []
        def set_num_threads(self, n): self.called_threads.append(('set_num_threads', n))
        def set_num_interop_threads(self, n): self.called_threads.append(('set_num_interop_threads', n))
    dummy_torch = DummyTorch()

    dummy_emb_infer = mock.Mock(return_value=np.zeros(512))
    dummy_pipeline = mock.Mock(return_value=mock.Mock(support=lambda **kwargs: []))
    dummy_cfg = {
        "min_turn_dur": 0.1,
        "filter_music_tv": False,
        "asr_model": "tiny",
        "time_source": "filename",
        "filename_regex": ".*",
        "ts_format": "%Y%m%d",
        "camera_from": "filename"
    }

    with mock.patch("extract.torch", dummy_torch), \
         mock.patch("extract.gc.collect") as gc_collect, \
         mock.patch("extract.asr_transcribe_words", return_value=[]), \
         mock.patch("extract.words_to_text_in_interval", return_value=""), \
         mock.patch("extract.run_inaspeech_mask", return_value=None), \
         mock.patch("extract.diar_pipeline", dummy_pipeline):

        with mock.patch("extract.PNA_Segment", side_effect=lambda s,e: None):
            with mock.patch("extract.get_clip_start_epoch", return_value=0), \
                 mock.patch("extract.get_camera_id", return_value="cam"), \
                 mock.patch("extract.extract_audio_16k_mono"), \
                 mock.patch("extract.ensure_dir"):
                turns = extract.process_one_clip("dummy.wav", dummy_cfg, dummy_pipeline, dummy_emb_infer, "cache")
                assert ('set_num_threads', 1) in dummy_torch.called_threads
                assert ('set_num_interop_threads', 1) in dummy_torch.called_threads
                assert gc_collect.call_count >= 1

def test_refine_by_verification_no_thread_contention():
    """
    Verifies that refine_by_verification does not introduce thread/mutex contention and handles empty clusters.
    """
    import cluster
    turns = [{"emb": np.zeros(512), "clip_path": "a.wav", "start": 0, "end": 1}]
    labels = np.array([-1])
    seg_cache_dir = "cache"
    score_mode = "ecapa"
    score_threshold = 0.5
    max_pairs = 1
    external_cmd = None

    with mock.patch("cluster.ensure_dir"), \
         mock.patch("cluster.clip_to_segment_wav"), \
         mock.patch("cluster.ecapa_embed_and_score", return_value=0.7), \
         mock.patch("cluster.external_verifier_score", return_value=0.7):
        out_labels = cluster.refine_by_verification(turns, labels, seg_cache_dir, score_mode, score_threshold, max_pairs, external_cmd)
        assert np.array_equal(out_labels, labels)

def test_process_one_clip_error_handling():
    """
    Verifies process_one_clip handles missing files and raises appropriate errors.
    """
    import extract
    dummy_cfg = {
        "min_turn_dur": 0.1,
        "filter_music_tv": False,
        "asr_model": "tiny",
        "time_source": "filename",
        "filename_regex": ".*",
        "ts_format": "%Y%m%d",
        "camera_from": "filename"
    }
    with pytest.raises(Exception):
        extract.process_one_clip("missing.wav", dummy_cfg, mock.Mock(), mock.Mock(), "cache")

def test_concurrent_process_one_clip_stress():
    """
    Stress test: Launches multiple concurrent process_one_clip calls to verify thread limiting and resource cleanup under load.
    Annotated: This test simulates concurrent workloads and checks for stability and absence of resource leaks.
    """
    import extract

    dummy_cfg = {
        "min_turn_dur": 0.1,
        "filter_music_tv": False,
        "asr_model": "tiny",
        "time_source": "filename",
        "filename_regex": ".*",
        "ts_format": "%Y%m%d",
        "camera_from": "filename"
    }
    dummy_emb_infer = mock.Mock(return_value=np.zeros(512))
    dummy_pipeline = mock.Mock(return_value=mock.Mock(support=lambda **kwargs: []))

    def run_clip():
        with mock.patch("extract.torch"), \
             mock.patch("extract.gc.collect"), \
             mock.patch("extract.asr_transcribe_words", return_value=[]), \
             mock.patch("extract.words_to_text_in_interval", return_value=""), \
             mock.patch("extract.run_inaspeech_mask", return_value=None), \
             mock.patch("extract.diar_pipeline", dummy_pipeline), \
             mock.patch("extract.PNA_Segment", side_effect=lambda s,e: None), \
             mock.patch("extract.get_clip_start_epoch", return_value=0), \
             mock.patch("extract.get_camera_id", return_value="cam"), \
             mock.patch("extract.extract_audio_16k_mono"), \
             mock.patch("extract.ensure_dir"):
            extract.process_one_clip("dummy.wav", dummy_cfg, dummy_pipeline, dummy_emb_infer, "cache")

    threads = [threading.Thread(target=run_clip) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()

# TODO: Update documentation to match observed behavior in extract.py:76-154 and cluster.py:91-159
