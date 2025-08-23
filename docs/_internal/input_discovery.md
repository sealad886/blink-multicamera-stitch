# Input discovery (internal)

This internal note documents how input media files are discovered and how to configure the process.

Supported layouts

- Top-level directory containing month -> day -> camera subdirs (e.g. 2024-01/2024-01-01/cam1/*.mp4)
- Directory with day subdirectories
- Directory with media files directly
- Mixed layouts combining the above

Where discovery lives

- Canonical helper: [`src/blink_stitch/helpers.py`](src/blink_stitch/helpers.py:117) -> discover_media_paths
- CLI mapping: [`src/blink_stitch/cli.py`](src/blink_stitch/cli.py:1) parses --input-path/--recursive and maps into app.config
- Runtime usage: [`src/blink_stitch/main.py`](src/blink_stitch/main.py:102) -> BlinkMulticameraStitch._discover_input_files

Discovery behavior

- Inputs: list of paths (files or directories).
  - If recursive discovery is enabled (default) directories are traversed recursively using Path.rglob.
  - If recursive discovery is disabled (--no-recursive), discovery first looks for media files at the top-level of each provided directory. If any top-level media files are found those are returned. If no top-level media files exist, discovery falls back to scanning immediate subdirectories (one level deep) and returns files found there.
  - Audio-only preference: when non-recursive discovery is used and any standalone audio files are present at the top level (for example `.wav` or `.flac`), the runner prefers audio-only results and will return only those audio files (implementation: [`src/blink_stitch/main.py`](src/blink_stitch/main.py:217-222)).
- Extensions: case-insensitive matching against VIDEO_EXTS|AUDIO_EXTS or user-specified list. User-provided extensions are normalized (leading dot optional) and matching is case-insensitive; the list may include audio extensions and will restrict discovery to matching extensions.
- Output: deterministic sorted list of absolute paths (strings).
- Non-existent paths are skipped and logged at debug level.

Configuration keys

- input_paths: string or list of strings. Example:
```yaml
input_paths:
  - /data/blink_exports
  - /mnt/camera/day-2025-01-01
```
- recursive_discovery: boolean (default: true)
- video_extensions: optional list or comma-separated string to restrict discovery

CLI flags

- -i / --input-path PATH (repeatable) — add roots
- --recursive / --no-recursive — toggle recursion
- --extensions 'mp4,mov,wav' — restrict extensions

Runtime precedence

1. self.config["input_paths"] (set via config file or CLI)
2. CLI-mapped values merged into app.config before runner starts
3. legacy audio_dir fallback (glob .wav/.flac) when nothing else found

Notes and recommendations

- For very large datasets prefer passing per-month or per-day paths to limit scan scope.
- Discovery returns both video files and standalone audio files; downstream code extracts embedded audio when needed.
- If you change extension lists, ensure tests and CI reflect the changes.

Troubleshooting

- If you see zero files discovered, check:
  - the paths are correct and accessible to the process
  - file extensions are included in the configured list
- Logs:
  - debug: skipped non-existent paths (see [`src/blink_stitch/helpers.py`](src/blink_stitch/helpers.py:117))

See also

- README input discovery section in [`README.md`](README.md:1)
