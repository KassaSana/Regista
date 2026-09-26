"""Command-line composition root for Regista."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from regista import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface without performing any I/O."""
    parser = argparse.ArgumentParser(
        prog="regista",
        description="Evidence-backed soccer match insights from event data.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Choose concrete adapters and run the application.

    The concrete pipeline will be wired here as later increments introduce its
    ports and adapters. Keeping that choice in one place prevents domain code
    from depending on infrastructure.
    """
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
