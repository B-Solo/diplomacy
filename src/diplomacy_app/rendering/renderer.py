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
    UnparseableOrder,
    VisibleTerritory,
    WaiveOrder,
)
from diplomacy_app.map_library.svg_importer import view_box
from diplomacy_app.presentation import (
    HOLD_UNDERLINE_HALF_WIDTH,
    HOLD_UNDERLINE_STROKE_WIDTH,
    coast_label_text,
    darken_colour,
    embedded_unit_svg,
    supply_centre_star_points,
)
from diplomacy_app.rendering.labels import add_label_element

_SVG = "http://www.w3.org/2000/svg"
_MOVE_ARROW_TIP_INSET = 4.0
_SEMANTIC_FILL_ATTRIBUTE = "data-map-fill"
ElementTree.register_namespace("", _SVG)


def _tag(name: str) -> str:
    return f"{{{_SVG}}}{name}"


def _anchor(map_definition: MapDefinition, unit: UnitRef) -> Point:
    if unit.unit_type is UnitType.ARMY:
        return map_definition.presentation.army_anchors[unit.location.territory_id]
    if unit.location in map_definition.presentation.fleet_anchors:
        return map_definition.presentation.fleet_anchors[unit.location]
    return map_definition.presentation.fleet_anchors[Location(unit.location.territory_id)]


def _move_points(
    map_definition: MapDefinition,
    order: MoveOrder,
    label_anchors: dict[object, Point],
) -> tuple[Point, Point]:
    start = _anchor(map_definition, order.unit)
    destination_definition = next(
        territory
        for territory in map_definition.territories
        if territory.id == order.destination.territory_id
    )
    if order.unit.unit_type is UnitType.ARMY:
        end = map_definition.presentation.army_anchors[destination_definition.id]
    else:
        end = map_definition.presentation.fleet_anchors.get(
            order.destination,
            label_anchors[destination_definition.id],
        )
    return start, end


def _support_move_curve_2(
    support_start: Point, move_start: Point, move_end: Point
) -> tuple[Point, Point, Point]:
    """Calculate a support curve that merges into the supported move.
    Plan is:
    1) Pick a point on the support line to start curving.
    2) Pick a point of the move line that the support line would be aiming for if it was straight
    3) Pick a point on the move line that the support line must have met by.
    4) The desired result is then: Start Point->Point 1, QuadraticBezier(Point 1, Point 2, Point 3), Point 3->End Point
    
    """

    # Aim for a point early down on the arrow (to give plenty of time to curve)
    support_end = move_start + (move_end - move_start) * 0.1
    curve_start = support_start + (support_end - support_start) * 0.4
    curve_end = move_start + (move_end - move_start) * 0.75

    # # @@@
    # if move_start.x == move_end.x or support_start.x == support_end.x:
    #     raise NotImplementedError("Support move curve not implemented for perfectly horizontal or vertical moves")

    # # Find the theoretical meeting point. Solve the simultaneous equations!
    # m_move = (move_start.y - move_end.y) / (move_start.x - move_end.x)
    # m_support = (support_start.y - support_end.y) / (support_start.x - support_end.x)
    # if m_move == m_support:
    #     raise NotImplementedError("Support move curve not implemented for colinear support and move.")

    # # This is a 'trust me bro I did the maths on my whiteboard'
    # x_meet = (support_start.y - move_start.y + m_move * move_start.x - m_support * support_start.x) / (m_move - m_support)
    # y_meet = m_move * (x_meet - move_start.x) + move_start.y

    # curve_start = support_start + (support_end - support_start) * 0.3
    # curve_end = move_start + (move_end - move_start) * 0.7

    # return curve_start, Point(x_meet, y_meet), curve_end
    return curve_start, support_end, curve_end

