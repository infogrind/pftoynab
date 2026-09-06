# pftoynab

Convert a PostFinance account movements ("Bewegungen") or credit card
statement ("Kreditkartenübersicht") CSV export into a CSV ready for
YNAB's file-based import.

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

Both PostFinance export types are auto-detected from the file's header
content, so no flag is needed to say which one you're converting:

- Account movements ("Bewegungen"), e.g. `export_bewegungen_....csv`.
- Credit card statements ("Kreditkartenübersicht"), e.g.
  `export_kreditkartenuebersicht_....csv`. The `Date` column uses
  `Buchungsdatum` (posting date), matching the same posting-date semantics
  `Datum` has for account movements; the statement's separate
  `Einkaufsdatum` (purchase date) column is not used. A credit card bill
  payment row (`"2002 IHRE ZAHLUNG"`) is really a transfer from your
  checking account, not income; set `transfers.checking_account` (see
  Configuration) to have it rewritten to YNAB's special transfer payee
  automatically, or leave it unset to import it as a plain Inflow and fix
  it up manually in YNAB instead.

If the path is omitted, the newest file matching either configured glob
(`export_bewegungen_*.csv` or `export_kreditkartenuebersicht_*.csv`) in
`~/Downloads` is used automatically (the directory and both globs are
configurable -- see Configuration) -- handy since those are exactly the
default filenames and location a PostFinance export lands in.

Options:

- `-o, --output PATH` — write to a specific output path instead of the default.
- `--force` — overwrite the output file if it already exists.
- `-i, --interactive-memo` — after parsing, walk through every transaction in
  date order and type a `Memo` for each (Enter to leave one empty).
- `-c, --category-memo` — populate `Memo` from the input's `Label`/`Kategorie`
  columns instead of leaving it empty (the default -- PostFinance's
  auto-assigned `Kategorie` is rarely useful as-is). `-i` always starts each
  prompt blank regardless of this flag, since it's meant for typing a fresh
  Memo by hand.

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
# and which filenames count as a match for each export type. All three
# default to the values shown.
directory = "~/Downloads"
glob = "export_bewegungen_*.csv"
credit_card_glob = "export_kreditkartenuebersicht_*.csv"

[transfers]
# Credit card exports only. When set, a credit card bill payment row
# ("2002 IHRE ZAHLUNG") gets its Payee rewritten to "Transfer : <name>"
# instead of importing as a plain Inflow -- YNAB recognizes that special
# payee and turns the row into a real transfer. <name> must exactly match
# an existing account name in your YNAB budget (the checking account the
# payment came from). Unset by default (no rewriting).
checking_account = "Postfinance R&M"
```

With `transfers.checking_account` set, make sure the matching entry
doesn't also get imported on the checking account's own side (e.g. a
`"CH-DD PostFinance, Kreditkarten"` row there) -- YNAB creates the other
half of a transfer automatically, so importing both halves separately
creates a duplicate.

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
- YNAB categories cannot be set via CSV import. `Memo` is left empty by
  default; pass `-c`/`--category-memo` to carry the PostFinance-assigned
  category (and any user-set label) into it instead, for reference when
  categorizing in YNAB -- or use `-i`/`--interactive-memo` to type your own.
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
- Since same-date/same-amount transactions are exactly where that
  occurrence-based deduplication depends on import order rather than
  content, this tool warns (without blocking conversion) whenever the input
  contains such a group, listing them in their output order so you can
  double-check that order if you re-import an overlapping date range.
