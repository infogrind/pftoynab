from decimal import Decimal

import pytest
from conftest import build_export, row

from pftoynab.errors import PftoynabError
from pftoynab.parser import parse_postfinance_csv


def test_parses_valid_export():
    text = build_export(
        [
            row(date="02.01.2026", desc="Coop Zürich", debit="-9.15", credit="", kategorie="Einkaufen"),
            row(date="01.01.2026", desc="Gutschrift von ACME AG", debit="", credit="40", kategorie="Einkommen"),
        ]
    )
    transactions, warnings = parse_postfinance_csv(text)

    assert warnings == []
    assert len(transactions) == 2
    # sorted ascending by date
    assert [t.txn_date.isoformat() for t in transactions] == ["2026-01-01", "2026-01-02"]
    income, expense = transactions
    assert income.payee == "Gutschrift von ACME AG"
    assert income.inflow == Decimal(40)
    assert income.outflow is None
    assert expense.payee == "Coop Zürich"
    assert expense.outflow == Decimal("9.15")
    assert expense.inflow is None
    assert expense.memo == "Einkaufen"


def test_trailing_disclaimer_ignored_without_warning():
    text = build_export([row()], with_disclaimer=True)
    transactions, warnings = parse_postfinance_csv(text)
    assert len(transactions) == 1
    assert warnings == []


def test_unexpected_trailing_content_warns():
    text = build_export([row()], with_disclaimer=False)
    text += "\r\nsomething unexpected;that is not a disclaimer\r\n"
    transactions, warnings = parse_postfinance_csv(text)
    assert len(transactions) == 1
    assert any("ignored 1 non-blank line" in w for w in warnings)


def test_missing_header_raises():
    with pytest.raises(PftoynabError, match="could not find the expected PostFinance header row"):
        parse_postfinance_csv("just,some,random,csv\n1,2,3,4\n")


def test_no_data_rows_raises():
    text = build_export([])
    with pytest.raises(PftoynabError, match="no transactions found"):
        parse_postfinance_csv(text)


@pytest.mark.parametrize(
    ("row_kwargs", "match"),
    [
        pytest.param(
            {"credit": "5", "debit": "-5"},
            "both credit and debit amounts are populated",
            id="ambiguous-amounts",
        ),
        pytest.param(
            {"credit": "", "debit": ""},
            "neither credit nor debit amount is populated",
            id="no-amount",
        ),
        pytest.param({"date": "32.01.2026"}, "invalid date", id="invalid-date"),
        pytest.param(
            {"debit": "abc", "credit": ""}, "not a valid amount", id="invalid-amount-format"
        ),
        pytest.param(
            {"debit": "-10.999", "credit": ""},
            "more than 2 decimal places",
            id="excess-precision",
        ),
        pytest.param(
            {"credit": "-5", "debit": ""}, "credit amount is negative", id="negative-credit"
        ),
        pytest.param(
            {"debit": "5", "credit": ""}, "debit amount is positive", id="positive-debit"
        ),
    ],
)
def test_validation_errors_for_single_bad_field(row_kwargs, match):
    text = build_export([row(**row_kwargs)])
    with pytest.raises(PftoynabError, match=match):
        parse_postfinance_csv(text)


def test_amount_does_not_cascade_into_extra_error():
    # A single unparsable amount should surface exactly one error, not also
    # trigger the "neither populated" check on top of it.
    text = build_export([row(debit="abc", credit="")])
    with pytest.raises(PftoynabError) as exc_info:
        parse_postfinance_csv(text)
    messages = str(exc_info.value).splitlines()[1:]
    assert len(messages) == 1


def test_swiss_thousands_separator_parsed():
    text = build_export([row(debit="-1'234.50", credit="")])
    transactions, _ = parse_postfinance_csv(text)
    assert transactions[0].outflow == Decimal("1234.50")


def test_row_too_short_raises():
    text = build_export(["15.01.2026;\"Too short\";;-5"])
    with pytest.raises(PftoynabError, match="expected at least"):
        parse_postfinance_csv(text)


def test_empty_description_raises():
    text = build_export([row(desc="")])
    with pytest.raises(PftoynabError, match="description/payee is empty"):
        parse_postfinance_csv(text)


def test_multiple_errors_collected_together():
    text = build_export(
        [
            row(date="32.01.2026"),
            row(credit="5", debit="-5"),
            row(credit="", debit=""),
        ]
    )
    with pytest.raises(PftoynabError) as exc_info:
        parse_postfinance_csv(text)
    message = str(exc_info.value)
    assert "record 1" in message
    assert "record 2" in message
    assert "record 3" in message


