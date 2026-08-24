"""Deterministic map scene composer."""

from __future__ import annotations

import base64
import math
from xml.etree import ElementTree

from diplomacy_app.domain.errors import RenderingError
from diplomacy_app.domain.models import (
    BuildOrder,
    ConvoyOrder,
    DisbandOrder,
    HiddenTerritory,
    HoldOrder,
    Location,
    MapBounds,
    MapDefinition,
    MapHotspot,
    MapScene,
    MoveOrder,
    Point,
    ProjectedMapState,
    RenderRequest,
    RetreatOrder,
    SupportOrder,
    TerritoryKind,
    UnitRef,
    UnitType,
    VisibleTerritory,
    WaiveOrder,
)
from diplomacy_app.map_library.svg_importer import view_box
from diplomacy_app.rendering.labels import label_lines

_SVG = "http://www.w3.org/2000/svg"
ElementTree.register_namespace("", _SVG)


def _tag(name: str) -> str:
    return f"{{{_SVG}}}{name}"


def _darken(colour: str, factor: float) -> str:
    value = colour.lstrip("#")
    if len(value) != 6:
        return colour
    channels = [
        max(0, min(255, round(int(value[index : index + 2], 16) * factor))) for index in (0, 2, 4)
    ]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def _anchor(map_definition: MapDefinition, unit: UnitRef) -> Point:
    if unit.unit_type is UnitType.ARMY:
        return map_definition.presentation.army_anchors[unit.location.territory_id]
    if unit.location in map_definition.presentation.fleet_anchors:
        return map_definition.presentation.fleet_anchors[unit.location]
    return map_definition.presentation.fleet_anchors[Location(unit.location.territory_id)]


def _image_href(svg: bytes, colour: str) -> str:
    tinted = svg.replace(b"currentColor", colour.encode())
    return "data:image/svg+xml;base64," + base64.b64encode(tinted).decode()


