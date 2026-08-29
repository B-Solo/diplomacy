from __future__ import annotations

import math
from dataclasses import replace
from types import MappingProxyType
from xml.etree import ElementTree

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QGraphicsScene

from diplomacy_app.domain.models import (
    DislodgedUnit,
    DisplayMode,
    GameId,
    HiddenTerritory,
    LabelMode,
    MapBounds,
    MoveOrder,
    Perspective,
    PerspectiveKind,
    PhaseSnapshot,
    PixelSize,
    Point,
    ProjectedMapState,
    ProjectionRequest,
    RenderRequest,
    Revision,
    VisibilityPolicy,
)
from diplomacy_app.order_processing import OrderProcessor
from diplomacy_app.presentation import (
    HOLD_UNDERLINE_STROKE_WIDTH,
    aspect_fitted_size,
    darken_colour,
)
from diplomacy_app.rendering import MapRenderer
from diplomacy_app.rendering.labels import label_lines
from diplomacy_app.rules_engine import StandardRulesEngine
from diplomacy_app.ui.map_canvas import TextAnchorItem
from diplomacy_app.visibility import VisibilityProjector


def phase_for(england):
    setup = england.default_starting_setup
    return PhaseSnapshot(
        GameId("visibility"),
        setup.phase_id,
        setup.state,
        MappingProxyType({}),
        (),
        Revision("test"),
    )


def test_power_projection_has_discriminated_hidden_values(england):
    phase = phase_for(england)
    engine = StandardRulesEngine()
    power = england.powers[0]
    projection = VisibilityProjector().project(
        england,
        phase,
        engine.effective_orders(england, phase),
        VisibilityPolicy(True, 1),
        ProjectionRequest(
            Perspective(PerspectiveKind.POWER, power.id),
            LabelMode.ABBREVIATION,
            True,
            True,
        ),
    )
    hidden = [item for item in projection.territories if isinstance(item, HiddenTerritory)]
    assert hidden
    assert all(not hasattr(item, "controller") for item in hidden)
    assert all(
        order.order.unit.location.territory_id not in {item.territory_id for item in hidden}
        for order in projection.orders
        if hasattr(order.order, "unit")
    )


def test_retreat_projection_keeps_previous_position_and_movement_overlay(england):
    engine = StandardRulesEngine()
    processor = OrderProcessor(engine)
    spring = phase_for(england)
    power = england.powers[0]
    submission = processor.prepare_submission(england, spring, power.id, "A Cheshire - Shropshire")
    spring = replace(spring, submissions=MappingProxyType({power.id: submission}))
    summer_proposal = engine.adjudicate(england, spring)
    summer = PhaseSnapshot(
        spring.game_id,
        summer_proposal.next_phase,
        summer_proposal.next_state,
        MappingProxyType({}),
        (),
        spring.revision,
        summer_proposal.next_resolution_state,
    )
    previous_orders = engine.effective_orders(england, spring)
    effective_movement = next(item for item in previous_orders if isinstance(item.order, MoveOrder))
    projection = VisibilityProjector().project(
        england,
        summer,
        engine.effective_orders(england, summer),
        VisibilityPolicy(False, 1),
        ProjectionRequest(
            Perspective(PerspectiveKind.GAMEMASTER),
            LabelMode.FULL_NAME,
            True,
            True,
        ),
        previous_orders,
        summer_proposal.results,
    )

    cheshire = next(item for item in projection.territories if item.territory_id == "cheshire")
    shropshire = next(item for item in projection.territories if item.territory_id == "shropshire")
    movement = next(item for item in projection.orders if isinstance(item.order, MoveOrder))

    assert cheshire.unit is not None
    assert cheshire.unit.location.territory_id == "cheshire"
    assert shropshire.unit is None
    assert movement.order.destination.territory_id == "shropshire"

    assert summer.resolution_state is not None
    dislodged_summer = replace(
        summer,
        resolution_state=replace(
            summer.resolution_state,
            dislodged_units=(DislodgedUnit(spring.state.units[0], ()),),
        ),
    )
    dislodged_projection = VisibilityProjector().project(
        england,
        dislodged_summer,
        engine.effective_orders(england, dislodged_summer),
        VisibilityPolicy(False, 1),
        ProjectionRequest(
            Perspective(PerspectiveKind.GAMEMASTER),
            LabelMode.FULL_NAME,
            True,
            False,
        ),
    )
    projected_cheshire = next(
        item for item in dislodged_projection.territories if item.territory_id == "cheshire"
    )
    assert projected_cheshire.unit is None
    assert projected_cheshire.dislodged_unit == spring.state.units[0]

    filtered = VisibilityProjector().project(
        england,
        summer,
        (),
        VisibilityPolicy(False, 1),
        ProjectionRequest(
            Perspective(PerspectiveKind.GAMEMASTER),
            LabelMode.FULL_NAME,
            True,
            True,
            True,
        ),
        (effective_movement,),
        (
            replace(
                next(item for item in summer_proposal.results if isinstance(item.order, MoveOrder)),
                outcome_codes=("BOUNCE",),
            ),
        ),
    )
    assert not any(isinstance(item.order, MoveOrder) for item in filtered.orders)


