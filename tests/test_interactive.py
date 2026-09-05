from datetime import date
from decimal import Decimal

import pytest

from pftoynab.errors import PftoynabError
from pftoynab.interactive import run_interactive_memo
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
