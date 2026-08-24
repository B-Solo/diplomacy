from __future__ import annotations

import pytest

from diplomacy_app.domain.errors import MapLibraryError
from diplomacy_app.domain.models import CoastId, Location, MapId, SvgElementRole, TerritoryId
from diplomacy_app.map_library import FileMapLibrary
from diplomacy_app.map_library.defaults import DEFAULT_FLEET_SVG
from diplomacy_app.map_library.svg_importer import sanitise_svg, shape_ids, territory_geometries
from diplomacy_app.storage.serialization import map_definition_data, map_definition_from_data


def test_england_compiles_complete_valid_topology(project_root, england):
    library = FileMapLibrary(
        user_maps_root=project_root / ".test-user-maps",
        bundled_maps_root=project_root / "maps",
    )
    draft = library.load_draft(MapId("england"))
    assert library.validate(draft).is_valid
    assert england.presentation.abbreviation_anchors == england.presentation.label_anchors
    assert len(england.territories) == 74
    assert sum(item.is_supply_centre for item in england.territories) == 34
    assert len(england.powers) == 6
    assert len(england.adjacencies) == 480
    devon_north = Location(TerritoryId("devon"), CoastId("north"))
    assert devon_north in england.presentation.coast_label_anchors
    assert england.presentation.coast_label_rotations[devon_north] == 0
    legacy_data = map_definition_data(england)
    legacy_data["presentation"].pop("coast_labels")
    legacy_data["presentation"].pop("abbreviations")
    legacy_data["presentation"].pop("territory_label_font_size")
    legacy_data["presentation"].pop("coast_label_font_size")
    for territory in legacy_data["territories"]:
        territory.pop("display_name")
    restored = map_definition_from_data(legacy_data, england.assets)
    assert devon_north in restored.presentation.coast_label_anchors
    assert restored.presentation.abbreviation_anchors == restored.presentation.label_anchors
    assert restored.presentation.territory_label_font_size == 11
    assert restored.presentation.coast_label_font_size == 9
    assert all(item.display_name == item.name for item in restored.territories)
    assert all(
        type(edge)(edge.destination, edge.origin, edge.unit_type) in england.adjacencies
        for edge in england.adjacencies
    )


@pytest.mark.parametrize(
    "payload",
    [
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.com/a.png"/></svg>',
        b'<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg"/>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><path id="x"/><path id="x"/></svg>',
    ],
)
def test_svg_sanitiser_rejects_active_or_ambiguous_content(payload):
    with pytest.raises(MapLibraryError):
        sanitise_svg(payload)


def test_import_classifies_and_can_promote_structured_shapes(tmp_path, project_root):
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">
      <path id="territory-alpha" d="M0 0 L50 0 L50 50 L0 50 Z"/>
      <path id="region-beta" d="M50 0 L100 0 L100 50 L50 50 Z"/>
    </svg>"""
    library = FileMapLibrary(tmp_path / "user", tmp_path / "bundled")
    draft = library.import_svg("Tiny map", svg)
    assert library.preview_definition(draft).assets.fleet_svg == DEFAULT_FLEET_SVG
    assert (project_root / "maps/england/fleet.svg").read_bytes() == DEFAULT_FLEET_SVG
    assert draft.element_roles["territory-alpha"] is SvgElementRole.TERRITORY
    assert draft.element_roles["region-beta"] is SvgElementRole.DECORATION
    promoted = library.update_element_role(draft, "region-beta", SvgElementRole.TERRITORY)
    assert len(promoted.territories) == 2


def test_svg_group_can_be_used_as_one_territory():
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">
      <g id="territory-islands">
        <path id="west-island" d="M0 0 L40 0 L40 40 L0 40 Z"/>
        <path id="east-island" d="M60 0 L100 0 L100 40 L60 40 Z"/>
      </g>
    </svg>"""
    assert "territory-islands" in shape_ids(svg)
    geometry = territory_geometries(svg, ["territory-islands"])["territory-islands"]
    assert geometry.area == 3200
    assert len(geometry.geoms) == 2
