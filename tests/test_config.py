import pytest

from pftoynab.config import Config, find_config_path, load_config
from pftoynab.errors import PftoynabError


def test_missing_config_file_returns_defaults(tmp_path):
    config = load_config(tmp_path / "does-not-exist.toml")
    assert config == Config(strip_prefixes=[])
    assert config.input_directory is None
    assert config.input_glob == "export_bewegungen_*.csv"
    assert config.credit_card_glob == "export_kreditkartenuebersicht_*.csv"


def test_loads_strip_prefixes(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[payee]\nstrip_prefixes = ["Gutschrift von", "Lastschrift an "]\n',
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert config.strip_prefixes == ["Gutschrift von", "Lastschrift an "]


def test_missing_payee_section_returns_defaults(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("# no [payee] section here\n", encoding="utf-8")
    config = load_config(config_file)
    assert config.strip_prefixes == []


def test_invalid_toml_raises(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("this is not [valid toml", encoding="utf-8")
    with pytest.raises(PftoynabError, match="not valid TOML"):
        load_config(config_file)


def test_payee_not_a_table_raises(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("payee = 5\n", encoding="utf-8")
    with pytest.raises(PftoynabError, match=r"\[payee\] must be a table"):
        load_config(config_file)


def test_strip_prefixes_not_a_list_raises(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[payee]\nstrip_prefixes = "oops"\n', encoding="utf-8")
    with pytest.raises(PftoynabError, match="must be a list of strings"):
        load_config(config_file)


def test_strip_prefixes_with_non_string_entry_raises(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("[payee]\nstrip_prefixes = [1, 2]\n", encoding="utf-8")
    with pytest.raises(PftoynabError, match="must be a list of strings"):
        load_config(config_file)


def test_loads_input_section(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[input]\ndirectory = "~/Desktop"\nglob = "*.csv"\ncredit_card_glob = "cc_*.csv"\n',
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert config.input_directory == "~/Desktop"
    assert config.input_glob == "*.csv"
    assert config.credit_card_glob == "cc_*.csv"


def test_missing_input_section_returns_defaults(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("# no [input] section here\n", encoding="utf-8")
    config = load_config(config_file)
    assert config.input_directory is None
    assert config.input_glob == "export_bewegungen_*.csv"
    assert config.credit_card_glob == "export_kreditkartenuebersicht_*.csv"


def test_input_not_a_table_raises(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("input = 5\n", encoding="utf-8")
    with pytest.raises(PftoynabError, match=r"\[input\] must be a table"):
        load_config(config_file)


def test_input_directory_not_a_string_raises(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("[input]\ndirectory = 5\n", encoding="utf-8")
    with pytest.raises(PftoynabError, match="input.directory must be a string"):
        load_config(config_file)


def test_input_glob_not_a_string_raises(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("[input]\nglob = 5\n", encoding="utf-8")
    with pytest.raises(PftoynabError, match="input.glob must be a string"):
        load_config(config_file)


def test_credit_card_glob_not_a_string_raises(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("[input]\ncredit_card_glob = 5\n", encoding="utf-8")
    with pytest.raises(PftoynabError, match="input.credit_card_glob must be a string"):
        load_config(config_file)


def test_find_config_path_defaults_to_dot_config(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert find_config_path() == tmp_path / ".config" / "pftoynab" / "config.toml"


def test_find_config_path_honors_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert find_config_path() == tmp_path / "xdg" / "pftoynab" / "config.toml"


def test_find_config_path_ignores_empty_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert find_config_path() == tmp_path / ".config" / "pftoynab" / "config.toml"


def test_find_config_path_ignores_relative_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/path")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert find_config_path() == tmp_path / ".config" / "pftoynab" / "config.toml"
