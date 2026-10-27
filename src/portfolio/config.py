"""Settings loaded from the environment and an optional `.env` file."""

import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel

_URL_FORBIDDEN_CHARS = frozenset("\"'<>")


class ConfigError(Exception):
    """Raised when required settings are missing or invalid."""


class SiteSettings(BaseModel):
    """Configuration needed to render the site; no Drive access required."""

    site_title: str = "Portfolio"
    site_base_url: str = "http://localhost:8000"
    contact_form_url: str | None = None


class Settings(SiteSettings):
    """Runtime configuration for sync and build."""

    credentials_path: Path
    root_folder_id: str


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
    values = _merged_values(env_file, environ)

    # Report every missing name at once, never the values (they may be secrets).
    required = ("GOOGLE_APPLICATION_CREDENTIALS", "DRIVE_ROOT_FOLDER_ID")
    missing = [name for name in required if not values.get(name)]
    if missing:
        raise ConfigError(f"Missing required settings: {', '.join(missing)}. See .env.example.")

    return Settings(
        credentials_path=Path(values["GOOGLE_APPLICATION_CREDENTIALS"]),
        root_folder_id=values["DRIVE_ROOT_FOLDER_ID"],
        **_site_values(values),
    )


def load_site_settings(
    env_file: Path = Path(".env"), environ: Mapping[str, str] | None = None
) -> SiteSettings:
    """Site settings from `env_file` and the environment; Drive settings are not required.

    Raises ConfigError if CONTACT_FORM_URL is set but not an https:// URL.
    """
    return SiteSettings(**_site_values(_merged_values(env_file, environ)))


def _merged_values(env_file: Path, environ: Mapping[str, str] | None) -> dict[str, str]:
    values = parse_env_file(env_file.read_text(encoding="utf-8")) if env_file.is_file() else {}
    values.update(os.environ if environ is None else environ)
    return values


def is_valid_form_url(url: str) -> bool:
    """Whether `url` is a plain https:// URL that is safe to put in a form `action`."""
    if any(
        char.isspace() or not char.isprintable() or char in _URL_FORBIDDEN_CHARS for char in url
    ):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme.lower() == "https" and bool(parsed.netloc)


def _site_values(values: Mapping[str, str]) -> dict[str, str]:
    # Empty values mean "unset" so the model defaults apply.
    optional = {
        "site_title": values.get("SITE_TITLE"),
        "site_base_url": values.get("SITE_BASE_URL"),
        "contact_form_url": values.get("CONTACT_FORM_URL"),
    }
    present = {key: value for key, value in optional.items() if value}
    # Never echo the value: the form URL can embed a private form id or token.
    if "contact_form_url" in present and not is_valid_form_url(present["contact_form_url"]):
        raise ConfigError("CONTACT_FORM_URL must be an https:// URL.")
    return present
