"""A minimal HTML tree for asserting on rendered pages, built on the standard library.

Selectors support tags, classes, and the descendant combinator: `"ul.album-grid li.album-card"`.
Text is entity-decoded and whitespace-collapsed, so an escaped `&lt;script&gt;` title reads back
as the literal string, while an unescaped one would have become a child element.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser

_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
)


@dataclass
class Element:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list["Element | str"] = field(default_factory=list)

    @property
    def classes(self) -> list[str]:
        return (self.attrs.get("class") or "").split()

    def text(self) -> str:
        return " ".join("".join(self._strings()).split())

    def descendants(self) -> Iterator["Element"]:
        for child in self.children:
            if isinstance(child, Element):
                yield child
                yield from child.descendants()

    def find_all(self, selector: str) -> list["Element"]:
        scope: list[Element] = [self]
        for part in selector.split():
            matches: dict[int, Element] = {}
            for element in scope:
                for found in element.descendants():
                    if _matches(found, part):
                        matches.setdefault(id(found), found)
            scope = list(matches.values())
        return scope

    def find(self, selector: str) -> "Element | None":
        found = self.find_all(selector)
        return found[0] if found else None

    def _strings(self) -> Iterator[str]:
        for child in self.children:
            if isinstance(child, Element):
                yield from child._strings()
            else:
                yield child


def _matches(element: Element, simple_selector: str) -> bool:
    tag, *classes = simple_selector.split(".")
    if tag and element.tag != tag:
        return False
    return all(name in element.classes for name in classes)


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("#document")
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag, dict(attrs))
        self._stack[-1].children.append(element)
        if tag not in _VOID_TAGS:
            self._stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stack[-1].children.append(Element(tag, dict(attrs)))

    def handle_endtag(self, tag: str) -> None:
        for depth in range(len(self._stack) - 1, 0, -1):
            if self._stack[depth].tag == tag:
                del self._stack[depth:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].children.append(data)


def parse_html(html: str) -> Element:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root
