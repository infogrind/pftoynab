from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import PftoynabError
from .parser import parse_postfinance_csv
from .writer import write_ynab_csv

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB; a personal transaction export is orders of magnitude smaller.


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
        help="Path to the PostFinance CSV export (e.g. export_bewegungen_....csv)",
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


def _run(input_path: Path, output_path: Path | None, force: bool) -> int:
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
    transactions, warnings = parse_postfinance_csv(text)

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
