import logging
from pathlib import Path

import pytest

from reel.pages import (
    MAX_PAGE_BYTES,
    AboutPage,
    ContactEntry,
    ContactPage,
    parse_about,
    parse_contact,
    read_page_text,
)


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]


@pytest.fixture
def warnings_logged(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.WARNING)
    return caplog


def _write(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / "t-about"
    path.write_bytes(content)
    return path


# --- read_page_text ----------------------------------------------------------------------


def test_max_page_bytes_is_64_kib() -> None:
    assert MAX_PAGE_BYTES == 64 * 1024


def test_read_page_text_utf8_file_returns_text(tmp_path: Path) -> None:
    path = _write(tmp_path, "Olá, café.\n".encode())
    assert read_page_text(path, "about.txt") == "Olá, café.\n"


def test_read_page_text_bom_dropped(tmp_path: Path) -> None:
    path = _write(tmp_path, b"\xef\xbb\xbfHello")
    assert read_page_text(path, "about.txt") == "Hello"


def test_read_page_text_crlf_normalized_to_lf(tmp_path: Path) -> None:
    path = _write(tmp_path, b"one\r\ntwo\r\n")
    assert read_page_text(path, "about.txt") == "one\ntwo\n"


def test_read_page_text_lone_cr_normalized_to_lf(tmp_path: Path) -> None:
    path = _write(tmp_path, b"one\rtwo\r")
    assert read_page_text(path, "about.txt") == "one\ntwo\n"


def test_read_page_text_exactly_max_bytes_accepted(tmp_path: Path) -> None:
    path = _write(tmp_path, b"a" * MAX_PAGE_BYTES)
    assert read_page_text(path, "about.txt") == "a" * MAX_PAGE_BYTES


def test_read_page_text_over_max_bytes_returns_none(tmp_path: Path) -> None:
    path = _write(tmp_path, b"a" * (MAX_PAGE_BYTES + 1))
    assert read_page_text(path, "about.txt") is None


def test_read_page_text_over_max_bytes_warning_names_file(
    tmp_path: Path, warnings_logged: pytest.LogCaptureFixture
) -> None:
    path = _write(tmp_path, b"a" * (MAX_PAGE_BYTES + 1))
    read_page_text(path, "About.txt")
    assert any("About.txt" in message for message in _warnings(warnings_logged))


def test_read_page_text_over_max_bytes_warning_names_limit(
    tmp_path: Path, warnings_logged: pytest.LogCaptureFixture
) -> None:
    path = _write(tmp_path, b"a" * (MAX_PAGE_BYTES + 1))
    read_page_text(path, "about.txt")
    limits = ("65536", "65,536", "64 KiB", "64KiB", "64 KB", "64KB")
    assert any(limit in message for message in _warnings(warnings_logged) for limit in limits)


def test_read_page_text_invalid_utf8_returns_none(tmp_path: Path) -> None:
    path = _write(tmp_path, b"caf\xe9 \xff\xfe")
    assert read_page_text(path, "contact.txt") is None


def test_read_page_text_invalid_utf8_warning_names_file(
    tmp_path: Path, warnings_logged: pytest.LogCaptureFixture
) -> None:
    path = _write(tmp_path, b"caf\xe9 \xff\xfe")
    read_page_text(path, "Contact.TXT")
    assert any("Contact.TXT" in message for message in _warnings(warnings_logged))


def test_read_page_text_valid_file_logs_no_warning(
    tmp_path: Path, warnings_logged: pytest.LogCaptureFixture
) -> None:
    read_page_text(_write(tmp_path, b"Hello"), "about.txt")
    assert _warnings(warnings_logged) == []


def test_read_page_text_crlf_file_parses_into_paragraphs(tmp_path: Path) -> None:
    path = _write(tmp_path, b"Hello there.\r\n\r\nI shoot film.\r\nMostly at night.\r\n")
    text = read_page_text(path, "about.txt")
    assert text is not None and parse_about(text) == AboutPage(
        "Hello there.", ("I shoot film. Mostly at night.",)
    )


# --- parse_about -------------------------------------------------------------------------


def test_parse_about_spec_example_lede_and_paragraphs() -> None:
    text = "Hello there.\n\nI shoot film.\nMostly at night.\n\n\nThanks."
    assert parse_about(text) == AboutPage(
        "Hello there.", ("I shoot film. Mostly at night.", "Thanks.")
    )


def test_parse_about_single_paragraph_only_lede() -> None:
    assert parse_about("Only a lede\n") == AboutPage("Only a lede", ())


@pytest.mark.parametrize("text", ["", "  \n\n \t\n", "\n"])
def test_parse_about_blank_text_returns_none(text: str) -> None:
    assert parse_about(text) is None


def test_parse_about_html_kept_unescaped() -> None:
    page = parse_about("<b>Hi</b> & bye")
    assert page is not None and page.lede == "<b>Hi</b> & bye"


def test_parse_about_whitespace_only_line_separates_paragraphs() -> None:
    assert parse_about("First.\n \t \nSecond.") == AboutPage("First.", ("Second.",))


def test_parse_about_lines_stripped_and_inner_whitespace_collapsed() -> None:
    assert parse_about("  Wide   gaps\there \n   and   more  ") == AboutPage(
        "Wide gaps here and more", ()
    )


def test_parse_about_leading_and_trailing_blank_lines_ignored() -> None:
    assert parse_about("\n\n\nLede.\n\nBody.\n\n\n") == AboutPage("Lede.", ("Body.",))


# --- parse_contact -----------------------------------------------------------------------


def test_parse_contact_spec_example_email_link_and_plain_entry() -> None:
    text = "Email: hello@example.com\nInstagram: https://instagram.com/me/\nBased in: Lisbon"
    assert parse_contact(text) == ContactPage(
        "hello@example.com",
        (
            ContactEntry("Instagram", "instagram.com/me", "https://instagram.com/me/"),
            ContactEntry("Based in", "Lisbon", None),
        ),
    )


def test_parse_contact_url_only_has_no_email() -> None:
    assert parse_contact("Website: https://example.com") == ContactPage(
        None, (ContactEntry("Website", "example.com", "https://example.com"),)
    )


def test_parse_contact_nothing_usable_returns_none() -> None:
    assert parse_contact("Email: not-an-email\nnonsense line") is None


def test_parse_contact_nothing_usable_warns_for_each_line(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_contact("Email: not-an-email\nnonsense line")
    assert len(_warnings(warnings_logged)) == 2


def test_parse_contact_email_value_under_other_label_links_mailto() -> None:
    assert parse_contact("Studio: studio@example.com") == ContactPage(
        None, (ContactEntry("Studio", "studio@example.com", "mailto:studio@example.com"),)
    )


@pytest.mark.parametrize("label", ["Email", "email", "EMAIL", "eMail"])
def test_parse_contact_email_label_case_insensitive(label: str) -> None:
    page = parse_contact(f"{label}: hello@example.com")
    assert page is not None and page.email == "hello@example.com"


def test_parse_contact_second_email_becomes_entry() -> None:
    page = parse_contact("Email: first@example.com\nemail: second@example.com")
    assert page == ContactPage(
        "first@example.com",
        (ContactEntry("email", "second@example.com", "mailto:second@example.com"),),
    )


def test_parse_contact_invalid_email_skipped_and_later_valid_one_used() -> None:
    page = parse_contact("Email: nope\nEmail: yes@example.com")
    assert page == ContactPage("yes@example.com", ())


def test_parse_contact_invalid_email_warns(warnings_logged: pytest.LogCaptureFixture) -> None:
    parse_contact("Email: nope\nBased in: Lisbon")
    assert len(_warnings(warnings_logged)) == 1


def test_parse_contact_invalid_email_keeps_other_entries() -> None:
    assert parse_contact("Email: nope\nBased in: Lisbon") == ContactPage(
        None, (ContactEntry("Based in", "Lisbon", None),)
    )


@pytest.mark.parametrize(
    "value", ["javascript:alert(1)", "@yourhandle", "Lisbon, Portugal", "data:text/html,<b>x</b>"]
)
def test_parse_contact_non_url_value_is_plain_text(value: str) -> None:
    assert parse_contact(f"Note: {value}") == ContactPage(
        None, (ContactEntry("Note", value, None),)
    )


def test_parse_contact_javascript_value_logs_no_warning(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_contact("Website: javascript:alert(1)")
    assert _warnings(warnings_logged) == []


@pytest.mark.parametrize(
    "value", ["https://", "https:///path", "https://exa mple.com", "http://example.com/a b"]
)
def test_parse_contact_malformed_url_is_plain_text(value: str) -> None:
    page = parse_contact(f"Site: {value}")
    assert page is not None and page.entries[0].href is None


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("http://example.com/", "example.com"),
        ("HTTPS://Example.com/Me/", "Example.com/Me"),
        ("https://example.com/a?b=1", "example.com/a?b=1"),
        ("https://example.com//", "example.com/"),
    ],
)
def test_parse_contact_url_text_drops_scheme_and_one_trailing_slash(value: str, text: str) -> None:
    assert parse_contact(f"Site: {value}") == ContactPage(
        None, (ContactEntry("Site", text, value),)
    )


def test_parse_contact_split_on_first_colon_only() -> None:
    assert parse_contact("Hours: 9:00-17:00") == ContactPage(
        None, (ContactEntry("Hours", "9:00-17:00", None),)
    )


def test_parse_contact_label_and_value_stripped() -> None:
    assert parse_contact("   Based in  :   Lisbon   ") == ContactPage(
        None, (ContactEntry("Based in", "Lisbon", None),)
    )


def test_parse_contact_entries_keep_file_order() -> None:
    page = parse_contact("B: two\nA: one\nC: three")
    assert page is not None and [entry.label for entry in page.entries] == ["B", "A", "C"]


def test_parse_contact_comment_lines_skipped() -> None:
    page = parse_contact("# Email: hidden@example.com\n  # a note\nBased in: Lisbon")
    assert page == ContactPage(None, (ContactEntry("Based in", "Lisbon", None),))


def test_parse_contact_comment_and_blank_lines_log_no_warning(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_contact("# just a comment\n\n   \nBased in: Lisbon")
    assert _warnings(warnings_logged) == []


@pytest.mark.parametrize("line", ["no colon here", ": value only", "Label only:", "Label:    "])
def test_parse_contact_malformed_line_skipped(line: str) -> None:
    assert parse_contact(f"{line}\nBased in: Lisbon") == ContactPage(
        None, (ContactEntry("Based in", "Lisbon", None),)
    )


def test_parse_contact_malformed_line_warning_has_one_based_line_number(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_contact("# header\n\nBased in: Lisbon\nnonsense")
    assert _warnings(warnings_logged) == ['Skipping line 4 of contact.txt: expected "Label: value"']


def test_parse_contact_html_kept_unescaped() -> None:
    page = parse_contact("<i>Studio</i>: <b>Lisbon</b> & Porto")
    assert page == ContactPage(
        None, (ContactEntry("<i>Studio</i>", "<b>Lisbon</b> & Porto", None),)
    )


@pytest.mark.parametrize("text", ["", "\n\n", "# only comments\n# here"])
def test_parse_contact_empty_text_returns_none(text: str) -> None:
    assert parse_contact(text) is None


@pytest.mark.parametrize(
    "value",
    [
        "https://a\\@evil.example",
        "https://x\u202e.com",
        "http\u017f://x.com",
        "https://example.com/\u200bpath",
        "https://[oops",
    ],
    ids=["backslash", "bidi-override", "long-s-scheme", "zero-width-space", "bad-host"],
)
def test_parse_contact_deceptive_url_is_plain_text(value: str) -> None:
    assert parse_contact(f"Site: {value}") == ContactPage(
        None, (ContactEntry("Site", value, None),)
    )


def test_parse_contact_uppercase_scheme_url_still_linked() -> None:
    assert parse_contact("Site: HTTPS://Example.com/x") == ContactPage(
        None, (ContactEntry("Site", "Example.com/x", "HTTPS://Example.com/x"),)
    )
