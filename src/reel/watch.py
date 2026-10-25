"""Polling file watcher for `reel watch`: rebuild the site whenever a source file changes."""

import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from reel.scripts import compile_scripts

Snapshot = dict[Path, int]

IGNORED_DIRS = frozenset({"__pycache__"})


def snapshot(paths: Iterable[Path]) -> Snapshot:
    """Modification times (ns) of every file under `paths`; missing paths are skipped."""
    times: Snapshot = {}
    for root in paths:
        candidates = [root] if root.is_file() else root.rglob("*") if root.is_dir() else []
        for path in candidates:
            if path.is_file() and not IGNORED_DIRS.intersection(path.parts):
                try:
                    times[path] = path.stat().st_mtime_ns
                except OSError:
                    continue
    return times


def changed_files(before: Snapshot, after: Snapshot) -> list[Path]:
    """Files added, removed, or modified between two snapshots, sorted."""
    return sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )


def needs_script_compile(changes: Iterable[Path]) -> bool:
    """Only TypeScript edits change the compiled site script; CSS and templates don't."""
    return any(path.suffix == ".ts" for path in changes)


def run_build(scripts_dir: Path) -> bool:
    """Run `reel build` in a fresh interpreter so edits to Python modules take effect."""
    command = [sys.executable, "-m", "reel", "build", "--scripts-dir", str(scripts_dir)]
    return subprocess.run(command, check=False).returncode == 0


LIVE_RELOAD_SCRIPT = "reel-live-reload.js"

# Polls its own URL; a rebuild rewrites this file with a new id, so a mismatch means reload.
_LIVE_RELOAD_SOURCE = """(() => {
  const script = document.currentScript;
  if (!(script instanceof HTMLScriptElement)) return;
  const buildId = "%s";
  setInterval(async () => {
    try {
      const response = await fetch(script.src, { cache: "no-store" });
      if (response.ok && !(await response.text()).includes(buildId)) location.reload();
    } catch {}
  }, 1000);
})();
"""


class WatchSession:
    """Compiled site scripts kept between rebuilds, so TypeScript compiles only when it changed."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._compiled: Path | None = None

    def compile(self) -> None:
        """Compile the TypeScript; on failure the previous compiled scripts stay in use."""
        target = Path(tempfile.mkdtemp(prefix="compiled-", dir=self._workspace))
        try:
            compile_scripts(target)
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
        if self._compiled is not None:
            shutil.rmtree(self._compiled, ignore_errors=True)
        self._compiled = target

    def stage(self) -> Path:
        """Fresh scripts folder for one build: the compiled scripts plus a new live-reload id."""
        staged = self._workspace / "site-scripts"
        shutil.rmtree(staged, ignore_errors=True)
        staged.mkdir()
        if self._compiled is not None:
            for script in self._compiled.glob("*.js"):
                shutil.copy2(script, staged / script.name)
        build_id = str(time.time_ns())
        (staged / LIVE_RELOAD_SCRIPT).write_text(_LIVE_RELOAD_SOURCE % build_id, encoding="utf-8")
        return staged


def watch(
    paths: list[Path],
    on_change: Callable[[list[Path]], None],
    interval: float = 0.5,
    settle: float = 0.3,
) -> None:
    """Call `on_change` with the changed files each time `paths` change; runs until interrupted.

    Waits `settle` seconds after a change so an editor's multi-file save triggers one rebuild.
    """
    current = snapshot(paths)
    while True:
        time.sleep(interval)
        latest = snapshot(paths)
        if latest == current:
            continue
        time.sleep(settle)
        latest = snapshot(paths)
        changes = changed_files(current, latest)
        current = latest
        if changes:
            on_change(changes)
