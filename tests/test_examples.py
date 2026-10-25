"""The ready-to-upload samples in docs/examples/ and .env.example must match what reel accepts."""

import logging
from pathlib import Path

import pytest

from reel.build import build_site
from reel.config import is_valid_form_url, parse_env_file
from reel.models import Manifest
from reel.pages import (
    AboutPage,
    ContactEntry,
    ContactPage,
    parse_about,
    parse_contact,
    read_page_text,
)
from tests.fixtures.html import parse_html
from tests.fixtures.pages import make_text_file, write_text_original

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "docs" / "examples"
ABOUT_EXAMPLE = EXAMPLES / "about.json"
CONTACT_EXAMPLE = EXAMPLES / "contact.json"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
EXPECTED_ENTRIES = (
    ContactEntry("Instagram", "instagram.com/yourhandle", "https://instagram.com/yourhandle"),
    ContactEntry("Website", "example.com", "https://example.com"),
    ContactEntry("Based in", "Example City, Country", None),
    ContactEntry("Available for", "Commissions, editorial, prints", None),
)


def _about() -> AboutPage | None:
    text = read_page_text(ABOUT_EXAMPLE, "about.json")
    return parse_about(text, "about.json") if text is not None else None


def _contact() -> ContactPage | None:
    text = read_page_text(CONTACT_EXAMPLE, "contact.json")
    return parse_contact(text, "contact.json") if text is not None else None


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]


def test_about_example_lede_is_placeholder() -> None:
    about = _about()
    assert about is not None and about.lede.startswith("Placeholder lede:")


def test_about_example_has_three_body_paragraphs() -> None:
    about = _about()
    assert about is not None and len(about.paragraphs) == 3


def test_about_example_parses_without_warnings(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    _about()
    assert _warnings(caplog) == []


def test_contact_example_email_is_placeholder_address() -> None:
    contact = _contact()
    assert contact is not None and contact.email == "hello@example.com"


def test_contact_example_entries_match_documented_facts() -> None:
    contact = _contact()
    assert contact is not None and contact.entries == EXPECTED_ENTRIES


def test_contact_example_parses_without_warnings(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    _contact()
    assert _warnings(caplog) == []


def test_env_example_contact_form_url_placeholder_is_valid() -> None:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    commented = [line for line in lines if line.lstrip("# ").startswith("CONTACT_FORM_URL=")]
    assert len(commented) == 1, f"expected one CONTACT_FORM_URL line, found {commented}"
    url = parse_env_file(commented[0].lstrip("# "))["CONTACT_FORM_URL"]
    assert is_valid_form_url(url)


def _build_with_examples(tmp_path: Path) -> Path:
    cache, out = tmp_path / ".cache", tmp_path / "dist"
    write_text_original(cache, "t-about", ABOUT_EXAMPLE.read_bytes())
    write_text_original(cache, "t-contact", CONTACT_EXAMPLE.read_bytes())
    manifest = Manifest(
        albums=[],
        about=make_text_file("t-about", "about.json"),
        contact=make_text_file("t-contact", "contact.json"),
    )
    build_site(manifest, cache, out, "Site")
    return out


@pytest.mark.parametrize("page", ["about", "contact"])
def test_build_site_with_examples_writes_page(tmp_path: Path, page: str) -> None:
    out = _build_with_examples(tmp_path)
    assert (out / page / "index.html").is_file()


def test_build_site_with_examples_contact_shows_four_facts(tmp_path: Path) -> None:
    out = _build_with_examples(tmp_path)
    page = parse_html((out / "contact" / "index.html").read_text(encoding="utf-8"))
    labels = [label.text() for label in page.find_all("ul.contact-facts li span.label")]
    assert labels == ["Instagram", "Website", "Based in", "Available for"]