def _move_line_and_arrow(start: Point, end: Point) -> tuple[tuple[Point, Point], tuple[Point, Point, Point]]:
    """
    Given a start and end of a move, give the start and end points of its line,
    and the three points of its arrowhead.

    The arrow tip must be the first point in its tuple.
    """
    angle = math.atan2(end.y - start.y, end.x - start.x)
    move_length = math.hypot(end.x - start.x, end.y - start.y)
    tip_inset = min(_MOVE_ARROW_TIP_INSET, max(0.0, move_length - 1.0))
    arrow_tip = Point(
        end.x - tip_inset * math.cos(angle),
        end.y - tip_inset * math.sin(angle),
    )
    shaft_end = Point(
        arrow_tip.x - 8.8 * math.cos(angle),
        arrow_tip.y - 8.8 * math.sin(angle),
    )

    points = (
        arrow_tip,
        Point(
            arrow_tip.x - 10 * math.cos(angle - 0.5),
            arrow_tip.y - 10 * math.sin(angle - 0.5),
        ),
        Point(
            arrow_tip.x - 10 * math.cos(angle + 0.5),
            arrow_tip.y - 10 * math.sin(angle + 0.5),
        ),
    )

    return ((start, shaft_end), points)

def _convoy(convoy_start: Point, move_start: Point, move_end: Point) -> tuple[Point, list[Point]]:
    """
    The convoy curve moves a little off the fleet, and then just oscillates until
    it hits the move line.

    Returns the initial start point again (for consistency), then the list of
    points that make up the curve, including the end point on the move line.
    """

    # Aim for the midpoint of the move arrow. Start just after the unit.
    convoy_end = move_start + (move_end - move_start) * 0.6
    curve_start = convoy_start + (convoy_end - convoy_start) * 0.1

    # How much would you have to rotate a regular sine wave by to get it at
    # the angle of the convoy line?
    theta = math.atan2(convoy_end.y - curve_start.y, convoy_end.x - curve_start.x)

    points = []
    for index in range(41):
        t = index / 40
        p = curve_start + (convoy_end - curve_start) * t
        # Oscillate up and down by a sine wave.
        # Sine wave is just x = t, y = sin(t * freq) * amp
        # Rotation sends x -> x cos(theta) - y sin(theta)
        # y -> x sin(theta) + y cos(theta)
        amp = 5
        freq = 23
        x = p.x + (t * math.cos(theta) - math.sin(t * freq) * amp) * math.sin(theta)
        y = p.y + (t * math.sin(theta) + math.sin(t * freq) * amp) * math.cos(theta)
        points.append(Point(x, y))

    return convoy_start, points


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


