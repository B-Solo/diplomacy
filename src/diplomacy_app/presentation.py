"""Shared presentation conventions for named split coasts."""

from __future__ import annotations

from diplomacy_app.domain.models import CoastId, Point


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
