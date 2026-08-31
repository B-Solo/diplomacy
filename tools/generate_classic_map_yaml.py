#!/usr/bin/env python3
"""Generate a best-effort standard Diplomacy setup for the classic SVG."""

from __future__ import annotations

from pathlib import Path

import yaml
from reconstruct_classic_map import PROVINCES, SEA_PROVINCES

from diplomacy_app.map_library.svg_importer import sanitise_svg, territory_geometries

NAMES = dict(
    item.split("|", 1)
    for item in """
adr|Adriatic Sea
aeg|Aegean Sea
alb|Albania
ank|Ankara
apu|Apulia
arm|Armenia
bal|Baltic Sea
bar|Barents Sea
bel|Belgium
ber|Berlin
bla|Black Sea
boh|Bohemia
bot|Gulf of Bothnia
bre|Brest
bud|Budapest
bul|Bulgaria
bur|Burgundy
cly|Clyde
con|Constantinople
den|Denmark
eas|Eastern Mediterranean
edi|Edinburgh
eng|English Channel
fin|Finland
gal|Galicia
gas|Gascony
gol|Gulf of Lyon
gre|Greece
hel|Helgoland Bight
hol|Holland
ion|Ionian Sea
iri|Irish Sea
kie|Kiel
lon|London
lvn|Livonia
lvp|Liverpool
mar|Marseilles
mid|Mid-Atlantic Ocean
mos|Moscow
mun|Munich
naf|North Africa
nap|Naples
nat|North Atlantic Ocean
nrg|Norwegian Sea
nth|North Sea
nwy|Norway
par|Paris
pic|Picardy
pie|Piedmont
por|Portugal
pru|Prussia
rom|Rome
ruh|Ruhr
rum|Rumania
ser|Serbia
sev|Sevastopol
sil|Silesia
ska|Skagerrak
smy|Smyrna
spa|Spain
stp|St Petersburg
swe|Sweden
syr|Syria
tri|Trieste
tun|Tunis
tus|Tuscany
tyn|Tyrrhenian Sea
tyr|Tyrolia
ukr|Ukraine
ven|Venice
vie|Vienna
wal|Wales
war|Warsaw
wes|Western Mediterranean
yor|Yorkshire
""".strip().splitlines()
)

COASTAL = {
    "alb", "ank", "apu", "arm", "bel", "ber", "bre", "bul", "cly", "con", "den",
    "edi", "fin", "gas", "gre", "hol", "kie", "lon", "lvn", "lvp", "mar", "naf",
    "nap", "nwy", "pic", "pie", "por", "pru", "rom", "rum", "sev", "smy", "spa",
    "stp", "swe", "syr", "tri", "tus", "ven", "wal", "yor",
}
SUPPLY_CENTRES = {
    "ank", "bel", "ber", "bre", "bud", "bul", "con", "den", "edi", "gre", "hol",
    "kie", "lon", "lvp", "mar", "mos", "mun", "nap", "nwy", "par", "por", "rom",
    "rum", "ser", "sev", "smy", "spa", "stp", "swe", "tri", "tun", "ven", "vie", "war",
}

TEAMS = {
    "austria": ("Austria", "#b36b35", ["bud", "tri", "vie"], [("army", "bud"), ("army", "vie"), ("fleet", "tri")]),
    "england": ("England", "#4d76a8", ["edi", "lon", "lvp"], [("fleet", "edi"), ("fleet", "lon"), ("army", "lvp")]),
    "france": ("France", "#5c8d5a", ["bre", "mar", "par"], [("fleet", "bre"), ("army", "mar"), ("army", "par")]),
    "germany": ("Germany", "#777777", ["ber", "kie", "mun"], [("army", "ber"), ("fleet", "kie"), ("army", "mun")]),
    "italy": ("Italy", "#b05a50", ["nap", "rom", "ven"], [("fleet", "nap"), ("army", "rom"), ("army", "ven")]),
    "russia": ("Russia", "#6e6eaa", ["mos", "sev", "stp", "war"], [("army", "mos"), ("fleet", "sev"), ("fleet", "stp/sc"), ("army", "war")]),
    "turkey": ("Turkey", "#c28b3c", ["ank", "con", "smy"], [("fleet", "ank"), ("army", "con"), ("army", "smy")]),
}

