from datetime import date
from decimal import Decimal

from pftoynab.parser import Transaction
from pftoynab.writer import write_ynab_csv


def test_write_ynab_csv_header_and_formatting(tmp_path):
    transactions = [
        Transaction(date(2026, 1, 1), "Coffee Shop", "Freizeit", Decimal("4.5"), None),
        Transaction(date(2026, 1, 2), "Employer, Inc.", "", None, Decimal(3000)),
    ]
    out = tmp_path / "out.csv"
    write_ynab_csv(transactions, out)

    content = out.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert lines[0] == "Date,Payee,Memo,Outflow,Inflow"
    assert lines[1] == "2026-01-01,Coffee Shop,Freizeit,4.50,"
    # Payee containing a comma must be quoted by the CSV writer.
    assert lines[2] == '2026-01-02,"Employer, Inc.",,,3000.00'


def test_output_has_no_utf8_bom(tmp_path):
    transactions = [Transaction(date(2026, 1, 1), "Zürich Café", "", Decimal(1), None)]
    out = tmp_path / "out.csv"
    write_ynab_csv(transactions, out)

    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "Zürich Café" in raw.decode("utf-8")


def test_write_empty_transaction_list_writes_header_only(tmp_path):
    out = tmp_path / "out.csv"
    write_ynab_csv([], out)
    assert out.read_text(encoding="utf-8").splitlines() == ["Date,Payee,Memo,Outflow,Inflow"]
