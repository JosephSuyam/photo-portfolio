"""Command-line entry point: `reel sync | build | serve | all`."""

import logging
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from google.auth.exceptions import GoogleAuthError
from httplib2 import HttpLib2Error

from reel.build import BuildError, base_path_from_url, build_site, load_manifest
from reel.config import ConfigError, load_settings, load_site_settings
from reel.drive import DriveError, GoogleDriveClient
from reel.scripts import NodeNotFoundError, ScriptError, compile_scripts
from reel.server import make_preview_server
from reel.sync import sync_portfolio

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
    try:
        client = GoogleDriveClient.from_credentials(settings.credentials_path)
    except (OSError, ValueError) as error:
        # The underlying message can echo the key path or contents, so name the setting only.
        typer.echo(
            "Cannot load the service account key named by GOOGLE_APPLICATION_CREDENTIALS.",
            err=True,
        )
        raise typer.Exit(code=1) from error
    try:
        manifest = sync_portfolio(client, settings.root_folder_id, CACHE_DIR)
    except (DriveError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    except (GoogleAuthError, HttpLib2Error) as error:
        typer.echo(
            f"Cannot reach Google Drive ({type(error).__name__}). Check the network connection "
            "and that the key named by GOOGLE_APPLICATION_CREDENTIALS is valid.",
            err=True,
        )
        raise typer.Exit(code=1) from error
    count = len(manifest.albums)
    typer.echo(f"Synced {count} album{'' if count == 1 else 's'} into {CACHE_DIR}/")


@app.command()
def build() -> None:
    """Render the site from the local cache into dist/."""
    settings = load_site_settings()
    try:
        manifest = load_manifest(CACHE_DIR / "manifest.json")
        with tempfile.TemporaryDirectory(prefix="reel-scripts-") as temp_dir:
            scripts_dir: Path | None = Path(temp_dir)
            try:
                compile_scripts(Path(temp_dir))
            except NodeNotFoundError as error:
                typer.echo(f"Warning: {error} Building without the site script.", err=True)
                scripts_dir = None
            count = build_site(
                manifest,
                CACHE_DIR,
                DIST_DIR,
                settings.site_title,
                base_path_from_url(settings.site_base_url),
                scripts_dir=scripts_dir,
            )
    except (BuildError, ScriptError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"Built {count} album{'' if count == 1 else 's'} into {DIST_DIR}/")


@app.command()
def serve(
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8000,
    directory: Annotated[Path, typer.Option(help="Directory to serve.")] = Path("dist"),
) -> None:
    """Serve the generated site locally."""
    if not directory.is_dir():
        typer.echo(f"{directory}/ does not exist. Run `reel build` first.", err=True)
        raise typer.Exit(code=1)
    with make_preview_server(directory, port) as server:
        typer.echo(f"Serving {directory}/ on http://localhost:{port}")
        server.serve_forever()


@app.command(name="all")
def run_all() -> None:
    """Sync, then build."""
    sync()
    build()
