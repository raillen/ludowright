"""Command-line entry point for generated JSON Schema publication."""

from __future__ import annotations

import argparse
from pathlib import Path

from ludowright.contracts.publication import (
    DEFAULT_SCHEMA_ROOT,
    publication_drift,
    write_publication,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ludowright.contracts")
    parser.add_argument("command", choices=("publish", "check"))
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SCHEMA_ROOT,
        help="Schema publication directory.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "publish":
        paths = write_publication(args.output)
        for path in paths:
            print(path.as_posix())
        return 0

    drift = publication_drift(args.output)
    if drift:
        for item in drift:
            print(item)
        return 1
    print(f"JSON Schema publication is current: {args.output.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
