"""Install, list and remove Xcursor themes in the user's icon directory."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from . import theme as theme_mod
from . import xcursor


class InstallError(Exception):
    """Raised when a theme cannot be installed/uninstalled."""


@dataclass
class ThemeInfo:
    name: str
    path: Path
    sizes: List[int]
    animated: bool

    @property
    def size_range(self) -> str:
        if not self.sizes:
            return "-"
        return f"{self.sizes[0]}-{self.sizes[-1]}" if len(self.sizes) > 1 else str(self.sizes[0])


def icons_dir() -> Path:
    """``$XDG_DATA_HOME/icons`` (``~/.local/share/icons`` by default)."""
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(Path.home(), ".local", "share")
    return Path(base) / "icons"


def theme_path(name: str) -> Path:
    return icons_dir() / name


def is_theme(path) -> bool:
    """True when ``path`` looks like an installable Xcursor theme."""
    cursors = Path(path) / "cursors"
    if not cursors.is_dir():
        return False
    return any(p.is_file() for p in cursors.iterdir())


def _is_animated(theme_dir: Path) -> bool:
    cursors = Path(theme_dir) / "cursors"
    for name in ("left_ptr", "watch", "normal", "default"):
        p = cursors / name
        if p.is_file():
            try:
                return any(im.delay > 0 for im in xcursor.read(p))
            except xcursor.XcursorError:
                continue
    return False


def info(name: str) -> ThemeInfo:
    path = theme_path(name)
    if not is_theme(path):
        raise InstallError(f"not an installed cursor theme: {name}")
    return ThemeInfo(
        name=name,
        path=path,
        sizes=theme_mod.read_theme_sizes(path),
        animated=_is_animated(path),
    )


def list_installed() -> List[ThemeInfo]:
    directory = icons_dir()
    if not directory.is_dir():
        return []
    found = []
    for child in sorted(directory.iterdir()):
        if child.is_dir() and is_theme(child):
            found.append(
                ThemeInfo(
                    name=child.name,
                    path=child,
                    sizes=theme_mod.read_theme_sizes(child),
                    animated=_is_animated(child),
                )
            )
    return found


def install(src_dir, name: str, *, force: bool = True, dry_run: bool = False) -> Path:
    """Copy a built theme into the icon directory as ``name``."""
    src = Path(src_dir)
    if not is_theme(src):
        raise InstallError(f"{src} is not a cursor theme (no cursors/ directory)")
    dest = theme_path(name)
    if dest.exists() and not force:
        raise InstallError(f"{dest} already exists (pass --force to replace)")
    if dry_run:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, symlinks=True)
    _refresh_cache(dest)
    return dest


def uninstall(name: str, *, dry_run: bool = False) -> Path:
    dest = theme_path(name)
    if not dest.is_dir():
        raise InstallError(f"theme not installed: {name}")
    if not dry_run:
        shutil.rmtree(dest)
    return dest


def _refresh_cache(dest: Path) -> None:
    exe = shutil.which("gtk-update-icon-cache")
    if not exe:
        return
    try:
        subprocess.run(
            [exe, "-q", "-f", "-t", str(dest)],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        pass
