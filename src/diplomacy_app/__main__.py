"""Application entry point."""

from __future__ import annotations

import sys
import logging
import datetime
import os


def main() -> int:
    """Start the desktop application."""
    from diplomacy_app.ui.application_window import run_application



    # Everything -> file
    os.makedirs("logs", exist_ok=True)
    logname = datetime.datetime.now().strftime("logs/app-%Y-%m-%d_%H-%M-%S.log")
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(logname, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.getLogger().handlers[0].setLevel(logging.DEBUG)
    logging.getLogger().handlers[1].setLevel(logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("Starting application...")

    return run_application(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
