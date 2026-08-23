"""Application entry point."""

from __future__ import annotations

import sys


def main() -> int:
    """Start the desktop application."""
    from diplomacy_app.ui.application_window import run_application

    return run_application(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
