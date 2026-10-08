"""Folder/file browser: native picker with an in-terminal fallback.

``pick_directory`` / ``pick_file`` first try a native OS dialog (tkinter).
If tkinter isn't installed, there's no display (SSH, headless, Docker), or
the caller passes ``allow_gui=False``, they fall back to a browser that
runs entirely in the terminal.
"""

import os
import string
import sys
from pathlib import Path
from typing import List, Optional

import typer

from .converter import VIDEO_EXTENSIONS

PAGE_SIZE = 20


# --------------------------------------------------------------------------- #
# Native dialog
# --------------------------------------------------------------------------- #

def gui_available() -> bool:
    """True if a native file dialog can plausibly be shown."""
    if sys.platform.startswith("linux"):
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return False
    try:
        import tkinter  # noqa: F401
    except Exception:
        return False
    return True


def _gui_dialog(kind: str, title: str, start: Path) -> Optional[Path]:
    """Show a native dialog. Raises on failure so the caller can fall back."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    try:
        if kind == "dir":
            result = filedialog.askdirectory(
                title=title, initialdir=str(start), mustexist=False
            )
        else:
            patterns = " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTENSIONS))
            result = filedialog.askopenfilename(
                title=title,
                initialdir=str(start),
                filetypes=[("Video files", patterns), ("All files", "*.*")],
            )
    finally:
        root.destroy()
    return Path(result) if result else None


# --------------------------------------------------------------------------- #
# Terminal browser
# --------------------------------------------------------------------------- #

def _windows_drives() -> List[Path]:
    """List available drive roots on Windows."""
    try:
        import ctypes

        mask = ctypes.windll.kernel32.GetLogicalDrives()
        return [
            Path(f"{letter}:\\")
            for i, letter in enumerate(string.ascii_uppercase)
            if mask & (1 << i)
        ]
    except Exception:
        return [
            Path(f"{letter}:\\")
            for letter in string.ascii_uppercase
            if os.path.exists(f"{letter}:\\")
        ]


def _list_entries(directory: Path, select: str) -> List[Path]:
    """Sub-folders (and video files when selecting a file), folders first."""
    try:
        children = list(directory.iterdir())
    except (PermissionError, OSError):
        return []
    dirs, files = [], []
    for child in children:
        if child.name.startswith("."):
            continue
        try:
            if child.is_dir():
                dirs.append(child)
            elif select == "file" and child.suffix.lower() in VIDEO_EXTENSIONS:
                files.append(child)
        except OSError:
            continue
    key = lambda p: p.name.lower()
    return sorted(dirs, key=key) + sorted(files, key=key)


def terminal_browse(title: str, start: Path, select: str = "dir") -> Optional[Path]:
    """Browse the filesystem in the terminal.

    Args:
        title: Heading shown above the listing.
        start: Directory to start in.
        select: "dir" to choose a folder, "file" to choose a video file.

    Returns:
        The chosen path, or None if the user cancelled.
    """
    current = start if start.is_dir() else Path.home()
    try:
        current = current.resolve()
    except OSError:
        current = Path.home()
    page = 0
    show_drives = False

    while True:
        if show_drives:
            entries = _windows_drives()
            location = "Drives"
        else:
            entries = _list_entries(current, select)
            location = str(current)

        pages = max(1, -(-len(entries) // PAGE_SIZE))
        page = max(0, min(page, pages - 1))
        chunk = entries[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

        typer.secho(f"\n{title}", fg=typer.colors.CYAN, bold=True)
        typer.echo(f"Location: {location}")
        if not entries:
            typer.echo("  (nothing here)")
        for i, entry in enumerate(chunk, start=1):
            label = str(entry) if show_drives else entry.name
            suffix = "/" if (show_drives or entry.is_dir()) else ""
            typer.echo(f"  {i:>2}) {label}{suffix}")
        if pages > 1:
            typer.echo(f"  page {page + 1}/{pages}  (n = next, p = previous)")

        hints = ["number = open", ".. = up"]
        if select == "dir" and not show_drives:
            hints.append(". = choose this folder")
            hints.append("m = new folder")
        if sys.platform == "win32":
            hints.append("d = drives")
        hints += ["~ = home", "or type a path", "q = cancel"]
        typer.secho("  " + " | ".join(hints), dim=True)

        raw = typer.prompt("Select", default="", show_default=False).strip().strip('"')
        cmd = raw.lower()

        if cmd == "q":
            return None
        if cmd == "n":
            page += 1
            continue
        if cmd == "p":
            page -= 1
            continue
        if cmd == "d" and sys.platform == "win32":
            show_drives, page = True, 0
            continue
        if raw == "~":
            current, show_drives, page = Path.home(), False, 0
            continue
        if raw == ".." and not show_drives:
            parent = current.parent
            if parent == current and sys.platform == "win32":
                show_drives = True  # at a drive root: offer the drive list
            else:
                current = parent
            page = 0
            continue
        if raw == "." and select == "dir" and not show_drives:
            return current
        if cmd == "m" and select == "dir" and not show_drives:
            name = typer.prompt("New folder name").strip()
            if name:
                new_dir = current / name
                try:
                    new_dir.mkdir(parents=True, exist_ok=True)
                    current, page = new_dir, 0
                except OSError as e:
                    typer.secho(f"Couldn't create folder: {e}", fg=typer.colors.RED)
            continue

        if raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(chunk):
                chosen = chunk[index - 1]
                if show_drives or chosen.is_dir():
                    current, show_drives, page = chosen, False, 0
                else:
                    return chosen
            else:
                typer.secho("No entry with that number.", fg=typer.colors.YELLOW)
            continue

        if raw:
            typed = Path(raw).expanduser()
            if typed.is_dir():
                current, show_drives, page = typed.resolve(), False, 0
            elif typed.is_file() and select == "file":
                return typed
            else:
                typer.secho(f"Not found: {raw}", fg=typer.colors.YELLOW)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def _pick(kind: str, title: str, start: Optional[Path], allow_gui: bool) -> Optional[Path]:
    start_dir = start if start and start.is_dir() else Path.cwd()
    if allow_gui and gui_available():
        try:
            return _gui_dialog(kind, title, start_dir)
        except Exception:
            typer.secho(
                "Couldn't open a folder picker window; using the terminal browser.",
                fg=typer.colors.YELLOW,
            )
    return terminal_browse(title, start_dir, select="dir" if kind == "dir" else "file")


def pick_directory(
    title: str = "Choose a folder",
    start: Optional[Path] = None,
    allow_gui: bool = True,
) -> Optional[Path]:
    """Let the user choose a folder. Returns None if cancelled."""
    return _pick("dir", title, start, allow_gui)


def pick_file(
    title: str = "Choose a video file",
    start: Optional[Path] = None,
    allow_gui: bool = True,
) -> Optional[Path]:
    """Let the user choose a video file. Returns None if cancelled."""
    return _pick("file", title, start, allow_gui)