def _apply_semantic_detail_fills(
    root: ElementTree.Element,
    map_definition: MapDefinition,
    inaccessible_pattern: str,
) -> None:
    """Colour non-playable map details by their declared terrain role.

    Detail geometry may sit inside a playable territory group, such as water
    through a canal or an impassable island inside a sea. Applying these fills
    after territory ownership keeps the detail independent of its containing
    province without making it a separate rules-engine location.

    :param root: SVG document or subtree containing semantic detail geometry.
    :param map_definition: Map whose presentation palette supplies the colours.
    :param inaccessible_pattern: Generated pattern identifier for inaccessible land.
    """
    colours = {
        "land": map_definition.presentation.unclaimed_region_colour,
        "sea": map_definition.presentation.sea_colour,
        "inaccessible": f"url(#{inaccessible_pattern})",
    }
    for node in root.iter():
        colour = colours.get(node.attrib.get(_SEMANTIC_FILL_ATTRIBUTE, "").casefold())
        if colour is not None:
            _set_fill(node, colour)


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
        _apply_semantic_detail_fills(root, map_definition, inaccessible_pattern)
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
            _apply_semantic_detail_fills(
                root,
                map_definition,
                "gamemaster-inaccessible-stripes",
            )

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

            hotspots: list[MapHotspot] = []
            for projected_order in projected_state.orders:
                order = projected_order.order
                if isinstance(order, MoveOrder):
                    start, end = _move_points(map_definition, order, label_anchors)
                    ((start, shaft_end), points) = _move_line_and_arrow(start, end)
                    arrow_tip, _, _ = points

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

                    ElementTree.SubElement(
                        orders_layer,
                        _tag("polygon"),
                        {"points": " ".join(f"{p.x},{p.y}" for p in points), "fill": "#22251f"},
                    )
                    hotspots.append(
                        MapHotspot(
                            projected_order.source_line,
                            (start, arrow_tip),
                            10.0,
                            projected_order.outcome_codes,
                        )
                    )
            for projected_order in projected_state.orders:
                order = projected_order.order
                if isinstance(order, HoldOrder) or isinstance(order, UnparseableOrder):
                    point = _anchor(map_definition, order.unit)
                    hold_offset = (
                        map_definition.presentation.army_hold_offset
                        if order.unit.unit_type is UnitType.ARMY
                        else map_definition.presentation.fleet_hold_offset
                    )
                    marker_point = Point(point.x + hold_offset.x, point.y + hold_offset.y)
                    ElementTree.SubElement(
                        orders_layer,
                        _tag("line"),
                        {
                            "x1": str(marker_point.x - HOLD_UNDERLINE_HALF_WIDTH),
                            "y1": str(marker_point.y),
                            "x2": str(marker_point.x + HOLD_UNDERLINE_HALF_WIDTH),
                            "y2": str(marker_point.y),
                            "stroke": "#22251f",
                            "stroke-width": str(HOLD_UNDERLINE_STROKE_WIDTH),
                            "stroke-linecap": "round",
                            # For invalid orders, they're a dashed hold
                            "stroke-dasharray": "4 7"
                            if projected_order.is_valid is False
                            else "none",
                            "class": "hold-marker",
                            "data-unit-type": order.unit.unit_type.value,
                        },
                    )
                elif isinstance(order, SupportOrder):
                    start = _anchor(map_definition, order.unit)
                    target = _anchor(map_definition, order.supported_unit)
                    support_class = "support-hold"

                    # Destination is set for Supporting a Move.
                    if order.destination:
                        ## Work out where the move line would be.
                        move_start, move_end = _move_points(map_definition, MoveOrder(order.supported_unit, order.destination), label_anchors)
                        ((move_start, move_end), arrow_points) = _move_line_and_arrow(move_start, move_end)
                        ## Work out where the support line goes.
                        support_end, control, support_join = _support_move_curve_2(
                            start, move_start, move_end
                        )
                        path = (
                            f"M {start.x} {start.y} L {support_end.x} {support_end.y} "
                            f"Q {control.x} {control.y} {support_join.x} {support_join.y} "
                            f"L {move_end.x} {move_end.y}"
                        )
                        support_class = "support-move"

                    # Else support a hold.
                    else:
                        control = Point(
                            (start.x + target.x) / 2,
                            min(start.y, target.y) - abs(target.x - start.x) * 0.16,
                        )
                        path = (
                            f"M {start.x} {start.y} Q {control.x} {control.y} {target.x} {target.y}"
                        )
                    ElementTree.SubElement(
                        orders_layer,
                        _tag("path"),
                        {
                            "d": path,
                            "fill": "none",
                            "stroke": "#3b3d37",
                            "stroke-width": "3",
                            "stroke-dasharray": "3 5",
                            "stroke-linecap": "round",
                            "class": support_class,
                        },
                    )
                elif isinstance(order, ConvoyOrder):
                    start = _anchor(map_definition, order.unit)
                    move_start, move_end = _move_points(map_definition, MoveOrder(order.convoyed_army, order.destination), label_anchors)
                    start, points = _convoy(start, move_start, move_end)
                    ElementTree.SubElement(
                        orders_layer,
                        _tag("path"),
                        {
                            "d": f"M {start.x} {start.y} {' '.join(f'L {p.x} {p.y}' for p in points)}",
                            "fill": "none",
                            "stroke": "#263b4a",
                            "stroke-width": "2.5",
                            "stroke-dasharray": "2 2",
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
