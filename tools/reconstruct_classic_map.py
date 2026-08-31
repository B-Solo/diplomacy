#!/usr/bin/env python3
"""Build the editor-ready classic map from GoDip's semantic province SVG."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from xml.etree import ElementTree

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
ElementTree.register_namespace("", SVG_NAMESPACE)

WIDTH = 1524
HEIGHT = 1357

PROVINCES = {
    "adr": "adriatic-sea",
    "aeg": "aegean-sea",
    "alb": "albania",
    "ank": "ankara",
    "apu": "apulia",
    "arm": "armenia",
    "bal": "baltic-sea",
    "bar": "barents-sea",
    "bel": "belgium",
    "ber": "berlin",
    "bla": "black-sea",
    "boh": "bohemia",
    "bot": "gulf-of-bothnia",
    "bre": "brest",
    "bud": "budapest",
    "bul": "bulgaria",
    "bur": "burgundy",
    "cly": "clyde",
    "con": "constantinople",
    "den": "denmark",
    "eas": "eastern-mediterranean",
    "edi": "edinburgh",
    "eng": "english-channel",
    "fin": "finland",
    "gal": "galicia",
    "gas": "gascony",
    "gol": "gulf-of-lyon",
    "gre": "greece",
    "hel": "helgoland-bight",
    "hol": "holland",
    "ion": "ionian-sea",
    "iri": "irish-sea",
    "kie": "kiel",
    "lon": "london",
    "lvn": "livonia",
    "lvp": "liverpool",
    "mar": "marseilles",
    "mid": "mid-atlantic-ocean",
    "mos": "moscow",
    "mun": "munich",
    "naf": "north-africa",
    "nap": "naples",
    "nat": "north-atlantic-ocean",
    "nrg": "norwegian-sea",
    "nth": "north-sea",
    "nwy": "norway",
    "par": "paris",
    "pic": "picardy",
    "pie": "piedmont",
    "por": "portugal",
    "pru": "prussia",
    "rom": "rome",
    "ruh": "ruhr",
    "rum": "rumania",
    "ser": "serbia",
    "sev": "sevastopol",
    "sil": "silesia",
    "ska": "skagerrak",
    "smy": "smyrna",
    "spa": "spain",
    "stp": "st-petersburg",
    "swe": "sweden",
    "syr": "syria",
    "tri": "trieste",
    "tun": "tunis",
    "tus": "tuscany",
    "tyn": "tyrrhenian-sea",
    "tyr": "tyrolia",
    "ukr": "ukraine",
    "ven": "venice",
    "vie": "vienna",
    "wal": "wales",
    "war": "warsaw",
    "wes": "western-mediterranean",
    "yor": "yorkshire",
}

SEA_PROVINCES = {
    "adr", "aeg", "bal", "bar", "bla", "bot", "eas", "eng", "gol", "hel",
    "ion", "iri", "mid", "nat", "nrg", "nth", "ska", "tyn", "wes",
}


def _svg_tag(name: str) -> str:
    return f"{{{SVG_NAMESPACE}}}{name}"


def _by_id(root: ElementTree.Element) -> dict[str, ElementTree.Element]:
    return {element_id: node for node in root.iter() if (element_id := node.get("id"))}


def _clean_geometry(node: ElementTree.Element) -> ElementTree.Element:
    """Copy source geometry without presentation or editor-specific metadata."""
    result = copy.deepcopy(node)
    for item in result.iter():
        for attribute in tuple(item.attrib):
            if attribute.startswith("{") or attribute in {
                "class", "display", "fill", "fill-opacity", "id", "style", "stroke",
                "stroke-width",
            }:
                item.attrib.pop(attribute, None)
    return result


def _water_detail(
    group: ElementTree.Element,
    element_id: str,
    path_data: str,
) -> None:
    ElementTree.SubElement(
        group,
        _svg_tag("path"),
        {
            "id": element_id,
            "class": "terrain-detail water-detail",
            "data-map-fill": "sea",
            "fill": "#9ebbd2",
            "stroke": "none",
            "d": path_data,
        },
    )


def build_map(source_path: Path) -> bytes:
    source = ElementTree.parse(source_path).getroot()
    source_ids = _by_id(source)
    root = ElementTree.Element(
        _svg_tag("svg"),
        {
            "viewBox": f"0 0 {WIDTH} {HEIGHT}",
            "role": "img",
            "aria-labelledby": "classic-map-title classic-map-description",
        },
    )
    title = ElementTree.SubElement(root, _svg_tag("title"), {"id": "classic-map-title"})
    title.text = "Classic Diplomacy map"
    description = ElementTree.SubElement(
        root, _svg_tag("desc"), {"id": "classic-map-description"}
    )
    description.text = (
        "Unlabelled standard Diplomacy provinces using detailed, coincident borders and "
        "semantic water and inaccessible terrain details."
    )
    definitions = ElementTree.SubElement(root, _svg_tag("defs"))
    style = ElementTree.SubElement(definitions, _svg_tag("style"))
    style.text = """
      .territory-shape { stroke:#343a3a; stroke-width:1.6; stroke-linejoin:round; stroke-linecap:round; fill-rule:evenodd; }
      .land .territory-shape { fill:#d0c9aa; }
      .sea .territory-shape { fill:#9ebbd2; }
      .terrain-detail { stroke-linejoin:round; stroke-linecap:round; fill-rule:evenodd; }
    """
    ElementTree.SubElement(
        root,
        _svg_tag("rect"),
        {
            "id": "map-background",
            "width": str(WIDTH),
            "height": str(HEIGHT),
            "fill": "#9ebbd2",
        },
    )
    territories = ElementTree.SubElement(root, _svg_tag("g"), {"id": "territories"})
    groups: dict[str, ElementTree.Element] = {}
    for source_id, slug in PROVINCES.items():
        terrain = "sea" if source_id in SEA_PROVINCES else "land"
        group = ElementTree.SubElement(
            territories,
            _svg_tag("g"),
            {
                "id": f"territory-{slug}",
                "class": f"territory {terrain}",
                "data-territory-kind": terrain,
            },
        )
        geometry = _clean_geometry(source_ids["tys" if source_id == "tyn" else source_id])
        geometry.set("id", f"shape-{slug}")
        geometry.set("class", "territory-shape")
        geometry.set("fill", "#9ebbd2" if terrain == "sea" else "#d0c9aa")
        geometry.set("stroke", "#343a3a")
        geometry.set("stroke-width", "1.6")
        geometry.set("fill-rule", "evenodd")
        group.append(geometry)
        groups[slug] = group

    # These closed overlays sit inside their parent territory. The renderer
    # recolours them from the map's sea colour even when the land is controlled.
    _water_detail(
        groups["kiel"],
        "detail-kiel-canal",
        "M 619 672.7 C 639 672 660 669.5 681.7 666.4 L 681.8 668 C 660 671.2 639 673.7 619.2 674.3 Z",
    )
    _water_detail(
        groups["constantinople"],
        "detail-constantinople-canal",
        "M 1115 1084 C 1124 1096 1115 1107 1098 1118 C 1081 1129 1075 1136 1061 1140 C 1048 1144 1040 1151 1029 1158 L 1026 1153 C 1038 1145 1046 1138 1059 1135 C 1072 1131 1078 1124 1095 1113 C 1110 1103 1117 1095 1110 1087 Z",
    )
    # Constantinople's compound outline already contains the Bosporus and
    # Dardanelles. Keep its semantic sea overlay beneath that outline so it
    # colours only the genuine openings and never erases their coast stroke.
    constantinople = groups["constantinople"]
    constantinople_detail = constantinople[-1]
    constantinople.remove(constantinople_detail)
    constantinople.insert(0, constantinople_detail)

    details = ElementTree.SubElement(root, _svg_tag("g"), {"id": "terrain-details"})
    impassable = [
        node
        for node in source.iter()
        if "impassableStripes" in node.get("style", "")
    ]
    swiss_source = next(node for node in impassable if node.get("id") == "swiss")
    swiss = _clean_geometry(swiss_source)
    swiss.attrib.update(
        {
            "id": "detail-switzerland",
            "class": "terrain-detail",
            "data-map-fill": "inaccessible",
            "fill": "#777870",
            "stroke": "#343a3a",
            "stroke-width": "1.6",
        }
    )
    details.append(swiss)
    islands = ElementTree.SubElement(
        details,
        _svg_tag("g"),
        {
            "id": "detail-impassable-islands",
            "class": "terrain-detail",
            "data-map-fill": "inaccessible",
            "fill": "#777870",
            "stroke": "#343a3a",
            "stroke-width": "1.6",
        },
    )
    island_number = 0
    for source_node in impassable:
        if source_node is swiss_source or source_node.get("id") == "Path-28":
            continue
        island_number += 1
        island = _clean_geometry(source_node)
        island.set("id", f"detail-impassable-island-{island_number}")
        islands.append(island)

    ElementTree.indent(root, space="  ")
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=project_root / "vendor/godip/classical-map.svg",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "maps/classic/map.svg",
    )
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(build_map(arguments.source))


if __name__ == "__main__":
    main()
