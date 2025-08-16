#!/usr/bin/env python3
"""
Console entry point for blink-stitch.

Provides a thin wrapper that invokes the package's main runner.
"""

import sys
from typing import List, Optional

def main(argv: Optional[List[str]] = None):
    """
    Console entry point used by setuptools' console_scripts.

    If argv is provided it temporarily sets sys.argv for downstream argparse usage.
    """
    old_argv = None
    if argv is not None:
        old_argv = sys.argv[:]
        sys.argv = [sys.argv[0]] + list(argv)

    try:
        # Import the package's main module and call its main(). Use a local import
        # so package initialization happens first.
        from . import main as _main  # type: ignore
        return _main.main()
    finally:
        if old_argv is not None:
            sys.argv = old_argv