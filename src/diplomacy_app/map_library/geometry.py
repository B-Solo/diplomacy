"""Geometry-derived ordinary movement suggestions."""

from __future__ import annotations

from collections.abc import Mapping

from shapely.geometry import MultiPolygon, Polygon
from shapely.strtree import STRtree

from diplomacy_app.domain.models import TerritoryDefinition, TerritoryId, TerritoryKind


def inferred_connections(
    territories: tuple[TerritoryDefinition, ...],
    geometries: Mapping[str, Polygon | MultiPolygon],
) -> dict[frozenset[TerritoryId], frozenset[str]]:
    """Infer army/fleet movement from materially shared SVG boundaries."""
    available = [item for item in territories if item.svg_element_id in geometries]
    shapes = [geometries[item.svg_element_id] for item in available]
    tree = STRtree(shapes)
    shared: set[tuple[int, int]] = set()
    for left_index, shape in enumerate(shapes):
        for right_index in tree.query(shape):
            right = int(right_index)
            if right <= left_index:
                continue
            # Point contacts are corners, not province borders. Imported maps can
            # be at any scale, so use a tiny relative tolerance and boundary length.
            intersection = shape.boundary.intersection(shapes[right].boundary)
            scale = max(shape.bounds[2] - shape.bounds[0], shape.bounds[3] - shape.bounds[1], 1.0)
            if intersection.length > max(scale * 0.002, 0.25):
                shared.add((left_index, right))

    coastal: set[int] = set()
    for left, right in shared:
        if (
            available[left].kind is TerritoryKind.SEA
            and available[right].kind is TerritoryKind.LAND
        ):
            coastal.add(right)
        if (
            available[right].kind is TerritoryKind.SEA
            and available[left].kind is TerritoryKind.LAND
        ):
            coastal.add(left)

    result: dict[frozenset[TerritoryId], frozenset[str]] = {}
    for left, right in shared:
        origin, destination = available[left], available[right]
        units: set[str] = set()
        if origin.kind is TerritoryKind.LAND and destination.kind is TerritoryKind.LAND:
            units.add("army")
        origin_navigable = origin.kind is TerritoryKind.SEA or left in coastal
        destination_navigable = destination.kind is TerritoryKind.SEA or right in coastal
        if origin_navigable and destination_navigable:
            units.add("fleet")
        if units:
            result[frozenset((origin.id, destination.id))] = frozenset(units)
    return result
