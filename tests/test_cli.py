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
    monkeypatch.delenv("CONTACT_FORM_URL", raising=False)
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


@pytest.fixture
def no_drive_settings(site_cwd: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`site_cwd` with the Drive settings removed from the environment too."""
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("DRIVE_ROOT_FOLDER_ID", raising=False)
    return site_cwd


def test_cli_sync_missing_settings_exits_with_error(no_drive_settings: Path) -> None:
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 1


@pytest.mark.parametrize("name", ["GOOGLE_APPLICATION_CREDENTIALS", "DRIVE_ROOT_FOLDER_ID"])
def test_cli_sync_missing_settings_names_missing_setting(
    no_drive_settings: Path, name: str
) -> None:
    result = runner.invoke(app, ["sync"])
    assert name in result.output


def test_cli_sync_missing_settings_no_traceback(no_drive_settings: Path) -> None:
    result = runner.invoke(app, ["sync"])
    assert isinstance(result.exception, SystemExit)


def test_cli_sync_one_setting_missing_names_only_that_setting(
    no_drive_settings: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(no_drive_settings / "sa.json"))
    result = runner.invoke(app, ["sync"])
    assert "DRIVE_ROOT_FOLDER_ID" in result.output and "GOOGLE_APPLICATION_CREDENTIALS" not in (
        result.output
    )


def test_cli_build_base_url_path_used_in_links(
    site_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(site_cwd)
    monkeypatch.setenv("SITE_BASE_URL", "https://x.com/portfolio")
    runner.invoke(app, ["build"])
    html = (site_cwd / "dist" / "index.html").read_text(encoding="utf-8")
    assert 'href="/portfolio/book/"' in html


@pytest.fixture
def drive_settings(site_cwd: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`site_cwd` with a service-account key path and root id set."""
    key = site_cwd / "secret-key.json"
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(key))
    monkeypatch.setenv("DRIVE_ROOT_FOLDER_ID", "root")
    return key


def test_cli_sync_missing_key_file_exits_without_echoing_path(drive_settings: Path) -> None:
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 1 and str(drive_settings) not in result.output


def test_cli_sync_malformed_key_does_not_echo_contents(drive_settings: Path) -> None:
    drive_settings.write_text('{"private_key": "TOP-SECRET-VALUE"', encoding="utf-8")
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 1 and "TOP-SECRET-VALUE" not in result.output


def _use_fake_drive(monkeypatch: pytest.MonkeyPatch, drive: object) -> None:
    from reel.drive import GoogleDriveClient

    monkeypatch.setattr(GoogleDriveClient, "from_credentials", lambda _path: drive)


def test_cli_sync_unshared_root_exits_with_sharing_hint(
    drive_settings: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.fixtures.fake_drive import FakeDriveClient

    _use_fake_drive(monkeypatch, FakeDriveClient())
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 1 and "shared with the service account" in result.output


def test_cli_sync_auth_failure_exits_with_clean_message(
    drive_settings: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from google.auth.exceptions import RefreshError

    from tests.fixtures.fake_drive import FakeDriveClient

    drive = FakeDriveClient()

    def refused(_folder_id: str) -> None:
        raise RefreshError("invalid_grant")

    monkeypatch.setattr(drive, "get_folder", refused)
    _use_fake_drive(monkeypatch, drive)
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 1 and "Cannot reach Google Drive (RefreshError)" in result.output


def test_cli_sync_success_reports_album_count(
    drive_settings: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.fixtures.fake_drive import FakeDriveClient

    drive = FakeDriveClient()
    drive.add_root("root")
    drive.add_folder("root", "f1", "Book")
    drive.add_file("f1", "p1", "1.jpg", content=b"x")
    _use_fake_drive(monkeypatch, drive)
    result = runner.invoke(app, ["sync"])
    assert "Synced 1 album into .cache/" in result.output


def test_cli_build_without_node_builds_without_script(
    site_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import reel.cli
    from reel.scripts import NodeNotFoundError

    def no_node(_out_dir: Path) -> None:
        raise NodeNotFoundError("Node.js not found.")

    _write_manifest(site_cwd)
    monkeypatch.setattr(reel.cli, "compile_scripts", no_node)
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0 and "Building without the site script" in result.output


FORM_URL = "https://forms.example.test/f/reel"
INVALID_FORM_URL = "http://forms.example.test/f/reel"


def test_cli_build_invalid_contact_form_url_exits_with_error(
    site_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(site_cwd)
    monkeypatch.setenv("CONTACT_FORM_URL", INVALID_FORM_URL)
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 1


def test_cli_build_invalid_contact_form_url_prints_config_error(
    site_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(site_cwd)
    monkeypatch.setenv("CONTACT_FORM_URL", INVALID_FORM_URL)
    result = runner.invoke(app, ["build"])
    assert "CONTACT_FORM_URL must be an https:// URL." in result.output


def test_cli_build_invalid_contact_form_url_no_traceback(
    site_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(site_cwd)
    monkeypatch.setenv("CONTACT_FORM_URL", INVALID_FORM_URL)
    result = runner.invoke(app, ["build"])
    assert isinstance(result.exception, SystemExit)


def test_cli_build_invalid_contact_form_url_does_not_echo_value(
    site_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(site_cwd)
    monkeypatch.setenv("CONTACT_FORM_URL", INVALID_FORM_URL)
    result = runner.invoke(app, ["build"])
    assert "forms.example.test" not in result.output


def test_cli_build_invalid_contact_form_url_writes_no_dist(
    site_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(site_cwd)
    monkeypatch.setenv("CONTACT_FORM_URL", INVALID_FORM_URL)
    runner.invoke(app, ["build"])
    assert not (site_cwd / "dist").exists()


def _record_build_site(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Replace `build_site` and `compile_scripts` in the CLI; return the build_site kwargs."""
    import reel.cli

    calls: dict[str, object] = {}

    def fake_build_site(*args: object, **kwargs: object) -> int:
        calls.update(kwargs)
        return 1

    monkeypatch.setattr(reel.cli, "build_site", fake_build_site)
    monkeypatch.setattr(reel.cli, "compile_scripts", lambda _out_dir: None)
    return calls


def test_cli_build_valid_contact_form_url_passed_to_build_site(
    site_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(site_cwd)
    monkeypatch.setenv("CONTACT_FORM_URL", FORM_URL)
    calls = _record_build_site(monkeypatch)
    runner.invoke(app, ["build"])
    assert calls.get("contact_form_url") == FORM_URL


def test_cli_build_unset_contact_form_url_passes_none(
    site_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(site_cwd)
    calls = _record_build_site(monkeypatch)
    runner.invoke(app, ["build"])
    assert "contact_form_url" in calls and calls["contact_form_url"] is None
