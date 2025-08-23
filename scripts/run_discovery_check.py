#!/usr/bin/env python3
# scripts/run_discovery_check.py
# Create temporary layouts and invoke blink_stitch.helpers.discover_media_paths
# Uses only stdlib + importing the project's helper function.
from __future__ import annotations

import os
import json
import sys
import platform
import tempfile
from pathlib import Path
from typing import List

# Ensure the project src/ is on sys.path so this script can be run from repo root.
# Insert absolute repo_root/src at sys.path[0] before importing blink_stitch.
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_src_path = os.path.join(_repo_root, "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# Import the discovery function from the package
try:
    from blink_stitch.helpers import discover_media_paths
except Exception as e:
    discover_media_paths = None  # will report as error below
    _import_error = str(e)


def make_files(paths: List[Path]) -> None:
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        # create an empty file (deterministic content)
        p.write_bytes(b"")  # minimal dummy file


def layout_month_day_camera(root: Path) -> List[Path]:
    # root/2024-01/2024-01-01/cam1/video1.mp4
    # root/2024-02/2024-02-02/cam2/video2.MP4
    p1 = root / "2024-01" / "2024-01-01" / "cam1" / "video1.mp4"
    p2 = root / "2024-02" / "2024-02-02" / "cam2" / "video2.MP4"
    make_files([p1, p2])
    return [p1.resolve(), p2.resolve()]


def layout_day_only(root: Path) -> List[Path]:
    # root/2024-01-01/videoA.mp4
    p1 = root / "2024-01-01" / "videoA.mp4"
    make_files([p1])
    return [p1.resolve()]


def layout_flat(root: Path) -> List[Path]:
    # root/video_flat.mov
    p1 = root / "video_flat.mov"
    make_files([p1])
    return [p1.resolve()]


def layout_mixed(root: Path) -> List[Path]:
    # root/video_top.mp4, root/nested/cam/video_nested.MP4
    p1 = root / "video_top.mp4"
    p2 = root / "nested" / "cam" / "video_nested.MP4"
    make_files([p1, p2])
    return [p1.resolve(), p2.resolve()]


def run_check_for_layout(layout_name: str, create_fn):
    results = []
    with tempfile.TemporaryDirectory() as td:
        base = Path(td).resolve()
        try:
            expected_files = create_fn(base)
        except Exception as e:
            # Creation error
            results.append(
                {
                    "python_version": platform.python_version(),
                    "pytest_version": get_pytest_version(),
                    "layout_name": layout_name,
                    "recursive": None,
                    "discovered": [],
                    "error": f"layout_creation_failed: {e}",
                }
            )
            return results

        for recursive in (True, False):
            json_obj = {
                "python_version": platform.python_version(),
                "pytest_version": get_pytest_version(),
                "layout_name": layout_name,
                "recursive": recursive,
                "discovered": [],
            }
            if discover_media_paths is None:
                json_obj["error"] = f"import_discover_media_paths_failed: {_import_error}"
                results.append(json_obj)
                continue
            try:
                found = discover_media_paths([str(base)], recursive=recursive)
                # normalize to absolute sorted list (deterministic)
                resolved = sorted(str(Path(p).resolve()) for p in found)
                json_obj["discovered"] = resolved
            except Exception as e:
                json_obj["error"] = f"discover_media_paths_exception: {e}"
            results.append(json_obj)
    return results


def get_pytest_version():
    try:
        import pytest

        return getattr(pytest, "__version__", None)
    except Exception:
        return None


def main():
    all_layouts = [
        ("month_day_camera", layout_month_day_camera),
        ("day_only", layout_day_only),
        ("flat", layout_flat),
        ("mixed", layout_mixed),
    ]
    # Print one JSON object per discovery run (layout x recursive flag)
    outputs = []
    for name, fn in all_layouts:
        outputs.extend(run_check_for_layout(name, fn))

    # Print newline-delimited JSON objects for easier capture
    for o in outputs:
        sys.stdout.write(json.dumps(o, ensure_ascii=False) + "\n")
    # Always exit 0 as requested
    sys.exit(0)


if __name__ == "__main__":
    main()