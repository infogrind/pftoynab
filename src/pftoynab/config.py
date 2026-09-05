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


DEFAULT_INPUT_GLOB = "export_bewegungen_*.csv"


@dataclass
class Config:
    strip_prefixes: list[str] = field(default_factory=list)
    input_directory: str | None = None
    input_glob: str = DEFAULT_INPUT_GLOB


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

    return Config(
        strip_prefixes=strip_prefixes,
        input_directory=input_directory,
        input_glob=input_glob,
    )
