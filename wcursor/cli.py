"""Command line interface for ``wcursor``.

Examples::

    wcursor convert ~/Downloads/"Frieren Cursor" -o ./Frieren
    wcursor install ~/Downloads/"Cursor 1" --name Frieren --sizes 24,32,48,64 --apply --size 64
    wcursor upscale Frieren --sizes 96
    wcursor list
    wcursor set Frieren --size 64
    wcursor current
    wcursor doctor
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from . import __version__, apply, install, pack, roles, theme, xcursor
from .icons import CursorFormatError

ACTIVE_MARK = "*"


# --- shared helpers ----------------------------------------------------------

def _current_size(default: int = 32) -> int:
    for location in apply.current():
        if location.name.startswith("dms") and location.size:
            return int(location.size)
    return default


def _active_theme() -> str | None:
    for location in apply.current():
        if location.name == "dms (settings.json)":
            return location.theme
    return None


def _print_built(built, verbose: bool) -> None:
    if not verbose:
        return
    for name in sorted(built):
        info = built[name]
        print(f"  {name:<18} {info.native}px x{info.frames}  ->  {info.sizes}")


def _resolve_source(args) -> pack.Pack:
    return pack.load_pack(args.src, name=getattr(args, "name", None))


def _apply_now(theme_name: str, size: int | None, args) -> int:
    size = int(size or _current_size())
    flags = dict(
        dms=not getattr(args, "no_dms", False),
        xresources=not getattr(args, "no_xresources", False),
        icons_default=not getattr(args, "no_icons_default", False),
        gtk=not getattr(args, "no_gtk", False),
        gsettings=not getattr(args, "no_gsettings", False),
        niri=not getattr(args, "no_niri", False),
        dry_run=getattr(args, "dry_run", False),
    )
    if not install.is_theme(install.theme_path(theme_name)) and not flags["dry_run"]:
        print(f"error: cursor theme {theme_name!r} is not installed", file=sys.stderr)
        return 1
    available = theme.read_theme_sizes(install.theme_path(theme_name))
    if available and size not in available:
        print(f"note: {theme_name} has no {size}px bitmap (available: {available}); "
              "the compositor will scale", file=sys.stderr)
    print(f"{'would set' if flags['dry_run'] else 'setting'} cursor to {theme_name} / {size}px")
    for step in apply.apply_cursor(theme_name, size, **flags):
        print(f"  {step}")
    return 0


# --- commands ----------------------------------------------------------------

def cmd_convert(args) -> int:
    source = _resolve_source(args)
    out = Path(args.output).expanduser() if args.output else Path(source.name)
    sizes = theme.parse_sizes(args.sizes)
    built = theme.build(source, out, sizes=sizes, method=args.method,
                        name=source.name, verbose=False)
    print(f"converted {source.directory} -> {out}  ({len(built)} cursors, {source.source})")
    _print_built(built, not args.quiet)
    if source.unmapped and not args.quiet:
        print(f"  unmapped files: {', '.join(p.name for p in source.unmapped)}")
    return 0


def cmd_install(args) -> int:
    source = _resolve_source(args)
    sizes = theme.parse_sizes(args.sizes)
    name = source.name
    if args.dry_run:
        print(f"would install {name!r} from {source.directory} "
              f"(sizes: {sizes or list(theme.DEFAULT_LADDER)})")
        return _apply_now(name, args.size, args) if args.apply else 0

    with tempfile.TemporaryDirectory(prefix="wcursor-") as tmp:
        built = theme.build(source, tmp, sizes=sizes, method=args.method,
                            name=name, verbose=False)
        dest = install.install(tmp, name, force=True)
    print(f"installed {name!r} ({len(built)} cursors) -> {dest}")
    _print_built(built, not args.quiet)
    if args.apply:
        return _apply_now(name, args.size, args)
    return 0


def cmd_upscale(args) -> int:
    theme_dir = install.theme_path(args.theme)
    if not install.is_theme(theme_dir):
        print(f"error: cursor theme {args.theme!r} is not installed", file=sys.stderr)
        return 1
    sizes = theme.parse_sizes(args.sizes) or []
    before = theme.read_theme_sizes(theme_dir)
    result = theme.add_sizes(
        theme_dir, sizes, method=args.method,
        from_size=args.from_size, dry_run=args.dry_run, verbose=not args.quiet,
    )
    added = sorted(set(theme.read_theme_sizes(theme_dir) if not args.dry_run
                       else _union(result.values())) - set(before))
    verb = "would add" if args.dry_run else "added"
    print(f"{verb} sizes {added or '[]'} to {args.theme} ({len(result)} files); "
          f"now: {theme.read_theme_sizes(theme_dir) if not args.dry_run else sorted(set(before) | set(added))}")
    if args.apply:
        return _apply_now(args.theme, args.size, args)
    return 0


def _union(values) -> set:
    out: set = set()
    for v in values:
        out.update(v)
    return out


def cmd_list(args) -> int:
    themes = install.list_installed()
    if not themes:
        print(f"no cursor themes in {install.icons_dir()}")
        return 0
    active = _active_theme()
    width = max(len(t.name) for t in themes)
    for t in themes:
        mark = ACTIVE_MARK if t.name == active else " "
        kind = "animated" if t.animated else "static"
        print(f"{mark} {t.name:<{width}}  {kind:<8}  sizes: {', '.join(map(str, t.sizes)) or '-'}")
    return 0


def cmd_info(args) -> int:
    target = args.target
    theme_dir = install.theme_path(target)
    if install.is_theme(theme_dir):
        info = install.info(target)
        print(f"theme:    {info.name}")
        print(f"path:     {info.path}")
        print(f"type:     {'animated' if info.animated else 'static'}")
        print(f"sizes:    {', '.join(map(str, info.sizes)) or '-'}")
        return 0

    path = Path(target).expanduser()
    if not path.exists():
        print(f"error: {target!r} is neither an installed theme nor an existing path",
              file=sys.stderr)
        return 1
    source = pack.load_pack(path)
    print(f"pack:     {source.name!r}")
    print(f"folder:   {source.directory}")
    print(f"roles via {source.source}")
    print(f"mapped:   {len(source.mapping)}/{len(roles.CANONICAL)} canonical cursors")
    for canonical in roles.CANONICAL:
        src = source.mapping.get(canonical)
        print(f"  {canonical:<18} {src.name if src else '-'}")
    if source.unmapped:
        print("unmapped files:")
        for p in source.unmapped:
            print(f"  {p.name}")
    return 0


def cmd_uninstall(args) -> int:
    dest = install.uninstall(args.theme, dry_run=args.dry_run)
    verb = "would remove" if args.dry_run else "removed"
    print(f"{verb} {dest}")
    return 0


def cmd_set(args) -> int:
    if not install.is_theme(install.theme_path(args.theme)) and not args.dry_run:
        print(f"error: cursor theme {args.theme!r} is not installed "
              f"(see `wcursor list`)", file=sys.stderr)
        return 1
    return _apply_now(args.theme, args.size, args)


def cmd_current(args) -> int:
    locations = apply.current()
    resolved = None
    for location in locations:
        if location.name == "dms (settings.json)" and location.theme:
            resolved = (location.theme, location.size)
    width = max(len(l.name) for l in locations)
    for location in locations:
        size = location.size if location.size is not None else "-"
        print(f"  {location.name:<{width}}  {str(location.theme or '-'):<20} {size}")
        if resolved and location.theme and location.theme != resolved[0]:
            print(f"  {' ' * width}  ^ does not match {resolved[0]!r}")
    if resolved:
        print(f"\nactive: {resolved[0]} / {resolved[1]}px")
    return 0


def cmd_doctor(args) -> int:
    import shutil

    ok = True

    def check(label: str, condition: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and condition
        print(f"  [{'ok' if condition else '!!'}] {label}" + (f"  {detail}" if detail else ""))

    print("wcursor doctor")
    check("python >= 3.9", sys.version_info >= (3, 9), sys.version.split()[0])
    icons = install.icons_dir()
    check("icons directory", icons.is_dir() or True, str(icons))
    check("icons directory writable", _writable(icons))
    installed = install.list_installed()
    check("installed cursor themes", bool(installed), f"{len(installed)} found")
    check("dms binary", shutil.which("dms") is not None,
          str(shutil.which("dms") or "missing"))
    check("dms running", apply.dms_running())
    check("niri binary", shutil.which("niri") is not None,
          str(shutil.which("niri") or "missing"))
    check("gsettings", shutil.which("gsettings") is not None)
    check("mutable DMS settings", apply.DMS_SETTINGS.exists(), str(apply.DMS_SETTINGS))
    check("mutable niri cursor.kdl", apply.DMS_CURSOR_KDL.parent.exists(),
          str(apply.DMS_CURSOR_KDL.parent))

    print("\ncurrent cursor state")
    for location in apply.current():
        size = location.size if location.size is not None else "-"
        print(f"  {location.name:<20} {str(location.theme or '-'):<20} {size}")
    return 0 if ok else 1


def _writable(path: Path) -> bool:
    import os

    probe = path if path.is_dir() else path.parent
    return os.access(probe, os.W_OK)


# --- parser ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wcursor",
        description="Convert, upscale, install and switch Windows cursors on Linux.",
    )
    parser.add_argument("--version", action="version", version=f"wcursor {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument("--name", help="override the theme name")
        p.add_argument("--sizes", help="comma separated sizes, e.g. 24,32,48,64")
        p.add_argument("--method", choices=["auto", "nearest", "pixel", "smooth"],
                       default="auto", help="resampling method (default: auto)")
        p.add_argument("-q", "--quiet", action="store_true")

    def add_apply_flags(p):
        p.add_argument("--apply", action="store_true", help="also switch to the theme")
        p.add_argument("--size", type=int, help="cursor size to apply (px)")
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--no-dms", action="store_true", help="leave DMS settings alone")
        p.add_argument("--no-xresources", action="store_true")
        p.add_argument("--no-icons-default", action="store_true")
        p.add_argument("--no-gtk", action="store_true")
        p.add_argument("--no-gsettings", action="store_true")
        p.add_argument("--no-niri", action="store_true")

    p_convert = sub.add_parser("convert", help="convert a Windows pack into a theme directory")
    p_convert.add_argument("src", help="pack folder, or a single .ani/.cur/.ico file")
    p_convert.add_argument("-o", "--output", help="output theme directory")
    add_common(p_convert)
    p_convert.set_defaults(func=cmd_convert)

    p_install = sub.add_parser("install", help="convert and install a Windows pack")
    p_install.add_argument("src")
    add_common(p_install)
    add_apply_flags(p_install)
    p_install.set_defaults(func=cmd_install)

    p_upscale = sub.add_parser("upscale", help="add extra sizes to an installed theme")
    p_upscale.add_argument("theme")
    p_upscale.add_argument("--sizes", required=True, help="sizes to add, e.g. 48,96")
    p_upscale.add_argument("--from", dest="from_size", type=int,
                           help="explicit source size to rescale from")
    p_upscale.add_argument("--method", choices=["auto", "nearest", "pixel", "smooth"],
                           default="auto")
    p_upscale.add_argument("-q", "--quiet", action="store_true")
    add_apply_flags(p_upscale)
    p_upscale.set_defaults(func=cmd_upscale)

    p_list = sub.add_parser("list", help="list installed cursor themes")
    p_list.set_defaults(func=cmd_list)

    p_info = sub.add_parser("info", help="show an installed theme, or inspect a pack")
    p_info.add_argument("target", help="installed theme name, or a path to a pack")
    p_info.set_defaults(func=cmd_info)

    p_uninstall = sub.add_parser("uninstall", help="remove an installed theme")
    p_uninstall.add_argument("theme")
    p_uninstall.add_argument("--dry-run", action="store_true")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_set = sub.add_parser("set", aliases=["use"], help="switch cursor theme/size system-wide")
    p_set.add_argument("theme")
    add_apply_flags(p_set)
    p_set.set_defaults(func=cmd_set)

    p_current = sub.add_parser("current", help="show where the cursor is configured")
    p_current.set_defaults(func=cmd_current)

    p_doctor = sub.add_parser("doctor", help="diagnose the environment")
    p_doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (pack.PackError, theme.ThemeError, install.InstallError,
            xcursor.XcursorError, CursorFormatError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
