from pathlib import Path

from typer.testing import CliRunner

from reel.cli import app

runner = CliRunner()


def test_cli_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert all(name in result.output for name in ("sync", "build", "serve", "all"))


def test_cli_serve_missing_directory_exits_with_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["serve", "--directory", str(tmp_path / "nope")])
    assert result.exit_code == 1
