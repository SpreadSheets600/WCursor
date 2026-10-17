"""Allow ``python -m wcursor``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