SPLIT_COASTS = {
    "bul": {
        "ec": ([1030.0, 1050.0], [1035.0, 1037.0], ["black-sea", "constantinople"]),
        "sc": ([1004.0, 1110.0], [1004.0, 1124.0], ["aegean-sea", "constantinople"]),
    },
    "spa": {
        "nc": ([285.0, 1027.0], [285.0, 1014.0], ["gascony", "mid-atlantic-ocean", "portugal"]),
        "sc": ([300.0, 1134.0], [300.0, 1150.0], ["gulf-of-lyon", "mid-atlantic-ocean", "marseilles", "portugal", "western-mediterranean"]),
    },
    "stp": {
        "nc": ([1110.0, 210.0], [1110.0, 195.0], ["barents-sea", "norway"]),
        "sc": ([1080.0, 390.0], [1080.0, 405.0], ["gulf-of-bothnia", "finland", "livonia"]),
    },
}


def _offset(point: list[float], dy: float) -> list[float]:
    return [round(point[0], 1), round(point[1] + dy, 1)]


def build_yaml(project_root: Path) -> str:
    svg = sanitise_svg((project_root / "maps/classic/map.svg").read_bytes())
    geometries = territory_geometries(
        svg, [f"territory-{slug}" for slug in PROVINCES.values()]
    )

    def point(abbreviation: str) -> list[float]:
        representative = geometries[
            f"territory-{PROVINCES[abbreviation]}"
        ].representative_point()
        return [round(representative.x, 1), round(representative.y, 1)]

    def territory_id(value: str) -> str:
        base, separator, coast = value.partition("/")
        return PROVINCES[base] + (f"/{coast}" if separator else "")

    document = {
        "schema_version": 1,
        "map_id": "classic",
        "name": "Classic Diplomacy",
        "rules_engine": "standard",
        "assets": {"map": "map.svg"},
        "start": {"year": 1901, "season": "spring"},
        "teams": {},
    }
    for power_id, (name, colour, homes, units) in TEAMS.items():
        document["teams"][power_id] = {
            "name": name,
            "colour": colour,
            "home_supply_centres": [territory_id(value) for value in homes],
            "starting_supply_centres": [territory_id(value) for value in homes],
            "starting_territories": [territory_id(value) for value in homes],
            "initial_units": [
                {"type": kind, "location": territory_id(location)}
                for kind, location in units
            ],
        }

    document["territories"] = {}
    for abbreviation, slug in PROVINCES.items():
        anchor = point(abbreviation)
        anchors = {"label": anchor[:], "abbreviation": anchor[:]}
        if abbreviation in SEA_PROVINCES:
            anchors["fleet"] = _offset(anchor, 9)
        else:
            anchors["army"] = _offset(anchor, 11)
            if abbreviation in COASTAL:
                anchors["fleet"] = _offset(anchor, 9)
            if abbreviation in SUPPLY_CENTRES:
                anchors["supply_centre"] = anchor[:]
        document["territories"][slug] = {
            "name": NAMES[abbreviation],
            "abbreviation": abbreviation.upper(),
            "kind": "sea" if abbreviation in SEA_PROVINCES else "land",
            "svg_element": f"territory-{slug}",
            "supply_centre": abbreviation in SUPPLY_CENTRES,
            "anchors": anchors,
        }

    for abbreviation, coast_data in SPLIT_COASTS.items():
        split = {}
        for coast, (fleet_anchor, label_anchor, destinations) in coast_data.items():
            split[coast] = {
                "fleet_anchor": fleet_anchor,
                "label_anchor": label_anchor,
                "label_rotation": 0,
                "add_connections": destinations,
            }
        document["territories"][PROVINCES[abbreviation]]["split_coasts"] = split

    document["non_playable_elements"] = {
        "detail-switzerland": "impassable",
        "detail-impassable-islands": "impassable",
        "detail-kiel-canal": "decoration",
        "detail-constantinople-canal": "decoration",
    }
    document["presentation"] = {
        "territory_label_font_size": 9.0,
        "coast_label_font_size": 8.0,
        "inaccessible_region_colour": "#777870",
        "sea_colour": "#9ebbd2",
        "unclaimed_region_colour": "#d0c9aa",
        "label_colour": "#343a3a",
        "hold_underlines": {"army": [-2.0, 11.0], "fleet": [0.0, 8.0]},
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    output = project_root / "maps/classic/map.yaml"
    output.write_text(
        "# Best-effort standard 1901 setup; review anchors and colours in the map editor.\n"
        + build_yaml(project_root),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
