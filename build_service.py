#!/usr/bin/env python3

from __future__ import annotations
import os
import sys
import shutil
import subprocess
import site
import importlib
from pathlib import Path
import glob
import json

# ---------- CONFIG ----------
SCRIPT_NAME = "edge_tts_service.py"
EXE_NAME = "edge_tts_service"
ONEFILE = True
CONSOLE = True

HIDDEN_IMPORTS = [
    "edge_tts",
    "edge_tts.communicate",
    "edge_tts.list_voices",
    "websockets",
    "asyncio",
]

DATA_FILES = []
# ---------- END CONFIG ----------


def ensure_package(pkg: str):
    try:
        importlib.import_module(pkg)
        return True
    except Exception:
        return False


def pip_install(packages):
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + packages
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)


def find_pywin32_binaries():
    """
    Returns list of (src, dest) pairs suitable for PyInstaller --add-binary
    For pywin32 we need to include pywintypesXX.dll and pythoncomXX.dll
    (the exact filenames vary by Python version).
    """
    pairs = []
    try:
        import pywintypes  # type: ignore
        import pythoncom  # type: ignore
        # pywintypes.__file__ gives a .pyd path; find sibling DLLs in same folder
        pyw_path = Path(pywintypes.__file__).resolve().parent
        pythoncom_path = Path(pythoncom.__file__).resolve().parent

        # Typical DLL names: pywintypes39.dll / pythoncom39.dll or with cp311 tags.
        # Use glob to find the matching DLLs in the parent dirs.
        candidates = []
        for folder in {pyw_path, pythoncom_path, Path(sys.base_prefix) / "Lib" / "site-packages"}:
            for name in ("pywintypes*.dll", "pythoncom*.dll"):
                candidates.extend(glob.glob(str(folder / name)))

        # Deduplicate and create pairs ("src;dest")
        unique = sorted(set(candidates))
        for src in unique:
            src_path = Path(src)
            # destination inside exe: use '.' to place in root next to exe
            pairs.append((str(src_path), "."))

    except Exception as e:
        print("Warning: cannot detect pywin32 binaries automatically:", e)

    return pairs


def build():
    if not ensure_package("PyInstaller"):
        print("PyInstaller not found; installing it...")
        pip_install(["pyinstaller"])

    required_build = []
    for pkg in ("websockets", "edge_tts"):
        if not ensure_package(pkg):
            required_build.append(pkg)

    if required_build:
        print("Installing missing runtime requirements for packaging:", required_build)
        pip_install(required_build)

    add_binary_pairs = find_pywin32_binaries()
    if add_binary_pairs:
        print("Detected pywin32 binaries to bundle:")
        for src, dest in add_binary_pairs:
            print("  ", src, "->", dest)
    else:
        print("No pywin32 DLLs detected automatically. PyInstaller may still work, but if it fails,")
        print("you may need to add the pywintypes/pythoncom DLLs manually using --add-binary.")

    pyinstaller_args = [SCRIPT_NAME]

    if ONEFILE:
        pyinstaller_args.append("--onefile")
    else:
        pyinstaller_args.append("--onedir")

    if CONSOLE:
        pyinstaller_args.append("--console")
    else:
        pyinstaller_args.append("--noconsole")

    pyinstaller_args += ["--name", EXE_NAME, "--clean", "--log-level=INFO"]

    for h in HIDDEN_IMPORTS:
        pyinstaller_args += ["--hidden-import", h]

    for src, dest in add_binary_pairs:
        # PyInstaller expects "SRC;DEST"
        pair = f"{src};{dest}"
        pyinstaller_args += ["--add-binary", pair]

    for src, dest in DATA_FILES:
        pyinstaller_args += ["--add-data", f"{src};{dest}"]

    print("\nPyInstaller args:", pyinstaller_args)

    import PyInstaller.__main__ as pyi_main  # type: ignore

    try:
        pyi_main.run(pyinstaller_args)
    except Exception as e:
        print("PyInstaller failed:", e)
        raise

    dist_path = Path("dist") / f"{EXE_NAME}.exe" if ONEFILE else Path("dist") / EXE_NAME
    print("\nBuild complete!")
    print("Executable:", dist_path.resolve())
    return dist_path.resolve()


if __name__ == "__main__":
    print("Building", SCRIPT_NAME, "into single exe", EXE_NAME)
    # Sanity check: script exists
    if not Path(SCRIPT_NAME).exists():
        print(f"Error: {SCRIPT_NAME} not found in current directory: {Path.cwd()}")
        sys.exit(2)

    try:
        exe = build()
    except Exception as exc:
        print("Build failed:", exc)
        sys.exit(1)
    print("Done.")