class MapRenderer:
    def compose(
        self,
        map_definition: MapDefinition,
        projected_state: ProjectedMapState,
        request: RenderRequest,
    ) -> MapScene:
        try:
            root = ElementTree.fromstring(map_definition.assets.map_svg)
            bounds = MapBounds(*view_box(map_definition.assets.map_svg))
            by_svg_id = {node.attrib["id"]: node for node in root.iter() if "id" in node.attrib}
            definitions = {item.id: item for item in map_definition.territories}
            powers = {item.id: item for item in map_definition.powers}
            projected = {item.territory_id: item for item in projected_state.territories}
            for territory_id, item in projected.items():
                node = by_svg_id.get(definitions[territory_id].svg_element_id)
                if node is None:
                    continue
                if isinstance(item, HiddenTerritory):
                    fill = "#8d8b85"
                elif definitions[territory_id].kind is TerritoryKind.SEA:
                    fill = "#9ebbd2"
                elif item.controller and item.controller in powers:
                    fill = powers[item.controller].colour
                else:
                    fill = "#d0c9aa"
                previous = node.attrib.get("style", "")
                node.set("style", previous + f";fill:{fill};")

            generated = ElementTree.SubElement(root, _tag("g"), {"id": "gamemaster-layers"})
            labels = ElementTree.SubElement(generated, _tag("g"), {"id": "territory-labels"})
            centres = ElementTree.SubElement(generated, _tag("g"), {"id": "supply-centres"})
            units_layer = ElementTree.SubElement(generated, _tag("g"), {"id": "units"})
            orders_layer = ElementTree.SubElement(generated, _tag("g"), {"id": "orders"})
            for territory in map_definition.territories:
                item = projected[territory.id]
                anchor = map_definition.presentation.label_anchors[territory.id]
                label = ElementTree.SubElement(
                    labels,
                    _tag("text"),
                    {
                        "x": str(anchor.x),
                        "y": str(anchor.y),
                        "text-anchor": "middle",
                        "dominant-baseline": "central",
                        "font-family": "Georgia, serif",
                        "font-size": "11",
                        "font-weight": "700",
                        "fill": "#252621",
                        "paint-order": "stroke",
                        "stroke": "#f5f0df",
                        "stroke-width": "2",
                    },
                )
                lines = label_lines(item.label)
                if len(lines) == 1:
                    label.text = lines[0]
                else:
                    for index, line in enumerate(lines):
                        tspan = ElementTree.SubElement(
                            label,
                            _tag("tspan"),
                            {
                                "x": str(anchor.x),
                                "dy": f"{-0.55 * (len(lines) - 1):g}em" if index == 0 else "1.1em",
                            },
                        )
                        tspan.text = line
                if isinstance(item, VisibleTerritory) and territory.is_supply_centre:
                    point = map_definition.presentation.supply_centre_anchors[territory.id]
                    owner_colour = (
                        powers[item.supply_centre_owner].colour
                        if item.supply_centre_owner in powers
                        else "#eee6c8"
                    )
                    star = ElementTree.SubElement(
                        centres,
                        _tag("text"),
                        {
                            "x": str(point.x),
                            "y": str(point.y),
                            "text-anchor": "middle",
                            "dominant-baseline": "central",
                            "font-size": "18",
                            "fill": owner_colour,
                            "stroke": "#3d3b33",
                            "stroke-width": "1",
                        },
                    )
                    star.text = "★"
                if isinstance(item, VisibleTerritory):
                    for unit, dislodged in ((item.unit, False), (item.dislodged_unit, True)):
                        if unit is None:
                            continue
                        unit_ref = UnitRef(unit.power_id, unit.unit_type, unit.location)
                        point = _anchor(map_definition, unit_ref)
                        offset = 9 if dislodged and item.unit else 0
                        colour = _darken(powers[unit.power_id].colour, 0.82)
                        asset = (
                            map_definition.assets.army_svg
                            if unit.unit_type is UnitType.ARMY
                            else map_definition.assets.fleet_svg
                        )
                        ElementTree.SubElement(
                            units_layer,
                            _tag("image"),
                            {
                                "x": str(point.x - 16 + offset),
                                "y": str(point.y - 11 + offset),
                                "width": "32",
                                "height": "22",
                                "href": _image_href(asset, colour),
                            },
                        )
                        if dislodged:
                            marker = ElementTree.SubElement(
                                units_layer,
                                _tag("text"),
                                {
                                    "x": str(point.x + 13 + offset),
                                    "y": str(point.y - 9 + offset),
                                    "font-size": "10",
                                    "font-weight": "bold",
                                    "fill": "#8b2028",
                                },
                            )
                            marker.text = "R"

            result_by_line = {
                item.source_line: item.outcome_codes for item in projected_state.results
            }
            hotspots: list[MapHotspot] = []
            move_paths: dict[tuple[object, object], tuple[Point, Point]] = {}
            for projected_order in projected_state.orders:
                order = projected_order.order
                if isinstance(order, MoveOrder):
                    start = _anchor(map_definition, order.unit)
                    destination_definition = definitions[order.destination.territory_id]
                    if order.unit.unit_type is UnitType.ARMY:
                        end = map_definition.presentation.army_anchors[destination_definition.id]
                    else:
                        end = map_definition.presentation.fleet_anchors.get(
                            order.destination,
                            map_definition.presentation.label_anchors[destination_definition.id],
                        )
                    move_paths[(order.unit.location, order.destination)] = (start, end)
                    ElementTree.SubElement(
                        orders_layer,
                        _tag("line"),
                        {
                            "x1": str(start.x),
                            "y1": str(start.y),
                            "x2": str(end.x),
                            "y2": str(end.y),
                            "stroke": "#22251f",
                            "stroke-width": "3",
                            "stroke-linecap": "round",
                        },
                    )
                    angle = math.atan2(end.y - start.y, end.x - start.x)
                    points = [
                        end,
                        Point(
                            end.x - 10 * math.cos(angle - 0.5), end.y - 10 * math.sin(angle - 0.5)
                        ),
                        Point(
                            end.x - 10 * math.cos(angle + 0.5), end.y - 10 * math.sin(angle + 0.5)
                        ),
                    ]
                    ElementTree.SubElement(
                        orders_layer,
                        _tag("polygon"),
                        {"points": " ".join(f"{p.x},{p.y}" for p in points), "fill": "#22251f"},
                    )
                    hotspots.append(
                        MapHotspot(
                            projected_order.source_line,
                            (start, end),
                            10.0,
                            result_by_line.get(projected_order.source_line, ()),
                        )
                    )
            for projected_order in projected_state.orders:
                order = projected_order.order
                if isinstance(order, HoldOrder):
                    point = _anchor(map_definition, order.unit)
                    ElementTree.SubElement(
                        orders_layer,
                        _tag("circle"),
                        {
                            "cx": str(point.x),
                            "cy": str(point.y),
                            "r": "17",
                            "fill": "none",
                            "stroke": "#22251f",
                            "stroke-width": "2.5",
                            "stroke-dasharray": "3 5"
                            if projected_order.is_valid is False
                            else "none",
                        },
                    )
                elif isinstance(order, SupportOrder):
                    start = _anchor(map_definition, order.unit)
                    target = _anchor(map_definition, order.supported_unit)
                    if (
                        order.destination
                        and (order.supported_unit.location, order.destination) in move_paths
                    ):
                        move_start, move_end = move_paths[
                            (order.supported_unit.location, order.destination)
                        ]
                        target = Point(
                            (move_start.x + move_end.x) / 2, (move_start.y + move_end.y) / 2
                        )
                    control_y = min(start.y, target.y) - abs(target.x - start.x) * 0.16
                    ElementTree.SubElement(
                        orders_layer,
                        _tag("path"),
                        {
                            "d": f"M {start.x} {start.y} Q {(start.x + target.x) / 2} {control_y} {target.x} {target.y}",
                            "fill": "none",
                            "stroke": "#3b3d37",
                            "stroke-width": "2",
                            "stroke-dasharray": "3 5",
                        },
                    )
                elif isinstance(order, ConvoyOrder):
                    start = _anchor(map_definition, order.unit)
                    target = _anchor(map_definition, order.convoyed_army)
                    ElementTree.SubElement(
                        orders_layer,
                        _tag("path"),
                        {
                            "d": f"M {start.x} {start.y} Q {(start.x + target.x) / 2} {start.y - 18} {target.x} {target.y}",
                            "fill": "none",
                            "stroke": "#263b4a",
                            "stroke-width": "2.5",
                            "stroke-dasharray": "8 4 2 4",
                        },
                    )
                elif isinstance(order, (BuildOrder, DisbandOrder)):
                    point = _anchor(map_definition, order.unit)
                    mark = ElementTree.SubElement(
                        orders_layer,
                        _tag("text"),
                        {
                            "x": str(point.x),
                            "y": str(point.y + 5),
                            "text-anchor": "middle",
                            "font-size": "27",
                            "font-weight": "bold",
                            "fill": "#254e33" if isinstance(order, BuildOrder) else "#8b2028",
                            "paint-order": "stroke",
                            "stroke": "#f5f0df",
                            "stroke-width": "3",
                        },
                    )
                    mark.text = "+" if isinstance(order, BuildOrder) else "−"
                elif isinstance(order, RetreatOrder):
                    start = _anchor(map_definition, order.unit)
                    end = map_definition.presentation.label_anchors[order.destination.territory_id]
                    ElementTree.SubElement(
                        orders_layer,
                        _tag("line"),
                        {
                            "x1": str(start.x),
                            "y1": str(start.y),
                            "x2": str(end.x),
                            "y2": str(end.y),
                            "stroke": "#8b2028",
                            "stroke-width": "2.5",
                            "stroke-dasharray": "6 4",
                        },
                    )
                elif isinstance(order, WaiveOrder):
                    continue
            return MapScene(
                ElementTree.tostring(root, encoding="utf-8", xml_declaration=True),
                bounds,
                tuple(hotspots),
            )
        except Exception as exc:
            if isinstance(exc, RenderingError):
                raise
            raise RenderingError(f"Could not compose map: {exc}") from exc

    def export(self, scene: MapScene, request: RenderRequest):
        from diplomacy_app.rendering.raster_export import export_scene

        return export_scene(scene, request)
