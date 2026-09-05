# pftoynab

Convert a PostFinance account movements ("Bewegungen") CSV export into a
CSV ready for YNAB's file-based import.

## Usage

```sh
uv run pftoynab <path to export CSV>
```

This writes `<input file name>_ynab.csv` next to the input file and prints
its path. Drag that file into YNAB's "File Based Import" for the matching
account.

Options:

- `-o, --output PATH` — write to a specific output path instead of the default.
- `--force` — overwrite the output file if it already exists.

The script validates the input thoroughly and refuses to write output if
anything looks wrong (unparsable dates/amounts, ambiguous or missing
amounts, an unrecognized file structure, etc.) rather than guessing.
Non-fatal issues (e.g. a field that had to be truncated, or text that
looked like a spreadsheet formula and was neutralized) are reported as
warnings but don't block the conversion.

Deduplication of transactions already present in your YNAB budget is left
entirely to YNAB itself — see "Notes on YNAB import" below.

## Development

```sh
uv sync
uv run pytest
uv run ruff check .
```

## Notes on YNAB import

- YNAB's file-based CSV import recognizes the header
  `Date,Payee,Memo,Outflow,Inflow` (dates as `YYYY-MM-DD`; `Outflow`/`Inflow`
  are non-negative amounts, only one populated per row). This is the format
  this tool produces.
- YNAB categories cannot be set via CSV import, so the PostFinance-assigned
  category (and any user-set label) is carried over into the `Memo` field
  instead, for reference when categorizing in YNAB.
- YNAB automatically deduplicates imported transactions per account using
  an identifier derived from `date + amount + occurrence` (the Nth
  transaction seen with that exact date and amount) — it does not look at
  the payee or memo text at all. This means re-importing the same file, or
  overlapping date ranges, is safe as long as same-day/same-amount
  transactions stay in a consistent relative order across exports (which
  PostFinance does). This tool sorts output chronologically while
  preserving each day's original relative order for exactly this reason.
- Payee matching/renaming (e.g. mapping "TWINT Kauf/Dienstleistung Coop-5646
  ..." to a clean "Coop" payee) is handled by YNAB's own Payee Rename Rules
  after import, not by this tool.
