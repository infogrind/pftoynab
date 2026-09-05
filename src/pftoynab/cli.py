from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config, find_config_path, load_config
from .errors import PftoynabError
from .parser import parse_postfinance_csv
from .writer import write_ynab_csv

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB; a personal transaction export is orders of magnitude smaller.


def _find_latest_export(config: Config) -> Path:
    directory = Path(config.input_directory).expanduser() if config.input_directory else Path.home() / "Downloads"
    if not directory.is_dir():
        raise PftoynabError(f"downloads directory not found: {directory}")

    matches = [p for p in directory.glob(config.input_glob) if p.is_file()]
    if not matches:
        raise PftoynabError(
            f"no file matching {config.input_glob!r} found in {directory}; "
            "pass a file path explicitly"
        )
    return max(matches, key=lambda p: p.stat().st_mtime)


def _load_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError as e:
        raise PftoynabError(
            f"could not decode {path} as UTF-8 or Windows-1252: {e}"
        ) from e


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pftoynab",
        description="Convert a PostFinance account movements CSV export into a CSV ready for YNAB's file-based import.",
    )
    parser.add_argument(
        "input_csv",
        type=Path,
        nargs="?",
        default=None,
        help=(
            "Path to the PostFinance CSV export (e.g. export_bewegungen_....csv). "
            "If omitted, the newest file matching the configured glob "
            "(default: export_bewegungen_*.csv) in ~/Downloads is used."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: <input file name>_ynab.csv next to the input file)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists",
    )
    return parser


def _run(input_path: Path | None, output_path: Path | None, force: bool) -> int:
    config = load_config(find_config_path())

    if input_path is None:
        input_path = _find_latest_export(config)
        print(f"No input file given; using the newest export in Downloads: {input_path}")
    else:
        input_path = input_path.expanduser()

    if not input_path.exists():
        raise PftoynabError(f"input file not found: {input_path}")
    if input_path.is_dir():
        raise PftoynabError(f"input path is a directory, not a file: {input_path}")

    size = input_path.stat().st_size
    if size == 0:
        raise PftoynabError(f"input file is empty: {input_path}")
    if size > MAX_FILE_SIZE:
        raise PftoynabError(
            f"input file is too large ({size:,} bytes > {MAX_FILE_SIZE:,} byte limit): {input_path}"
        )

    text = _load_text(input_path)
    transactions, warnings = parse_postfinance_csv(text, strip_prefixes=config.strip_prefixes)

    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)

    if output_path is None:
        output_path = input_path.with_name(f"{input_path.stem}_ynab.csv")
    else:
        output_path = output_path.expanduser()

    if output_path.resolve() == input_path.resolve():
        raise PftoynabError("output path must differ from the input path")
    if output_path.exists() and not force:
        raise PftoynabError(
            f"output file already exists: {output_path} (use --force to overwrite)"
        )

    write_ynab_csv(transactions, output_path)

    print(f"Wrote {len(transactions)} transaction(s) to {output_path}; ready for import into YNAB.")
    if warnings:
        print(f"({len(warnings)} warning(s) above -- review before importing.)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args.input_csv, args.output, args.force)
    except PftoynabError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
