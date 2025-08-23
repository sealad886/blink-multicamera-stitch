#!/usr/bin/env python3
"""
Console entry point for blink-stitch.

This CLI parses a few lightweight flags related to input discovery and
maps them into the application's configuration before the runner is created.
"""
from typing import List, Optional
import argparse
# Local import to avoid heavy imports at module import time
from .main import BlinkMulticameraStitch, DEFAULT_CONFIG_PATH

def _parse_extensions(exts: Optional[str]):
    if not exts:
        return None
    return [e.strip() for e in exts.split(",") if e.strip()]

def main(argv: Optional[List[str]] = None):
    """
    Console entry point used by setuptools' console_scripts.

    Supported flags (additive and backward-compatible):
      -i, --input-path  (repeatable) : path to file or directory to discover media in
      --recursive / --no-recursive   : whether discovery should be recursive (default: True)
      --extensions                    : comma-separated list of extensions -> config["video_extensions"]

    If argv is provided, it is parsed instead of sys.argv.
    """
    parser = argparse.ArgumentParser(prog="blink-stitch")
    parser.add_argument("--config", help="Path to configuration file", default=None)
    parser.add_argument("-i", "--input-path", dest="input_paths", action="append", help="File or directory to include (repeatable)")
    parser.add_argument("--recursive", dest="recursive", action="store_true", help="Enable recursive discovery")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false", help="Disable recursive discovery")
    parser.set_defaults(recursive=True)
    parser.add_argument("--extensions", dest="extensions", help="Comma-separated list of extensions to limit discovery (e.g. mp4, wav)")

    args = parser.parse_args(argv)

    config_path = args.config if args.config is not None else DEFAULT_CONFIG_PATH

    # Instantiate application
    app = BlinkMulticameraStitch(config_path)

    # Map CLI args into app.config (additive; do not override if not provided)
    if args.input_paths:
        # preserve as list of strings
        app.config["input_paths"] = list(args.input_paths)

    # map recursive flag
    app.config["recursive_discovery"] = bool(args.recursive)

    # map extensions into video_extensions if provided
    if args.extensions:
        app.config["video_extensions"] = _parse_extensions(args.extensions)

    # Run application (unchanged behavior otherwise)
    return app.run()
