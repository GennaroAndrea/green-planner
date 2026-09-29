"""Pipeline command line: `uv run python -m pipeline <command>`."""

import argparse
import sys

from pipeline.build import build
from pipeline.config import load_config
from pipeline.download import download_all


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # show progress live when output is redirected
    parser = argparse.ArgumentParser(prog="pipeline", description="Urban green planner pipeline")
    parser.add_argument("--city", default="bari", help="city config in config/<city>.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    dl = sub.add_parser("download", help="download raw datasets into data/raw/")
    dl.add_argument("--only", nargs="+", metavar="SOURCE", help="download only these sources")
    dl.add_argument("--force", action="store_true", help="re-download existing files")

    sub.add_parser("build", help="build data/processed/ artefacts from data/raw/")

    args = parser.parse_args()
    config = load_config(args.city)

    if args.command == "download":
        return 0 if download_all(config, only=args.only, force=args.force) else 1
    if args.command == "build":
        build(config)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
