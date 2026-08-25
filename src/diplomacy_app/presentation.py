"""Shared presentation conventions for named split coasts."""

from __future__ import annotations

import math
from xml.etree import ElementTree

from diplomacy_app.domain.models import CoastId, MapBounds, PixelSize, Point

DEFAULT_TERRITORY_LABEL_FONT_SIZE = 11.0
DEFAULT_COAST_LABEL_FONT_SIZE = 9.0
DEFAULT_LABEL_COLOUR = "#4c3b1e"
DEFAULT_INACCESSIBLE_REGION_COLOUR = "#777870"
DEFAULT_SEA_COLOUR = "#9ebbd2"
DEFAULT_UNCLAIMED_REGION_COLOUR = "#d0c9aa"
SUPPLY_CENTRE_STAR_OUTER_RADIUS = 9.0
SUPPLY_CENTRE_STAR_INNER_RADIUS = 3.5


def aspect_fitted_size(bounds: MapBounds, maximum: PixelSize) -> PixelSize:
    """Fit pixel dimensions inside a maximum without distorting map bounds."""
    if bounds.width <= 0 or bounds.height <= 0:
        return maximum
    aspect_ratio = bounds.width / bounds.height
    if maximum.width / maximum.height > aspect_ratio:
        return PixelSize(max(1, round(maximum.height * aspect_ratio)), maximum.height)
    return PixelSize(maximum.width, max(1, round(maximum.width / aspect_ratio)))


def supply_centre_star_points(centre: Point | None = None) -> tuple[Point, ...]:
    """Return the shared sharp five-point supply-centre star geometry."""
    centre = centre or Point(0, 0)
    points = []
    for index in range(10):
        radius = (
            SUPPLY_CENTRE_STAR_OUTER_RADIUS if index % 2 == 0 else SUPPLY_CENTRE_STAR_INNER_RADIUS
        )
        angle = -math.pi / 2 + index * math.pi / 5
        points.append(
            Point(
                centre.x + radius * math.cos(angle),
                centre.y + radius * math.sin(angle),
            )
        )
    return tuple(points)


def darken_colour(colour: str, factor: float) -> str:
    """Darken a six-digit SVG colour while preserving unsupported colour formats."""
    value = colour.lstrip("#")
    if len(value) != 6:
        return colour
    channels = [
        max(0, min(255, round(int(value[index : index + 2], 16) * factor))) for index in (0, 2, 4)
    ]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def coast_label_text(coast_id: CoastId) -> str:
    """Return a readable label for a stable coast identifier."""
    name = str(coast_id).replace("-", " ").replace("_", " ").title()
    return name if name.casefold().endswith(" coast") else f"{name} Coast"


def default_coast_label_anchor(coast_id: CoastId, fleet_anchor: Point) -> Point:
    """Offset a missing coast-label anchor away from its fleet anchor."""
    name = str(coast_id).casefold()
    horizontal = -18 if "west" in name else 18 if "east" in name else 0
    vertical = -18 if "north" in name else 18 if "south" in name else 0
    if horizontal == 0 and vertical == 0:
        vertical = -18
    return Point(fleet_anchor.x + horizontal, fleet_anchor.y + vertical)


def embedded_unit_svg(asset: bytes, colour: str) -> bytes:
    """Normalise unit artwork for consistent view-box sizing when embedded in a map."""
    root = ElementTree.fromstring(asset.replace(b"currentColor", colour.encode()))
    root.attrib.pop("width", None)
    root.attrib.pop("height", None)
    return ElementTree.tostring(root, encoding="utf-8")
