from datetime import date
from decimal import Decimal

import pytest

from pftoynab.errors import PftoynabError
from pftoynab.interactive import ask_twint_contact_names, run_interactive_memo
from pftoynab.parser import Transaction


def _tx(day, payee, memo="", outflow=None, inflow=None):
    return Transaction(date(2026, 1, day), payee, memo, outflow, inflow)


def test_enters_memo_for_each_transaction_in_order(monkeypatch, capsys):
    transactions = [
        _tx(1, "Coop", "Einkaufen", outflow=Decimal("9.15")),
        _tx(2, "Employer", "Einkommen", inflow=Decimal(3000)),
    ]
    answers = iter(["groceries", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    warnings = run_interactive_memo(transactions)

    assert warnings == []
    assert transactions[0].memo == "groceries"
    assert transactions[1].memo == ""
    out = capsys.readouterr().out
    assert "[1/2] 2026-01-01  Coop  -9.15" in out
    assert "[2/2] 2026-01-02  Employer  3000.00" in out


def test_discards_previously_derived_memo(monkeypatch):
    transactions = [_tx(1, "Coop", "some Kategorie value", outflow=Decimal(1))]
    monkeypatch.setattr("builtins.input", lambda prompt: "")

    run_interactive_memo(transactions)

    assert transactions[0].memo == ""


def test_formula_like_memo_is_neutralized(monkeypatch):
    transactions = [_tx(1, "Coop", outflow=Decimal(1))]
    monkeypatch.setattr("builtins.input", lambda prompt: "=cmd|'/c calc'")

    warnings = run_interactive_memo(transactions)

    assert transactions[0].memo == "'=cmd|'/c calc'"
    assert len(warnings) == 1
    assert "formula-like" in warnings[0]


def test_eof_aborts_with_pftoynab_error(monkeypatch):
    transactions = [_tx(1, "Coop", outflow=Decimal(1)), _tx(2, "Migros", outflow=Decimal(2))]

    def raise_eof(prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    with pytest.raises(PftoynabError, match="aborted"):
        run_interactive_memo(transactions)


def test_keyboard_interrupt_aborts_with_pftoynab_error(monkeypatch):
    transactions = [_tx(1, "Coop", outflow=Decimal(1))]

    def raise_interrupt(prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", raise_interrupt)

    with pytest.raises(PftoynabError, match="aborted"):
        run_interactive_memo(transactions)


def _twint_tx(day, number, outflow=None, inflow=None):
    payee = f"TWINT Geld senden an {number[1:]}" if outflow else f"TWINT Geld empfangen von {number[1:]}"
    return Transaction(date(2026, 1, day), payee, "", outflow, inflow, number)


def test_asks_once_per_unknown_number_and_saves_each_name(monkeypatch, capsys):
    transactions = [
        _twint_tx(1, "+41791234567", inflow=Decimal(40)),
        _twint_tx(2, "+41790000000", outflow=Decimal(10)),
        _twint_tx(3, "+41791234567", outflow=Decimal(50)),
        _twint_tx(4, "+41795555555", outflow=Decimal(5)),
        _tx(5, "Coop", outflow=Decimal(1)),
    ]
    answers = iter(["  Kristina   Schuricht ", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    saved = []

    new = ask_twint_contact_names(
        transactions, {"+41795555555": "Known"}, lambda n, name: saved.append((n, name))
    )

    assert new == {"+41791234567": "Kristina Schuricht"}
    assert saved == [("+41791234567", "Kristina Schuricht")]
    out = capsys.readouterr().out
    assert "[1/2] +41791234567" in out
    assert "2026-01-01  TWINT Geld empfangen von 41791234567  40.00" in out
    assert "2026-01-03  TWINT Geld senden an 41791234567  -50.00" in out
    assert "[2/2] +41790000000" in out
    assert "+41795555555" not in out


def test_no_prompt_without_unknown_numbers(monkeypatch, capsys):
    transactions = [_tx(1, "Coop", outflow=Decimal(1))]

    def fail_if_called(prompt):
        raise AssertionError("input() should not be called")

    monkeypatch.setattr("builtins.input", fail_if_called)

    assert ask_twint_contact_names(transactions, {}, lambda n, name: None) == {}
    assert capsys.readouterr().out == ""


def test_twint_contact_entry_aborts_on_keyboard_interrupt(monkeypatch):
    def raise_interrupt(prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", raise_interrupt)

    with pytest.raises(PftoynabError, match="TWINT contact entry aborted"):
        ask_twint_contact_names(
            [_twint_tx(1, "+41791234567", inflow=Decimal(1))], {}, lambda n, name: None
        )


def test_numbers_named_in_the_export_are_not_asked_for(monkeypatch):
    named = Transaction(
        date(2026, 1, 1), "TWINT GELD SENDEN ...", "", Decimal(1), None, "+41791234567", "Erika Muster"
    )

    def fail_if_called(prompt):
        raise AssertionError("input() should not be called")

    monkeypatch.setattr("builtins.input", fail_if_called)

    assert ask_twint_contact_names([named], {}, lambda n, name: None) == {}
