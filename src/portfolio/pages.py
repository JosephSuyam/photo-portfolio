"""Parse the root `about.json` and `contact.json` into the About and Contact pages.

Everything here is pure except `read_page_text`. The text comes from Drive and is untrusted:
it is returned as plain strings for the autoescaping templates, only `http(s)://` and email
values ever become links, and warnings never quote the file's contents.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

MAX_PAGE_BYTES = 64 * 1024
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_URL_SCHEMES = frozenset({"https", "http"})
_MAX_REPORTED_ERRORS = 3
# json's own recursion limit depends on the Python version and the C stack, so we cap depth.
_MAX_JSON_DEPTH = 32
# The closing quote is optional so an unterminated string ends the scan (linear, not quadratic).
_JSON_STRING = re.compile(r'"(?:[^"\\]|\\.)*"?', re.DOTALL)
# JSON has no comments, so unknown keys such as "_comment" are ignored rather than rejected.
_PAGE_FILE_CONFIG = ConfigDict(extra="ignore", str_strip_whitespace=True)


class AboutFile(BaseModel):
    """The schema of about.json."""

    model_config = _PAGE_FILE_CONFIG

    lede: str = Field(min_length=1)
    paragraphs: list[str] = []


class ContactDetail(BaseModel):
    """One labelled entry in contact.json."""

    model_config = _PAGE_FILE_CONFIG

    label: str = Field(min_length=1)
    value: str = Field(min_length=1)


class ContactFile(BaseModel):
    """The schema of contact.json."""

    model_config = _PAGE_FILE_CONFIG

    email: str | None = None
    details: list[ContactDetail] = []


@dataclass(frozen=True)
class AboutPage:
    """The About text: a lede paragraph, then the remaining paragraphs."""

    lede: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class ContactEntry:
    """One contact detail; `href` is set only for email and http(s) values."""

    label: str
    text: str
    href: str | None


@dataclass(frozen=True)
class ContactPage:
    """The Contact details: a headline email address and the other entries in file order."""

    email: str | None
    entries: tuple[ContactEntry, ...]


def read_page_text(path: Path, name: str) -> str | None:
    """Text of the page source at `path` with `\\n` line endings, or None if unusable.

    `name` is the Drive file name, used in warnings. Files over `MAX_PAGE_BYTES` or not valid
    UTF-8 are skipped with a warning; a leading BOM is dropped.
    """
    data = path.read_bytes()
    if len(data) > MAX_PAGE_BYTES:
        logger.warning("Skipping %r: larger than %d bytes", name, MAX_PAGE_BYTES)
        return None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        logger.warning("Skipping %r: not valid UTF-8 text", name)
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n")


def parse_about(text: str, name: str = "about.json") -> AboutPage | None:
    """The About page from about.json text, or None (with a warning) if it is unusable.

    `name` is the Drive file name, used in warnings. Whitespace runs are collapsed and blank
    paragraphs dropped.
    """
    about = _load_page_file(AboutFile, text, name)
    if about is None:
        return None
    lede = _collapse(about.lede)
    if not lede:
        logger.warning("Skipping %r: lede: has no visible text", name)
        return None
    paragraphs = tuple(
        collapsed for paragraph in about.paragraphs if (collapsed := _collapse(paragraph))
    )
    return AboutPage(lede=lede, paragraphs=paragraphs)


def parse_contact(text: str, name: str = "contact.json") -> ContactPage | None:
    """The Contact page from contact.json text, or None (with a warning) if it is unusable.

    `name` is the Drive file name, used in warnings. An invalid headline email is dropped
    with a warning; the details are kept in file order.
    """
    contact = _load_page_file(ContactFile, text, name)
    if contact is None:
        return None
    email = contact.email or None
    if email is not None and not EMAIL_PATTERN.fullmatch(email):
        logger.warning("Ignoring the email in %r: not an email address", name)
        email = None
    entries = tuple(_contact_entry(detail.label, detail.value) for detail in contact.details)
    if email is None and not entries:
        logger.warning("Skipping %r: no email or details", name)
        return None
    return ContactPage(email=email, entries=entries)


def _load_page_file[M: BaseModel](model: type[M], text: str, name: str) -> M | None:
    if _nesting_depth(text) > _MAX_JSON_DEPTH:
        logger.warning("Skipping %r: not valid JSON (nested too deeply)", name)
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        logger.warning(
            "Skipping %r: not valid JSON (line %d, column %d)", name, error.lineno, error.colno
        )
        return None
    except ValueError:
        # Python refuses integers longer than its digit limit; the message would echo them.
        logger.warning("Skipping %r: not valid JSON (a number is too long)", name)
        return None
    try:
        return model.model_validate(data)
    except ValidationError as error:
        logger.warning("Skipping %r: %s", name, _describe_errors(error))
        return None


def _nesting_depth(text: str) -> int:
    """The deepest `[`/`{` nesting outside JSON strings, counted without parsing."""
    depth = deepest = 0
    for char in _JSON_STRING.sub('""', text):
        if char in "[{":
            depth += 1
            deepest = max(deepest, depth)
        elif char in "]}":
            depth -= 1
            if depth < 0:
                break  # a stray closer: let json report its position
    return deepest


def _describe_errors(error: ValidationError) -> str:
    """Error locations and messages only: `str(error)` and `input` would echo the file."""
    details = error.errors(include_url=False, include_context=False, include_input=False)
    parts = [
        f"{'.'.join(str(part) for part in detail['loc']) or '(root)'}: {detail['msg']}"
        for detail in details[:_MAX_REPORTED_ERRORS]
    ]
    if len(details) > _MAX_REPORTED_ERRORS:
        parts.append("...")
    return "; ".join(parts)


def _collapse(text: str) -> str:
    """Whitespace runs as one space, without invisible controls such as NUL or bidi overrides."""
    visible = "".join(char for char in text if char.isprintable() or char.isspace())
    return " ".join(visible.split())


def _contact_entry(label: str, value: str) -> ContactEntry:
    """Link only email addresses and http(s) URLs; anything else stays plain text."""
    if EMAIL_PATTERN.fullmatch(value):
        return ContactEntry(label=label, text=value, href=f"mailto:{value}")
    if _is_web_url(value):
        _, _, rest = value.partition("://")
        return ContactEntry(label=label, text=rest.removesuffix("/"), href=value)
    return ContactEntry(label=label, text=value, href=None)


def _is_web_url(value: str) -> bool:
    """Whether `value` is a plain http(s) URL; a backslash or an invisible or bidi control
    character could make the link text disagree with where the browser goes."""
    if any(char.isspace() or not char.isprintable() or char == "\\" for char in value):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        # urlparse rejects malformed hosts such as "https://[oops".
        return False
    return parsed.scheme in _URL_SCHEMES and bool(parsed.netloc)
