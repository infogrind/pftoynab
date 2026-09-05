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

from .errors import PftoynabError

APP_NAME = "pftoynab"
CONFIG_FILENAME = "config.toml"


@dataclass
class Config:
    strip_prefixes: list[str] = field(default_factory=list)


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

    return Config(strip_prefixes=strip_prefixes)
