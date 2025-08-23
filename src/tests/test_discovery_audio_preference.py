import sys
from pathlib import Path
# Make package importable when tests run from project root:
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blink_stitch.helpers import discover_media_paths

def test_discovery_non_recursive_audio_preference(tmp_path):
    p = tmp_path
    audio = p / "top_audio.wav"
    video = p / "top_video.mp4"
    audio.write_text("dummy")
    video.write_text("dummy")

    # When non-recursive discovery is run on a dir with both top-level audio and video,
    # the discovery should prefer audio-only and return only the audio files.
    found = discover_media_paths([str(p)], recursive=False)
    expected = {str(audio.resolve())}
    assert set(found) == expected