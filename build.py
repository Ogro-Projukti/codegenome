#!/usr/bin/env python3
"""Build a standalone watcher CLI binary with PyInstaller."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / "codegenome.spec"

BINARY_NAME = "watcher"

HIDDEN_IMPORTS = [
    "codegenome",
    "codegenome.__main__",
    "codegenome.mcp_server",
    "codegenome.parser",
    "codegenome.resources",
    "codegenome.workspace_metrics",
    "codegenome.live_graph_monitor",
    "tree_sitter",
    "tree_sitter_python",
    "tree_sitter_javascript",
    "tree_sitter_typescript",
    "tree_sitter_go",
    "tree_sitter_rust",
    "igraph",
    "leidenalg",
    "networkx",
    "watchdog",
    "watchdog.observers",
    "watchdog.observers.polling",
    "fastmcp",
    "starlette",
    "uvicorn",
    "radon",
]

COLLECT_ALL = [
    "tree_sitter",
    "tree_sitter_python",
    "tree_sitter_javascript",
    "tree_sitter_typescript",
    "tree_sitter_go",
    "tree_sitter_rust",
    "igraph",
    "leidenalg",
    "fastmcp",
]


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller>=6.0,<7"],
        )


def ensure_package_installed() -> None:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-e", f"{ROOT}[dev]"],
        cwd=ROOT,
    )


def bundle_datas() -> list[tuple[str, str]]:
    package_root = SRC / "codegenome"
    datas: list[tuple[str, str]] = []
    assets = package_root / "assets"
    templates = package_root / "templates"
    if assets.is_dir():
        datas.append((str(assets), "assets"))
    if templates.is_dir():
        datas.append((str(templates), "templates"))
    return datas


def write_spec() -> Path:
    datas = bundle_datas()
    hidden = HIDDEN_IMPORTS
    collect_all = COLLECT_ALL

    spec = f'''# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all as pyi_collect_all

block_cipher = None
datas = {datas!r}
binaries = []
hiddenimports = {hidden!r}

for package in {collect_all!r}:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = pyi_collect_all(package)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

a = Analysis(
    ["{SRC.as_posix()}/codegenome/__main__.py"],
    pathex=["{SRC.as_posix()}"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=["pytest", "pytest_cov", "ruff"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="{BINARY_NAME}",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
'''
    SPEC.write_text(spec, encoding="utf-8")
    return SPEC


def clean_output() -> None:
    for path in (BUILD, DIST, SPEC):
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()


def build(*, clean: bool = True) -> Path:
    ensure_pyinstaller()
    ensure_package_installed()

    if clean:
        clean_output()

    spec_path = write_spec()
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(spec_path),
            "--distpath",
            str(DIST),
            "--workpath",
            str(BUILD),
        ],
        cwd=ROOT,
    )

    system = platform.system()
    suffix = ".exe" if system == "Windows" else ""
    binary = DIST / f"{BINARY_NAME}{suffix}"
    if not binary.is_file():
        raise FileNotFoundError(f"Expected PyInstaller output at {binary}")

    return binary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build watcher standalone binary")
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Keep previous build artifacts before rebuilding",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    binary = build(clean=not args.no_clean)
    print(f"Built standalone binary: {binary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
