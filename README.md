# Blink MultiCamera Stitch

![blink-multicamera-stitch logo](assets/logo.svg)

Blink MultiCamera Stitch is an Apple‑Silicon‑optimised toolkit for automatically aligning and fusing large, overlapping Blink® home security camera exports. A Python backend selects the clearest audio and most speaker‑centric video with minimal user input, while an Electron front end offers a macOS‑native interface for optional review.

## Goals

- Automatically ingest and sort Blink exports with almost no manual effort.
- Align overlapping streams, pick the cleanest audio and the best speaker view, and produce a single coherent timeline.
- Provide a visually polished, easy‑to‑use desktop interface on macOS.

## Features

- **Python processing pipeline**: scripts for extraction (`extract.py`), clustering (`cluster.py`), deduplication (`dedupe.py`), annotation (`annotate.py`) and packaging (`package.py`).
- **Automatic stream selection**: `stitch.py` aligns clips and chooses the best audio/video tracks.
- **Electron GUI**: modern drag‑and‑drop interface housed in `gui/`.
- **Apple Silicon ready**: defaults to low thread counts and prefers Metal (MPS) when available.

## Repository Layout

- `gui/` – Electron application providing the macOS‑style UI.
- `extract.py`, `cluster.py`, `dedupe.py`, `annotate.py`, `stitch.py`, `package.py` – backend processing stages.
- `helpers.py`, `data.py` – shared utilities and data models.
- `progress/` – progress tracking and lightweight console UI components.

## Quickstart

### Backend
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # heavy deps optional in test environments
```

### GUI
```bash
cd gui
npm install
npm start
```

### Typical Workflow
```bash
python preflight.py
python stitch.py /path/to/export/*.mp4 --out releases/best.mp4  # auto-select best streams
python extract.py --input /path/to/export --output data/frames
python cluster.py --frames data/frames --out data/clustered
python dedupe.py --clusters data/clustered --out data/deduped
python annotate.py --input data/deduped --out data/annotated
python package.py --input data/annotated --out releases/stitched
```

## Development

- Tests: `pytest`
- Linting: run the project's linter if configured
- Pull requests welcome; please include tests and documentation updates

## License

Apache License 2.0; see `LICENSE` for details.
