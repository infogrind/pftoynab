# Ideas for later

Things that came up in conversation but aren't worth building yet.

## Skip already-imported transactions in `-i`/`--interactive-memo`

Right now `-i` walks every transaction in the export, including ones from
prior overlapping exports that have already been imported into YNAB (see
"Notes on YNAB import" in the README for why exports overlap on purpose).
Re-typing (or re-skipping) memos for those every time is the main annoyance
with interactive mode.

Considered and rejected as too complex for the payoff: an interactive
picker that pages through recent entries (newest first, N per page) and
lets the user pick the first not-yet-imported one as a starting point.

More promising: a local watermark file (e.g.
`~/.local/state/pftoynab/state.json`) recording the last processed date and
how many transactions fell on that exact date, updated after each
successful run. `-i` would skip prompting for anything at or before the
watermark. Since the normal workflow is convert-then-immediately-import,
"already written by pftoynab" is a solid proxy for "already in YNAB"
without needing any YNAB API access.

Caveats to design around:

- Relies on the same ordering-consistency assumption the existing
  same-date/same-amount dedup warning already documents (PostFinance
  emitting same-day transactions in a stable order across exports). If
  that ever breaks, the watermark could skip a genuinely new transaction
  or re-show an old one -- low-stakes since it only affects the memo
  *prompt*, not what's written to the output CSV or YNAB's own dedup.
- Needs an escape hatch (e.g. `--reset-watermark`) for whenever an import
  is skipped, fails partway, or is deliberately redone.

## Import directly via the YNAB API instead of a CSV hand-off

Instead of writing a CSV for manual drag-and-drop import, use YNAB's API
(<https://api.ynab.com/>) to create transactions directly. Would need:

- A personal access token, stored somewhere sane (not plain-text in the
  TOML config -- maybe via the OS keychain, or at least a file with
  restricted permissions and a clear warning).
- Budget/account selection (config or a flag).
- Rethinking deduplication: YNAB's `import_id` field
  (`YNAB:<milliunits>:<date>:<occurrence>`) is exactly the same
  date+amount+occurrence identifier described in the README, so this tool
  would compute it itself rather than relying on YNAB's CSV importer to.
  That actually removes the ambiguity the same-date/same-amount warning
  exists for today, since we'd control `occurrence` explicitly instead of
  hoping row order matches between overlapping exports.
- Would make the "already imported" problem largely moot: the API can be
  asked what's already in the register, so both the interactive-memo
  skip-already-imported issue above and general dedup could be solved
  properly instead of via heuristics.

Bigger effort than the watermark idea, but more fundamentally solves
several problems at once (this one, dedup ambiguity, and the manual
drag-and-drop step itself).

## Mark credit card bill payments as transfers

Credit card statement exports contain a `"2002 IHRE ZAHLUNG"` row for each
payment of the bill from the linked checking account -- really a transfer,
not income, but YNAB's file-based CSV import has no field for marking a
row as a transfer, so it lands as a plain Inflow today (see "Notes on YNAB
import" in the README).

YNAB does recognize a special payee value on CSV import,
`"Transfer : <Account Name>"`, that turns a row into a real transfer
instead of a plain external transaction. Since `"2002 IHRE ZAHLUNG"` is a
fixed, reliably-matchable description, this tool could rewrite just that
payee to `Transfer : <configured checking account name>` automatically
(via a new config option naming the paired checking account), removing
the manual fixup step. Not done yet since it only came up in passing while
adding credit card export support, and needs checking exactly how strict
YNAB is about the account name matching an existing account in the target
budget.
