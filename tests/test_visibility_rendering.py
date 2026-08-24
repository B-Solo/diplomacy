from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from xml.etree import ElementTree

from diplomacy_app.domain.models import (
    DisplayMode,
    GameId,
    HiddenTerritory,
    LabelMode,
    MapBounds,
    Perspective,
    PerspectiveKind,
    PhaseSnapshot,
    PixelSize,
    Point,
    ProjectionRequest,
    RenderRequest,
    Revision,
    VisibilityPolicy,
)
from diplomacy_app.presentation import darken_colour
from diplomacy_app.rendering import MapRenderer
from diplomacy_app.rendering.labels import label_lines
from diplomacy_app.rules_engine import StandardRulesEngine
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
    assert artifact.size == PixelSize(640, 480)

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
        for label in root.findall(".//{*}g[@id='territory-labels']/{*}text")
        if "".join(label.itertext()) == "Derbyshire &Nottinghamshire"
    )
    assert [line.text for line in derbyshire.findall("{*}tspan")] == [
        "Derbyshire &",
        "Nottinghamshire",
    ]
    assert derbyshire.attrib["fill"] == "#4c3b1e"
    assert "stroke" not in derbyshire.attrib
    assert label_lines("Short Name") == ("Short Name",)
    assert label_lines("Manual\nBreak") == ("Manual", "Break")
    assert label_lines("A deliberately long line\nSecond line") == (
        "A deliberately long line",
        "Second line",
    )
    coast_labels = root.findall(".//{*}g[@id='coast-labels']/{*}text")
    assert {label.text for label in coast_labels} >= {"North Coast", "South Coast"}
    assert {label.attrib["font-size"] for label in coast_labels} == {"9"}
    assert all("rotate(" in label.attrib["transform"] for label in coast_labels)
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
        for label in abbreviation_root.findall(".//{*}g[@id='territory-labels']/{*}text")
        if "".join(label.itertext()) == territory.abbreviation
    )
    assert rendered_abbreviation.attrib["x"] == str(abbreviation_anchor.x)
    assert rendered_abbreviation.attrib["y"] == str(abbreviation_anchor.y)

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
        for label in display_root.findall(".//{*}g[@id='territory-labels']/{*}text")
        if "".join(label.itertext()) == "Chosen first lineChosen second line"
    )
    assert [line.text for line in displayed.findall("{*}tspan")] == [
        "Chosen first line",
        "Chosen second line",
    ]
    rendered_lines = displayed.findall("{*}tspan")
    assert len({line.attrib["y"] for line in rendered_lines}) == 2
    assert all("dy" not in line.attrib for line in rendered_lines)
    assert displayed.attrib["font-size"] == "12.5"
    assert displayed.attrib["fill"] == "#201810"
    assert {
        label.attrib["font-size"]
        for label in display_root.findall(".//{*}g[@id='coast-labels']/{*}text")
    } == {"8.5"}
    assert {
        label.attrib["fill"]
        for label in display_root.findall(".//{*}g[@id='coast-labels']/{*}text")
    } == {"#201810"}
    assert {
        label.attrib["font-weight"]
        for label in display_root.findall(".//{*}g[@id='coast-labels']/{*}text")
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