@pytest.mark.parametrize("trigger", ["=", "+", "-", "@"])
def test_formula_injection_in_payee_is_neutralized(trigger):
    text = build_export([row(desc=f"{trigger}cmd|'/c calc'!A1")])
    transactions, warnings = parse_postfinance_csv(text)
    assert transactions[0].payee.startswith("'" + trigger)
    assert any("formula-like character" in w for w in warnings)


def test_payee_over_max_length_is_truncated_with_warning():
    long_desc = "A" * 600
    text = build_export([row(desc=long_desc)])
    transactions, warnings = parse_postfinance_csv(text)
    assert len(transactions[0].payee) == 500
    assert any("payee exceeded 500 characters" in w for w in warnings)


def test_memo_over_max_length_is_truncated_with_warning():
    text = build_export([row(kategorie="B" * 300)])
    transactions, warnings = parse_postfinance_csv(text)
    assert len(transactions[0].memo) == 200
    assert any("memo exceeded 200 characters" in w for w in warnings)


def test_null_byte_rejected():
    with pytest.raises(PftoynabError, match="null bytes"):
        parse_postfinance_csv("some\x00text")


def test_currency_agnostic_header_columns_detected():
    header = "Datum;Avisierungstext;Gutschrift in EUR;Lastschrift in EUR;Label;Kategorie;Valuta;Saldo in EUR"
    text = build_export([row()], header=header)
    transactions, _ = parse_postfinance_csv(text)
    assert len(transactions) == 1


def test_intraday_relative_order_preserved_on_sort():
    # Same-day rows should keep their original relative order after the
    # stable sort, which matters for YNAB's same-date/same-amount
    # duplicate-occurrence counting on re-import.
    text = build_export(
        [
            row(date="05.01.2026", desc="First same-day txn", debit="-1"),
            row(date="05.01.2026", desc="Second same-day txn", debit="-1"),
            row(date="01.01.2026", desc="Earlier day", debit="-1"),
        ]
    )
    transactions, _ = parse_postfinance_csv(text)
    same_day = [t for t in transactions if t.txn_date.isoformat() == "2026-01-05"]
    assert [t.payee for t in same_day] == ["First same-day txn", "Second same-day txn"]


def test_label_and_kategorie_combined_into_memo():
    text = build_export([row(label="Vacation", kategorie="Freizeit // Reisen")])
    transactions, _ = parse_postfinance_csv(text)
    assert transactions[0].memo == "Vacation | Freizeit // Reisen"


def test_strip_prefixes_removes_configured_prefix():
    text = build_export([row(desc="TWINT Kauf/Dienstleistung Coop Zürich")])
    transactions, _ = parse_postfinance_csv(text, strip_prefixes=["TWINT Kauf/Dienstleistung "])
    assert transactions[0].payee == "Coop Zürich"


def test_strip_prefixes_works_without_trailing_space_in_config():
    text = build_export([row(desc="Lastschrift an Wingo")])
    transactions, _ = parse_postfinance_csv(text, strip_prefixes=["Lastschrift an"])
    assert transactions[0].payee == "Wingo"


def test_strip_prefixes_only_applies_first_match():
    text = build_export([row(desc="Gutschrift von ACME AG")])
    transactions, _ = parse_postfinance_csv(
        text, strip_prefixes=["Lastschrift an", "Gutschrift von"]
    )
    assert transactions[0].payee == "ACME AG"


def test_strip_prefixes_no_match_leaves_payee_unchanged():
    text = build_export([row(desc="Some other payee")])
    transactions, _ = parse_postfinance_csv(text, strip_prefixes=["Gutschrift von"])
    assert transactions[0].payee == "Some other payee"


def test_strip_prefixes_empty_string_entry_ignored():
    text = build_export([row(desc="Normal payee")])
    transactions, _ = parse_postfinance_csv(text, strip_prefixes=[""])
    assert transactions[0].payee == "Normal payee"


def test_strip_prefixes_stripping_to_empty_is_a_validation_error():
    text = build_export([row(desc="CH-DD")])
    with pytest.raises(PftoynabError, match="description/payee is empty"):
        parse_postfinance_csv(text, strip_prefixes=["CH-DD"])


def test_extra_trailing_columns_tolerated():
    # A row with more columns than the mapped ones (e.g. a future PostFinance
    # export adding a new trailing column) should not be rejected.
    text = build_export(["15.01.2026;\"Extra col\";;-5;;Kategorie;15.01.2026;1000;EXTRA"])
    transactions, _ = parse_postfinance_csv(text)
    assert len(transactions) == 1
