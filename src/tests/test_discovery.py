import os
from pathlib import Path
import sys
# Make package importable when tests run from project root:
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blink_stitch.helpers import discover_media_paths


def create_layout(tmp_path):
    p = tmp_path
    (p / "2024-01" / "2024-01-01" / "cam1").mkdir(parents=True)
    (p / "2024-02" / "2024-02-02").mkdir(parents=True)
    (p / "day3").mkdir()
    # create files
    f1 = p / "2024-01" / "2024-01-01" / "cam1" / "video1.mp4"
    f1.write_text("dummy")
    f2 = p / "2024-02" / "2024-02-02" / "video2.MP4"
    f2.write_text("dummy")
    f3 = p / "day3" / "video3.mov"
    f3.write_text("dummy")
    f4 = p / "some_audio.wav"
    f4.write_text("dummy")
    return [f1, f2, f3, f4]


def test_discover_recursive_all(tmp_path):
    files = create_layout(tmp_path)
    found = discover_media_paths([str(tmp_path)])
    assert set(found) == set(str(p.resolve()) for p in files)


def test_discover_non_recursive_top_level(tmp_path):
    files = create_layout(tmp_path)
    found = discover_media_paths([str(tmp_path)], recursive=False)
    expected = {str((tmp_path / "some_audio.wav").resolve())}
    assert set(found) == expected


def test_discover_single_file(tmp_path):
    files = create_layout(tmp_path)
    single = files[0]
    found = discover_media_paths([str(single)])
    assert found == [str(single.resolve())]


def test_discover_extension_case_insensitive(tmp_path):
    files = create_layout(tmp_path)
    found = discover_media_paths([str(tmp_path)], recursive=True, exts=[".mp4"])
    expected = {
        str((tmp_path / "2024-01" / "2024-01-01" / "cam1" / "video1.mp4").resolve()),
        str((tmp_path / "2024-02" / "2024-02-02" / "video2.MP4").resolve()),
    }
    assert expected.issubset(set(found))


def test_discover_non_recursive_fallback_to_immediate_subdirs(tmp_path):
    """
    Non-recursive discovery should:
    - include files at the top-level if present
    - otherwise fall back to files in immediate subdirectories
    This test ensures the fallback behavior when no top-level media exists.
    """
    p = tmp_path
    # create immediate subdirectories with media files
    (p / "cam1").mkdir()
    (p / "cam2").mkdir()
    f1 = p / "cam1" / "video1.MP4"
    f2 = p / "cam2" / "audio1.wav"
    f1.write_text("dummy")
    f2.write_text("dummy")

    found = discover_media_paths([str(tmp_path)], recursive=False)
    expected = {str(f1.resolve()), str(f2.resolve())}
    assert set(found) == expected


def test_discover_mixed_layout_non_recursive_prefers_top_level(tmp_path):
    """
    When non-recursive discovery is run on a mixed layout that contains both
    top-level files and nested files, discovery should prefer top-level files
    (i.e. not fall back into subdirectories when top-level media exists).
    """
    p = tmp_path
    top = p / "video_top.mp4"
    nested = p / "nested" / "cam" / "video_nested.MP4"
    nested.parent.mkdir(parents=True)
    top.write_text("dummy")
    nested.write_text("dummy")

    found = discover_media_paths([str(tmp_path)], recursive=False)
    expected = {str(top.resolve())}
    assert set(found) == expected
