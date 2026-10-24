"""Settings loaded from the environment and an optional `.env` file."""

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel


class ConfigError(Exception):
    """Raised when required settings are missing."""


class Settings(BaseModel):
    """Runtime configuration for sync and build."""

    credentials_path: Path
    root_folder_id: str
    site_title: str = "Portfolio"
    site_base_url: str = "http://localhost:8000"


def parse_env_file(text: str) -> dict[str, str]:
    """Parse `KEY=VALUE` lines, ignoring blanks, comments, and surrounding quotes."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = _unquote(value.strip())
    return values


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def load_settings(
    env_file: Path = Path(".env"), environ: Mapping[str, str] | None = None
) -> Settings:
    """Build settings from `env_file`, with real environment variables taking precedence."""
    values = parse_env_file(env_file.read_text(encoding="utf-8")) if env_file.is_file() else {}
    values.update(os.environ if environ is None else environ)

    # Report every missing name at once, never the values (they may be secrets).
    required = ("GOOGLE_APPLICATION_CREDENTIALS", "DRIVE_ROOT_FOLDER_ID")
    missing = [name for name in required if not values.get(name)]
    if missing:
        raise ConfigError(f"Missing required settings: {', '.join(missing)}. See .env.example.")

    optional = {
        "site_title": values.get("SITE_TITLE"),
        "site_base_url": values.get("SITE_BASE_URL"),
    }
    return Settings(
        credentials_path=Path(values["GOOGLE_APPLICATION_CREDENTIALS"]),
        root_folder_id=values["DRIVE_ROOT_FOLDER_ID"],
        **{key: value for key, value in optional.items() if value},
    )
