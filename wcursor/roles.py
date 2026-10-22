"""Windows cursor roles -> X11 cursor names, plus the standard alias table.

A Windows cursor *scheme* names its cursors after the slots in
``Control Panel\\Cursors`` (``Arrow``, ``Wait``, ``SizeNWSE`` ...).  A Linux
Xcursor theme instead ships a set of *canonical* files (``left_ptr``,
``watch``, ``bd_double_arrow`` ...) and then creates symlinks so that every
known alias resolves to one of them.

This module holds that knowledge in one place:

* :data:`CANONICAL`      - canonical Xcursor file names this tool generates.
* :data:`WINDOWS_ROLES`  - INF ``[Strings]`` key (and common variants) -> canonical.
* :data:`ALIASES`        - canonical -> list of alias names to symlink.
* :func:`normalize_role` - normalise an INF key and look it up.
* :func:`infer_role`     - guess a role from a bare filename.
"""

from __future__ import annotations

import os
import re

# --- canonical cursors -------------------------------------------------------
# The 17 cursors every Windows scheme covers (the ones with a real bitmap).
CANONICAL = [
    "left_ptr",           # Arrow / Normal select
    "help",               # Help select
    "left_ptr_watch",     # Working in background / AppStarting
    "watch",              # Busy / Wait
    "crosshair",          # Precision select
    "xterm",              # Text select
    "pencil",             # Handwriting / NWPen
    "not-allowed",        # Unavailable / No
    "sb_v_double_arrow",  # Vertical resize
    "sb_h_double_arrow",  # Horizontal resize
    "bd_double_arrow",    # Diagonal resize 1 (NW-SE)
    "fd_double_arrow",    # Diagonal resize 2 (NE-SW)
    "fleur",              # Move / Size all
    "center_ptr",         # Alternate select / Up arrow
    "hand2",              # Link select
    "pin",                # Location select
    "person",             # Person select
]

# --- INF [Strings] key -> canonical -----------------------------------------
# Packs are inconsistent ("work" vs "working", "cross" vs "precision",
# "unavailiable" [sic] vs "unavailable"), so every variant is accepted.
WINDOWS_ROLES = {
    # pointer / arrow
    "pointer": "left_ptr",
    "normal": "left_ptr",
    "arrow": "left_ptr",
    "default": "left_ptr",
    # help
    "help": "help",
    "question": "help",
    # working in background
    "work": "left_ptr_watch",
    "working": "left_ptr_watch",
    "progress": "left_ptr_watch",
    "appstarting": "left_ptr_watch",
    # busy / wait
    "busy": "watch",
    "wait": "watch",
    # precision
    "cross": "crosshair",
    "precision": "crosshair",
    "precisionhair": "crosshair",
    # text
    "text": "xterm",
    "ibeam": "xterm",
    # handwriting
    "hand": "pencil",
    "handwriting": "pencil",
    "nwpen": "pencil",
    # unavailable
    "unavailable": "not-allowed",
    "unavailiable": "not-allowed",  # common typo in the wild
    "unavail": "not-allowed",
    "no": "not-allowed",
    # vertical resize
    "vert": "sb_v_double_arrow",
    "vertical": "sb_v_double_arrow",
    "ns": "sb_v_double_arrow",
    "sizens": "sb_v_double_arrow",
    # horizontal resize
    "horz": "sb_h_double_arrow",
    "horizontal": "sb_h_double_arrow",
    "ew": "sb_h_double_arrow",
    "sizewe": "sb_h_double_arrow",
    # diagonal resize 1 (NW-SE)
    "dgn1": "bd_double_arrow",
    "diagonal1": "bd_double_arrow",
    "nwse": "bd_double_arrow",
    "sizenwse": "bd_double_arrow",
    # diagonal resize 2 (NE-SW)
    "dgn2": "fd_double_arrow",
    "diagonal2": "fd_double_arrow",
    "nesw": "fd_double_arrow",
    "sizenesw": "fd_double_arrow",
    # move / size all
    "move": "fleur",
    "sizeall": "fleur",
    "all": "fleur",
    # alternate / up arrow
    "alternate": "center_ptr",
    "alt": "center_ptr",
    "up": "center_ptr",
    "uparrow": "center_ptr",
    # link select
    "link": "hand2",
    "pointinghand": "hand2",
    # location / pin select
    "pin": "pin",
    "location": "pin",
    # person select
    "person": "person",
}

