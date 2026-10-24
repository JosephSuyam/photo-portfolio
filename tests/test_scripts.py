import shutil
from pathlib import Path

import pytest

from reel.scripts import PROJECT_ROOT, ScriptError, compile_scripts

needs_node = pytest.mark.skipif(
    shutil.which("npx") is None or not (PROJECT_ROOT / "node_modules" / "typescript").is_dir(),
    reason="Node.js and `npm install` are required to compile TypeScript",
)


def test_compile_scripts_without_node_raises_script_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(ScriptError):
        compile_scripts(tmp_path)


@needs_node
def test_compile_scripts_writes_site_js(tmp_path: Path) -> None:
    compile_scripts(tmp_path)
    assert (tmp_path / "site.js").is_file()


@needs_node
def test_compile_scripts_output_has_no_type_annotations(tmp_path: Path) -> None:
    compile_scripts(tmp_path)
    assert "HTMLElement" not in (tmp_path / "site.js").read_text(encoding="utf-8")


def test_compile_scripts_without_node_raises_node_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reel.scripts import NodeNotFoundError

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(NodeNotFoundError):
        compile_scripts(tmp_path)


@needs_node
def test_compile_scripts_type_error_raises_script_error_with_tsc_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import reel.scripts

    bad = tmp_path / "project"
    (bad / "src").mkdir(parents=True)
    (bad / "src" / "bad.ts").write_text("const n: number = 'text';\n", encoding="utf-8")
    tsconfig = '{"compilerOptions": {"strict": true, "rootDir": "src"}, "include": ["src/*.ts"]}'
    (bad / "tsconfig.json").write_text(tsconfig, encoding="utf-8")
    monkeypatch.setattr(reel.scripts, "TSCONFIG", bad / "tsconfig.json")
    with pytest.raises(ScriptError, match="bad.ts"):
        compile_scripts(tmp_path / "out")


def test_compile_scripts_timeout_raises_script_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    import reel.scripts

    def hanging_run(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="tsc", timeout=1)

    # Stand-in compiler so the test runs without `npm install`; subprocess.run never starts it.
    stand_in_tsc = tmp_path / "tsc"
    stand_in_tsc.write_text("", encoding="utf-8")
    monkeypatch.setattr(reel.scripts, "TSC", stand_in_tsc)
    monkeypatch.setattr(shutil, "which", lambda _name: "node")
    monkeypatch.setattr(subprocess, "run", hanging_run)
    with pytest.raises(ScriptError, match="timed out"):
        compile_scripts(tmp_path)
