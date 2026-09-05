"""Interactive entry of the YNAB Memo field.

The Memo that ``parser.py`` derives from PostFinance's "Label" and
"Kategorie" columns is often not useful (the auto-assigned "Kategorie" in
particular). This lets the user type their own Memo for each transaction
instead, one at a time in date order, discarding whatever was derived from
the input.
"""

from __future__ import annotations

from .errors import PftoynabError
from .parser import MAX_MEMO_LEN, Transaction, sanitize_field


def run_interactive_memo(transactions: list[Transaction]) -> list[str]:
    warnings: list[str] = []
    total = len(transactions)
    print(f"Interactive memo entry for {total} transaction(s); press Enter to leave one empty.")

    for i, t in enumerate(transactions, start=1):
        # outflow/inflow are both stored as non-negative magnitudes (YNAB's CSV
        # format requires that), so negate outflow here to show a signed amount.
        amount = -t.outflow if t.outflow is not None else t.inflow
        print(f"[{i}/{total}] {t.txn_date.isoformat()}  {t.payee}  {amount:.2f}")
        try:
            raw = input("> ")
        except EOFError as e:
            raise PftoynabError("interactive memo entry aborted (end of input)") from e
        except KeyboardInterrupt as e:
            raise PftoynabError("interactive memo entry aborted") from e
        t.memo = sanitize_field(raw, MAX_MEMO_LEN, "memo", i, warnings)

    return warnings
