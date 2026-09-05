"""End-to-end tests that run the CLI against real-file-shaped fixtures.

`testdata/postfinance_export.csv` mirrors the structure of a genuine
PostFinance "Bewegungen" export (preamble, header, quoting quirks, umlauts,
a multi-line quoted field) but contains no real personal data -- all
names, phone numbers, and amounts are fabricated.

`testdata/malformed/` holds fixtures for realistic ways such a file can go
wrong: the wrong file entirely, an interrupted download, spreadsheet
mangling, corrupted columns, and adversarial payee content.
"""

from pathlib import Path

import pytest

from pftoynab import cli

TESTDATA = Path(__file__).parent / "testdata"


def _copy(tmp_path: Path, relative_name: str) -> Path:
    src = TESTDATA / relative_name
    dest = tmp_path / Path(relative_name).name
    dest.write_bytes(src.read_bytes())
    return dest


@pytest.fixture(autouse=True)
def _use_testdata_config(monkeypatch):
    # Exercise the real strip_prefixes config end-to-end rather than the
    # user's actual (unrelated) XDG config on the machine running the tests.
    monkeypatch.setattr(cli, "find_config_path", lambda: TESTDATA / "config.toml")


def test_real_world_shaped_export_matches_golden_output(tmp_path):
    input_csv = _copy(tmp_path, "postfinance_export.csv")
    output_csv = tmp_path / "output.csv"

    exit_code = cli.main([str(input_csv), "-o", str(output_csv)])

    assert exit_code == 0
    golden = (TESTDATA / "postfinance_export_ynab_golden.csv").read_bytes()
    assert output_csv.read_bytes() == golden


def test_html_error_page_instead_of_csv_is_rejected(tmp_path, capsys):
    # A very real mistake: the online-banking session expired and the user
    # saved the browser's error page instead of the actual export.
    input_csv = _copy(tmp_path, "malformed/html_error_page.csv")

    exit_code = cli.main([str(input_csv)])

    assert exit_code == 1
    assert "could not find the expected PostFinance header row" in capsys.readouterr().err
    assert not (tmp_path / "html_error_page_ynab.csv").exists()


def test_csv_from_a_different_bank_is_rejected(tmp_path, capsys):
    input_csv = _copy(tmp_path, "malformed/wrong_bank_format.csv")

    exit_code = cli.main([str(input_csv)])

    assert exit_code == 1
    assert "could not find the expected PostFinance header row" in capsys.readouterr().err
    assert not (tmp_path / "wrong_bank_format_ynab.csv").exists()


def test_download_truncated_mid_quoted_field_is_rejected(tmp_path, capsys):
    # Simulates an interrupted download that cuts off inside a quoted
    # field: the unterminated quote swallows the rest of the line, leaving
    # the row with too few columns.
    input_csv = _copy(tmp_path, "malformed/truncated_mid_row.csv")

    exit_code = cli.main([str(input_csv)])

    assert exit_code == 1
    assert "expected at least" in capsys.readouterr().err
    assert not (tmp_path / "truncated_mid_row_ynab.csv").exists()


def test_swapped_credit_debit_columns_are_rejected(tmp_path, capsys):
    # Simulates corrupted/tampered data where an amount ended up in the
    # wrong (credit vs. debit) column.
    input_csv = _copy(tmp_path, "malformed/swapped_polarity.csv")

    exit_code = cli.main([str(input_csv)])

    assert exit_code == 1
    assert "debit amount is positive" in capsys.readouterr().err
    assert not (tmp_path / "swapped_polarity_ynab.csv").exists()


def test_spreadsheet_mangled_scientific_notation_amount_is_rejected(tmp_path, capsys):
    # Simulates a CSV that was opened and re-saved in a spreadsheet tool,
    # which silently reformatted a plain decimal into scientific notation.
    input_csv = _copy(tmp_path, "malformed/scientific_notation_amount.csv")

    exit_code = cli.main([str(input_csv)])

    assert exit_code == 1
    assert "not a valid amount" in capsys.readouterr().err
    assert not (tmp_path / "scientific_notation_amount_ynab.csv").exists()


def test_formula_injection_payees_are_neutralized_and_match_golden_output(tmp_path):
    input_csv = _copy(tmp_path, "malformed/formula_injection_batch.csv")
    output_csv = tmp_path / "output.csv"

    exit_code = cli.main([str(input_csv), "-o", str(output_csv)])

    assert exit_code == 0
    golden = (TESTDATA / "malformed" / "formula_injection_batch_ynab_golden.csv").read_bytes()
    assert output_csv.read_bytes() == golden
