"""Safe SVG handling and geometry extraction for configured maps."""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from io import BytesIO
from xml.etree import ElementTree

from defusedxml import ElementTree as SafeElementTree
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.ops import unary_union
from svgelements import SVG, Close, Move, Path

from diplomacy_app.domain.errors import MapLibraryError

_ALLOWED_TAGS = {
    "svg",
    "g",
    "defs",
    "style",
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "text",
    "tspan",
    "title",
    "desc",
    "clipPath",
    "mask",
    "linearGradient",
    "radialGradient",
    "stop",
    "use",
    "symbol",
    "marker",
    "pattern",
}
_URL = re.compile(r"url\s*\(\s*(['\"]?)(?!#)", re.IGNORECASE)


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def sanitise_svg(data: bytes) -> bytes:
    """Return safe, inactive SVG or raise a contextual map-library error."""
    lowered = data.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered or b"<?xml-stylesheet" in lowered:
        raise MapLibraryError("SVG declarations, entities, and stylesheets are not supported")
    try:
        root = SafeElementTree.fromstring(data)
    except Exception as exc:  # defusedxml exposes several parser exception types
        raise MapLibraryError(f"Invalid SVG: {exc}") from exc
    if _local_name(root.tag) != "svg":
        raise MapLibraryError("The selected file is not an SVG document")
    ids: set[str] = set()
    for element in root.iter():
        tag = _local_name(element.tag)
        if tag not in _ALLOWED_TAGS:
            raise MapLibraryError(f"Unsupported SVG element <{tag}>")
        element_id = element.attrib.get("id")
        if element_id:
            if element_id in ids:
                raise MapLibraryError(f"Duplicate SVG element id: {element_id}")
            ids.add(element_id)
        for attribute, value in tuple(element.attrib.items()):
            name = _local_name(attribute).lower()
            if name.startswith("on"):
                raise MapLibraryError(f"Active SVG attribute is not permitted: {name}")
            if name in {"href", "src"} and value and not value.startswith("#"):
                raise MapLibraryError("External SVG resources are not permitted")
            if _URL.search(value):
                raise MapLibraryError("External SVG URL references are not permitted")
    ElementTree.register_namespace("", "http://www.w3.org/2000/svg")
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def element_ids(svg: bytes) -> tuple[str, ...]:
    root = SafeElementTree.fromstring(svg)
    return tuple(
        element_id for node in root.iter() if (element_id := node.attrib.get("id")) is not None
    )


def shape_ids(svg: bytes) -> tuple[str, ...]:
    """Return IDs attached to geometry or geometry-containing groups."""
    root = SafeElementTree.fromstring(svg)
    shape_tags = {"path", "rect", "circle", "ellipse", "polygon", "polyline"}
    return tuple(
        element_id
        for node in root.iter()
        if _local_name(node.tag) in shape_tags
        or (
            _local_name(node.tag) == "g"
            and any(_local_name(child.tag) in shape_tags for child in node.iter())
        )
        if (element_id := node.attrib.get("id")) is not None
    )


def view_box(svg: bytes) -> tuple[float, float, float, float]:
    root = SafeElementTree.fromstring(svg)
    value = root.attrib.get("viewBox")
    if value:
        parts = [float(item) for item in value.replace(",", " ").split()]
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            return parts[0], parts[1], parts[2], parts[3]
    width = float(root.attrib.get("width", "1000").removesuffix("px"))
    height = float(root.attrib.get("height", "1000").removesuffix("px"))
    return 0.0, 0.0, width, height


def _rings(path: Path) -> Iterable[list[tuple[float, float]]]:
    ring: list[tuple[float, float]] = []
    for segment in path:
        if isinstance(segment, Move):
            if len(ring) >= 3:
                yield ring
            ring = [(float(segment.end.x), float(segment.end.y))]
        elif isinstance(segment, Close):
            if len(ring) >= 3:
                yield ring
            ring = []
        else:
            samples = 1 if segment.__class__.__name__ == "Line" else 12
            for index in range(1, samples + 1):
                point = segment.point(index / samples)
                ring.append((float(point.x), float(point.y)))
    if len(ring) >= 3:
        yield ring


def territory_geometries(svg: bytes, svg_ids: Iterable[str]) -> dict[str, Polygon | MultiPolygon]:
    """Convert selected SVG shapes into transformed Shapely geometry.

    Geometry extraction dominates map compilation for detailed SVGs. Draft
    presentation edits reuse the same immutable SVG and territory elements, so
    cache that pure result while returning a fresh mapping to each caller.

    :param svg: Sanitised SVG document bytes.
    :param svg_ids: Shape or group identifiers to extract.
    :return: Extracted geometry keyed by requested SVG identifier.
    """
    return dict(_territory_geometries(svg, tuple(svg_ids)))


@lru_cache(maxsize=8)
def _territory_geometries(
    svg: bytes, svg_ids: tuple[str, ...]
) -> dict[str, Polygon | MultiPolygon]:
    """Return cached geometry for an immutable SVG and identifier sequence.

    :param svg: Sanitised SVG document bytes.
    :param svg_ids: Stable sequence of shape or group identifiers to extract.
    :return: Cached extracted geometry; callers must not mutate this mapping.
    """
    wanted = set(svg_ids)
    geometries: dict[str, Polygon | MultiPolygon] = {}
    try:
        root = SafeElementTree.fromstring(svg)
        shape_tags = {"path", "rect", "circle", "ellipse", "polygon", "polyline"}
        group_members = {
            element_id: {
                child_id
                for child in node.iter()
                if _local_name(child.tag) in shape_tags
                if (child_id := child.attrib.get("id")) is not None
            }
            for node in root.iter()
            if _local_name(node.tag) == "g"
            if (element_id := node.attrib.get("id")) in wanted
        }
        shape_wanted = wanted | set().union(*group_members.values()) if group_members else wanted
        shape_geometries: dict[str, Polygon | MultiPolygon] = {}
        document = SVG.parse(BytesIO(svg))
        for element in document.elements():
            element_id = getattr(element, "id", None)
            if not isinstance(element_id, str) or element_id not in shape_wanted:
                continue
            if element_id in group_members:
                continue
            try:
                path = Path(element)
            except (AttributeError, TypeError):
                continue
            polygons = [Polygon(ring) for ring in _rings(path)]
            valid = [polygon.buffer(0) for polygon in polygons if not polygon.is_empty]
            if not valid:
                continue
            # Configured territory paths use even-odd fill so nested rings are
            # holes (islands in seas), not additional filled polygons.
            merged = GeometryCollection()
            for polygon in valid:
                merged = merged.symmetric_difference(polygon)
            if isinstance(merged, (Polygon, MultiPolygon)):
                shape_geometries[element_id] = merged
        geometries.update(
            (element_id, geometry)
            for element_id, geometry in shape_geometries.items()
            if element_id in wanted
        )
        for group_id, member_ids in group_members.items():
            merged_group = unary_union(
                [
                    shape_geometries[member_id]
                    for member_id in member_ids
                    if member_id in shape_geometries
                ]
            )
            if isinstance(merged_group, (Polygon, MultiPolygon)):
                geometries[group_id] = merged_group
    except Exception as exc:
        raise MapLibraryError(f"Could not analyse SVG geometry: {exc}") from exc
    return geometries
