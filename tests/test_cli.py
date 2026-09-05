from pathlib import Path

from conftest import build_export, row

from pftoynab import cli


def write(path: Path, text: str) -> Path:
    path.write_bytes(text.encode("utf-8-sig"))
    return path


def test_successful_conversion_end_to_end(tmp_path, capsys):
    input_csv = write(tmp_path / "export.csv", build_export([row()]))

    exit_code = cli.main([str(input_csv)])

    assert exit_code == 0
    output_csv = tmp_path / "export_ynab.csv"
    assert output_csv.exists()
    out = capsys.readouterr().out
    assert "Wrote 1 transaction(s)" in out
    assert "ready for import into YNAB" in out


def test_missing_input_file(tmp_path, capsys):
    exit_code = cli.main([str(tmp_path / "nope.csv")])
    assert exit_code == 1
    assert "input file not found" in capsys.readouterr().err


def test_directory_as_input_rejected(tmp_path, capsys):
    exit_code = cli.main([str(tmp_path)])
    assert exit_code == 1
    assert "is a directory" in capsys.readouterr().err


def test_empty_input_file_rejected(tmp_path, capsys):
    input_csv = tmp_path / "empty.csv"
    input_csv.write_bytes(b"")
    exit_code = cli.main([str(input_csv)])
    assert exit_code == 1
    assert "input file is empty" in capsys.readouterr().err


def test_file_too_large_rejected(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "MAX_FILE_SIZE", 10)
    input_csv = write(tmp_path / "export.csv", build_export([row()]))
    assert input_csv.stat().st_size > 10

    exit_code = cli.main([str(input_csv)])

    assert exit_code == 1
    assert "too large" in capsys.readouterr().err


def test_output_already_exists_without_force(tmp_path, capsys):
    input_csv = write(tmp_path / "export.csv", build_export([row()]))
    output_csv = tmp_path / "export_ynab.csv"
    output_csv.write_text("existing content")

    exit_code = cli.main([str(input_csv)])

    assert exit_code == 1
    assert "already exists" in capsys.readouterr().err
    assert output_csv.read_text() == "existing content"


def test_force_overwrites_existing_output(tmp_path):
    input_csv = write(tmp_path / "export.csv", build_export([row()]))
    output_csv = tmp_path / "export_ynab.csv"
    output_csv.write_text("stale content")

    exit_code = cli.main([str(input_csv), "--force"])

    assert exit_code == 0
    assert "stale content" not in output_csv.read_text()


def test_custom_output_path(tmp_path):
    input_csv = write(tmp_path / "export.csv", build_export([row()]))
    output_csv = tmp_path / "custom.csv"

    exit_code = cli.main([str(input_csv), "-o", str(output_csv)])

    assert exit_code == 0
    assert output_csv.exists()


def test_output_path_same_as_input_rejected(tmp_path, capsys):
    input_csv = write(tmp_path / "export.csv", build_export([row()]))

    exit_code = cli.main([str(input_csv), "-o", str(input_csv)])

    assert exit_code == 1
    assert "must differ from the input path" in capsys.readouterr().err


def test_no_output_written_on_validation_failure(tmp_path, capsys):
    input_csv = write(tmp_path / "export.csv", build_export([row(date="32.01.2026")]))

    exit_code = cli.main([str(input_csv)])

    assert exit_code == 1
    assert "input validation failed" in capsys.readouterr().err
    assert not (tmp_path / "export_ynab.csv").exists()


def test_utf8_bom_is_stripped(tmp_path):
    input_csv = write(tmp_path / "export.csv", build_export([row()]))
    assert input_csv.read_bytes().startswith(b"\xef\xbb\xbf")

    exit_code = cli.main([str(input_csv)])

    assert exit_code == 0


def test_cp1252_fallback_decoding(tmp_path):
    text = build_export([row(desc="Bäckerei Müller")])
    input_csv = tmp_path / "export.csv"
    input_csv.write_bytes(text.encode("cp1252"))

    exit_code = cli.main([str(input_csv)])

    assert exit_code == 0
    output = (tmp_path / "export_ynab.csv").read_text(encoding="utf-8")
    assert "Bäckerei Müller" in output


def test_undecodable_file_rejected(tmp_path, capsys):
    input_csv = tmp_path / "export.csv"
    # Byte sequence invalid in both UTF-8 and CP1252.
    input_csv.write_bytes(b"\x81\x8d\x90")
    exit_code = cli.main([str(input_csv)])
    assert exit_code == 1
    assert "could not decode" in capsys.readouterr().err


def test_config_file_strip_prefixes_applied_end_to_end(tmp_path, monkeypatch):
    xdg_config_home = tmp_path / "xdg-config"
    config_dir = xdg_config_home / "pftoynab"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        '[payee]\nstrip_prefixes = ["Gutschrift von", "Lastschrift an"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config_home))

    input_csv = write(
        tmp_path / "export.csv",
        build_export([row(desc="Lastschrift an Wingo", debit="-10", credit="")]),
    )

    exit_code = cli.main([str(input_csv)])

    assert exit_code == 0
    output = (tmp_path / "export_ynab.csv").read_text(encoding="utf-8")
    assert "Wingo" in output
    assert "Lastschrift an Wingo" not in output


def test_invalid_config_file_reported_as_error(tmp_path, monkeypatch, capsys):
    xdg_config_home = tmp_path / "xdg-config"
    config_dir = xdg_config_home / "pftoynab"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text("not [valid toml", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config_home))

    input_csv = write(tmp_path / "export.csv", build_export([row()]))

    exit_code = cli.main([str(input_csv)])

    assert exit_code == 1
    assert "not valid TOML" in capsys.readouterr().err


def test_warnings_are_printed_but_conversion_still_succeeds(tmp_path, capsys):
    input_csv = write(tmp_path / "export.csv", build_export([row(desc="=malicious")]))

    exit_code = cli.main([str(input_csv)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Warning:" in captured.err
    assert "1 warning(s) above" in captured.out
