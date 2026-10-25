from pathlib import Path

import pytest

from reel.config import ConfigError, load_settings, parse_env_file

REQUIRED = {
    "GOOGLE_APPLICATION_CREDENTIALS": "/keys/sa.json",
    "DRIVE_ROOT_FOLDER_ID": "root123",
}


def test_parse_env_file_comments_and_blanks_ignored() -> None:
    assert parse_env_file("# comment\n\nA=1\n") == {"A": "1"}


def test_parse_env_file_quoted_value_unquoted() -> None:
    assert parse_env_file('TITLE="My Book"') == {"TITLE": "My Book"}


def test_parse_env_file_mismatched_quotes_kept() -> None:
    assert parse_env_file("A='abc\"") == {"A": "'abc\""}


def test_parse_env_file_line_without_equals_skipped() -> None:
    assert parse_env_file("garbage\nA=1") == {"A": "1"}


def test_load_settings_required_present_returns_settings(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "missing.env", environ=REQUIRED)
    assert settings.root_folder_id == "root123"


def test_load_settings_optional_missing_uses_default(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "missing.env", environ=REQUIRED)
    assert settings.site_title == "Portfolio"


def test_load_settings_environ_overrides_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SITE_TITLE=From File\n", encoding="utf-8")
    settings = load_settings(env_file, environ={**REQUIRED, "SITE_TITLE": "From Env"})
    assert settings.site_title == "From Env"


def test_load_settings_values_read_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GOOGLE_APPLICATION_CREDENTIALS=/k.json\nDRIVE_ROOT_FOLDER_ID=abc\n", encoding="utf-8"
    )
    settings = load_settings(env_file, environ={})
    assert settings.root_folder_id == "abc"


def test_load_settings_required_missing_names_all_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="GOOGLE_APPLICATION_CREDENTIALS, DRIVE_ROOT_FOLDER_ID"):
        load_settings(tmp_path / "missing.env", environ={})


def test_load_settings_required_empty_treated_as_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="DRIVE_ROOT_FOLDER_ID"):
        load_settings(
            tmp_path / "missing.env",
            environ={**REQUIRED, "DRIVE_ROOT_FOLDER_ID": ""},
        )


def test_load_site_settings_nothing_set_uses_defaults(tmp_path: Path) -> None:
    from reel.config import SiteSettings, load_site_settings

    settings = load_site_settings(tmp_path / "missing.env", environ={})
    assert settings == SiteSettings(site_title="Portfolio", site_base_url="http://localhost:8000")


def test_load_site_settings_drive_settings_not_required(tmp_path: Path) -> None:
    from reel.config import load_site_settings

    settings = load_site_settings(tmp_path / "missing.env", environ={"SITE_TITLE": "Jo"})
    assert settings.site_title == "Jo"


def test_load_site_settings_values_read_from_env_file(tmp_path: Path) -> None:
    from reel.config import load_site_settings

    env_file = tmp_path / ".env"
    env_file.write_text("SITE_BASE_URL=https://x.com/portfolio\n", encoding="utf-8")
    settings = load_site_settings(env_file, environ={})
    assert settings.site_base_url == "https://x.com/portfolio"


def test_load_site_settings_environ_overrides_env_file(tmp_path: Path) -> None:
    from reel.config import load_site_settings

    env_file = tmp_path / ".env"
    env_file.write_text("SITE_TITLE=From File\n", encoding="utf-8")
    settings = load_site_settings(env_file, environ={"SITE_TITLE": "From Env"})
    assert settings.site_title == "From Env"


def test_load_site_settings_empty_value_uses_default(tmp_path: Path) -> None:
    from reel.config import load_site_settings

    settings = load_site_settings(tmp_path / "missing.env", environ={"SITE_TITLE": ""})
    assert settings.site_title == "Portfolio"


# CONTACT_FORM_URL

