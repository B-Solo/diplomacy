"""Build the map editor's topology diagram and hover metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from xml.etree import ElementTree

from diplomacy_app.domain.models import (
    CoastId,
    Location,
    MapDefinition,
    Point,
    TerritoryKind,
    UnitType,
)
from diplomacy_app.presentation import coast_label_text

_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_EDGE_COLOURS = {"army": "#f4511e", "fleet": "#00b8d4", "both": "#d500f9"}


@dataclass(frozen=True, slots=True)
class TopologyDiagram:
    """A rendered topology diagram and the metadata used for hover navigation."""

    svg: bytes
    node_points: Mapping[str, Point]
    node_territories: Mapping[str, str]
    node_names: Mapping[str, str]


def _tag(name: str) -> str:
    """Return an ElementTree tag in the SVG namespace."""
    return f"{{{_SVG_NAMESPACE}}}{name}"


def _location_id(location: Location) -> str:
    """Return the stable diagram identifier for a province or named coast."""
    return str(location.territory_id) + (
        f"/{location.coast_id}" if location.coast_id is not None else ""
    )


def build_topology_diagram(base_svg: bytes, definition: MapDefinition) -> TopologyDiagram:
    """Render effective movement topology over a faded map.

    :param base_svg: Composed starting-position SVG used as the diagram underlay.
    :param definition: Validated map whose effective adjacencies should be drawn.
    :return: Diagram SVG together with immutable hover-navigation metadata.
    """
    root = ElementTree.fromstring(base_svg)
    original_children = list(root)
    underlay = ElementTree.Element(_tag("g"), {"id": "topology-map-underlay", "opacity": "0.58"})
    for child in original_children:
        if child.tag.rsplit("}", 1)[-1] not in {"defs", "style", "title", "desc"}:
            root.remove(child)
            underlay.append(child)
    root.append(underlay)

    defs = ElementTree.SubElement(root, _tag("defs"))
    for name, colour in _EDGE_COLOURS.items():
        marker = ElementTree.SubElement(
            defs,
            _tag("marker"),
            {
                "id": f"topology-arrow-{name}",
                "viewBox": "0 0 10 10",
                "refX": "8",
                "refY": "5",
                "markerWidth": "6",
                "markerHeight": "6",
                "orient": "auto-start-reverse",
            },
        )
        ElementTree.SubElement(
            marker,
            _tag("path"),
            {"d": "M 0 0 L 10 5 L 0 10 z", "fill": colour},
        )

    directions: dict[tuple[str, str], set[UnitType]] = {}
    for edge in definition.adjacencies:
        origin = _location_id(edge.origin)
        destination = _location_id(edge.destination)
        if origin != destination:
            directions.setdefault((origin, destination), set()).add(edge.unit_type)

    territories_by_id = {str(item.id): item for item in definition.territories}
    nodes: dict[str, tuple[Point, str, str, str]] = {}
    for territory in definition.territories:
        if territory.kind is TerritoryKind.LAND:
            point = definition.presentation.army_anchors.get(
                territory.id, definition.presentation.label_anchors[territory.id]
            )
            anchor_type = "army"
        else:
            point = definition.presentation.fleet_anchors.get(
                Location(territory.id), definition.presentation.label_anchors[territory.id]
            )
            anchor_type = "fleet"
        nodes[str(territory.id)] = (
            point,
            anchor_type,
            str(territory.id),
            territory.abbreviation,
        )
        for coast_id in territory.split_coast_ids:
            location = Location(territory.id, coast_id)
            nodes[_location_id(location)] = (
                definition.presentation.fleet_anchors[location],
                "fleet",
                str(territory.id),
                f"{territory.abbreviation}/{coast_id}",
            )

    node_points = {
        node_id: point for node_id, (point, _anchor_type, _territory_id, _label) in nodes.items()
    }
    node_territories = {
        node_id: territory_id
        for node_id, (_point, _anchor_type, territory_id, _label) in nodes.items()
    }
    node_names = {
        node_id: territories_by_id[territory_id].name
        + (f" — {coast_label_text(CoastId(node_id.partition('/')[2]))}" if "/" in node_id else "")
        for node_id, territory_id in node_territories.items()
    }

    edge_layer = ElementTree.SubElement(root, _tag("g"), {"id": "topology-edges"})
    pairs = sorted({tuple(sorted(pair)) for pair in directions})
    for left, right in pairs:
        forward = directions.get((left, right), set())
        reverse = directions.get((right, left), set())
        variants = (
            [(left, right, forward, False)]
            if forward == reverse
            else [
                (left, right, forward, True),
                (right, left, reverse, True),
            ]
        )
        for origin, destination, units, directed in variants:
            if not units:
                continue
            kind = "both" if units == {UnitType.ARMY, UnitType.FLEET} else next(iter(units)).value
            origin_anchor = nodes[origin][0]
            destination_anchor = nodes[destination][0]
            attributes = {
                "x1": str(origin_anchor.x),
                "y1": str(origin_anchor.y),
                "x2": str(destination_anchor.x),
                "y2": str(destination_anchor.y),
                "fill": "none",
                "data-origin": origin,
                "data-destination": destination,
                "data-kind": kind,
            }
            halo = attributes | {
                "stroke": "#263238",
                "stroke-width": "5",
                "stroke-opacity": "0.72",
            }
            ElementTree.SubElement(edge_layer, _tag("line"), halo)
            attributes |= {
                "stroke": _EDGE_COLOURS[kind],
                "stroke-width": "2.4",
                "stroke-opacity": "0.96",
            }
            if directed:
                attributes["marker-end"] = f"url(#topology-arrow-{kind})"
            ElementTree.SubElement(edge_layer, _tag("line"), attributes)

    node_layer = ElementTree.SubElement(root, _tag("g"), {"id": "topology-nodes"})
    for node_id, (point, anchor_type, territory_id, node_label) in sorted(nodes.items()):
        ElementTree.SubElement(
            node_layer,
            _tag("circle"),
            {
                "cx": str(point.x),
                "cy": str(point.y),
                "r": "4.5",
                "fill": "#ffcc80" if anchor_type == "army" else "#80deea",
                "stroke": "#263238",
                "stroke-width": "1.8",
                "data-territory": territory_id,
                "data-location": node_id,
                "data-anchor-type": anchor_type,
            },
        )
        label = ElementTree.SubElement(
            node_layer,
            _tag("text"),
            {
                "x": str(point.x + 6),
                "y": str(point.y - 6),
                "font-size": "11",
                "font-weight": "600",
                "fill": "#111111",
            },
        )
        label.text = node_label

    return TopologyDiagram(
        ElementTree.tostring(root, encoding="utf-8", xml_declaration=True),
        MappingProxyType(node_points),
        MappingProxyType(node_territories),
        MappingProxyType(node_names),
    )
