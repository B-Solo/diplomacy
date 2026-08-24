"""Shared territory-label line breaking for SVG and interactive previews."""

from __future__ import annotations

import re
import textwrap

LABEL_LINE_HEIGHT = 1.1


def label_lines(text: str, width: int = 16) -> tuple[str, ...]:
    """Wrap a label at words and ampersands while preserving explicit line breaks."""
    if "\n" in text or "\r" in text:
        return tuple(line.strip() for line in text.splitlines())
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        normalised = re.sub(r"\s*&\s*", " & ", paragraph).strip()
        lines.extend(
            textwrap.wrap(
                normalised,
                width=width,
                break_long_words=False,
                break_on_hyphens=False,
            )
            or [""]
        )
    return tuple(lines)
