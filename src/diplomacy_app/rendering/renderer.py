"""Deterministic map scene composer."""

from __future__ import annotations

import copy
import math
from xml.etree import ElementTree

from diplomacy_app.domain.errors import RenderingError
from diplomacy_app.domain.models import (
    BuildOrder,
    ConvoyOrder,
    DisbandOrder,
    HiddenTerritory,
    HoldOrder,
    LabelMode,
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
from diplomacy_app.presentation import (
    coast_label_text,
    darken_colour,
    embedded_unit_svg,
    supply_centre_star_points,
)
from diplomacy_app.rendering.labels import add_label_element

_SVG = "http://www.w3.org/2000/svg"
ElementTree.register_namespace("", _SVG)


def _tag(name: str) -> str:
    return f"{{{_SVG}}}{name}"


def _anchor(map_definition: MapDefinition, unit: UnitRef) -> Point:
    if unit.unit_type is UnitType.ARMY:
        return map_definition.presentation.army_anchors[unit.location.territory_id]
    if unit.location in map_definition.presentation.fleet_anchors:
        return map_definition.presentation.fleet_anchors[unit.location]
    return map_definition.presentation.fleet_anchors[Location(unit.location.territory_id)]


def _add_unit_symbol(
    layer: ElementTree.Element,
    asset: bytes,
    colour: str,
    point: Point,
    offset: int,
) -> None:
    source = ElementTree.fromstring(embedded_unit_svg(asset, colour))
    x, y, width, height = view_box(asset)
    scale = min(32 / max(width, 1), 22 / max(height, 1))
    translate_x = point.x + offset - (x + width / 2) * scale
    translate_y = point.y + offset - (y + height / 2) * scale
    symbol = ElementTree.SubElement(
        layer,
        _tag("g"),
        {
            "class": "unit-symbol",
            "transform": f"translate({translate_x:g} {translate_y:g}) scale({scale:g})",
        },
    )
    for child in source:
        symbol.append(copy.deepcopy(child))


def _set_fill(node: ElementTree.Element, colour: str) -> None:
    geometry_tags = {"path", "rect", "circle", "ellipse", "polygon", "polyline"}
    targets = [node, *(child for child in node.iter() if child is not node)]
    for target in targets:
        if target is not node and target.tag.rsplit("}", 1)[-1] not in geometry_tags:
            continue
        declarations = [
            declaration.strip()
            for declaration in target.attrib.get("style", "").split(";")
            if declaration.strip() and declaration.partition(":")[0].strip().casefold() != "fill"
        ]
        declarations.append(f"fill:{colour}")
        target.set("style", ";".join(declarations))


def _add_inaccessible_pattern(root: ElementTree.Element, colour: str) -> str:
    pattern_id = "gamemaster-inaccessible-stripes"
    definitions = ElementTree.SubElement(root, _tag("defs"))
    pattern = ElementTree.SubElement(
        definitions,
        _tag("pattern"),
        {
            "id": pattern_id,
            "width": "12",
            "height": "12",
            "patternUnits": "userSpaceOnUse",
        },
    )
    ElementTree.SubElement(
        pattern,
        _tag("rect"),
        {"width": "12", "height": "12", "fill": colour},
    )
    ElementTree.SubElement(
        pattern,
        _tag("path"),
        {
            "d": "M -3 3 L 3 -3 M 0 12 L 12 0 M 9 15 L 15 9",
            "fill": "none",
            "stroke": "#fffdf7",
            "stroke-opacity": "0.24",
            "stroke-width": "3",
        },
    )
    return pattern_id


class MapRenderer:
    def base_map_svg(self, map_definition: MapDefinition) -> bytes:
        """Apply map-wide neutral presentation colours without game-state overlays."""
        root = ElementTree.fromstring(map_definition.assets.map_svg)
        inaccessible_pattern = _add_inaccessible_pattern(
            root, map_definition.presentation.inaccessible_region_colour
        )
        by_svg_id = {node.attrib["id"]: node for node in root.iter() if "id" in node.attrib}
        for element_id in map_definition.inaccessible_svg_element_ids:
            node = by_svg_id.get(element_id)
            if node is not None:
                _set_fill(node, f"url(#{inaccessible_pattern})")
        for territory in map_definition.territories:
            node = by_svg_id.get(territory.svg_element_id)
            if node is None:
                continue
            colour = (
                map_definition.presentation.sea_colour
                if territory.kind is TerritoryKind.SEA
                else map_definition.presentation.unclaimed_region_colour
            )
            _set_fill(node, colour)
        return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)

    def compose(
        self,
        map_definition: MapDefinition,
        projected_state: ProjectedMapState,
        request: RenderRequest,
    ) -> MapScene:
        try:
            root = ElementTree.fromstring(self.base_map_svg(map_definition))
            bounds = MapBounds(*view_box(map_definition.assets.map_svg))
            by_svg_id = {node.attrib["id"]: node for node in root.iter() if "id" in node.attrib}
            definitions = {item.id: item for item in map_definition.territories}
            powers = {item.id: item for item in map_definition.powers}
            label_anchors = (
                map_definition.presentation.abbreviation_anchors
                if request.label_mode is LabelMode.ABBREVIATION
                else map_definition.presentation.label_anchors
            )
            projected = {item.territory_id: item for item in projected_state.territories}
            for territory_id, item in projected.items():
                node = by_svg_id.get(definitions[territory_id].svg_element_id)
                if node is None:
                    continue
                if isinstance(item, HiddenTerritory):
                    fill = "#8d8b85"
                elif definitions[territory_id].kind is TerritoryKind.SEA:
                    fill = map_definition.presentation.sea_colour
                elif item.controller and item.controller in powers:
                    fill = powers[item.controller].colour
                else:
                    fill = map_definition.presentation.unclaimed_region_colour
                _set_fill(node, fill)

            generated = ElementTree.SubElement(root, _tag("g"), {"id": "gamemaster-layers"})
            labels = ElementTree.SubElement(generated, _tag("g"), {"id": "territory-labels"})
            coast_labels = ElementTree.SubElement(generated, _tag("g"), {"id": "coast-labels"})
            centres = ElementTree.SubElement(generated, _tag("g"), {"id": "supply-centres"})
            units_layer = ElementTree.SubElement(generated, _tag("g"), {"id": "units"})
            orders_layer = ElementTree.SubElement(generated, _tag("g"), {"id": "orders"})
            for territory in map_definition.territories:
                item = projected[territory.id]
                anchor = label_anchors[territory.id]
                add_label_element(
                    labels,
                    element_id=f"territory-label-{territory.id}",
                    text=item.label,
                    anchor=anchor,
                    size=map_definition.presentation.territory_label_font_size,
                    colour=map_definition.presentation.label_colour,
                    bold=True,
                    css_class="territory-label",
                    data={"data-territory": str(territory.id)},
                )
                for coast_id in territory.split_coast_ids:
                    location = Location(territory.id, coast_id)
                    coast_anchor = map_definition.presentation.coast_label_anchors[location]
                    rotation = map_definition.presentation.coast_label_rotations.get(location, 0)
                    add_label_element(
                        coast_labels,
                        element_id=f"coast-label-{territory.id}-{coast_id}",
                        text=coast_label_text(coast_id),
                        anchor=coast_anchor,
                        size=map_definition.presentation.coast_label_font_size,
                        colour=map_definition.presentation.label_colour,
                        bold=True,
                        italic=True,
                        rotation=rotation,
                        wrap=False,
                        css_class="coast-label",
                        data={"data-location": f"{territory.id}/{coast_id}"},
                    )
                if isinstance(item, VisibleTerritory) and territory.is_supply_centre:
                    point = map_definition.presentation.supply_centre_anchors[territory.id]
                    owner_colour = (
                        darken_colour(powers[item.supply_centre_owner].colour, 0.82)
                        if item.supply_centre_owner in powers
                        else "#eee6c8"
                    )
                    ElementTree.SubElement(
                        centres,
                        _tag("polygon"),
                        {
                            "points": " ".join(
                                f"{star_point.x:g},{star_point.y:g}"
                                for star_point in supply_centre_star_points(point)
                            ),
                            "fill": owner_colour,
                            "stroke": "#3d3b33",
                            "stroke-width": "1.25",
                            "stroke-linejoin": "miter",
                            "data-territory": str(territory.id),
                        },
                    )
                if isinstance(item, VisibleTerritory):
                    for unit, dislodged in ((item.unit, False), (item.dislodged_unit, True)):
                        if unit is None:
                            continue
                        unit_ref = UnitRef(unit.power_id, unit.unit_type, unit.location)
                        point = _anchor(map_definition, unit_ref)
                        offset = 9 if dislodged and item.unit else 0
                        colour = darken_colour(powers[unit.power_id].colour, 0.82)
                        asset = (
                            map_definition.assets.army_svg
                            if unit.unit_type is UnitType.ARMY
                            else map_definition.assets.fleet_svg
                        )
                        _add_unit_symbol(units_layer, asset, colour, point, offset)
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
                            label_anchors[destination_definition.id],
                        )
                    move_paths[(order.unit.location, order.destination)] = (start, end)
                    angle = math.atan2(end.y - start.y, end.x - start.x)
                    shaft_end = Point(
                        end.x - 8.8 * math.cos(angle),
                        end.y - 8.8 * math.sin(angle),
                    )
                    ElementTree.SubElement(
                        orders_layer,
                        _tag("line"),
                        {
                            "x1": str(start.x),
                            "y1": str(start.y),
                            "x2": str(shaft_end.x),
                            "y2": str(shaft_end.y),
                            "stroke": "#22251f",
                            "stroke-width": "3",
                            "stroke-linecap": "butt",
                        },
                    )
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
                    badge = ElementTree.SubElement(
                        orders_layer,
                        _tag("g"),
                        {"class": "hold-marker"},
                    )
                    badge_x = point.x + 17
                    badge_y = point.y - 13
                    ElementTree.SubElement(
                        badge,
                        _tag("circle"),
                        {
                            "cx": str(badge_x),
                            "cy": str(badge_y),
                            "r": "8.5",
                            "fill": "#fffaf0",
                            "fill-opacity": "0.94",
                            "stroke": "#22251f",
                            "stroke-width": "1.5",
                            "stroke-dasharray": "2 2"
                            if projected_order.is_valid is False
                            else "none",
                        },
                    )
                    marker = ElementTree.SubElement(
                        badge,
                        _tag("text"),
                        {
                            "x": str(badge_x),
                            "y": str(badge_y),
                            "fill": "#22251f",
                            "font-size": "10",
                            "font-weight": "700",
                            "text-anchor": "middle",
                            "dominant-baseline": "central",
                        },
                    )
                    marker.text = "H"
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
                    end = label_anchors[order.destination.territory_id]
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
