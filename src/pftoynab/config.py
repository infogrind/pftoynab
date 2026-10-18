"""User configuration, loaded per the XDG Base Directory Specification.

The config file lives at ``$XDG_CONFIG_HOME/pftoynab/config.toml``, falling
back to ``~/.config/pftoynab/config.toml`` when ``$XDG_CONFIG_HOME`` is
unset, empty, or not an absolute path (per the spec, such values must be
ignored in favor of the default).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomlkit
from tomlkit.exceptions import TOMLKitError

from .errors import PftoynabError
from .parser import normalize_phone_number

APP_NAME = "pftoynab"
CONFIG_FILENAME = "config.toml"


DEFAULT_INPUT_GLOB = "export_bewegungen_*.csv"
DEFAULT_CREDIT_CARD_GLOB = "export_kreditkartenuebersicht_*.csv"


@dataclass
class Config:
    strip_prefixes: list[str] = field(default_factory=list)
    input_directory: str | None = None
    input_glob: str = DEFAULT_INPUT_GLOB
    credit_card_glob: str = DEFAULT_CREDIT_CARD_GLOB
    transfer_checking_account: str | None = None
    # Normalized phone number ("+41791234567") -> name, for TWINT P2P payees.
    twint_contacts: dict[str, str] = field(default_factory=dict)


def find_config_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg_config_home) if xdg_config_home and Path(xdg_config_home).is_absolute() else Path.home() / ".config"
    return base / APP_NAME / CONFIG_FILENAME


def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()

    try:
        raw = path.read_bytes()
    except OSError as e:
        raise PftoynabError(f"could not read config file {path}: {e}") from e

    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as e:
        raise PftoynabError(f"config file {path} is not valid UTF-8: {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise PftoynabError(f"config file {path} is not valid TOML: {e}") from e

    payee_section = data.get("payee", {})
    if not isinstance(payee_section, dict):
        raise PftoynabError(f"config file {path}: [payee] must be a table")

    strip_prefixes = payee_section.get("strip_prefixes", [])
    if not isinstance(strip_prefixes, list) or not all(isinstance(p, str) for p in strip_prefixes):
        raise PftoynabError(f"config file {path}: payee.strip_prefixes must be a list of strings")

    input_section = data.get("input", {})
    if not isinstance(input_section, dict):
        raise PftoynabError(f"config file {path}: [input] must be a table")

    input_directory = input_section.get("directory")
    if input_directory is not None and not isinstance(input_directory, str):
        raise PftoynabError(f"config file {path}: input.directory must be a string")

    input_glob = input_section.get("glob", DEFAULT_INPUT_GLOB)
    if not isinstance(input_glob, str):
        raise PftoynabError(f"config file {path}: input.glob must be a string")

    credit_card_glob = input_section.get("credit_card_glob", DEFAULT_CREDIT_CARD_GLOB)
    if not isinstance(credit_card_glob, str):
        raise PftoynabError(f"config file {path}: input.credit_card_glob must be a string")

    transfers_section = data.get("transfers", {})
    if not isinstance(transfers_section, dict):
        raise PftoynabError(f"config file {path}: [transfers] must be a table")

    transfer_checking_account = transfers_section.get("checking_account")
    if transfer_checking_account is not None and not isinstance(transfer_checking_account, str):
        raise PftoynabError(f"config file {path}: transfers.checking_account must be a string")

    twint_section = data.get("twint", {})
    if not isinstance(twint_section, dict):
        raise PftoynabError(f"config file {path}: [twint] must be a table")

    contacts_section = twint_section.get("contacts", {})
    if not isinstance(contacts_section, dict) or not all(
        isinstance(v, str) for v in contacts_section.values()
    ):
        raise PftoynabError(
            f"config file {path}: [twint.contacts] must be a table of \"<phone number>\" = \"<name>\""
        )
    twint_contacts: dict[str, str] = {}
    for number, name in contacts_section.items():
        if not any(c.isdigit() for c in number):
            raise PftoynabError(f"config file {path}: twint.contacts key {number!r} is not a phone number")
        if not name.strip():
            raise PftoynabError(f"config file {path}: twint.contacts name for {number!r} is empty")
        twint_contacts[normalize_phone_number(number)] = name.strip()

    return Config(
        strip_prefixes=strip_prefixes,
        input_directory=input_directory,
        input_glob=input_glob,
        credit_card_glob=credit_card_glob,
        transfer_checking_account=transfer_checking_account,
        twint_contacts=twint_contacts,
    )


def save_twint_contact(path: Path, number: str, name: str) -> None:
    """Add (or overwrite) one entry in the config's [twint.contacts] table.

    Edits the file with tomlkit so the user's existing formatting and
    comments survive, creating the file (and its directory) if needed. The
    new content is written to a temporary file first and then moved into
    place, so an interrupted write can't leave a truncated config behind.
    """
    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8")) if path.exists() else tomlkit.document()
    except (OSError, UnicodeDecodeError, TOMLKitError) as e:
        raise PftoynabError(f"could not read config file {path} to save a TWINT contact: {e}") from e

    twint = doc.get("twint")
    if twint is None:
        twint = tomlkit.table(is_super_table=True)
        doc["twint"] = twint
    contacts = twint.get("contacts")
    if contacts is None:
        contacts = tomlkit.table()
        twint["contacts"] = contacts
    contacts[number] = name

    tmp_path = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
        tmp_path.replace(path)
    except OSError as e:
        raise PftoynabError(f"could not save TWINT contact to config file {path}: {e}") from e
