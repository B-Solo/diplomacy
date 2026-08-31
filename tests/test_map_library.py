from __future__ import annotations

import json

import pytest

from diplomacy_app.domain.errors import MapLibraryError
from diplomacy_app.domain.models import CoastId, Location, MapId, Point, SvgElementRole, TerritoryId
from diplomacy_app.map_library import FileMapLibrary, map_codec
from diplomacy_app.map_library.defaults import DEFAULT_ARMY_SVG, DEFAULT_FLEET_SVG
from diplomacy_app.map_library.svg_importer import sanitise_svg, shape_ids, territory_geometries
from diplomacy_app.storage.serialization import map_definition_data, map_definition_from_data


def test_england_compiles_complete_valid_topology(project_root, england):
    library = FileMapLibrary(project_root / "maps")
    draft = library.load_draft(MapId("england"))
    assert library.validate(draft).is_valid
    assert set(england.presentation.abbreviation_anchors) == set(england.presentation.label_anchors)
    assert england.presentation.abbreviation_anchors != england.presentation.label_anchors
    assert len(england.territories) == 74
    assert sum(item.is_supply_centre for item in england.territories) == 34
    assert len(england.powers) == 6
    assert len(england.adjacencies) == 480
    assert "impassable-scotland" in england.inaccessible_svg_element_ids
    devon_north = Location(TerritoryId("devon"), CoastId("north"))
    assert devon_north in england.presentation.coast_label_anchors
    assert england.presentation.coast_label_rotations[devon_north] == -50
    legacy_data = map_definition_data(england)
    round_tripped = map_definition_from_data(legacy_data, england.assets)
    assert round_tripped.inaccessible_svg_element_ids == england.inaccessible_svg_element_ids
    assert round_tripped.presentation.army_hold_offset == Point(-2, 11)
    assert round_tripped.presentation.fleet_hold_offset == Point(0, 8)
    legacy_data["presentation"].pop("hold_underlines")
    legacy_data["presentation"].pop("coast_labels")
    legacy_data["presentation"].pop("abbreviations")
    legacy_data["presentation"].pop("territory_label_font_size")
    legacy_data["presentation"].pop("coast_label_font_size")
    legacy_data["presentation"].pop("inaccessible_region_colour")
    legacy_data["presentation"].pop("sea_colour")
    legacy_data["presentation"].pop("unclaimed_region_colour")
    legacy_data["presentation"].pop("label_colour", None)
    legacy_data.pop("inaccessible_svg_elements")
    for territory in legacy_data["territories"]:
        territory.pop("display_name")
    restored = map_definition_from_data(legacy_data, england.assets)
    assert devon_north in restored.presentation.coast_label_anchors
    assert restored.presentation.abbreviation_anchors == restored.presentation.label_anchors
    assert restored.presentation.territory_label_font_size == 11
    assert restored.presentation.coast_label_font_size == 9
    assert restored.presentation.inaccessible_region_colour == "#777870"
    assert restored.presentation.sea_colour == "#9ebbd2"
    assert restored.presentation.unclaimed_region_colour == "#d0c9aa"
    assert restored.presentation.label_colour == "#4c3b1e"
    assert restored.presentation.army_hold_offset == Point(0, 13)
    assert restored.presentation.fleet_hold_offset == Point(0, 13)
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
    library = FileMapLibrary(tmp_path / "maps")
    draft = library.import_svg("Tiny map", svg)
    assert library.preview_definition(draft).assets.army_svg == DEFAULT_ARMY_SVG
    assert library.preview_definition(draft).assets.fleet_svg == DEFAULT_FLEET_SVG
    assert (project_root / "maps/england/army.svg").read_bytes() == DEFAULT_ARMY_SVG
    assert (project_root / "maps/england/fleet.svg").read_bytes() == DEFAULT_FLEET_SVG
    assert draft.element_roles["territory-alpha"] is SvgElementRole.TERRITORY
    assert draft.element_roles["region-beta"] is SvgElementRole.DECORATION
    promoted = library.update_element_role(draft, "region-beta", SvgElementRole.TERRITORY)
    assert len(promoted.territories) == 2


def test_import_assigns_unique_abbreviations_to_similarly_named_territories(tmp_path):
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">
      <path id="territory-alpha" d="M0 0 L50 0 L50 50 L0 50 Z"/>
      <path id="territory-alps" d="M50 0 L100 0 L100 50 L50 50 Z"/>
    </svg>"""
    library = FileMapLibrary(tmp_path / "maps")

    draft = library.import_svg("Tiny map", svg)

    assert library.validate(draft).is_valid
    abbreviations = {territory.abbreviation.casefold() for territory in draft.territories}
    assert len(abbreviations) == len(draft.territories)


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


def test_save_preserves_ancillary_files_and_loads_current_cache(configured_maps, monkeypatch):
    library = configured_maps
    map_id = library.list()[0].map_id
    folder = library.maps_root / str(map_id)
    provenance = (folder / "SOURCE.md").read_bytes()
    draft = library.load_draft(map_id)
    territory_id, point = next(iter(draft.presentation.label_anchors.items()))
    saved = library.save(
        library.update_anchor(draft, territory_id, "label", Point(point.x + 1, point.y + 1))
    )

    payload = json.loads((folder / "_compiled-map.json").read_text(encoding="utf-8"))
    assert payload["source"]["cache_version"] == 1
    assert len(payload["source"]["digest"]) == 64
    assert (folder / "SOURCE.md").read_bytes() == provenance

    def fail_compilation(_text, _svg):
        raise AssertionError("A current compiled cache should avoid source compilation")

    monkeypatch.setattr(map_codec, "compile_map", fail_compilation)
    assert library.load(map_id) == saved


def test_stale_compiled_cache_is_not_authoritative(configured_maps):
    library = configured_maps
    map_id = library.list()[0].map_id
    folder = library.maps_root / str(map_id)
    draft = library.load_draft(map_id)
    library.save(draft)
    payload = json.loads((folder / "_compiled-map.json").read_text(encoding="utf-8"))
    payload["name"] = "Stale compiled name"
    payload["source"]["digest"] = "0" * 64
    (folder / "_compiled-map.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert library.load(map_id).name == draft.name