def test_exported_multiline_label_paints_two_distinct_lines(qapp, england):
    territory = england.territories[0]
    outside = Point(-1000, -1000)
    label_anchors = {item.id: outside for item in england.territories}
    label_anchors[territory.id] = Point(100, 50)
    presentation = replace(
        england.presentation,
        label_anchors=MappingProxyType(label_anchors),
        coast_label_anchors=MappingProxyType(
            {location: outside for location in england.presentation.coast_label_anchors}
        ),
        territory_label_font_size=14,
        label_colour="#000000",
    )
    minimal_map = replace(
        england,
        presentation=presentation,
        assets=replace(
            england.assets,
            map_svg=(
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
                b'<rect width="200" height="100" fill="#ffffff"/></svg>'
            ),
        ),
    )
    projection = ProjectedMapState(
        england.default_starting_setup.phase_id,
        Perspective(PerspectiveKind.GAMEMASTER),
        tuple(
            HiddenTerritory(
                item.id,
                "FIRST LINE\nSECOND LINE" if item.id == territory.id else "",
            )
            for item in england.territories
        ),
        (),
        (),
    )
    request = RenderRequest(
        DisplayMode.POSITION,
        LabelMode.FULL_NAME,
        MapBounds(0, 0, 200, 100),
        PixelSize(200, 100),
    )
    renderer = MapRenderer()
    image = QImage.fromData(
        renderer.export(renderer.compose(minimal_map, projection, request), request).data
    )
    assert not image.isNull()

    placement = QImage(200, 100, QImage.Format.Format_ARGB32)
    placement.fill(QColor("white"))
    placement_scene = QGraphicsScene()
    placement_scene.setSceneRect(0, 0, 200, 100)
    placement_scene.addItem(
        TextAnchorItem(
            Point(100, 50),
            "FIRST LINE\nSECOND LINE",
            "#000000",
            lambda _point: None,
            size=14,
            bold=True,
        )
    )
    painter = QPainter(placement)
    placement_scene.render(
        painter,
        QRectF(0, 0, 200, 100),
        QRectF(0, 0, 200, 100),
    )
    painter.end()

    def dark_pixel_bounds(value: QImage) -> tuple[int, int, int, int]:
        pixels = [
            (x, y)
            for y in range(value.height())
            for x in range(value.width())
            if max(
                value.pixelColor(x, y).red(),
                value.pixelColor(x, y).green(),
                value.pixelColor(x, y).blue(),
            )
            < 100
        ]
        return (
            min(x for x, _y in pixels),
            min(y for _x, y in pixels),
            max(x for x, _y in pixels),
            max(y for _x, y in pixels),
        )

    assert dark_pixel_bounds(placement) == dark_pixel_bounds(image)
    dark_rows = [
        y
        for y in range(image.height())
        if any(
            max(
                image.pixelColor(x, y).red(),
                image.pixelColor(x, y).green(),
                image.pixelColor(x, y).blue(),
            )
            < 100
            for x in range(image.width())
        )
    ]
    row_groups: list[list[int]] = []
    for row in dark_rows:
        if not row_groups or row > row_groups[-1][-1] + 1:
            row_groups.append([])
        row_groups[-1].append(row)
    assert len(row_groups) == 2


