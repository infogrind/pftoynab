# pftoynab

Convert a PostFinance account movements ("Bewegungen") CSV export into a
CSV ready for YNAB's file-based import.

## Installation

Install via Homebrew from my personal tap,
[infogrind/homebrew-tap](https://github.com/infogrind/homebrew-tap):

```sh
brew install infogrind/tap/pftoynab
```

(This taps `infogrind/homebrew-tap` -- Homebrew drops the `homebrew-`
prefix in the short tap name -- and installs `pftoynab` from it in one
step; equivalent to `brew tap infogrind/tap && brew install pftoynab`.)

## Usage

```sh
pftoynab [path to export CSV]
```

This writes `<input file name>_ynab.csv` next to the input file and prints
its path. Drag that file into YNAB's "File Based Import" for the matching
account.

If the path is omitted, the newest file matching `export_bewegungen_*.csv`
in `~/Downloads` is used automatically (both the directory and the glob
are configurable -- see Configuration) -- handy since that's exactly the
default filename and location a PostFinance export lands in.

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

## Configuration

Settings are read from a TOML file at `$XDG_CONFIG_HOME/pftoynab/config.toml`
(defaulting to `~/.config/pftoynab/config.toml` if `$XDG_CONFIG_HOME` isn't
set). The file is optional; without one, no prefixes are stripped.

```toml
[payee]
# Generic PostFinance prefixes (e.g. "payment to") stripped from the start
# of the payee text. Matched in order, first match wins. A trailing space
# is optional -- any whitespace right after the matched prefix is removed
# either way.
strip_prefixes = [
    "Gutschrift von ",
    "Lastschrift an ",
    "TWINT Kauf/Dienstleistung ",
    "CH-DD ",
]

[input]
# Where to look for an export when no path is given on the command line,
# and which filenames count as a match. Both default to the values shown.
directory = "~/Downloads"
glob = "export_bewegungen_*.csv"
```

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
- Beyond the generic prefix stripping this tool does (see Configuration),
  further payee cleanup (e.g. mapping "Coop-5646 Zürich Enge Bahnhof" to a
  clean "Coop" payee) is handled by YNAB's own Payee Rename Rules, which
  are self-learning: the first time you rename an imported payee to an
  existing one (in the import review screen or later in the register),
  YNAB records that as a rule and automatically applies the same renaming
  to future imports with matching payee text -- so each merchant only
  needs to be cleaned up once.