# --- canonical -> aliases ----------------------------------------------------
# The classic X11 "cursorList" table.  Kept identical to what mainstream
# Linux themes (and ani2xcursor) create so applications find their cursor.
ALIASES = {
    "left_ptr": ["default", "arrow", "top_left_arrow"],
    "help": ["question_arrow", "whats_this", "d9ce0ab605698f320427677b458ad60b"],
    "left_ptr_watch": [
        "progress",
        "half-busy",
        "00000000000000020006000e7e9ffc3f",
        "3ecb610c1bf2410f44200f48c40d3599",
        "08e8e1c95fe2fc01f976f1e063a24ccd",
    ],
    "watch": ["wait", "clock", "0426c94ea35c87780ff01dc239897213"],
    "crosshair": ["cross", "cross_reverse", "tcross", "diamond_cross"],
    "xterm": ["ibeam", "text"],
    "pencil": ["handwriting"],
    "not-allowed": [
        "no-drop",
        "crossed_circle",
        "forbidden",
        "03b6e0fcb3499374a867c041f52298f0",
        "circle",
    ],
    "sb_v_double_arrow": [
        "ns-resize",
        "size_ver",
        "v_double_arrow",
        "row-resize",
        "n-resize",
        "s-resize",
        "00008160000006810000408080010102",
        "split_v",
        "top_side",
        "bottom_side",
    ],
    "sb_h_double_arrow": [
        "ew-resize",
        "size_hor",
        "h_double_arrow",
        "col-resize",
        "e-resize",
        "w-resize",
        "028006030e0e7ebffc7f7070c0600140",
        "split_h",
        "left_side",
        "right_side",
    ],
    "bd_double_arrow": [
        "nwse-resize",
        "size_fdiag",
        "nw-resize",
        "se-resize",
        "c7088f0f3e6c8088236ef8e1e3e70000",
        "top_left_corner",
        "bottom_right_corner",
    ],
    "fd_double_arrow": [
        "nesw-resize",
        "size_bdiag",
        "ne-resize",
        "sw-resize",
        "fcf1c3c7cd4491d801f1e1c78f100000",
        "top_right_corner",
        "bottom_left_corner",
    ],
    "fleur": [
        "move",
        "size_all",
        "all-scroll",
        "grab",
        "grabbing",
        "closedhand",
        "hand1",
        "openhand",
        "4498f0e0c1937ffe01fd06f973665830",
        "9081237383d90e509aa00f00170e968f",
    ],
    "center_ptr": ["up-arrow", "up_arrow"],
    "hand2": [
        "hand",
        "pointer",
        "pointing_hand",
        "e29285e634086352946a0e7090d73106",
        "9d800788f1b08800ae810202380a0822",
    ],
    "pin": [],
    "person": [],
}


def normalize_role(role: str) -> str | None:
    """Map an INF ``[Strings]`` key (any common spelling) to a canonical name."""
    key = re.sub(r"[\s_\-]", "", role.strip().lower())
    return WINDOWS_ROLES.get(key)


# Ordered filename heuristics - most specific patterns first.
_FILENAME_PATTERNS = [
    (r"dgn\s*1|diagonal\s*resize\s*1|diagonal1|nwse", "bd_double_arrow"),
    (r"dgn\s*2|diagonal\s*resize\s*2|diagonal2|nesw", "fd_double_arrow"),
    (r"vert|size\s*ns|ns[-_ ]?resize", "sb_v_double_arrow"),
    (r"horz|size\s*we|ew[-_ ]?resize", "sb_h_double_arrow"),
    (r"precision|cross", "crosshair"),
    (r"\btext\b|ibeam|i[-_ ]?beam", "xterm"),
    (r"handwriting|nwpen", "pencil"),
    (r"unavail", "not-allowed"),
    (r"person", "person"),
    (r"location|\bpin\b", "pin"),
    (r"link|point", "hand2"),
    (r"\bhand\b", "pencil"),
    (r"\bmove\b|size\s*all|fleur", "fleur"),
    (r"alternate|\balt\b|\bup\b|uparrow", "center_ptr"),
    (r"help|question", "help"),
    (r"busy|\bwait\b", "watch"),
    (r"working|\bwork\b|loading|progress|appstarting", "left_ptr_watch"),
    (r"normal|arrow|pointer|select", "left_ptr"),
]


def infer_role(filename: str) -> str | None:
    """Best-effort canonical role guess from a bare filename.

    Handles names like ``08-Unavailable.ani``, ``Frieren busy.ani`` or
    ``13-Diagonal Resize 1.ani``.  Returns ``None`` when nothing matches.
    """
    stem = os.path.splitext(os.path.basename(filename))[0].lower()
    stem = re.sub(r"^\d+[\s._-]*", "", stem)  # drop leading "01-"
    for pattern, canonical in _FILENAME_PATTERNS:
        if re.search(pattern, stem):
            return canonical
    return None


def aliases_for(canonical: str) -> list[str]:
    return list(ALIASES.get(canonical, []))


def all_alias_names() -> set[str]:
    names: set[str] = set()
    for aliases in ALIASES.values():
        names.update(aliases)
    return names