FORM_URL = "https://forms.example.test/f/reel"
FORM_URL_ERROR = "CONTACT_FORM_URL must be an https:// URL."
INVALID_FORM_URLS = [
    "http://forms.example.test/f/reel",
    "ftp://forms.example.test/f/reel",
    "javascript:alert(1)",
    "forms.example.test/f/reel",
    "https://",
    "https:///f/reel",
    "https://forms.example.test/f reel",
    "https://forms.example.test/f\treel",
    "https://forms.example.test/f\x07reel",
    'https://forms.example.test/f"onmouseover=alert(1)',
    "https://forms.example.test/f'x",
    "https://forms.example.test/<script>",
    "https://forms.example.test/f>",
]


def test_load_site_settings_contact_form_url_https_accepted(tmp_path: Path) -> None:
    from reel.config import load_site_settings

    settings = load_site_settings(tmp_path / "missing.env", environ={"CONTACT_FORM_URL": FORM_URL})
    assert settings.contact_form_url == FORM_URL


def test_load_site_settings_contact_form_url_unset_is_none(tmp_path: Path) -> None:
    from reel.config import load_site_settings

    settings = load_site_settings(tmp_path / "missing.env", environ={})
    assert settings.contact_form_url is None


def test_load_site_settings_contact_form_url_empty_is_none(tmp_path: Path) -> None:
    from reel.config import load_site_settings

    settings = load_site_settings(tmp_path / "missing.env", environ={"CONTACT_FORM_URL": ""})
    assert settings.contact_form_url is None


@pytest.mark.parametrize("url", INVALID_FORM_URLS)
def test_load_site_settings_contact_form_url_invalid_raises_config_error(
    tmp_path: Path, url: str
) -> None:
    from reel.config import load_site_settings

    with pytest.raises(ConfigError) as error:
        load_site_settings(tmp_path / "missing.env", environ={"CONTACT_FORM_URL": url})
    assert str(error.value) == FORM_URL_ERROR


@pytest.mark.parametrize("url", [url for url in INVALID_FORM_URLS if url not in FORM_URL_ERROR])
def test_load_site_settings_contact_form_url_error_does_not_echo_value(
    tmp_path: Path, url: str
) -> None:
    from reel.config import load_site_settings

    with pytest.raises(ConfigError) as error:
        load_site_settings(tmp_path / "missing.env", environ={"CONTACT_FORM_URL": url})
    assert url not in str(error.value)


def test_load_settings_contact_form_url_invalid_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"^CONTACT_FORM_URL must be an https:// URL\.$"):
        load_settings(
            tmp_path / "missing.env",
            environ={**REQUIRED, "CONTACT_FORM_URL": "http://forms.example.test/f"},
        )


def test_load_settings_contact_form_url_valid_accepted(tmp_path: Path) -> None:
    settings = load_settings(
        tmp_path / "missing.env", environ={**REQUIRED, "CONTACT_FORM_URL": FORM_URL}
    )
    assert settings.contact_form_url == FORM_URL


def test_load_site_settings_contact_form_url_read_from_env_file(tmp_path: Path) -> None:
    from reel.config import load_site_settings

    env_file = tmp_path / ".env"
    env_file.write_text(f"CONTACT_FORM_URL={FORM_URL}\n", encoding="utf-8")
    settings = load_site_settings(env_file, environ={})
    assert settings.contact_form_url == FORM_URL


def test_load_site_settings_contact_form_url_environ_overrides_env_file(tmp_path: Path) -> None:
    from reel.config import load_site_settings

    env_file = tmp_path / ".env"
    env_file.write_text("CONTACT_FORM_URL=https://file.example.test/f\n", encoding="utf-8")
    settings = load_site_settings(env_file, environ={"CONTACT_FORM_URL": FORM_URL})
    assert settings.contact_form_url == FORM_URL


def test_load_site_settings_invalid_env_file_url_overridden_by_valid_environ(
    tmp_path: Path,
) -> None:
    from reel.config import load_site_settings

    env_file = tmp_path / ".env"
    env_file.write_text("CONTACT_FORM_URL=http://file.example.test/f\n", encoding="utf-8")
    settings = load_site_settings(env_file, environ={"CONTACT_FORM_URL": FORM_URL})
    assert settings.contact_form_url == FORM_URL
