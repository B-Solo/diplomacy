"""Canonical SVG label construction for composed maps and interactive placement."""

from __future__ import annotations

import re
import textwrap
from xml.etree import ElementTree

from diplomacy_app.domain.models import Point

LABEL_LINE_HEIGHT = 1.1
_SVG = "http://www.w3.org/2000/svg"
ElementTree.register_namespace("", _SVG)


def _tag(name: str) -> str:
    return f"{{{_SVG}}}{name}"


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


def add_label_element(
    parent: ElementTree.Element,
    *,
    element_id: str,
    text: str,
    anchor: Point,
    size: float,
    colour: str,
    bold: bool,
    italic: bool = False,
    rotation: float = 0,
    wrap: bool = True,
    css_class: str = "map-label",
    data: dict[str, str] | None = None,
) -> ElementTree.Element:
    """Add the canonical SVG elements used for every map label display."""
    attributes = {"id": element_id, "class": css_class, **(data or {})}
    if rotation:
        attributes["transform"] = f"rotate({rotation:g} {anchor.x:g} {anchor.y:g})"
    group = ElementTree.SubElement(parent, _tag("g"), attributes)
    lines = label_lines(text) if wrap else (text,)
    line_height = size * LABEL_LINE_HEIGHT
    for index, line in enumerate(lines):
        line_label = ElementTree.SubElement(
            group,
            _tag("text"),
            {
                "x": f"{anchor.x:g}",
                "y": f"{anchor.y + (index - (len(lines) - 1) / 2) * line_height:g}",
                "text-anchor": "middle",
                "dominant-baseline": "central",
                "font-family": "Georgia, serif",
                "font-size": f"{size:g}",
                "font-weight": "700" if bold else "400",
                "fill": colour,
                "data-line": str(index),
            },
        )
        if italic:
            line_label.set("font-style", "italic")
        line_label.text = line
    return group


def isolated_label_svg(
    text: str,
    colour: str,
    size: float,
    *,
    bold: bool,
    italic: bool = False,
    wrap: bool = True,
) -> bytes:
    """Build a draggable label using the same SVG elements as composed maps."""
    root = ElementTree.Element(
        _tag("svg"),
        {"viewBox": "-1000 -1000 2000 2000"},
    )
    add_label_element(
        root,
        element_id="draggable-label",
        text=text,
        anchor=Point(0, 0),
        size=size,
        colour=colour,
        bold=bold,
        italic=italic,
        wrap=wrap,
    )
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
