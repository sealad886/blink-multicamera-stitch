# blink-multicamera-stitch

![blink-multicamera-stitch logo](assets/logo.svg)

blink-multicamera-stitch is a Python toolkit for processing, deduplicating, and stitching video/image data collected from multiple Blink-style cameras. It provides utilities for extraction, clustering, annotation, and progress tracking intended for offline batch processing and analysis.

## Features

- Extract frames and metadata from camera exports (`extract.py`).
- Cluster and deduplicate similar frames (`cluster.py`, `dedupe.py`).
- Annotate and prepare stitched outputs (`annotate.py`, `package.py`).
- Progress tracking and a small UI module (`progress/`, `ui.py`).
- Small, composable scripts for preflight checks and data helpers.

## Repository layout

- `extract.py` - tools to extract frames and metadata from Blink exports.
- `cluster.py` - clustering utilities for grouping similar frames.
- `dedupe.py` - deduplication logic.
- `annotate.py` - annotation helpers and workflows.
- `package.py` - final packaging / export helpers.
- `preflight.py` - checks to run before processing.
- `helpers.py`, `data.py` - helper functions and data models.
- `progress/` - progress tracking, errors, and lightweight UI components.
- `requirements.txt` - Python dependencies.

## Quickstart

---

### OpenMP Mutex Blocking and Thread Contention

Some native libraries (PyTorch, MKL, OpenMP) may cause mutex blocking or thread contention, resulting in hangs or poor performance. This is resolved by setting the following environment variables at startup:

- `KMP_DUPLICATE_LIB_OK=TRUE`
- `OMP_NUM_THREADS=1`
- `MKL_NUM_THREADS=1`

These are set programmatically in [`src/blink_stitch/helpers.py`](src/blink_stitch/helpers.py:6-14) and applied automatically when running the main entry point ([`src/blink_stitch/main.py`](src/blink_stitch/main.py:8)). If you run modules or scripts outside the packaged entry point, set these variables manually in your environment.

Example (bash):
```bash
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
```

For details, see [`docs/_internal/progress-system.md`](docs/_internal/progress-system.md:1).

1. Create a Python virtual environment (recommended) and install the package (editable):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
# or: pip install .
```

2. Run the packaged preflight check or view the CLI help:

```bash
blink-stitch --help
# or, run the module directly:
python -m blink_stitch.preflight
```

3. Extract frames from a Blink export (example):

```bash
python -m blink_stitch.extract --input /path/to/export --output data/frames
```

4. Cluster and deduplicate:

```bash
python -m blink_stitch.cluster --frames data/frames --out data/clustered
python -m blink_stitch.dedupe --clusters data/clustered --out data/deduped
```

5. Annotate and package results:

```bash
python -m blink_stitch.annotate --input data/deduped --out data/annotated
python -m blink_stitch.package --input data/annotated --out releases/stitched
```

Notes:
- The package includes repository assets and documentation in the distribution (see `MANIFEST.in` / `setup.cfg`).
- If a module does not implement a `__main__` guard, run it via the package's console entry (`blink-stitch`) or by importing the module programmatically.

Adjust CLI flags to your workflow; run each script with `-h` to view available options.

## Development

- Tests: run `pytest` (project includes a small `test_threading_resource.py`).
- Linting: run the project's linter if configured (check `pyproject.toml` or `requirements.txt`).
- When adding features, include unit tests and update this README.

## Contributing

Contributions welcome via issues and pull requests. Please include tests for new behavior.

## License

This repository is licensed under the Apache License 2.0. See `LICENSE` for details.

## Input discovery

The tool now supports flexible input layouts so you can point it at a wide variety of on-disk exports:

- Supported layouts
  - Top-level directory containing month directories (e.g. `2024-01/2024-01-01/cam1/*.mp4`)
  - Directory containing day directories
  - Directory containing video/audio files directly
  - Any mix of the above

- Discovery behavior notes
  - Recursive discovery (default) traverses directories using Path.rglob.
  - Non-recursive discovery (`--no-recursive`) prefers top-level files in each input directory. If top-level media files exist those are returned. If none are present, discovery falls back to scanning immediate subdirectories (one level) and returns files found there. For mixed layouts this ensures predictable results: top-level files are preferred when present.
  - Audio-only preference: when non-recursive discovery is used and top-level files include any standalone audio files (e.g. `.wav`, `.flac`), the runner prefers audio-only results and will return only those audio files (implementation: [`src/blink_stitch/main.py`](src/blink_stitch/main.py:217-222)).
- Audio handling
  - No separate audio files are required. When no standalone audio is present the pipeline will extract embedded audio from video containers as needed.
  - The discovery step returns both video containers and audio files; later pipeline stages extract or reuse audio as appropriate.

Configuration keys (YAML)
- input_paths: string or list of strings. Example:
  ```
  input_paths:
    - /data/blink_exports
    - /mnt/camera/day-2025-01-01
  ```
- Note: `video_extensions` / `--extensions` values are normalized (leading dot optional, case-insensitive); they may include audio extensions and will restrict discovery to matching extensions.
- recursive_discovery: boolean (default: true). If true, directories are searched recursively.
- video_extensions: optional list or comma-separated string to override which extensions are considered media (e.g. `['.mp4', '.mov']`).

CLI flags
- -i / --input-path PATH   (repeatable) — add one or more input roots
- --recursive / --no-recursive — toggle recursive discovery (default: enabled)
- --extensions 'mp4,mov,wav' — optional comma-separated list to restrict discovery to specific extensions

Examples
- Discover recursively from a data directory:
  ```
  blink-stitch -i /data/blink_exports --recursive
  ```
- Discover a single top-level directory only (no recursion):
  ```
  blink-stitch -i /mnt/camera --no-recursive
  ```
- Restrict discovery to mp4 files:
  ```
  blink-stitch -i /data --extensions mp4
  ```

Notes and recommendations
- The discovery uses pathlib.Path.rglob for recursive traversal; scanning very large filesystems may be slow. For large datasets prefer passing explicit per-month or per-day paths to limit the search scope.
- Backward compatibility: if no `input_paths` or CLI input is provided the application will fall back to the legacy `audio_dir` behavior (glob for `.wav` / `.flac`) so existing workflows continue to work.
- See `docs/_internal/input_discovery.md` for internal details and examples.