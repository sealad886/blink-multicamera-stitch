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
