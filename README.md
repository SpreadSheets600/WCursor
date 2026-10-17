# wcursor

Convert Windows cursor packs (`.ani` animated / `.cur` static / `.ico`) into
**Linux Xcursor themes**, install them, add extra sizes, and switch the theme +
size system-wide — in one tool, with no external dependencies.

Windows cursor packs are almost always 32px pixel art. Dragging them up to the
sizes modern desktops like (48px, 64px, 96px) normally produces either a blurry
smear or uneven "torn" pixels. `wcursor` is careful about *how* it rescales so
the result stays sharp:

| Target | Method | Why |
| ------ | ------ | --- |
| exact multiple (32 → 64) | nearest-neighbour | pixel-perfect, no blur |
| fractional (32 → 48, 96) | supersample: nearest to an integer multiple, then area-average down | crisp edges without uneven pixel doubling |
| downscale (32 → 24) | area average | clean, no aliasing |

All bitmaps are written with correctly **premultiplied ARGB**, which is what the
X cursor library expects.

## Install

```bash
cd ~/Projects/wcursor
pip install -e .            # provides the `wcursor` command
# or run it without installing:
python3 -m wcursor --help
```

Requires Python 3.9+ and nothing else.

## Quick start

```bash
# 1. See what a pack contains (roles are read from install.inf, then filenames):
wcursor info ~/Downloads/"Frieren Cursor"

# 2. Convert + install it, and switch to it at 64px:
wcursor install ~/Downloads/"Frieren Cursor" --name Frieren --apply --size 64

# 3. Later, add a bigger size to the installed theme:
wcursor upscale Frieren --sizes 96
wcursor set Frieren --size 96
```

## Commands

| Command | Purpose |
| ------- | ------- |
| `wcursor convert SRC [-o DIR] [--sizes ..] [--method ..]` | build a theme directory, no install |
| `wcursor install SRC [--name N] [--sizes ..] [--apply --size N]` | convert **and** install under `~/.local/share/icons` |
| `wcursor upscale THEME --sizes 48,96 [--from N]` | add missing sizes to an installed theme |
| `wcursor list` | installed cursor themes (marks the active one) |
| `wcursor info TARGET` | theme details, or a pack's role mapping |
| `wcursor uninstall THEME` | remove an installed theme |
| `wcursor set THEME [--size N]` (alias `use`) | apply theme + size everywhere |
| `wcursor current` | show where the cursor is configured, and flag mismatches |
| `wcursor doctor` | environment diagnostics |

Global options: `--sizes 24,32,48,64` (default ladder is 24/32/48/64 + the
native size), `--method auto|nearest|pixel|smooth`, `--dry-run`, and `--no-dms`
/ `--no-gtk` / `--no-gsettings` / `--no-niri` / `--no-xresources` /
`--no-icons-default` to skip individual targets when applying.

`upscale` derives new sizes from the best existing one — the largest size that
does not exceed the target (so a 48px comes from the 32px art, never the 24px).

## What `set` changes

There is no single place that controls the X11 cursor, so `wcursor` updates
every consumer it knows about, backing each file up to `<file>.wcursor-bak`
before touching it:

| Target | File / command |
| ------ | -------------- |
| DMS | `~/.config/DankMaterialShell/settings.json` (`cursorSettings.theme` / `.size`) |
| DMS → niri | `~/.config/niri/dms/cursor.kdl` |
| X11 / Xresources | `~/.Xresources` (`Xcursor.theme` / `Xcursor.size`) |
| X11 default theme | `~/.icons/default/index.theme` (`Inherits=`) |
| GTK 3 / GTK 4 | `settings.ini` (`gtk-cursor-theme-name` / `-size`) |
| GSettings | `org.gnome.desktop.interface cursor-theme` / `cursor-size` |
| niri | `niri msg action load-config-file` |

DMS keeps its settings in memory and rewrites `settings.json` on exit, and its
`settings set` IPC call **rejects** `cursorSettings`, so the only reliable path
is to stop DMS, edit the file, and start DMS again. `wcursor` does that
automatically (and leaves DMS alone if it is not running).

## Development

```bash
python3 -m unittest discover -s tests -t . -v
```

The suite is stdlib-only. Tests under `tests/test_integration.py` use real
cursor packs and installed themes when they are present and skip otherwise.

Layout:

| Module | Responsibility |
| ------ | -------------- |
| `wcursor/icons.py` | decode `.ico` / `.cur` / `.ani` (BMP + PNG + RIFF/ACON) |
| `wcursor/xcursor.py` | read/write Xcursor files, premultiply, resample |
| `wcursor/roles.py` | Windows slot ↔ canonical Xcursor names, alias table |
| `wcursor/pack.py` | find cursors in a folder, parse `install.inf`, map roles |
| `wcursor/theme.py` | build a theme (cursors + alias symlinks + `index.theme`) |
| `wcursor/install.py` | install / list / remove themes |
| `wcursor/apply.py` | push theme + size to DMS, X11, GTK, GSettings, niri |
| `wcursor/cli.py` | command line front end |

## License

MIT
