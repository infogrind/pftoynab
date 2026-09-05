"""Writing the YNAB file-based-import CSV format.

YNAB's CSV importer recognizes the header "Date,Payee,Memo,Outflow,Inflow"
(dates as YYYY-MM-DD, Outflow/Inflow as non-negative decimals with only one
populated per row). Written as plain UTF-8 without a BOM, since YNAB's
importer and most non-Excel tools expect that.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from .parser import Transaction

YNAB_HEADER = ["Date", "Payee", "Memo", "Outflow", "Inflow"]


def _format_amount(value: Decimal | None) -> str:
    if value is None:
        return ""
    return str(value.quantize(Decimal("0.01")))


def write_ynab_csv(transactions: list[Transaction], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=",", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(YNAB_HEADER)
        for t in transactions:
            writer.writerow(
                [
                    t.txn_date.strftime("%Y-%m-%d"),
                    t.payee,
                    t.memo,
                    _format_amount(t.outflow),
                    _format_amount(t.inflow),
                ]
            )