def test_order_graphics(england):
    england = replace(
        england,
        presentation=replace(
            england.presentation,
            army_hold_offset=Point(4, 16),
            fleet_hold_offset=Point(-3, 18),
        ),
    )
    phase = phase_for(england)
    engine = StandardRulesEngine()
    power = england.powers[0]
    move_submission = OrderProcessor(engine).prepare_submission(
        england,
        phase,
        power.id,
        "A Merseyside - Greater Manchester",
    )
    up_north = next(item for item in england.powers if item.name == "Up North")
    support_submission = OrderProcessor(engine).prepare_submission(
        england,
        phase,
        up_north.id,
        "A DUR S A NBL - CUM\nA NBL - CUM",
    )
    phase = replace(
        phase,
        submissions=MappingProxyType({power.id: move_submission, up_north.id: support_submission}),
    )
    projection = VisibilityProjector().project(
        england,
        phase,
        engine.effective_orders(england, phase),
        VisibilityPolicy(False, 1),
        ProjectionRequest(
            Perspective(PerspectiveKind.GAMEMASTER),
            LabelMode.FULL_NAME,
            True,
            False,
        ),
    )
    request = RenderRequest(
        DisplayMode.ORDERS,
        LabelMode.FULL_NAME,
        MapBounds(0, 0, 1013, 1026),
        PixelSize(640, 480),
    )
    root = ElementTree.fromstring(MapRenderer().compose(england, projection, request).svg)
    orders = next(group for group in root.findall(".//{*}g") if group.attrib.get("id") == "orders")
    move_line = orders.find("{*}line")
    arrowhead = orders.find("{*}polygon")
    assert move_line is not None
    assert arrowhead is not None
    assert move_line.attrib["stroke-linecap"] == "butt"
    tip_x, tip_y = arrowhead.attrib["points"].split()[0].split(",")
    assert (move_line.attrib["x2"], move_line.attrib["y2"]) != (tip_x, tip_y)
    support_move = orders.find("{*}path[@class='support-move']")
    assert support_move is not None
    assert support_move.attrib["stroke-width"] == move_line.attrib["stroke-width"] == "3"
    assert support_move.attrib["stroke-linecap"] == "round"
    path_values = support_move.attrib["d"].split()
    assert path_values[3] == "C"
    first_control = Point(float(path_values[4]), float(path_values[5]))
    second_control = Point(float(path_values[6]), float(path_values[7]))
    target = Point(float(path_values[8]), float(path_values[9]))
    durham = next(item for item in england.territories if item.abbreviation == "Dur")
    northumberland = next(item for item in england.territories if item.abbreviation == "Nbl")
    cumbria = next(item for item in england.territories if item.abbreviation == "Cum")
    supporting_start = england.presentation.army_anchors[durham.id]
    supported_start = england.presentation.army_anchors[northumberland.id]
    supported_end = england.presentation.army_anchors[cumbria.id]
    approach = Point(target.x - second_control.x, target.y - second_control.y)
    move = Point(supported_end.x - supported_start.x, supported_end.y - supported_start.y)
    assert approach.x * move.y - approach.y * move.x == pytest.approx(0, abs=1e-9)
    assert approach.x * move.x + approach.y * move.y > 0
    assert 24 <= math.hypot(approach.x, approach.y) <= 48
    chord = Point(target.x - supporting_start.x, target.y - supporting_start.y)
    first_handle = Point(
        first_control.x - supporting_start.x,
        first_control.y - supporting_start.y,
    )
    assert abs(first_handle.x * chord.y - first_handle.y * chord.x) > 1
    assert math.hypot(target.x - supported_end.x, target.y - supported_end.y) > 20
    hold_markers = [
        line for line in orders.findall("{*}line") if line.attrib.get("class") == "hold-marker"
    ]
    assert len(hold_markers) == len(phase.state.units) - 3
    assert {marker.attrib["stroke-dasharray"] for marker in hold_markers} == {"none"}
    assert all(marker.attrib["y1"] == marker.attrib["y2"] for marker in hold_markers)
    assert {float(marker.attrib["stroke-width"]) for marker in hold_markers} == {
        HOLD_UNDERLINE_STROKE_WIDTH
    }
    assert {marker.attrib["data-unit-type"] for marker in hold_markers} == {"army", "fleet"}
    army_marker = next(
        marker for marker in hold_markers if marker.attrib["data-unit-type"] == "army"
    )
    army_midpoint = (
        (float(army_marker.attrib["x1"]) + float(army_marker.attrib["x2"])) / 2,
        float(army_marker.attrib["y1"]),
    )
    assert any(
        army_midpoint == pytest.approx((anchor.x + 4, anchor.y + 16))
        for anchor in england.presentation.army_anchors.values()
    )
    fleet_marker = next(
        marker for marker in hold_markers if marker.attrib["data-unit-type"] == "fleet"
    )
    fleet_midpoint = (
        (float(fleet_marker.attrib["x1"]) + float(fleet_marker.attrib["x2"])) / 2,
        float(fleet_marker.attrib["y1"]),
    )
    assert any(
        fleet_midpoint == pytest.approx((anchor.x - 3, anchor.y + 18))
        for anchor in england.presentation.fleet_anchors.values()
    )


