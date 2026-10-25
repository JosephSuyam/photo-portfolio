"""Parse the root `about.txt` and `contact.txt` into the About and Contact pages.

Everything here is pure except `read_page_text`. The text comes from Drive and is untrusted:
it is returned as plain strings for the autoescaping templates, and only `http(s)://` and
email values ever become links.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MAX_PAGE_BYTES = 64 * 1024
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_URL_SCHEMES = frozenset({"https", "http"})


@dataclass(frozen=True)
class AboutPage:
    """The About text: a lede paragraph, then the remaining paragraphs."""

    lede: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class ContactEntry:
    """One "Label: value" line; `href` is set only for email and http(s) values."""

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


def parse_about(text: str) -> AboutPage | None:
    """Split `text` into paragraphs at blank lines; None if it has no text at all.

    Each paragraph is one line with whitespace collapsed. The first becomes the lede.
    """
    paragraphs: list[str] = []
    current: list[str] = []
    for line in [*text.split("\n"), ""]:
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append(" ".join(" ".join(current).split()))
            current = []
    if not paragraphs:
        return None
    return AboutPage(lede=paragraphs[0], paragraphs=tuple(paragraphs[1:]))


def parse_contact(text: str) -> ContactPage | None:
    """Read "Label: value" lines into the Contact page; None if nothing usable is left.

    Blank lines and `#` comments are skipped; malformed lines are skipped with a warning.
    The first valid `Email:` line becomes the headline address.
    """
    email: str | None = None
    entries: list[ContactEntry] = []
    for number, raw_line in enumerate(text.split("\n"), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        label, colon, value = (part.strip() for part in line.partition(":"))
        if not colon or not label or not value:
            logger.warning('Skipping line %d of contact.txt: expected "Label: value"', number)
            continue
        if label.casefold() == "email":
            if not EMAIL_PATTERN.fullmatch(value):
                logger.warning("Skipping line %d of contact.txt: not an email address", number)
                continue
            if email is None:
                email = value
                continue
        entries.append(_contact_entry(label, value))
    if email is None and not entries:
        return None
    return ContactPage(email=email, entries=tuple(entries))


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
