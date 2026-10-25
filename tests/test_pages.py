import json
import logging
import re
from collections.abc import Callable
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
    assert read_page_text(path, "about.json") == "Olá, café.\n"


def test_read_page_text_bom_dropped(tmp_path: Path) -> None:
    path = _write(tmp_path, b"\xef\xbb\xbfHello")
    assert read_page_text(path, "about.json") == "Hello"


def test_read_page_text_crlf_normalized_to_lf(tmp_path: Path) -> None:
    path = _write(tmp_path, b"one\r\ntwo\r\n")
    assert read_page_text(path, "about.json") == "one\ntwo\n"


def test_read_page_text_lone_cr_normalized_to_lf(tmp_path: Path) -> None:
    path = _write(tmp_path, b"one\rtwo\r")
    assert read_page_text(path, "about.json") == "one\ntwo\n"


def test_read_page_text_exactly_max_bytes_accepted(tmp_path: Path) -> None:
    path = _write(tmp_path, b"a" * MAX_PAGE_BYTES)
    assert read_page_text(path, "about.json") == "a" * MAX_PAGE_BYTES


def test_read_page_text_over_max_bytes_returns_none(tmp_path: Path) -> None:
    path = _write(tmp_path, b"a" * (MAX_PAGE_BYTES + 1))
    assert read_page_text(path, "about.json") is None


def test_read_page_text_over_max_bytes_warning_names_file(
    tmp_path: Path, warnings_logged: pytest.LogCaptureFixture
) -> None:
    path = _write(tmp_path, b"a" * (MAX_PAGE_BYTES + 1))
    read_page_text(path, "About.json")
    assert any("About.json" in message for message in _warnings(warnings_logged))


def test_read_page_text_over_max_bytes_warning_names_limit(
    tmp_path: Path, warnings_logged: pytest.LogCaptureFixture
) -> None:
    path = _write(tmp_path, b"a" * (MAX_PAGE_BYTES + 1))
    read_page_text(path, "about.json")
    limits = ("65536", "65,536", "64 KiB", "64KiB", "64 KB", "64KB")
    assert any(limit in message for message in _warnings(warnings_logged) for limit in limits)


def test_read_page_text_invalid_utf8_returns_none(tmp_path: Path) -> None:
    path = _write(tmp_path, b"caf\xe9 \xff\xfe")
    assert read_page_text(path, "contact.json") is None


def test_read_page_text_invalid_utf8_warning_names_file(
    tmp_path: Path, warnings_logged: pytest.LogCaptureFixture
) -> None:
    path = _write(tmp_path, b"caf\xe9 \xff\xfe")
    read_page_text(path, "Contact.JSON")
    assert any("Contact.JSON" in message for message in _warnings(warnings_logged))


def test_read_page_text_valid_file_logs_no_warning(
    tmp_path: Path, warnings_logged: pytest.LogCaptureFixture
) -> None:
    read_page_text(_write(tmp_path, b"Hello"), "about.json")
    assert _warnings(warnings_logged) == []


def test_read_page_text_crlf_json_file_parses(tmp_path: Path) -> None:
    path = _write(tmp_path, b'{\r\n  "lede": "Hello there.",\r\n  "paragraphs": ["Body."]\r\n}\r\n')
    text = read_page_text(path, "about.json")
    assert text is not None and parse_about(text) == AboutPage("Hello there.", ("Body.",))


def test_read_page_text_bom_json_file_parses(tmp_path: Path) -> None:
    path = _write(tmp_path, b'\xef\xbb\xbf{"email": "hello@example.com"}')
    text = read_page_text(path, "contact.json")
    assert text is not None and parse_contact(text) == ContactPage("hello@example.com", ())


# --- shared helpers for the JSON parsers --------------------------------------------------

SECRET = "SECRET-xyz"


def _json(value: object) -> str:
    return json.dumps(value)


def _details(*pairs: tuple[str, str]) -> str:
    return _json({"details": [{"label": label, "value": value} for label, value in pairs]})


def _logged(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records]


def _only_warning(caplog: pytest.LogCaptureFixture) -> str:
    warnings = _warnings(caplog)
    assert len(warnings) == 1, f"expected one warning, got {warnings}"
    return warnings[0]


# --- parse_about -------------------------------------------------------------------------