def test_renderer_composes_safe_scene_and_exact_png(qapp, england):
    phase = phase_for(england)
    engine = StandardRulesEngine()
    projection = VisibilityProjector().project(
        england,
        phase,
        engine.effective_orders(england, phase),
        VisibilityPolicy(False, 1),
        ProjectionRequest(
            Perspective(PerspectiveKind.GAMEMASTER), LabelMode.FULL_NAME, True, False
        ),
    )
    request = RenderRequest(
        DisplayMode.ORDERS,
        LabelMode.FULL_NAME,
        MapBounds(0, 0, 1013, 1026),
        PixelSize(640, 480),
    )
    renderer = MapRenderer()
    scene = renderer.compose(england, projection, request)
    assert b"gamemaster-layers" in scene.svg
    assert b"<script" not in scene.svg.lower()
    artifact = renderer.export(scene, request)
    assert artifact.media_type == "image/png"
    assert artifact.data.startswith(b"\x89PNG")
    assert artifact.size == aspect_fitted_size(scene.map_bounds, request.output_size)
    artifact_image = QImage.fromData(artifact.data)
    assert (artifact_image.width(), artifact_image.height()) == (
        artifact.size.width,
        artifact.size.height,
    )
    assert artifact.size.width / artifact.size.height == pytest.approx(
        scene.map_bounds.width / scene.map_bounds.height,
        abs=1 / artifact.size.height,
    )

    root = ElementTree.fromstring(scene.svg)
    unit_layer = next(
        group for group in root.findall(".//{*}g") if group.attrib.get("id") == "units"
    )
    unit_symbols = [
        group for group in unit_layer.findall("{*}g") if group.attrib.get("class") == "unit-symbol"
    ]
    assert len(unit_symbols) == len(phase.state.units)
    assert not unit_layer.findall("{*}image")
    assert all(symbol.findall(".//{*}path") for symbol in unit_symbols)
    derbyshire = next(
        label
        for label in root.findall(".//{*}g[@id='territory-labels']/{*}g")
        if "".join(line.text or "" for line in label.findall("{*}text"))
        == "Derbyshire &Nottinghamshire"
    )
    assert [line.text for line in derbyshire.findall("{*}text")] == [
        "Derbyshire &",
        "Nottinghamshire",
    ]
    assert {line.attrib["fill"] for line in derbyshire.findall("{*}text")} == {"#4c3b1e"}
    assert all("stroke" not in line.attrib for line in derbyshire.findall("{*}text"))
    assert label_lines("Short Name") == ("Short Name",)
    assert label_lines("Manual\nBreak") == ("Manual", "Break")
    assert label_lines("A deliberately long line\nSecond line") == (
        "A deliberately long line",
        "Second line",
    )
    coast_groups = root.findall(".//{*}g[@id='coast-labels']/{*}g")
    coast_labels = [line for group in coast_groups if (line := group.find("{*}text")) is not None]
    assert len(coast_labels) == len(coast_groups)
    assert {label.text for label in coast_labels} >= {"North Coast", "South Coast"}
    assert {label.attrib["font-size"] for label in coast_labels} == {"9"}
    assert all(
        "transform" not in group.attrib or "rotate(" in group.attrib["transform"]
        for group in coast_groups
    )
    assert all(label.attrib["fill"] == "#4c3b1e" for label in coast_labels)
    assert all("stroke" not in label.attrib for label in coast_labels)
    centre_stars = root.findall(".//{*}g[@id='supply-centres']/{*}polygon")
    assert centre_stars
    assert all(len(star.attrib["points"].split()) == 10 for star in centre_stars)
    assert all(star.attrib["stroke-width"] == "1.25" for star in centre_stars)
    assert all(star.attrib["stroke-linejoin"] == "miter" for star in centre_stars)
    powers = {str(power.id): power for power in england.powers}
    owners = {
        str(territory_id): str(owner) if owner is not None else None
        for territory_id, owner in phase.state.supply_centre_owners.items()
    }
    owned_star = next(
        star for star in centre_stars if owners[star.attrib["data-territory"]] in powers
    )
    owner = owners[owned_star.attrib["data-territory"]]
    assert owner is not None
    assert owned_star.attrib["fill"] == darken_colour(powers[owner].colour, 0.82)
    territory = england.territories[0]
    abbreviation_anchor = Point(17, 29)
    abbreviation_anchors = dict(england.presentation.abbreviation_anchors)
    abbreviation_anchors[territory.id] = abbreviation_anchor
    abbreviation_map = replace(
        england,
        presentation=replace(
            england.presentation,
            abbreviation_anchors=MappingProxyType(abbreviation_anchors),
        ),
    )
    abbreviation_projection = VisibilityProjector().project(
        abbreviation_map,
        phase,
        engine.effective_orders(abbreviation_map, phase),
        VisibilityPolicy(False, 1),
        ProjectionRequest(
            Perspective(PerspectiveKind.GAMEMASTER),
            LabelMode.ABBREVIATION,
            True,
            False,
        ),
    )
    abbreviation_scene = renderer.compose(
        abbreviation_map,
        abbreviation_projection,
        replace(request, label_mode=LabelMode.ABBREVIATION),
    )
    abbreviation_root = ElementTree.fromstring(abbreviation_scene.svg)
    rendered_abbreviation = next(
        label
        for label in abbreviation_root.findall(".//{*}g[@id='territory-labels']/{*}g")
        if "".join(line.text or "" for line in label.findall("{*}text")) == territory.abbreviation
    )
    abbreviation_line = rendered_abbreviation.find("{*}text")
    assert abbreviation_line is not None
    assert abbreviation_line.attrib["x"] == str(abbreviation_anchor.x)
    assert abbreviation_line.attrib["y"] == str(abbreviation_anchor.y)

    display_territory = replace(territory, display_name="Chosen first line\nChosen second line")
    display_map = replace(
        england,
        territories=tuple(
            display_territory if item.id == territory.id else item for item in england.territories
        ),
        presentation=replace(
            england.presentation,
            territory_label_font_size=12.5,
            coast_label_font_size=8.5,
            label_colour="#201810",
            inaccessible_region_colour="#303030",
            sea_colour="#406080",
            unclaimed_region_colour="#d8c8a8",
        ),
    )
    display_projection = VisibilityProjector().project(
        display_map,
        phase,
        engine.effective_orders(display_map, phase),
        VisibilityPolicy(False, 1),
        ProjectionRequest(
            Perspective(PerspectiveKind.GAMEMASTER),
            LabelMode.FULL_NAME,
            True,
            False,
        ),
    )
    display_scene = renderer.compose(display_map, display_projection, request)
    display_root = ElementTree.fromstring(display_scene.svg)
    displayed = next(
        label
        for label in display_root.findall(".//{*}g[@id='territory-labels']/{*}g")
        if "".join(line.text or "" for line in label.findall("{*}text"))
        == "Chosen first lineChosen second line"
    )
    rendered_lines = displayed.findall("{*}text")
    assert [line.text for line in rendered_lines] == [
        "Chosen first line",
        "Chosen second line",
    ]
    assert len({line.attrib["y"] for line in rendered_lines}) == 2
    assert all(line.attrib["font-size"] == "12.5" for line in rendered_lines)
    assert all(line.attrib["fill"] == "#201810" for line in rendered_lines)
    assert {
        label.attrib["font-size"]
        for label in display_root.findall(".//{*}g[@id='coast-labels']/{*}g/{*}text")
    } == {"8.5"}
    assert {
        label.attrib["fill"]
        for label in display_root.findall(".//{*}g[@id='coast-labels']/{*}g/{*}text")
    } == {"#201810"}
    assert {
        label.attrib["font-weight"]
        for label in display_root.findall(".//{*}g[@id='coast-labels']/{*}g/{*}text")
    } == {"700"}
    inaccessible = next(
        node for node in display_root.iter() if node.attrib.get("id") == "impassable-scotland"
    )
    sea = next(item for item in display_map.territories if item.kind.value == "sea")
    sea_node = next(
        node for node in display_root.iter() if node.attrib.get("id") == sea.svg_element_id
    )
    unclaimed = next(
        item
        for item in display_map.territories
        if item.kind.value == "land" and phase.state.territory_controllers.get(item.id) is None
    )
    unclaimed_node = next(
        node for node in display_root.iter() if node.attrib.get("id") == unclaimed.svg_element_id
    )
    assert inaccessible.attrib["style"].endswith("fill:url(#gamemaster-inaccessible-stripes)")
    assert sea_node.attrib["style"].endswith("fill:#406080")
    assert unclaimed_node.attrib["style"].endswith("fill:#d8c8a8")
