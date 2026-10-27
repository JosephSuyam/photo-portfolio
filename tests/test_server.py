from pathlib import Path

import pytest

from portfolio.server import make_preview_server


def test_preview_server_queues_many_parallel_connections(tmp_path: Path) -> None:
    with make_preview_server(tmp_path, 0) as server:
        assert server.request_queue_size >= 64


def test_preview_server_cancelled_request_not_logged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with make_preview_server(tmp_path, 0) as server:
        try:
            raise ConnectionAbortedError("browser went away")
        except ConnectionAbortedError:
            server.handle_error(None, ("127.0.0.1", 1))
    assert capsys.readouterr().err == ""


def test_preview_server_other_errors_still_logged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with make_preview_server(tmp_path, 0) as server:
        try:
            raise ValueError("real bug")
        except ValueError:
            server.handle_error(None, ("127.0.0.1", 1))
    assert "real bug" in capsys.readouterr().err
