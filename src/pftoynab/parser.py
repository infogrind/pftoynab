"""Parsing and validation of PostFinance CSV exports.

Two export types are supported: account movements ("Bewegungen") and
credit card statements ("Kreditkartenübersicht"). Both share the same
overall shape -- a metadata preamble, a blank line, the real header row,
another blank line, the data rows, a blank line, and finally a disclaimer
footer -- but use different column names (e.g. credit card statements
have "Buchungsdatum"/"Buchungsdetails" where account movements have
"Datum"/"Avisierungstext", plus an extra "Einkaufsdatum" purchase-date
column that this tool ignores in favor of "Buchungsdatum", to match the
posting-date semantics "Datum" already has for account movements).
Column order and the exact currency label ("Gutschrift in CHF" vs "...
in EUR") can also vary, so the header row is located by content rather
than by line number, and columns are read by name rather than by
position.

Validation is deliberately strict and fails loudly on anything
unexpected (unparsable dates/amounts, ambiguous or missing amounts,
malformed rows) rather than guessing, since this data feeds a budget.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterator
from dataclasses import astuple, dataclass
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

# PostFinance's fixed description for a credit card bill payment coming in
# from the linked checking account. Recognized so it can be rewritten into
# YNAB's special transfer payee instead of importing as plain income -- see
# transfer_checking_account below.
TRANSFER_TRIGGER_DESC = "2002 IHRE ZAHLUNG"


@dataclass
class Transaction:
    txn_date: date
    payee: str
    memo: str
    outflow: Decimal | None
    inflow: Decimal | None


def _normalize(cell: str) -> str:
    return cell.strip().lower()


@dataclass(frozen=True)
class ColumnIndices:
    date: int
    desc: int
    credit: int
    debit: int
    label: int | None
    kategorie: int | None


# Known (date column, description column) header-name pairs, one per
# supported PostFinance export type. Tried in order; the first pair fully
# present in a row wins.
_HEADER_PROFILES = [
    ("datum", "avisierungstext"),  # account movements ("Bewegungen")
    ("buchungsdatum", "buchungsdetails"),  # credit card statement ("Kreditkartenübersicht")
]


def _find_header(reader: Iterator[list[str]]) -> ColumnIndices:
    for row in reader:
        normalized = [_normalize(c) for c in row]
        profile = next(
            (
                (date_key, desc_key)
                for date_key, desc_key in _HEADER_PROFILES
                if date_key in normalized and desc_key in normalized
            ),
            None,
        )
        if profile is None:
            continue
        date_key, desc_key = profile
        credit_idx = next(
            (i for i, c in enumerate(normalized) if c.startswith("gutschrift in")), None
        )
        debit_idx = next(
            (i for i, c in enumerate(normalized) if c.startswith("lastschrift in")), None
        )
        if credit_idx is None or debit_idx is None:
            continue
        return ColumnIndices(
            date=normalized.index(date_key),
            desc=normalized.index(desc_key),
            credit=credit_idx,
            debit=debit_idx,
            label=normalized.index("label") if "label" in normalized else None,
            kategorie=normalized.index("kategorie") if "kategorie" in normalized else None,
        )
    raise PftoynabError(
        "could not find the expected PostFinance header row (looking for "
        "'Datum'+'Avisierungstext' (account movements) or 'Buchungsdatum'+"
        "'Buchungsdetails' (credit card statement), plus 'Gutschrift in ...' "
        "and 'Lastschrift in ...'). Is this a PostFinance CSV export?"
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
    exponent = value.as_tuple().exponent
    assert isinstance(exponent, int)  # stripped was regex-validated, so never NaN/Infinity
    if -exponent > 2:
        errors.append(
            f"record {record_no}: {field_name} has more than 2 decimal places: {raw!r}"
        )
        return None
    return value


def signed_amount(t: Transaction) -> Decimal:
    """Amount as YNAB will treat it: negative for an outflow, positive for an inflow.

    Exactly one of outflow/inflow is populated by _parse_row, so this is total.
    """
    if t.outflow is not None:
        return -t.outflow
    assert t.inflow is not None
    return t.inflow


def _strip_configured_prefix(text: str, prefixes: list[str]) -> str:
    """Strip the first configured prefix that matches the start of text.

    Prefixes may be given with or without a trailing space in the config;
    either way, any whitespace immediately following the matched prefix is
    also consumed, so "Gutschrift von" and "Gutschrift von " behave the same.
    """
    for prefix in prefixes:
        trimmed_prefix = prefix.rstrip()
        if trimmed_prefix and text.startswith(trimmed_prefix):
            return text[len(trimmed_prefix) :].lstrip()
    return text


def sanitize_field(
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


def _parse_row(
    row: list[str],
    record_no: int,
    cols: ColumnIndices,
    expected_ncols: int,
    strip_prefixes: list[str],
    include_category_memo: bool,
    transfer_checking_account: str | None,
    errors: list[str],
    warnings: list[str],
) -> Transaction | None:
    if len(row) < expected_ncols:
        errors.append(
            f"record {record_no}: expected at least {expected_ncols} columns, got {len(row)}"
        )
        return None

    date_raw = row[cols.date].strip()
    try:
        txn_date = datetime.strptime(date_raw, "%d.%m.%Y").date()  # noqa: DTZ007 -- calendar date only, no timezone concept applies
    except ValueError:
        errors.append(f"record {record_no}: invalid date {date_raw!r} (expected DD.MM.YYYY)")
        return None

    errors_before_amounts = len(errors)
    credit = _parse_amount(row[cols.credit], "credit amount", record_no, errors)
    debit = _parse_amount(row[cols.debit], "debit amount", record_no, errors)
    if len(errors) > errors_before_amounts:
        return None

    if credit is None and debit is None:
        errors.append(f"record {record_no}: neither credit nor debit amount is populated")
        return None
    if credit is not None and debit is not None:
        errors.append(
            f"record {record_no}: both credit and debit amounts are populated (ambiguous)"
        )
        return None
    if credit is not None and credit < 0:
        errors.append(
            f"record {record_no}: credit amount is negative ({credit}); expected non-negative"
        )
        return None
    if debit is not None and debit > 0:
        errors.append(
            f"record {record_no}: debit amount is positive ({debit}); expected non-positive"
        )
        return None

    raw_desc = row[cols.desc].strip()
    if transfer_checking_account and raw_desc.casefold() == TRANSFER_TRIGGER_DESC.casefold():
        payee = f"Transfer : {transfer_checking_account}"
        warnings.append(
            f"record {record_no}: rewrote {raw_desc!r} as a transfer to/from "
            f"{transfer_checking_account!r} -- make sure the matching entry on that "
            "account isn't also imported separately, or YNAB will create a duplicate"
        )
    else:
        desc = _strip_configured_prefix(raw_desc, strip_prefixes)
        payee = sanitize_field(desc, MAX_PAYEE_LEN, "payee", record_no, warnings)
        if not payee:
            errors.append(f"record {record_no}: description/payee is empty")
            return None

    if include_category_memo:
        memo_parts = [
            row[idx].strip()
            for idx in (cols.label, cols.kategorie)
            if idx is not None and idx < len(row) and row[idx].strip()
        ]
        memo = sanitize_field(" | ".join(memo_parts), MAX_MEMO_LEN, "memo", record_no, warnings)
    else:
        memo = ""

    outflow = -debit if debit is not None else None
    inflow = credit if credit is not None else None

    return Transaction(txn_date, payee, memo, outflow, inflow)


def _warn_about_ambiguous_dedup_groups(transactions: list[Transaction], warnings: list[str]) -> None:
    """Flag transactions YNAB's own deduplication can't tell apart by content.

    YNAB deduplicates imported transactions per account using date + amount +
    "occurrence" (the Nth transaction seen with that exact date and amount)
    -- it never looks at payee or memo. So when several transactions share a
    date and amount, re-importing an overlapping date range is only safe for
    them if their relative order is identical across both exports. This tool
    preserves PostFinance's original row order (see the sort below), but it
    has no visibility into any other export, so it can only flag the
    ambiguity, not confirm the order will actually hold up.
    """
    groups: dict[tuple[date, Decimal], list[Transaction]] = {}
    for t in transactions:
        groups.setdefault((t.txn_date, signed_amount(t)), []).append(t)

    for (txn_date, amount), group in groups.items():
        if len(group) < 2:
            continue
        occurrences = ", ".join(f"#{i} {t.payee!r}" for i, t in enumerate(group, start=1))
        warnings.append(
            f"{len(group)} transactions on {txn_date.isoformat()} share amount {amount:.2f}; "
            "YNAB distinguishes these only by their relative import order (occurrence "
            "1, 2, ...), not by payee/memo, so re-importing an overlapping date range is "
            f"only safe if that order matches this export's: {occurrences}"
        )


def parse_postfinance_csv(
    text: str,
    strip_prefixes: list[str] | None = None,
    include_category_memo: bool = False,
    transfer_checking_account: str | None = None,
) -> tuple[list[Transaction], list[str]]:
    strip_prefixes = strip_prefixes or []

    if "\x00" in text:
        raise PftoynabError(
            "input file contains null bytes; this does not look like a valid CSV export"
        )

    reader = csv.reader(io.StringIO(text), delimiter=";", quotechar='"')

    try:
        cols = _find_header(reader)

        expected_ncols = max(v for v in astuple(cols) if v is not None) + 1

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

            transaction = _parse_row(
                row,
                record_no,
                cols,
                expected_ncols,
                strip_prefixes,
                include_category_memo,
                transfer_checking_account,
                errors,
                warnings,
            )
            if transaction is not None:
                transactions.append(transaction)
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

    _warn_about_ambiguous_dedup_groups(transactions, warnings)

    return transactions, warnings
