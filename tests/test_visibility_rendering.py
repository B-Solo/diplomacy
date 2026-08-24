from __future__ import annotations

import base64
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
    ProjectionRequest,
    RenderRequest,
    Revision,
    VisibilityPolicy,
)
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
    derbyshire = next(
        label
        for label in root.findall(".//{*}g[@id='territory-labels']/{*}text")
        if "".join(label.itertext()) == "Derbyshire &Nottinghamshire"
    )
    assert [line.text for line in derbyshire.findall("{*}tspan")] == [
        "Derbyshire &",
        "Nottinghamshire",
    ]
    assert label_lines("Short Name") == ("Short Name",)
    assert label_lines("Manual\nBreak") == ("Manual", "Break")
    coast_labels = root.findall(".//{*}g[@id='coast-labels']/{*}text")
    assert {label.text for label in coast_labels} >= {"North Coast", "South Coast"}
    assert all("rotate(" in label.attrib["transform"] for label in coast_labels)
    asset_view_boxes = {
        ElementTree.fromstring(asset).attrib["viewBox"]
        for asset in (england.assets.army_svg, england.assets.fleet_svg)
    }
    unit_images = root.findall(".//{*}g[@id='units']/{*}image")
    assert unit_images
    for image in unit_images:
        embedded = ElementTree.fromstring(base64.b64decode(image.attrib["href"].partition(",")[2]))
        assert embedded.attrib["viewBox"] in asset_view_boxes
        assert "width" not in embedded.attrib
        assert "height" not in embedded.attrib
        assert image.attrib["preserveAspectRatio"] == "xMidYMid meet"
