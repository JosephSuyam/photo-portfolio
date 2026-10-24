"""Render the manifest into static HTML in `dist/` with Jinja2.

Not implemented yet.
"""

from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape


def make_environment() -> Environment:
    """Jinja2 environment for the bundled templates, with HTML autoescaping on.

    Album and photo names come from Drive and are untrusted, so autoescape is mandatory.
    """
    return Environment(
        loader=PackageLoader("reel", "templates"),
        autoescape=select_autoescape(["html"]),
    )


STATIC_DIR = Path(__file__).parent / "static"
