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

## Detect the checking-account side of a credit card transfer too

Credit card bill payments can now be rewritten to YNAB's
`"Transfer : <Account Name>"` payee via `transfers.checking_account` (see
README), but only on the credit card export's `"2002 IHRE ZAHLUNG"` row.
The matching outflow on the checking account side (typically labeled
`"CH-DD PostFinance, Kreditkarten"`) is not detected or rewritten, so
importing that row normally works fine on its own -- but if it's
*also* imported after the credit card side already created the transfer
automatically, that's a duplicate. Could extend the same rewriting to the
checking-account export (matching on the fixed description instead), but
that needs the credit card's account name configured symmetrically, and
carries the same "don't import both halves" caveat in the other
direction, so it wasn't done together with the credit card side.
