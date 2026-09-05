"""Parsing and validation of PostFinance "Bewegungen" CSV exports.

The exported file is not a plain data table: it starts with a metadata
preamble (date range, account, currency), then a blank line, the real
header row, another blank line, the data rows, a blank line, and finally
a disclaimer footer. Column order and the exact currency label
("Gutschrift in CHF" vs "... in EUR") can vary, so the header row is
located by content rather than by line number, and columns are read by
name rather than by position.

Validation is deliberately strict and fails loudly on anything
unexpected (unparsable dates/amounts, ambiguous or missing amounts,
malformed rows) rather than guessing, since this data feeds a budget.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .errors import PftoynabError

MAX_PAYEE_LEN = 500
MAX_MEMO_LEN = 200

# Leading characters that spreadsheet tools (Excel, LibreOffice, Google
# Sheets) may interpret as the start of a formula if a cell is opened
# unquoted. Bank transaction text can contain attacker-influenced content
# (e.g. a payer-chosen TWINT/payment description), so it is neutralized
# defensively before being written out. See OWASP "CSV Injection".
# (Tab/CR are not included: whitespace normalization below already strips
# them as leading characters, so they can never end up at the start of the
# sanitized text.)
FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@")

_AMOUNT_RE = re.compile(r"[+-]?\d+(\.\d+)?")


@dataclass
class Transaction:
    txn_date: date
    payee: str
    memo: str
    outflow: Decimal | None
    inflow: Decimal | None


def _normalize(cell: str) -> str:
    return cell.strip().lower()


def _find_header(reader: csv.reader) -> dict[str, int | None]:
    for row in reader:
        normalized = [_normalize(c) for c in row]
        if "datum" not in normalized or "avisierungstext" not in normalized:
            continue
        credit_idx = next(
            (i for i, c in enumerate(normalized) if c.startswith("gutschrift in")), None
        )
        debit_idx = next(
            (i for i, c in enumerate(normalized) if c.startswith("lastschrift in")), None
        )
        if credit_idx is None or debit_idx is None:
            continue
        return {
            "date": normalized.index("datum"),
            "desc": normalized.index("avisierungstext"),
            "credit": credit_idx,
            "debit": debit_idx,
            "label": normalized.index("label") if "label" in normalized else None,
            "kategorie": normalized.index("kategorie") if "kategorie" in normalized else None,
        }
    raise PftoynabError(
        "could not find the expected PostFinance header row (looking for "
        "'Datum', 'Avisierungstext', 'Gutschrift in ...', 'Lastschrift in ...'). "
        "Is this a PostFinance account movements ('Bewegungen') CSV export?"
    )


def _parse_amount(
    raw: str, field_name: str, record_no: int, errors: list[str]
) -> Decimal | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    # Tolerate Swiss thousands separators (apostrophe / right single quote).
    stripped = cleaned.replace("'", "").replace("’", "").replace(" ", "")
    if not _AMOUNT_RE.fullmatch(stripped):
        errors.append(f"record {record_no}: {field_name} is not a valid amount: {raw!r}")
        return None
    try:
        value = Decimal(stripped)
    except InvalidOperation:
        errors.append(f"record {record_no}: {field_name} is not a valid amount: {raw!r}")
        return None
    if -value.as_tuple().exponent > 2:
        errors.append(
            f"record {record_no}: {field_name} has more than 2 decimal places: {raw!r}"
        )
        return None
    return value


def _sanitize(
    raw: str, max_len: int, field_name: str, record_no: int, warnings: list[str]
) -> str:
    text = " ".join(raw.split())
    if text and text[0] in FORMULA_TRIGGER_CHARS:
        text = "'" + text
        warnings.append(
            f"record {record_no}: {field_name} started with a formula-like character "
            "and was prefixed with ' to neutralize it in spreadsheet tools"
        )
    if len(text) > max_len:
        warnings.append(
            f"record {record_no}: {field_name} exceeded {max_len} characters and was truncated"
        )
        text = text[:max_len]
    return text


def parse_postfinance_csv(text: str) -> tuple[list[Transaction], list[str]]:
    if "\x00" in text:
        raise PftoynabError(
            "input file contains null bytes; this does not look like a valid CSV export"
        )

    reader = csv.reader(io.StringIO(text), delimiter=";", quotechar='"')

    try:
        cols = _find_header(reader)

        expected_ncols = max(v for v in cols.values() if v is not None) + 1

        errors: list[str] = []
        warnings: list[str] = []
        transactions: list[Transaction] = []

        record_no = 0
        started = False
        finished = False
        saw_disclaimer = False
        trailing_unexpected = 0

        for row in reader:
            is_blank = all(not c.strip() for c in row)

            # PostFinance always appends a "Disclaimer:" footer after the
            # data block (with or without a preceding blank line). Treat it,
            # and everything after it, as expected boilerplate to swallow
            # silently rather than warning on every single normal export.
            if not is_blank and row[0].strip().lower().startswith("disclaimer"):
                finished = True
                saw_disclaimer = True
                continue

            if saw_disclaimer:
                continue

            if is_blank:
                if started:
                    finished = True
                continue

            if finished:
                trailing_unexpected += 1
                continue

            started = True
            record_no += 1

            if len(row) < expected_ncols:
                errors.append(
                    f"record {record_no}: expected at least {expected_ncols} columns, got {len(row)}"
                )
                continue

            date_raw = row[cols["date"]].strip()
            try:
                txn_date = datetime.strptime(date_raw, "%d.%m.%Y").date()  # noqa: DTZ007 -- calendar date only, no timezone concept applies
            except ValueError:
                errors.append(f"record {record_no}: invalid date {date_raw!r} (expected DD.MM.YYYY)")
                continue

            errors_before_amounts = len(errors)
            credit = _parse_amount(row[cols["credit"]], "credit amount", record_no, errors)
            debit = _parse_amount(row[cols["debit"]], "debit amount", record_no, errors)
            if len(errors) > errors_before_amounts:
                continue

            if credit is None and debit is None:
                errors.append(f"record {record_no}: neither credit nor debit amount is populated")
                continue
            if credit is not None and debit is not None:
                errors.append(
                    f"record {record_no}: both credit and debit amounts are populated (ambiguous)"
                )
                continue
            if credit is not None and credit < 0:
                errors.append(
                    f"record {record_no}: credit amount is negative ({credit}); expected non-negative"
                )
                continue
            if debit is not None and debit > 0:
                errors.append(
                    f"record {record_no}: debit amount is positive ({debit}); expected non-positive"
                )
                continue

            payee = _sanitize(row[cols["desc"]], MAX_PAYEE_LEN, "payee", record_no, warnings)
            if not payee:
                errors.append(f"record {record_no}: description/payee is empty")
                continue

            memo_parts = []
            for key in ("label", "kategorie"):
                idx = cols[key]
                if idx is not None and idx < len(row) and row[idx].strip():
                    memo_parts.append(row[idx].strip())
            memo = _sanitize(" | ".join(memo_parts), MAX_MEMO_LEN, "memo", record_no, warnings)

            outflow = -debit if debit is not None else None
            inflow = credit if credit is not None else None

            transactions.append(Transaction(txn_date, payee, memo, outflow, inflow))
    except csv.Error as e:
        raise PftoynabError(f"failed to parse CSV structure: {e}") from e

    if trailing_unexpected:
        warnings.append(
            f"ignored {trailing_unexpected} non-blank line(s) after the data block "
            "(expected only a trailing disclaimer)"
        )

    if errors:
        raise PftoynabError("input validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

    if not transactions:
        raise PftoynabError("no transactions found in the input file")

    # Stable sort: preserves each day's original relative row order, which
    # PostFinance exports consistently across overlapping date-range
    # re-exports. This keeps YNAB's same-date/same-amount duplicate
    # detection (which counts occurrences in row order) working correctly
    # if the same period is ever imported twice.
    transactions.sort(key=lambda t: t.txn_date)

    return transactions, warnings
