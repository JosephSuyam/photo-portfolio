"""Compile the site's TypeScript (`src/reel/ts/`) with the project's local `tsc`.

`PROJECT_ROOT` is the source checkout: reel runs from the repo, not as an installed wheel.
"""

import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TSCONFIG = PROJECT_ROOT / "tsconfig.json"
TSC = PROJECT_ROOT / "node_modules" / "typescript" / "bin" / "tsc"
COMPILE_TIMEOUT_SECONDS = 120


class ScriptError(Exception):
    """Raised when the TypeScript cannot be compiled."""


class NodeNotFoundError(ScriptError):
    """Raised when Node.js or the project's TypeScript compiler is not installed."""


def compile_scripts(out_dir: Path) -> None:
    """Compile the site's TypeScript into JavaScript files in `out_dir`."""
    node = shutil.which("node")
    if node is None:
        raise NodeNotFoundError("Node.js not found. Install Node.js, then run `npm install`.")
    if not TSC.is_file():
        raise NodeNotFoundError("TypeScript compiler not installed. Run `npm install`.")
    if not TSCONFIG.is_file():
        raise ScriptError(f"{TSCONFIG} not found; cannot compile the site's TypeScript.")
    # Run tsc with node directly: on Windows `npx` is a .cmd file routed through cmd.exe.
    command = [node, str(TSC), "-p", str(TSCONFIG), "--outDir", str(out_dir)]
    try:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=COMPILE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise ScriptError(
            f"TypeScript compilation timed out after {COMPILE_TIMEOUT_SECONDS}s."
        ) from error
    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        raise ScriptError(f"TypeScript compilation failed:\n{output}")
