"""Discover a Windows cursor pack and map its files to X11 cursor roles.

A "pack" is usually a folder full of ``.ani``/``.cur`` files plus an
``install.inf`` that names the Windows cursor slots.  Packs are inconsistent:

* some ship a proper ``[Strings]`` section (``pointer = "Normal.ani"``),
* some only have numbered files (``01-Normal.ani``, ``13-Diagonal Resize 1.ani``),
* some use ``.cur`` instead of ``.ani`` (static pack),
* a few contain *both* (``Windows/`` animated + ``Static/`` still).

:func:`load_pack` normalises all of that into a ``canonical -> file`` map.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import roles

CURSOR_SUFFIXES = (".ani", ".cur", ".ico")
INF_NAMES = ("install.inf", "installer.inf", "cursor.inf", "install.inf.txt")

# INF keys / filename stems that mean "real open palm" rather than the
# pointing "link" hand.  Packs rarely ship one.
PALM_KEYS = {"openhand", "handopen", "palm", "hand1"}


class PackError(Exception):
    """Raised when a folder cannot be interpreted as a cursor pack."""


@dataclass
class Pack:
    name: str
    directory: Path
    mapping: Dict[str, Path]                 # canonical role -> source file
    unmapped: List[Path] = field(default_factory=list)
    source: str = "guess"                    # "inf" | "guess" | "single"

    @property
    def roles_found(self) -> List[str]:
        return sorted(self.mapping)


# --- INF parsing -------------------------------------------------------------

def parse_inf(text: str) -> Dict[str, Dict[str, str]]:
    """Very small ``.inf`` reader -> ``{section: {key: value}}``."""
    sections: Dict[str, Dict[str, str]] = {}
    section: Optional[str] = None
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            sections.setdefault(section, {})
            continue
        if section is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        sections[section][key.strip().lower()] = _unquote(value)
    return sections


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value.strip()


def find_inf(directory: Path) -> Optional[Path]:
    try:
        children = list(directory.iterdir())
    except OSError:
        return None
    for child in children:
        if child.is_file() and child.name.lower() in INF_NAMES:
            return child
    return None


def _resolve_file(directory: Path, name: str) -> Optional[Path]:
    name = name.replace("\\", "/").split("/")[-1].strip()
    if not name:
        return None
    direct = directory / name
    if direct.is_file():
        return direct
    low = name.lower()
    for child in directory.iterdir():
        if child.is_file() and child.name.lower() == low:
            return child
    for sub in directory.iterdir():
        if sub.is_dir():
            for child in sub.iterdir():
                if child.is_file() and child.name.lower() == low:
                    return child
    return None


# --- discovery ---------------------------------------------------------------

def _count_cursors(directory: Path) -> Tuple[int, int]:
    ani = cur = 0
    try:
        children = list(directory.iterdir())
    except OSError:
        return 0, 0
    for p in children:
        if p.is_file():
            suffix = p.suffix.lower()
            if suffix == ".ani":
                ani += 1
            elif suffix in (".cur", ".ico"):
                cur += 1
    return ani, cur


def choose_directory(root: Path) -> Path:
    """Pick the folder that actually holds the cursor files.

    Prefers the directory with animated cursors, then falls back to static
    ones.  Refuses to guess when several sibling folders look equally valid.
    """
    if _count_cursors(root) != (0, 0):
        return root
    candidates = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            ani, cur = _count_cursors(child)
            if ani or cur:
                candidates.append((ani * 3 + cur, ani, str(child), child))
    if not candidates:
        raise PackError(f"no .ani/.cur/.ico files found under {root}")
    candidates.sort(key=lambda t: (-t[0], -t[1], t[2]))
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        names = ", ".join(t[2] for t in candidates)
        raise PackError(
            f"{root} contains several cursor folders ({names}); "
            "point at the one you want"
        )
    return candidates[0][3]


def collect_cursor_files(directory: Path) -> List[Path]:
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in CURSOR_SUFFIXES
    )


def _normalise_key(text: str) -> str:
    return re.sub(r"[\s_\-]", "", text.strip().lower())


def find_palm_source(directory: Path, files: List[Path],
                     strings: Dict[str, str]) -> Optional[Path]:
    """Return the pack's open-hand/palm image, if it ships one.

    Looks at the INF ``[Strings]`` values first (so a pack can declare
    ``openhand = Palm.ani``), then at bare filenames.
    """
    for key, value in strings.items():
        if _normalise_key(key) in PALM_KEYS:
            resolved = _resolve_file(directory, value)
            if resolved is not None:
                return resolved
    for path in files:
        if _normalise_key(path.stem) in PALM_KEYS:
            return path
    return None


def build_mapping(directory: Path) -> Tuple[Dict[str, Path], List[Path], Optional[str]]:
    """Return ``(canonical -> file, unmapped files, scheme name)``."""
    mapping: Dict[str, Path] = {}
    files = collect_cursor_files(directory)
    scheme: Optional[str] = None
    strings: Dict[str, str] = {}

    inf = find_inf(directory)
    if inf:
        sections = parse_inf(inf.read_text(errors="replace"))
        strings = sections.get("strings", {})
        scheme = strings.get("scheme_name") or None
        for key, value in strings.items():
            canonical = roles.normalize_role(key)
            if not canonical:
                continue
            resolved = _resolve_file(directory, value)
            if resolved is not None:
                mapping.setdefault(canonical, resolved)

    # Fill whatever the INF did not cover by guessing from file names.
    used = set(mapping.values())
    for path in files:
        if path in used:
            continue
        canonical = roles.infer_role(path.name)
        if canonical and canonical not in mapping:
            mapping[canonical] = path
            used.add(path)

    # The Move slot (fleur) should be an open palm when the pack ships one.
    # Windows packs almost never do, so keep the pack's 4-corner move arrow as
    # the fallback.  This never touches hand2/link, which keeps the pack's own
    # pointing hand.
    palm = find_palm_source(directory, files, strings)
    if palm is not None:
        mapping["fleur"] = palm

    used = set(mapping.values())
    unmapped = [p for p in files if p not in used]
    return mapping, unmapped, scheme


def clean_name(name: str) -> str:
    """Make a friendly, filesystem/theme-safe theme name."""
    name = _unquote(name or "")
    name = re.sub(r"\s*ver\.?\s*[\d.]+.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", name)
    name = re.sub(r"\s+", " ", name).strip(" -_.")
    return name or "cursor-theme"


def load_pack(path, name: Optional[str] = None) -> Pack:
    """Build a :class:`Pack` from a directory or a single cursor file."""
    path = Path(path).expanduser()
    if not path.exists():
        raise PackError(f"no such file or directory: {path}")
    path = path.resolve()

    if path.is_file():
        canonical = roles.infer_role(path.name) or "left_ptr"
        return Pack(
            name=name or clean_name(path.stem),
            directory=path.parent,
            mapping={canonical: path},
            unmapped=[],
            source="single",
        )

    directory = choose_directory(path)
    mapping, unmapped, scheme = build_mapping(directory)
    if not mapping:
        raise PackError(f"could not map any cursor roles in {directory}")
    return Pack(
        name=name or clean_name(scheme or directory.name),
        directory=directory,
        mapping=mapping,
        unmapped=unmapped,
        source="inf" if find_inf(directory) else "guess",
    )
