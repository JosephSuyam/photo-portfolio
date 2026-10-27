"""Local preview server for a built site."""

import functools
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_CLIENT_GONE_ERRORS = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)


class PreviewServer(ThreadingHTTPServer):
    """Threaded static file server that copes with a page requesting many images at once.

    The standard library default listen backlog is 5, so a gallery page firing dozens of
    parallel image requests gets some of them refused.
    """

    request_queue_size = 128

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Stay quiet when the browser cancels a request (e.g. a lazy image scrolled away)."""
        if isinstance(sys.exception(), _CLIENT_GONE_ERRORS):
            return
        super().handle_error(request, client_address)


def make_preview_server(directory: Path, port: int) -> PreviewServer:
    """Server for `directory` on localhost:`port`; call `serve_forever()` to run it."""
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(directory))
    return PreviewServer(("localhost", port), handler)