def test_parse_about_spec_example_collapses_whitespace_and_drops_blank_paragraphs() -> None:
    text = _json(
        {
            "lede": "Hello  there.",
            "paragraphs": ["I shoot\nfilm.", "  ", "Thanks."],
            "_comment": "x",
        }
    )
    assert parse_about(text) == AboutPage("Hello there.", ("I shoot film.", "Thanks."))


def test_parse_about_spec_example_logs_no_warning(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_about(
        _json({"lede": "Hello  there.", "paragraphs": ["I shoot\nfilm.", "  "], "_comment": "x"})
    )
    assert _warnings(warnings_logged) == []


def test_parse_about_only_lede_has_no_paragraphs() -> None:
    assert parse_about(_json({"lede": "Only a lede"})) == AboutPage("Only a lede", ())


def test_parse_about_empty_paragraph_list_has_no_paragraphs() -> None:
    assert parse_about(_json({"lede": "Lede", "paragraphs": []})) == AboutPage("Lede", ())


def test_parse_about_lede_whitespace_runs_collapsed() -> None:
    page = parse_about(_json({"lede": "  Wide   gaps\there \n   and   more  "}))
    assert page == AboutPage("Wide gaps here and more", ())


@pytest.mark.parametrize("blank", ["", "   ", "\t\n", "\u00a0"])
def test_parse_about_blank_paragraph_dropped(blank: str) -> None:
    page = parse_about(_json({"lede": "Lede", "paragraphs": ["One", blank, "Two"]}))
    assert page == AboutPage("Lede", ("One", "Two"))


def test_parse_about_paragraph_order_kept() -> None:
    page = parse_about(_json({"lede": "L", "paragraphs": ["c", "a", "b"]}))
    assert page is not None and page.paragraphs == ("c", "a", "b")


def test_parse_about_html_kept_unescaped() -> None:
    page = parse_about(_json({"lede": "<b>Hi</b> & bye"}))
    assert page is not None and page.lede == "<b>Hi</b> & bye"


def test_parse_about_extra_keys_ignored_without_warning(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_about(_json({"lede": "L", "_comment": "note", "extra": {"nested": [1, 2]}}))
    assert _warnings(warnings_logged) == []


def test_parse_about_missing_lede_returns_none() -> None:
    assert parse_about(_json({"paragraphs": ["x"]})) is None


def test_parse_about_missing_lede_warning_names_field(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_about(_json({"paragraphs": ["x"]}))
    assert _only_warning(warnings_logged) == "Skipping 'about.json': lede: Field required"


def test_parse_about_warning_names_given_drive_file(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_about(_json({"paragraphs": ["x"]}), "About.JSON")
    assert _only_warning(warnings_logged).startswith("Skipping 'About.JSON': ")


@pytest.mark.parametrize("lede", ["", "   ", "\n\t"])
def test_parse_about_blank_lede_returns_none(lede: str) -> None:
    assert parse_about(_json({"lede": lede})) is None


@pytest.mark.parametrize(
    "value",
    [5, 1.5, True, None, ["text"], {"text": "x"}],
    ids=["int", "float", "bool", "null", "list", "object"],
)
def test_parse_about_non_string_lede_returns_none(value: object) -> None:
    assert parse_about(_json({"lede": value})) is None


def test_parse_about_non_string_lede_warning_names_field(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_about(_json({"lede": 5}))
    assert _only_warning(warnings_logged).startswith("Skipping 'about.json': lede: ")


@pytest.mark.parametrize(
    "value",
    [{"lede": [SECRET]}, {"lede": {"x": SECRET}}, {"lede": "ok", "paragraphs": [[SECRET]]}],
    ids=["lede-list", "lede-object", "nested-paragraph"],
)
def test_parse_about_schema_error_never_logs_input(
    caplog: pytest.LogCaptureFixture, value: object
) -> None:
    caplog.set_level(logging.DEBUG)
    parse_about(_json(value))
    assert not any(SECRET in message for message in _logged(caplog))


def test_parse_about_paragraph_error_located_by_index(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_about(_json({"lede": "L", "paragraphs": ["ok", 7]}))
    assert _only_warning(warnings_logged).startswith("Skipping 'about.json': paragraphs.1: ")


def test_parse_about_paragraphs_not_a_list_returns_none() -> None:
    assert parse_about(_json({"lede": "L", "paragraphs": "one long paragraph"})) is None


def test_parse_about_more_than_three_errors_truncated(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_about(_json({"lede": 1, "paragraphs": [1, 2, 3, 4]}))
    body = _only_warning(warnings_logged).removeprefix("Skipping 'about.json': ")
    assert [part.split(":")[0] for part in body.split("; ")] == [
        "lede",
        "paragraphs.0",
        "paragraphs.1",
        "...",
    ]


def test_parse_about_exactly_three_errors_not_truncated(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_about(_json({"lede": 1, "paragraphs": [1, 2]}))
    assert not _only_warning(warnings_logged).endswith("...")


@pytest.mark.parametrize(
    "value", [[1, 2], "about", 42, None], ids=["array", "string", "number", "null"]
)
def test_parse_about_top_level_not_object_returns_none(value: object) -> None:
    assert parse_about(_json(value)) is None


def test_parse_about_top_level_array_warning_says_root(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_about(_json([1, 2]))
    assert _only_warning(warnings_logged).startswith("Skipping 'about.json': (root): ")


@pytest.mark.parametrize(
    "text", ['{"lede": "x",', "", "lede: x", "{'lede': 'x'}", '{"lede": "x"} trailing']
)
def test_parse_about_invalid_json_returns_none(text: str) -> None:
    assert parse_about(text) is None


def test_parse_about_invalid_json_warning_has_line_and_column(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_about('{"lede": "x",')
    assert re.fullmatch(
        r"Skipping 'about\.json': not valid JSON \(line 1, column \d+\)",
        _only_warning(warnings_logged),
    )


def test_parse_about_invalid_json_on_later_line_reports_that_line(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_about('{\n  "lede": "x",\n}\n')
    assert "(line 3, column 1)" in _only_warning(warnings_logged)


def test_parse_about_invalid_json_never_logs_text(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    parse_about(f'{{"lede": "{SECRET}",')
    assert not any(SECRET in message for message in _logged(caplog))


# --- parse_contact -----------------------------------------------------------------------


def test_parse_contact_spec_example_email_link_and_plain_entry() -> None:
    text = _json(
        {
            "email": "hello@example.com",
            "details": [
                {"label": "Instagram", "value": "https://instagram.com/me/"},
                {"label": "Based in", "value": "Lisbon"},
            ],
        }
    )
    assert parse_contact(text) == ContactPage(
        "hello@example.com",
        (
            ContactEntry("Instagram", "instagram.com/me", "https://instagram.com/me/"),
            ContactEntry("Based in", "Lisbon", None),
        ),
    )


def test_parse_contact_details_only_has_no_email() -> None:
    assert parse_contact(_details(("Website", "https://example.com"))) == ContactPage(
        None, (ContactEntry("Website", "example.com", "https://example.com"),)
    )


def test_parse_contact_email_only_has_no_entries() -> None:
    assert parse_contact(_json({"email": "hello@example.com"})) == ContactPage(
        "hello@example.com", ()
    )


def test_parse_contact_email_surrounding_whitespace_stripped() -> None:
    page = parse_contact(_json({"email": "  hello@example.com \n"}))
    assert page is not None and page.email == "hello@example.com"


def test_parse_contact_invalid_email_dropped_and_details_kept() -> None:
    text = _json({"email": "not-an-email", "details": [{"label": "Based in", "value": "Lisbon"}]})
    assert parse_contact(text) == ContactPage(None, (ContactEntry("Based in", "Lisbon", None),))


def test_parse_contact_invalid_email_warns_once(warnings_logged: pytest.LogCaptureFixture) -> None:
    parse_contact(_json({"email": "not-an-email", "details": [{"label": "A", "value": "b"}]}))
    assert _only_warning(warnings_logged) == (
        "Ignoring the email in 'contact.json': not an email address"
    )


def test_parse_contact_invalid_email_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    parse_contact(_json({"email": SECRET, "details": [{"label": "A", "value": "b"}]}))
    assert not any(SECRET in message for message in _logged(caplog))


def test_parse_contact_invalid_email_only_returns_none() -> None:
    assert parse_contact(_json({"email": "not-an-email"})) is None


@pytest.mark.parametrize("email", ["", "   "], ids=["empty", "whitespace"])
def test_parse_contact_blank_email_means_no_email_without_warning(
    warnings_logged: pytest.LogCaptureFixture, email: str
) -> None:
    page = parse_contact(_json({"email": email, "details": [{"label": "A", "value": "b"}]}))
    assert (page, _warnings(warnings_logged)) == (
        ContactPage(None, (ContactEntry("A", "b", None),)),
        [],
    )


@pytest.mark.parametrize(
    "value",
    [{"email": "", "details": []}, {}, {"email": None}, {"_comment": "only a note"}],
    ids=["empty-email-and-details", "empty-object", "null-email", "comment-only"],
)
def test_parse_contact_nothing_to_show_returns_none(value: object) -> None:
    assert parse_contact(_json(value)) is None


def test_parse_contact_nothing_to_show_warns(warnings_logged: pytest.LogCaptureFixture) -> None:
    parse_contact(_json({"email": "", "details": []}))
    assert _only_warning(warnings_logged) == "Skipping 'contact.json': no email or details"


def test_parse_contact_warning_names_given_drive_file(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_contact(_json({}), "Contact.JSON")
    assert _only_warning(warnings_logged) == "Skipping 'Contact.JSON': no email or details"


def test_parse_contact_empty_label_returns_none() -> None:
    assert parse_contact(_details(("", "x"))) is None


def test_parse_contact_empty_label_warning_locates_field(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_contact(_details(("", "x")))
    assert _only_warning(warnings_logged).startswith("Skipping 'contact.json': details.0.label: ")


def test_parse_contact_bad_second_detail_located_by_index(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_contact(_details(("A", "b"), ("C", "   ")))
    assert _only_warning(warnings_logged).startswith("Skipping 'contact.json': details.1.value: ")


def test_parse_contact_missing_value_warning_says_field_required(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_contact(_json({"details": [{"label": "A"}]}))
    assert _only_warning(warnings_logged) == (
        "Skipping 'contact.json': details.0.value: Field required"
    )


@pytest.mark.parametrize(
    "value",
    [
        {"details": [{"label": "A", "value": 5}]},
        {"details": {"label": "A", "value": "b"}},
        {"details": ["A: b"]},
        {"email": 5},
        {"email": ["hello@example.com"]},
    ],
    ids=["number-value", "details-object", "details-strings", "number-email", "list-email"],
)
def test_parse_contact_schema_error_returns_none(value: object) -> None:
    assert parse_contact(_json(value)) is None


@pytest.mark.parametrize(
    "value",
    [
        {"details": [{"label": SECRET, "value": 5}]},
        {"details": [{"label": "A", "value": [SECRET]}]},
        {"email": [SECRET]},
    ],
    ids=["label-with-bad-value", "value-list", "email-list"],
)
def test_parse_contact_schema_error_never_logs_input(
    caplog: pytest.LogCaptureFixture, value: object
) -> None:
    caplog.set_level(logging.DEBUG)
    parse_contact(_json(value))
    assert not any(SECRET in message for message in _logged(caplog))


def test_parse_contact_more_than_three_errors_truncated(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_contact(_json({"details": [{"label": 1, "value": 2}, {"label": 3, "value": 4}]}))
    assert _only_warning(warnings_logged).endswith("; ...")


def test_parse_contact_top_level_array_warning_says_root(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_contact(_json([{"label": "A", "value": "b"}]))
    assert _only_warning(warnings_logged).startswith("Skipping 'contact.json': (root): ")


def test_parse_contact_invalid_json_warning_names_file_and_position(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_contact('{"email": "hello@example.com"', "Contact.json")
    assert re.fullmatch(
        r"Skipping 'Contact\.json': not valid JSON \(line 1, column \d+\)",
        _only_warning(warnings_logged),
    )


def test_parse_contact_invalid_json_returns_none() -> None:
    assert parse_contact("Email: hello@example.com") is None


def test_parse_contact_extra_keys_ignored_without_warning(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_contact(
        _json(
            {
                "_comment": "x",
                "email": "a@example.com",
                "details": [{"label": "A", "value": "b", "_n": 1}],
            }
        )
    )
    assert _warnings(warnings_logged) == []


def test_parse_contact_details_keep_list_order() -> None:
    page = parse_contact(_details(("B", "two"), ("A", "one"), ("C", "three")))
    assert page is not None and [entry.label for entry in page.entries] == ["B", "A", "C"]


def test_parse_contact_label_and_value_stripped() -> None:
    assert parse_contact(_details(("  Based in ", "  Lisbon  "))) == ContactPage(
        None, (ContactEntry("Based in", "Lisbon", None),)
    )


def test_parse_contact_email_value_detail_links_mailto() -> None:
    assert parse_contact(_details(("Studio", "studio@example.com"))) == ContactPage(
        None, (ContactEntry("Studio", "studio@example.com", "mailto:studio@example.com"),)
    )


def test_parse_contact_detail_labelled_email_is_ordinary_entry() -> None:
    text = _json(
        {
            "email": "first@example.com",
            "details": [{"label": "Email", "value": "second@example.com"}],
        }
    )
    assert parse_contact(text) == ContactPage(
        "first@example.com",
        (ContactEntry("Email", "second@example.com", "mailto:second@example.com"),),
    )


@pytest.mark.parametrize(
    "value", ["javascript:alert(1)", "@yourhandle", "Lisbon, Portugal", "data:text/html,<b>x</b>"]
)
def test_parse_contact_non_url_value_is_plain_text(value: str) -> None:
    assert parse_contact(_details(("X", value))) == ContactPage(
        None, (ContactEntry("X", value, None),)
    )


def test_parse_contact_javascript_value_logs_no_warning(
    warnings_logged: pytest.LogCaptureFixture,
) -> None:
    parse_contact(_details(("X", "javascript:alert(1)")))
    assert _warnings(warnings_logged) == []


@pytest.mark.parametrize(
    "value", ["https://", "https:///path", "https://exa mple.com", "http://example.com/a b"]
)
def test_parse_contact_malformed_url_is_plain_text(value: str) -> None:
    page = parse_contact(_details(("Site", value)))
    assert page is not None and page.entries[0].href is None


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("http://example.com/", "example.com"),
        ("HTTPS://Example.com/Me/", "Example.com/Me"),
        ("https://example.com/a?b=1", "example.com/a?b=1"),
        ("https://example.com//", "example.com/"),
        ("https://example.com/a:b", "example.com/a:b"),
    ],
)
def test_parse_contact_url_text_drops_scheme_and_one_trailing_slash(value: str, text: str) -> None:
    assert parse_contact(_details(("Site", value))) == ContactPage(
        None, (ContactEntry("Site", text, value),)
    )


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
    page = parse_contact(_details(("Site", value)))
    assert page is not None and page.entries[0].href is None


def test_parse_contact_uppercase_scheme_url_still_linked() -> None:
    assert parse_contact(_details(("Site", "HTTPS://Example.com/x"))) == ContactPage(
        None, (ContactEntry("Site", "Example.com/x", "HTTPS://Example.com/x"),)
    )


def test_parse_contact_html_kept_unescaped() -> None:
    assert parse_contact(_details(("<i>Studio</i>", "<b>Lisbon</b> & Porto"))) == ContactPage(
        None, (ContactEntry("<i>Studio</i>", "<b>Lisbon</b> & Porto", None),)
    )


DEEPLY_NESTED = "[" * 60000


def test_deeply_nested_json_is_under_the_size_cap() -> None:
    assert len(DEEPLY_NESTED.encode()) < MAX_PAGE_BYTES


@pytest.mark.parametrize(
    ("parse", "name"), [(parse_about, "about.json"), (parse_contact, "contact.json")]
)
def test_parse_deeply_nested_json_returns_none(parse: Callable[..., object], name: str) -> None:
    assert parse(DEEPLY_NESTED, name) is None


@pytest.mark.parametrize(
    ("parse", "name"), [(parse_about, "About.json"), (parse_contact, "Contact.json")]
)
def test_parse_deeply_nested_json_warns_nested_too_deeply(
    warnings_logged: pytest.LogCaptureFixture, parse: Callable[..., object], name: str
) -> None:
    parse(DEEPLY_NESTED, name)
    assert (
        _only_warning(warnings_logged) == f"Skipping '{name}': not valid JSON (nested too deeply)"
    )


# --- numbers past Python's int digit limit -----------------------------------------------

LONG_DIGITS = "9" * 5000
LONG_NUMBER_CASES = [
    (parse_about, "about.json", '{"lede": "x", "_comment": ' + LONG_DIGITS + "}"),
    (parse_contact, "contact.json", '{"email": ' + LONG_DIGITS + "}"),
]
LONG_NUMBER_IDS = ["about", "contact"]


@pytest.mark.parametrize(("parse", "name", "text"), LONG_NUMBER_CASES, ids=LONG_NUMBER_IDS)
def test_parse_long_integer_returns_none(
    parse: Callable[..., object], name: str, text: str
) -> None:
    assert parse(text, name) is None


@pytest.mark.parametrize(("parse", "name", "text"), LONG_NUMBER_CASES, ids=LONG_NUMBER_IDS)
def test_parse_long_integer_warns_number_too_long(
    warnings_logged: pytest.LogCaptureFixture, parse: Callable[..., object], name: str, text: str
) -> None:
    parse(text, name)
    assert _only_warning(warnings_logged) == (
        f"Skipping '{name}': not valid JSON (a number is too long)"
    )


@pytest.mark.parametrize(("parse", "name", "text"), LONG_NUMBER_CASES, ids=LONG_NUMBER_IDS)
def test_parse_long_integer_never_logs_digits(
    caplog: pytest.LogCaptureFixture, parse: Callable[..., object], name: str, text: str
) -> None:
    caplog.set_level(logging.DEBUG)
    parse(text, name)
    assert not any("9" * 50 in message for message in _logged(caplog))


# --- scalar top level --------------------------------------------------------------------

SCALAR_CASES = [
    (parse_about, "about.json", '"SECRET-xyz"'),
    (parse_about, "about.json", "null"),
    (parse_contact, "contact.json", '"SECRET-xyz"'),
    (parse_contact, "contact.json", "null"),
]
SCALAR_IDS = ["about-string", "about-null", "contact-string", "contact-null"]


@pytest.mark.parametrize(("parse", "name", "text"), SCALAR_CASES, ids=SCALAR_IDS)
def test_parse_scalar_top_level_warning_says_root(
    warnings_logged: pytest.LogCaptureFixture, parse: Callable[..., object], name: str, text: str
) -> None:
    parse(text, name)
    assert _only_warning(warnings_logged).startswith(f"Skipping '{name}': (root): ")


@pytest.mark.parametrize(("parse", "name", "text"), SCALAR_CASES, ids=SCALAR_IDS)
def test_parse_scalar_top_level_never_logs_value(
    caplog: pytest.LogCaptureFixture, parse: Callable[..., object], name: str, text: str
) -> None:
    caplog.set_level(logging.DEBUG)
    parse(text, name)
    assert not any(SECRET in message for message in _logged(caplog))


# --- duplicate keys: the last one wins ----------------------------------------------------


def test_parse_about_duplicate_lede_last_one_wins() -> None:
    page = parse_about('{"lede": "first", "lede": "second"}')
    assert page is not None and page.lede == "second"


def test_parse_contact_duplicate_email_last_one_wins() -> None:
    page = parse_contact('{"email": "first@example.com", "email": "second@example.com"}')
    assert page is not None and page.email == "second@example.com"


# --- invisible and control characters in About text ---------------------------------------


def test_parse_about_spec_example_drops_invisible_characters() -> None:
    text = _json({"lede": "a\u0000b‮c  d", "paragraphs": ["​", "ok  fine"]})
    assert parse_about(text) == AboutPage("abc d", ("ok fine",))


@pytest.mark.parametrize(
    "char",
    ["\u0000", "\u0007", "​", "‎", "‮", "⁦", "﻿"],
    ids=["nul", "bell", "zero-width-space", "lrm", "rlo", "lri", "bom"],
)
def test_parse_about_invisible_character_removed_from_lede(char: str) -> None:
    page = parse_about(_json({"lede": f"Hel{char}lo"}))
    assert page is not None and page.lede == "Hello"


def test_parse_about_paragraph_of_only_invisible_characters_dropped() -> None:
    page = parse_about(_json({"lede": "L", "paragraphs": ["​‮\u0000", "Body"]}))
    assert page is not None and page.paragraphs == ("Body",)


def test_parse_about_lede_of_only_invisible_characters_returns_none() -> None:
    assert parse_about(_json({"lede": "​‮"})) is None


def test_parse_about_visible_unicode_kept() -> None:
    page = parse_about(_json({"lede": "Café — naïve 日本"}))
    assert page is not None and page.lede == "Café — naïve 日本"
