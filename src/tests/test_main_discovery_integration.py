import yaml
from pathlib import Path
import sys
# Make package importable when tests run from project root:
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blink_stitch.main import BlinkMulticameraStitch

def create_layout(tmp_path: Path):
    p = tmp_path
    (p / "2025-01" / "a" / "cam1").mkdir(parents=True)
    (p / "2025-02").mkdir(parents=True)
    (p / "top").mkdir()
    # create files
    f1 = p / "2025-01" / "a" / "cam1" / "video1.mp4"
    f1.write_text("dummy")
    f2 = p / "2025-02" / "video2.MP4"
    f2.write_text("dummy")
    f3 = p / "top" / "audio1.wav"
    f3.write_text("dummy")
    return [f1, f2, f3]

def write_config(path: Path, out_dir: Path):
    cfg = {"output_dir": str(out_dir)}
    path.write_text(yaml.safe_dump(cfg))

def test_discover_input_files_non_recursive(tmp_path):
    files = create_layout(tmp_path)
    cfg_path = tmp_path / "cfg.yaml"
    write_config(cfg_path, tmp_path / "out")

    app = BlinkMulticameraStitch(str(cfg_path))
    # simulate CLI mapping: input-path mapped and recursive flag set to False
    app.config["input_paths"] = [str(tmp_path)]
    app.config["recursive_discovery"] = False

    found = app._discover_input_files()
    # non-recursive should only find top-level audio1.wav
    expected = {str((tmp_path / "top" / "audio1.wav").resolve())}
    assert set(found) == expected

def test_discover_input_files_recursive(tmp_path):
    files = create_layout(tmp_path)
    cfg_path = tmp_path / "cfg.yaml"
    write_config(cfg_path, tmp_path / "out")

    app = BlinkMulticameraStitch(str(cfg_path))
    app.config["input_paths"] = [str(tmp_path)]
    app.config["recursive_discovery"] = True

    found = app._discover_input_files()
    expected = set(str(p.resolve()) for p in files)
    assert set(found) == expected
