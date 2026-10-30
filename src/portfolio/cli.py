"""Command-line entry point: `portfolio sync | build | serve | watch | subscribe | all`."""

import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from google.auth.exceptions import GoogleAuthError
from httplib2 import HttpLib2Error

from portfolio.build import BuildError, base_path_from_url, build_site, load_manifest
from portfolio.config import ConfigError, load_settings, load_site_settings, load_webhook_settings
from portfolio.drive import DriveError, GoogleDriveClient
from portfolio.scripts import NodeNotFoundError, ScriptError, compile_scripts
from portfolio.server import make_preview_server
from portfolio.sync import sync_portfolio
from portfolio.watch import WatchSession, needs_script_compile, run_build, watch

CACHE_DIR = Path(".cache")
DIST_DIR = Path("dist")

# Never print frame locals in tracebacks: they can hold credentials or tokens.
app = typer.Typer(
    help="Build a static photo portfolio from a Google Drive folder.",
    pretty_exceptions_show_locals=False,
)


@app.command()
def sync() -> None:
    """Pull albums and photos from Drive into the local cache."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        settings = load_settings()
    except ConfigError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    client = _drive_client(settings.credentials_path)
    try:
        manifest = sync_portfolio(client, settings.root_folder_id, CACHE_DIR)
    except (DriveError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    except (GoogleAuthError, HttpLib2Error) as error:
        _exit_unreachable(error)
    count = len(manifest.albums)
    typer.echo(f"Synced {count} album{'' if count == 1 else 's'} into {CACHE_DIR}/")


def _drive_client(credentials_path: Path) -> GoogleDriveClient:
    try:
        return GoogleDriveClient.from_credentials(credentials_path)
    except (OSError, ValueError) as error:
        # The underlying message can echo the key path or contents, so name the setting only.
        typer.echo(
            "Cannot load the service account key named by GOOGLE_APPLICATION_CREDENTIALS.",
            err=True,
        )
        raise typer.Exit(code=1) from error


def _exit_unreachable(error: Exception) -> NoReturn:
    typer.echo(
        f"Cannot reach Google Drive ({type(error).__name__}). Check the network connection "
        "and that the key named by GOOGLE_APPLICATION_CREDENTIALS is valid.",
        err=True,
    )
    raise typer.Exit(code=1) from error


@app.command()
def build(
    scripts_dir: Annotated[
        Path | None,
        typer.Option(hidden=True, help="Use these compiled scripts instead of compiling."),
    ] = None,
) -> None:
    """Render the site from the local cache into dist/."""
    try:
        if scripts_dir is not None:
            count = _build_with_scripts(scripts_dir)
        else:
            with tempfile.TemporaryDirectory(prefix="portfolio-scripts-") as temp_dir:
                compiled: Path | None = Path(temp_dir)
                try:
                    compile_scripts(Path(temp_dir))
                except NodeNotFoundError as error:
                    typer.echo(f"Warning: {error} Building without the site script.", err=True)
                    compiled = None
                count = _build_with_scripts(compiled)
    except (BuildError, ConfigError, ScriptError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"Built {count} album{'' if count == 1 else 's'} into {DIST_DIR}/")


def _build_with_scripts(scripts_dir: Path | None) -> int:
    settings = load_site_settings()
    return build_site(
        load_manifest(CACHE_DIR / "manifest.json"),
        CACHE_DIR,
        DIST_DIR,
        settings.site_title,
        base_path_from_url(settings.site_base_url),
        scripts_dir=scripts_dir,
        contact_form_url=settings.contact_form_url,
    )


@app.command()
def serve(
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8000,
    directory: Annotated[Path, typer.Option(help="Directory to serve.")] = Path("dist"),
) -> None:
    """Serve the generated site locally."""
    if not directory.is_dir():
        typer.echo(f"{directory}/ does not exist. Run `portfolio build` first.", err=True)
        raise typer.Exit(code=1)
    with make_preview_server(directory, port) as server:
        typer.echo(f"Serving {directory}/ on http://localhost:{port}")
        server.serve_forever()


@app.command(name="watch")
def watch_command(
    port: Annotated[
        int | None,
        typer.Option(help="Also serve dist/ on this port (leave unset if `portfolio serve` runs)."),
    ] = None,
) -> None:
    """Rebuild the site whenever templates, CSS, TypeScript, Python, or the cache change.

    Pages built here reload themselves in the browser after each successful rebuild;
    `portfolio build` output never includes that script.
    """
    watched = [Path(__file__).parent, CACHE_DIR / "manifest.json", Path(".env")]
    with tempfile.TemporaryDirectory(prefix="portfolio-watch-") as temp_dir:
        session = WatchSession(Path(temp_dir))
        _rebuild(session, changes=None)
        if port is not None:
            server = make_preview_server(DIST_DIR, port)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            typer.echo(f"Serving {DIST_DIR}/ on http://localhost:{port}")
        typer.echo("Watching for changes (Ctrl+C to stop)...")

        def on_change(changes: list[Path]) -> None:
            shown = ", ".join(path.name for path in changes[:3])
            more = f" and {len(changes) - 3} more" if len(changes) > 3 else ""
            typer.echo(f"\nChanged: {shown}{more}")
            _rebuild(session, changes)

        try:
            watch(watched, on_change)
        except KeyboardInterrupt:
            typer.echo("Stopped watching.")


def _rebuild(session: WatchSession, changes: list[Path] | None) -> None:
    started = time.monotonic()
    if changes is None or needs_script_compile(changes):
        try:
            session.compile()
        except NodeNotFoundError as error:
            typer.echo(f"Warning: {error} Building without the site script.", err=True)
        except ScriptError as error:
            typer.echo(f"{error}\nNot rebuilt; dist/ still has the last good site.", err=True)
            return
    if run_build(session.stage()):
        typer.echo(f"Rebuilt in {time.monotonic() - started:.1f}s")
    else:
        typer.echo("Build failed; dist/ still has the last good site.", err=True)


# Drive allows changes.watch channels up to one week (files.watch: one day).
WEBHOOK_TTL_SECONDS = 24 * 60 * 60


@app.command()
def subscribe() -> None:
    """Point Drive change notifications at DRIVE_WEBHOOK_URL for the next 24 hours.

    Scheduled and manual Deploy runs renew it (every 12 hours), so a channel stays live
    through long gaps between scheduled runs.
    """
    try:
        settings = load_settings()
        address, token = load_webhook_settings()
    except ConfigError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    client = _drive_client(settings.credentials_path)
    try:
        expires = client.watch_changes(address, token, WEBHOOK_TTL_SECONDS)
    except DriveError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    except (GoogleAuthError, HttpLib2Error, OSError) as error:
        _exit_unreachable(error)
    typer.echo(f"Drive change notifications active until {expires:%Y-%m-%d %H:%M} UTC")


@app.command(name="all")
def run_all() -> None:
    """Sync, then build."""
    sync()
    build()
