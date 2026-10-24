"""Command-line entry point: `reel sync | build | serve | all`."""

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="Build a static photo portfolio from a Google Drive folder.")


def _not_implemented(step: str) -> None:
    typer.echo(f"`reel {step}` is not implemented yet.", err=True)
    raise typer.Exit(code=1)


@app.command()
def sync() -> None:
    """Pull albums and photos from Drive into the local cache."""
    _not_implemented("sync")


@app.command()
def build() -> None:
    """Render the site from the local cache into dist/."""
    _not_implemented("build")


@app.command()
def serve(
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8000,
    directory: Annotated[Path, typer.Option(help="Directory to serve.")] = Path("dist"),
) -> None:
    """Serve the generated site locally."""
    if not directory.is_dir():
        typer.echo(f"{directory}/ does not exist. Run `reel build` first.", err=True)
        raise typer.Exit(code=1)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(directory))
    with ThreadingHTTPServer(("localhost", port), handler) as server:
        typer.echo(f"Serving {directory}/ on http://localhost:{port}")
        server.serve_forever()


@app.command(name="all")
def run_all() -> None:
    """Sync, then build."""
    sync()
    build()
