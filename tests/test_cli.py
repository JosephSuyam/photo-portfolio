from pathlib import Path

import pytest
from typer.testing import CliRunner

from reel.cli import app
from tests.fixtures.albums import make_album, make_photo, write_original

runner = CliRunner()


def test_cli_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert all(name in result.output for name in ("sync", "build", "serve", "all"))


def test_cli_serve_missing_directory_exits_with_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["serve", "--directory", str(tmp_path / "nope")])
    assert result.exit_code == 1


@pytest.fixture
def site_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A clean working directory with no `.env` and no site env vars leaking in."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SITE_TITLE", raising=False)
    monkeypatch.delenv("SITE_BASE_URL", raising=False)
    return tmp_path


def _write_manifest(cwd: Path) -> None:
    from reel.models import Manifest

    cache = cwd / ".cache"
    write_original(cache, "p1")
    manifest = Manifest(albums=[make_album("book", [make_photo("p1")], title="Book")])
    (cache / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")


def test_cli_build_no_manifest_exits_with_error(site_cwd: Path) -> None:
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 1


def test_cli_build_no_manifest_suggests_reel_sync(site_cwd: Path) -> None:
    result = runner.invoke(app, ["build"])
    assert "reel sync" in result.output


def test_cli_build_with_manifest_exits_zero(site_cwd: Path) -> None:
    _write_manifest(site_cwd)
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0, result.output


def test_cli_build_with_manifest_writes_dist_index(site_cwd: Path) -> None:
    _write_manifest(site_cwd)
    runner.invoke(app, ["build"])
    assert (site_cwd / "dist" / "index.html").is_file()


def test_cli_build_site_title_from_env(site_cwd: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_manifest(site_cwd)
    monkeypatch.setenv("SITE_TITLE", "Jo Photographs")
    runner.invoke(app, ["build"])
    assert "Jo Photographs" in (site_cwd / "dist" / "index.html").read_text(encoding="utf-8")


def test_cli_build_base_url_path_used_in_links(
    site_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(site_cwd)
    monkeypatch.setenv("SITE_BASE_URL", "https://x.com/portfolio")
    runner.invoke(app, ["build"])
    html = (site_cwd / "dist" / "index.html").read_text(encoding="utf-8")
    assert 'href="/portfolio/book/"' in html
