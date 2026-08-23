#!/usr/bin/env python3
"""Reconstruct the England map from the flat-colour vDiplomacy source assets.

The source image gives each land province a unique colour and separates sea
provinces with black lines.
This script assigns the raster boundary pixels to their nearest region, traces
the resulting partition into SVG paths, and writes the matching authored YAML.
"""

from __future__ import annotations

import argparse
import html
import math
import re
import struct
import zlib
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml


TEAM_NAMES = (
    "Merseyside",
    "Up North",
    "London",
    "Bristol",
    "Wales",
    "East-Anglia",
)

TEAM_COLOURS = {
    "Merseyside": "#a86f86",
    "Up North": "#426b87",
    "London": "#984843",
    "Bristol": "#a98538",
    "Wales": "#50764c",
    "East-Anglia": "#715a86",
}

STARTING_UNITS = {
    "Merseyside": {
        "Cheshire": "army",
        "Merseyside": "army",
        "Isle of Man": "fleet",
        "Anglesey": "fleet",
    },
    "Up North": {
        "Northumberland": "army",
        "Tyne & Wear": "fleet",
        "Durham": "army",
    },
    "London": {
        "London": "army",
        "Surrey": "army",
        "Kent": "fleet",
    },
    "Bristol": {
        "Avon": "fleet",
        "Gloucestershire": "army",
        "Wiltshire": "army",
    },
    "Wales": {
        "Dyfed": "army",
        "Pembrokeshire": "army",
        "Glamorgan": "fleet",
    },
    "East-Anglia": {
        "N.Lincolnshire": "army",
        "S.Lincolnshire": "army",
        "Norfolk": "fleet",
    },
}

# These coastal provinces share a land border, but their coastlines do not meet.
# The SVG importer will infer army and fleet movement from a touching pair of
# coastal shapes, so map.yaml removes the inapplicable fleet connection.
FLEET_CONNECTION_REMOVALS = {
    "Cumbria": ("Durham", "N.Yorkshire", "Northumberland"),
    "Dorset": ("Somerset",),
    "Durham": ("N.Yorkshire", "Northumberland"),
    "Lancashire": ("N.Yorkshire",),
}

ABBREVIATIONS = {
    "North Atlantic": "NAT",
    "Niarbyl Bay": "NBY",
    "Douglas Bay": "DBY",
    "Irish Sea": "IRS",
    "Menai Straits": "MEN",
    "Mersey Estuary": "MSE",
    "Cardigan Bay": "CDB",
    "N.Bristol Channel": "NBC",
    "S.Bristol Channel": "SBC",
    "Avon Estuary": "AVE",
    "English Channel": "ENG",
    "South Coast": "SOC",
    "Straights of Dover": "SOD",
    "Dutch Crossing": "DCR",
    "Thames Estuary": "THE",
    "Humber Estuary": "HUE",
    "North Sea": "NTH",
    "Northeast Coast": "NEC",
    "Cumbria": "Cum",
    "Northumberland": "Nbl",
    "Tyne & Wear": "Tyn",
    "Durham": "Dur",
    "Cleveland": "Cle",
    "Lancashire": "Lan",
    "N.Yorkshire": "Nyo",
    "Merseyside": "Mer",
    "W.Yorkshire": "Wyo",
    "Humberside": "Hum",
    "N.Lincolnshire": "Nli",
    "Derbyshire & Nottinghamshire": "Dno",
    "S.Yorkshire": "Syo",
    "Cheshire": "Che",
    "Greater Manchester": "Gma",
    "Staffordshire": "Sta",
    "Shropshire": "Shr",
    "S.Lincolnshire": "Sli",
    "Leicestershire": "Lei",
    "W.Midlands": "Wmi",
    "Warwickshire": "War",
    "Hereford & Worcester": "Hwo",
    "Gloucestershire": "Glo",
    "Oxfordshire": "Oxf",
    "Northants.": "Nha",
    "Cambs.": "Cam",
    "Norfolk": "Nfk",
    "Suffolk": "Sfk",
    "Essex": "Esx",
    "Hertfs.": "Htf",
    "Beds.": "Bed",
    "Bucks.": "Buc",
    "London": "Lon",
    "Kent": "Ken",
    "E.Sussex": "Esu",
    "Surrey": "Sur",
    "W.Sussex": "Wsu",
    "Hampshire": "Ham",
    "Berkshire": "Ber",
    "Wiltshire": "Wil",
    "Dorset": "Dor",
    "Somerset": "Som",
    "Avon": "Avo",
    "Devon": "Dev",
    "Cornwall": "Cor",
    "Isle of Wight": "Iow",
    "Gwent": "Gwe",
    "Glamorgan": "Gla",
    "S.Powys": "Spo",
    "Dyfed": "Dyf",
    "Pembrokeshire": "Pem",
    "N.Powys": "Npo",
    "Gwynedd": "Gwy",
    "Clwyd": "Clw",
    "Anglesey": "Ang",
    "Isle of Man": "Iom",
}

# Label centres reconstructed from the upstream names layer.
# These are deliberately distinct from unit and supply-centre anchors.
LABEL_ANCHORS = {
    "North Atlantic": (110.0, 145.0),
    "Niarbyl Bay": (205.0, 266.0),
    "Douglas Bay": (335.0, 176.0),
    "Irish Sea": (45.0, 470.0),
    "Menai Straits": (205.0, 385.0),
    "Mersey Estuary": (380.0, 325.0),
    "Cardigan Bay": (217.0, 532.0),
    "N.Bristol Channel": (225.0, 710.0),
    "S.Bristol Channel": (205.0, 785.0),
    "Avon Estuary": (400.0, 730.0),
    "English Channel": (380.0, 995.0),
    "South Coast": (490.0, 900.0),
    "Straights of Dover": (900.0, 950.0),
    "Dutch Crossing": (980.0, 675.0),
    "Thames Estuary": (885.0, 676.0),
    "Humber Estuary": (880.0, 380.0),
    "North Sea": (940.0, 145.0),
    "Northeast Coast": (775.0, 165.0),
    "Cumbria": (440.0, 185.0),
    "Northumberland": (525.0, 120.0),
    "Tyne & Wear": (612.0, 112.0),
    "Durham": (568.0, 157.0),
    "Cleveland": (650.0, 185.0),
    "Lancashire": (477.0, 310.0),
    "N.Yorkshire": (600.0, 245.0),
    "Merseyside": (431.0, 335.0),
    "W.Yorkshire": (575.0, 315.0),
    "Humberside": (682.0, 287.0),
    "N.Lincolnshire": (740.0, 385.0),
    "Derbyshire & Nottinghamshire": (620.0, 430.0),
    "S.Yorkshire": (613.0, 365.0),
    "Cheshire": (510.0, 420.0),
    "Greater Manchester": (505.0, 345.0),
    "Staffordshire": (530.0, 475.0),
    "Shropshire": (470.0, 505.0),
    "S.Lincolnshire": (690.0, 420.0),
    "Leicestershire": (620.0, 510.0),
    "W.Midlands": (535.0, 535.0),
    "Warwickshire": (585.0, 580.0),
    "Hereford & Worcester": (465.0, 600.0),
    "Gloucestershire": (495.0, 650.0),
    "Oxfordshire": (610.0, 665.0),
    "Northants.": (645.0, 545.0),
    "Cambs.": (745.0, 550.0),
    "Norfolk": (825.0, 470.0),
    "Suffolk": (840.0, 560.0),
    "Essex": (805.0, 628.0),
    "Hertfs.": (720.0, 650.0),
    "Beds.": (705.0, 598.0),
    "Bucks.": (675.0, 645.0),
    "London": (710.0, 690.0),
    "Kent": (790.0, 710.0),
    "E.Sussex": (790.0, 785.0),
    "Surrey": (675.0, 730.0),
    "W.Sussex": (690.0, 800.0),
    "Hampshire": (620.0, 765.0),
    "Berkshire": (620.0, 710.0),
    "Wiltshire": (540.0, 700.0),
    "Dorset": (525.0, 805.0),
    "Somerset": (435.0, 755.0),
    "Avon": (455.0, 730.0),
    "Devon": (350.0, 830.0),
    "Cornwall": (265.0, 855.0),
    "Isle of Wight": (615.0, 870.0),
    "Gwent": (435.0, 660.0),
    "Glamorgan": (340.0, 670.0),
    "S.Powys": (370.0, 590.0),
    "Dyfed": (300.0, 620.0),
    "Pembrokeshire": (270.0, 630.0),
    "N.Powys": (375.0, 500.0),
    "Gwynedd": (330.0, 440.0),
    "Clwyd": (405.0, 430.0),
    "Anglesey": (280.0, 350.0),
    "Isle of Man": (260.0, 200.0),
}


@dataclass(frozen=True)
class Territory:
    name: str
    kind: str
    supply_centre: bool
    country_id: int
    unit_x: int
    unit_y: int

    @property
    def is_split_coast_location(self) -> bool:
        return self.name.endswith("(North Coast)") or self.name.endswith("(South Coast)")


def slug(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def parse_install(path: Path) -> tuple[list[Territory], list[tuple[str, str, bool, bool]]]:
    text = path.read_text(encoding="utf-8")
    territory_pattern = re.compile(
        r"array\('([^']+)',\s*'(Sea|Coast|Land)',\s*'(Yes|No)',\s*(\d+),"
        r"\s*(\d+),\s*(\d+),\s*\d+,\s*\d+\)"
    )
    territories = [
        Territory(
            name=match.group(1),
            kind=match.group(2),
            supply_centre=match.group(3) == "Yes",
            country_id=int(match.group(4)),
            unit_x=int(match.group(5)),
            unit_y=int(match.group(6)),
        )
        for match in territory_pattern.finditer(text)
    ]
    border_pattern = re.compile(
        r"array\('([^']+)',\s*'([^']+)',\s*'(Yes|No)',\s*'(Yes|No)'\)"
    )
    borders = [
        (match.group(1), match.group(2), match.group(3) == "Yes", match.group(4) == "Yes")
        for match in border_pattern.finditer(text)
    ]
    if len(territories) != 78:
        raise ValueError(f"Expected 78 source locations, found {len(territories)}")
    if len(borders) != 215:
        raise ValueError(f"Expected 215 source borders, found {len(borders)}")
    return territories, borders


def decode_png(path: Path) -> tuple[int, int, list[list[tuple[int, int, int]]]]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG: {path}")
    position = 8
    idat: list[bytes] = []
    palette: list[tuple[int, int, int]] | None = None
    width = height = bit_depth = colour_type = interlace = -1
    while position < len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        chunk_type = data[position + 4 : position + 8]
        chunk_data = data[position + 8 : position + 8 + length]
        position += length + 12
        if chunk_type == b"IHDR":
            width, height, bit_depth, colour_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
        elif chunk_type == b"PLTE":
            palette = [
                tuple(chunk_data[index : index + 3])
                for index in range(0, len(chunk_data), 3)
            ]
        elif chunk_type == b"IDAT":
            idat.append(chunk_data)
    if bit_depth != 8 or interlace != 0 or colour_type not in (2, 3):
        raise ValueError("Only non-interlaced 8-bit RGB or indexed PNGs are supported")
    bytes_per_pixel = 3 if colour_type == 2 else 1
    stride = width * bytes_per_pixel
    inflated = zlib.decompress(b"".join(idat))
    rows: list[list[tuple[int, int, int]]] = []
    previous = bytearray(stride)
    offset = 0
    for _ in range(height):
        filter_type = inflated[offset]
        offset += 1
        scanline = bytearray(inflated[offset : offset + stride])
        offset += stride
        for index in range(stride):
            left = scanline[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            above = previous[index]
            upper_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            if filter_type == 1:
                scanline[index] = (scanline[index] + left) & 0xFF
            elif filter_type == 2:
                scanline[index] = (scanline[index] + above) & 0xFF
            elif filter_type == 3:
                scanline[index] = (scanline[index] + ((left + above) // 2)) & 0xFF
            elif filter_type == 4:
                estimate = left + above - upper_left
                distances = (
                    abs(estimate - left),
                    abs(estimate - above),
                    abs(estimate - upper_left),
                )
                predictor = (left, above, upper_left)[distances.index(min(distances))]
                scanline[index] = (scanline[index] + predictor) & 0xFF
            elif filter_type != 0:
                raise ValueError(f"Unsupported PNG filter {filter_type}")
        if colour_type == 2:
            rows.append(
                [tuple(scanline[index : index + 3]) for index in range(0, stride, 3)]
            )
        else:
            if palette is None:
                raise ValueError("Indexed PNG has no palette")
            rows.append([palette[index] for index in scanline])
        previous = scanline
    return width, height, rows


def flood_colour(
    pixels: list[list[tuple[int, int, int]]], seed: tuple[int, int]
) -> set[tuple[int, int]]:
    width = len(pixels[0])
    height = len(pixels)
    target = pixels[seed[1]][seed[0]]
    reached = {seed}
    queue = deque([seed])
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            point = (nx, ny)
            if (
                0 <= nx < width
                and 0 <= ny < height
                and point not in reached
                and pixels[ny][nx] == target
            ):
                reached.add(point)
                queue.append(point)
    return reached


def eroded_black_component(
    pixels: list[list[tuple[int, int, int]]], seed_hint: tuple[int, int]
) -> set[tuple[int, int]]:
    width = len(pixels[0])
    height = len(pixels)
    black = [[max(pixels[y][x]) < 20 for x in range(width)] for y in range(height)]
    core: set[tuple[int, int]] = set()
    for y in range(2, min(height - 2, 210)):
        for x in range(2, min(width - 2, 560)):
            if all(black[ny][nx] for ny in range(y - 2, y + 3) for nx in range(x - 2, x + 3)):
                core.add((x, y))
    seed = min(core, key=lambda point: math.dist(point, seed_hint))
    component = {seed}
    queue = deque([seed])
    while queue:
        x, y = queue.popleft()
        for point in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if point in core and point not in component:
                component.add(point)
                queue.append(point)
    return component


def partition_regions(
    pixels: list[list[tuple[int, int, int]]], territories: list[Territory]
) -> tuple[list[list[int]], list[str]]:
    width = len(pixels[0])
    height = len(pixels)
    base = [territory for territory in territories if not territory.is_split_coast_location]
    labels = [territory.name for territory in base] + ["impassable-scotland"]
    label_ids = {name: index for index, name in enumerate(labels)}
    grid = [[-1] * width for _ in range(height)]

    land_colours: dict[tuple[int, int, int], str] = {}
    for territory in base:
        if territory.kind == "Sea":
            continue
        colour = pixels[territory.unit_y][territory.unit_x]
        previous = land_colours.setdefault(colour, territory.name)
        if previous != territory.name:
            raise ValueError(f"Land colours are not unique: {previous} and {territory.name}")
    for y, row in enumerate(pixels):
        for x, colour in enumerate(row):
            territory_name = land_colours.get(colour)
            if territory_name is not None:
                grid[y][x] = label_ids[territory_name]

    for territory in base:
        if territory.kind != "Sea":
            continue
        for x, y in flood_colour(pixels, (territory.unit_x, territory.unit_y)):
            if grid[y][x] != -1:
                raise ValueError(f"Overlapping source regions at {x},{y}")
            grid[y][x] = label_ids[territory.name]

    for x, y in eroded_black_component(pixels, (320, 50)):
        grid[y][x] = label_ids["impassable-scotland"]

    queue: deque[tuple[int, int]] = deque()
    for y in range(height):
        for x in range(width):
            if grid[y][x] != -1:
                queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        label = grid[y][x]
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and grid[ny][nx] == -1:
                grid[ny][nx] = label
                queue.append((nx, ny))
    if any(value == -1 for row in grid for value in row):
        raise ValueError("Map partition left unassigned pixels")
    return grid, labels


def trace_region(grid: list[list[int]], label: int) -> list[list[tuple[int, int]]]:
    width = len(grid[0])
    height = len(grid)
    edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for y in range(height):
        for x in range(width):
            if grid[y][x] != label:
                continue
            if y == 0 or grid[y - 1][x] != label:
                edges.add(((x, y), (x + 1, y)))
            if x == width - 1 or grid[y][x + 1] != label:
                edges.add(((x + 1, y), (x + 1, y + 1)))
            if y == height - 1 or grid[y + 1][x] != label:
                edges.add(((x + 1, y + 1), (x, y + 1)))
            if x == 0 or grid[y][x - 1] != label:
                edges.add(((x, y + 1), (x, y)))
    outgoing: dict[tuple[int, int], set[tuple[int, int]]] = defaultdict(set)
    for start, end in edges:
        outgoing[start].add(end)

    direction_index = {(1, 0): 0, (0, 1): 1, (-1, 0): 2, (0, -1): 3}
    loops: list[list[tuple[int, int]]] = []
    unused = set(edges)
    while unused:
        start_edge = min(unused)
        first, current = start_edge
        unused.remove(start_edge)
        loop = [first, current]
        previous = first
        while current != first:
            candidates = [end for end in outgoing[current] if (current, end) in unused]
            if not candidates:
                raise ValueError(f"Open SVG boundary for label {label} at {current}")
            incoming = direction_index[(current[0] - previous[0], current[1] - previous[1])]

            def turn_priority(end: tuple[int, int]) -> int:
                outgoing_direction = direction_index[(end[0] - current[0], end[1] - current[1])]
                turn = (outgoing_direction - incoming) % 4
                return {1: 0, 0: 1, 3: 2, 2: 3}[turn]

            following = min(candidates, key=turn_priority)
            unused.remove((current, following))
            previous, current = current, following
            loop.append(current)
        compact: list[tuple[int, int]] = []
        for point in loop[:-1]:
            compact.append(point)
            while len(compact) >= 3:
                ax, ay = compact[-3]
                bx, by = compact[-2]
                cx, cy = compact[-1]
                if (bx - ax) * (cy - by) == (by - ay) * (cx - bx):
                    compact.pop(-2)
                else:
                    break
        if len(compact) >= 3:
            loops.append(compact)
    return loops


def path_data(loops: Iterable[list[tuple[int, int]]]) -> str:
    parts: list[str] = []
    for loop in loops:
        parts.append(f"M {loop[0][0]} {loop[0][1]}")
        parts.extend(f"L {x} {y}" for x, y in loop[1:])
        parts.append("Z")
    return " ".join(parts)


def shared_border_pairs(grid: list[list[int]], labels: list[str]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    height = len(grid)
    width = len(grid[0])
    for y in range(height):
        for x in range(width):
            here = grid[y][x]
            if x + 1 < width and grid[y][x + 1] != here:
                pair = tuple(sorted((labels[here], labels[grid[y][x + 1]])))
                counts[pair] += 1
            if y + 1 < height and grid[y + 1][x] != here:
                pair = tuple(sorted((labels[here], labels[grid[y + 1][x]])))
                counts[pair] += 1
    return counts


def interior_anchor(
    grid: list[list[int]],
    label: int,
    avoid: Iterable[tuple[float, float]],
) -> tuple[float, float]:
    height = len(grid)
    width = len(grid[0])
    distance: dict[tuple[int, int], int] = {}
    queue: deque[tuple[int, int]] = deque()
    for y in range(height):
        for x in range(width):
            if grid[y][x] != label:
                continue
            if any(
                nx < 0 or ny < 0 or nx >= width or ny >= height or grid[ny][nx] != label
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
            ):
                distance[(x, y)] = 0
                queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        next_distance = distance[(x, y)] + 1
        for point in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            nx, ny = point
            if (
                0 <= nx < width
                and 0 <= ny < height
                and grid[ny][nx] == label
                and point not in distance
            ):
                distance[point] = next_distance
                queue.append(point)

    avoided_points = tuple(avoid)

    def score(item: tuple[tuple[int, int], int]) -> float:
        (x, y), boundary_distance = item
        separation = min(
            (min(100.0, math.dist((x, y), point)) for point in avoided_points),
            default=100.0,
        )
        return boundary_distance + separation * 0.28

    (x, y), _ = max(distance.items(), key=score)
    return (x + 0.5, y + 0.5)


def supply_centres_from_names(
    names_pixels: list[list[tuple[int, int, int]]],
    grid: list[list[int]],
    labels: list[str],
) -> dict[str, tuple[float, float]]:
    black = {
        (x, y)
        for y, row in enumerate(names_pixels)
        for x, colour in enumerate(row)
        if max(colour) < 80
    }
    centres: list[tuple[float, float]] = []
    while black:
        seed = black.pop()
        component = [seed]
        queue = [seed]
        while queue:
            x, y = queue.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbour = (x + dx, y + dy)
                    if neighbour in black:
                        black.remove(neighbour)
                        queue.append(neighbour)
                        component.append(neighbour)
        xs = [point[0] for point in component]
        ys = [point[1] for point in component]
        if max(xs) - min(xs) + 1 == 9 and max(ys) - min(ys) + 1 == 9 and len(component) == 24:
            centres.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
    if len(centres) != 34:
        raise ValueError(f"Expected 34 supply-centre markers, found {len(centres)}")
    assigned: dict[str, tuple[float, float]] = {}
    for x, y in centres:
        territory_name = labels[grid[round(y)][round(x)]]
        if territory_name in assigned:
            raise ValueError(f"Two supply-centre markers assigned to {territory_name}")
        assigned[territory_name] = (x, y)
    return assigned


def star_path(cx: float, cy: float, outer: float = 7.0, inner: float = 3.2) -> str:
    points: list[tuple[float, float]] = []
    for index in range(10):
        radius = outer if index % 2 == 0 else inner
        angle = -math.pi / 2 + index * math.pi / 5
        points.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    return "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points) + " Z"


def darken_colour(colour: str, factor: float = 0.82) -> str:
    """Return the slightly darker team shade used to fill unit symbols."""
    channels = (int(colour[index : index + 2], 16) for index in (1, 3, 5))
    return "#" + "".join(f"{round(channel * factor):02x}" for channel in channels)


def svg_document(
    width: int,
    height: int,
    base_territories: list[Territory],
    labels: list[str],
    paths: dict[str, str],
    label_anchors: dict[str, tuple[float, float]],
    supply_anchors: dict[str, tuple[float, float]],
    review: bool,
) -> str:
    territory_by_name = {territory.name: territory for territory in base_territories}
    team_by_id = {index + 1: TEAM_NAMES[index] for index in range(len(TEAM_NAMES))}
    document_width = width + 430 if review else width
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {document_width} {height}" role="img">',
        "  <defs>",
        "    <style>",
        "      .territory { stroke: #343a3a; stroke-width: 1.35; stroke-linejoin: round; fill-rule: evenodd; }",
        "      .land { fill: #d0c9aa; }",
        "      .sea { fill: #9ebbd2; }",
        "      .impassable { fill: #777870; stroke: #343a3a; stroke-width: 1.35; }",
        "      .decoration { fill: none; stroke: #465050; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; }",
        "      .review-label { font: 700 11px sans-serif; fill: #202828; text-anchor: middle; dominant-baseline: central; paint-order: stroke; stroke: #f3efdd; stroke-width: 1.7px; stroke-linejoin: round; }",
        "    </style>",
        '    <symbol id="review-army" viewBox="0 0 52 28" overflow="visible">',
        '      <g fill="currentColor" stroke="#293333" stroke-width="1.8" stroke-linejoin="round">',
        '        <path d="M5 18.5h37l4 3.5-4 4H8q-4 0-5.5-3.5z"/>',
        '        <path d="m10 18.5 4-6.5h22l6 6.5z"/>',
        '        <path d="M19 12V7.5h13l4 4.5z"/>',
        '        <path d="M31 8.5h17.5q2 0 2 1.8t-2 1.7H34z"/>',
        "      </g>",
        '      <g fill="#293333">',
        '        <circle cx="10" cy="22.5" r="2.2"/><circle cx="18" cy="22.5" r="2.2"/>',
        '        <circle cx="26" cy="22.5" r="2.2"/><circle cx="34" cy="22.5" r="2.2"/>',
        '        <circle cx="41" cy="22.5" r="2.2"/>',
        "      </g>",
        "    </symbol>",
        '    <symbol id="review-fleet" viewBox="0 0 72 24" overflow="visible">',
        '      <g fill="currentColor" stroke="#293333" stroke-width="1.7" stroke-linejoin="round">',
        '        <path d="M2.5 14h55l11-5 1.5 2-6.5 7.5q-1.8 2-5.5 2H11q-5 0-7-3z"/>',
        '        <path d="M13 14v-4h10l3-4.5h11l3 4.5h12v4z"/>',
        '        <path d="M28 5.5V2h4.5v3.5zM35 5.5V3h4v4z"/>',
        '        <path d="M8 14v-3h9v3zM51 14v-3h7l5-2v3l-5 2z"/>',
        "      </g>",
        '      <path d="M8 17h55M30.2 2V.8" fill="none" stroke="#293333" stroke-width="1.4" stroke-linecap="round"/>',
        "    </symbol>",
        "  </defs>",
        '  <rect id="map-background" width="100%" height="100%" fill="#9ebbd2"/>',
        '  <g id="territories">',
    ]
    for territory in base_territories:
        territory_id = slug(territory.name)
        css_class = "sea" if territory.kind == "Sea" else "land"
        fill = ""
        if review and territory.country_id:
            fill = f' style="fill:{TEAM_COLOURS[team_by_id[territory.country_id]]}"'
        lines.append(
            f'    <path id="territory-{territory_id}" class="territory {css_class}"{fill} d="{paths[territory.name]}">'
        )
        if review:
            lines.append(f"      <title>{html.escape(territory.name)}</title>")
        lines.append("    </path>")
    lines.extend(
        [
            "  </g>",
            f'  <path id="impassable-scotland" class="impassable" d="{paths["impassable-scotland"]}"/>',
            '  <g id="connection-north-atlantic-north-sea" class="decoration">',
            '    <path d="M 151 30 L 151 10 M 144 18 L 151 10 L 158 18"/>',
            '    <path d="M 911 30 L 911 10 M 904 18 L 911 10 L 918 18"/>',
            "  </g>",
            '  <g id="bridge-gwynedd-anglesey" class="decoration">',
            '    <path d="M 307 412 L 311 416 M 313 406 L 317 410"/>',
            "  </g>",
            '  <g id="bridge-hampshire-isle-of-wight" class="decoration">',
            '    <path d="M 584 831 L 589 836 M 594 825 L 598 832"/>',
            "  </g>",
        ]
    )
    if review:
        lines.append('  <g id="review-supply-centres">')
        for territory in base_territories:
            if not territory.supply_centre:
                continue
            x, y = supply_anchors[territory.name]
            owner = team_by_id.get(territory.country_id)
            colour = TEAM_COLOURS[owner] if owner else "#7d7869"
            lines.append(
                f'    <path d="{star_path(x, y)}" fill="{colour}" stroke="#343a3a" stroke-width="1.2"/>'
            )
        lines.append("  </g>")
        lines.append('  <g id="review-labels" pointer-events="none">')
        for territory in base_territories:
            x, y = label_anchors[territory.name]
            lines.append(
                f'    <text class="review-label" x="{x:.1f}" y="{y:.1f}">{ABBREVIATIONS[territory.name]}</text>'
            )
        lines.append("  </g>")
        lines.append('  <g id="review-starting-units" pointer-events="none">')
        for team_name, units in STARTING_UNITS.items():
            colour = darken_colour(TEAM_COLOURS[team_name])
            for territory_name, unit_type in units.items():
                territory = territory_by_name[territory_name]
                x, y = territory.unit_x, territory.unit_y
                symbol = "review-army" if unit_type == "army" else "review-fleet"
                symbol_width, symbol_height = (42, 24) if unit_type == "army" else (52, 18)
                lines.append(
                    f'    <use href="#{symbol}" xlink:href="#{symbol}" '
                    f'x="{x - symbol_width / 2}" y="{y - symbol_height / 2}" '
                    f'width="{symbol_width}" height="{symbol_height}" style="color:{colour}"/>'
                )
        lines.append("  </g>")
        panel_x = width + 12
        lines.append('  <g id="review-key" pointer-events="none">')
        lines.append(
            f'    <rect x="{width}" y="0" width="430" height="{height}" fill="#f3efdd" stroke="#343a3a" stroke-width="1.5"/>'
        )
        lines.append(
            f'    <text x="{panel_x}" y="27" font-family="sans-serif" font-size="18" font-weight="700" fill="#252d2d">Territory key</text>'
        )
        for index, territory in enumerate(base_territories):
            column = index // 37
            row = index % 37
            x = panel_x + column * 207
            y = 51 + row * 22
            lines.append(
                f'    <text x="{x}" y="{y}" font-family="sans-serif" font-size="10" fill="#252d2d">'
                f'<tspan font-weight="700">{ABBREVIATIONS[territory.name]}</tspan>'
                f'<tspan dx="6">{html.escape(territory.name)}</tspan></text>'
            )
        lines.append(
            f'    <text x="{panel_x}" y="893" font-family="sans-serif" font-size="16" font-weight="700" fill="#252d2d">Starting powers</text>'
        )
        for index, team_name in enumerate(TEAM_NAMES):
            column = index % 2
            row = index // 2
            x = panel_x + column * 207
            y = 920 + row * 27
            lines.append(
                f'    <rect x="{x}" y="{y - 12}" width="15" height="15" rx="2" fill="{TEAM_COLOURS[team_name]}" stroke="#343a3a"/>'
            )
            lines.append(
                f'    <text x="{x + 23}" y="{y}" font-family="sans-serif" font-size="11" fill="#252d2d">{html.escape(team_name)}</text>'
            )
        lines.append("  </g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def connection_override(to: str, units: list[str]) -> dict[str, object]:
    return {"to": slug(to), "units": units}


def yaml_document(
    base_territories: list[Territory],
    source_territories: list[Territory],
    label_anchors: dict[str, tuple[float, float]],
    supply_anchors: dict[str, tuple[float, float]],
) -> str:
    by_name = {territory.name: territory for territory in source_territories}
    team_by_id = {index + 1: TEAM_NAMES[index] for index in range(len(TEAM_NAMES))}
    teams: dict[str, object] = {}
    for team_name in TEAM_NAMES:
        homes = [
            slug(territory.name)
            for territory in base_territories
            if territory.country_id == TEAM_NAMES.index(team_name) + 1
        ]
        teams[slug(team_name)] = {
            "name": team_name,
            "colour": TEAM_COLOURS[team_name],
            "home_supply_centres": list(homes),
            "starting_supply_centres": list(homes),
            "starting_territories": list(homes),
            "initial_units": [
                {"type": unit_type, "location": slug(territory_name)}
                for territory_name, unit_type in STARTING_UNITS[team_name].items()
            ],
        }

    territory_yaml: dict[str, object] = {}
    for territory in base_territories:
        entry: dict[str, object] = {
            "name": territory.name,
            "abbreviation": ABBREVIATIONS[territory.name],
            "kind": "sea" if territory.kind == "Sea" else "land",
            "svg_element": f"territory-{slug(territory.name)}",
            "supply_centre": territory.supply_centre,
        }
        label_x, label_y = label_anchors[territory.name]
        anchors: dict[str, object] = {"label": [round(label_x, 1), round(label_y, 1)]}
        if territory.kind != "Sea":
            anchors["army"] = [float(territory.unit_x), float(territory.unit_y)]
        if territory.kind == "Sea" or (territory.kind == "Coast" and territory.name not in ("Devon", "Dyfed")):
            anchors["fleet"] = [float(territory.unit_x), float(territory.unit_y)]
        if territory.supply_centre:
            supply_x, supply_y = supply_anchors[territory.name]
            anchors["supply_centre"] = [round(supply_x, 1), round(supply_y, 1)]
        entry["anchors"] = anchors

        additions: list[dict[str, object]] = []
        if territory.name == "North Atlantic":
            additions.append(connection_override("North Sea", ["fleet"]))
        elif territory.name == "Gwynedd":
            additions.append(connection_override("Anglesey", ["army", "fleet"]))
        elif territory.name == "Hampshire":
            additions.append(connection_override("Isle of Wight", ["army", "fleet"]))

        removals = [
            connection_override(destination, ["fleet"])
            for destination in FLEET_CONNECTION_REMOVALS.get(territory.name, ())
        ]
        if additions or removals:
            entry["connection_overrides"] = {}
            if additions:
                entry["connection_overrides"]["add"] = additions
            if removals:
                entry["connection_overrides"]["remove"] = removals

        if territory.name == "Devon":
            entry["split_coasts"] = {
                "north": {
                    "fleet_anchor": [
                        float(by_name["Devon (North Coast)"].unit_x),
                        float(by_name["Devon (North Coast)"].unit_y),
                    ],
                    "add_connections": [
                        slug("S.Bristol Channel"),
                        slug("Avon Estuary"),
                        slug("Cornwall"),
                    ],
                },
                "south": {
                    "fleet_anchor": [
                        float(by_name["Devon (South Coast)"].unit_x),
                        float(by_name["Devon (South Coast)"].unit_y),
                    ],
                    "add_connections": [slug("South Coast"), slug("Dorset"), slug("Cornwall")],
                },
            }
        elif territory.name == "Dyfed":
            entry["split_coasts"] = {
                "north": {
                    "fleet_anchor": [
                        float(by_name["Dyfed (North Coast)"].unit_x),
                        float(by_name["Dyfed (North Coast)"].unit_y),
                    ],
                    "add_connections": [
                        slug("Cardigan Bay"),
                        slug("Pembrokeshire"),
                        slug("Gwynedd"),
                    ],
                },
                "south": {
                    "fleet_anchor": [
                        float(by_name["Dyfed (South Coast)"].unit_x),
                        float(by_name["Dyfed (South Coast)"].unit_y),
                    ],
                    "add_connections": [
                        slug("N.Bristol Channel"),
                        slug("Pembrokeshire"),
                        slug("Glamorgan"),
                    ],
                },
            }
        territory_yaml[slug(territory.name)] = entry

    document = {
        "schema_version": 1,
        "map_id": "england",
        "name": "England",
        "rules_engine": "standard",
        "assets": {"map": "map.svg", "army": "army.svg", "fleet": "fleet.svg"},
        "start": {"year": 2000, "season": "spring"},
        "teams": teams,
        "territories": territory_yaml,
        "non_playable_elements": {
            "impassable-scotland": "impassable",
            "connection-north-atlantic-north-sea": "decoration",
            "bridge-gwynedd-anglesey": "decoration",
            "bridge-hampshire-isle-of-wight": "decoration",
        },
    }
    header = (
        "# Reconstructed from vDiplomacy's Anarchy in the UK variant.\n"
        "# See SOURCE.md for provenance and the authoritative topology source.\n"
    )
    class FriendlyDumper(yaml.SafeDumper):
        def ignore_aliases(self, data: object) -> bool:
            return True

        def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
            return super().increase_indent(flow, False)

    return header + yaml.dump(
        document,
        Dumper=FriendlyDumper,
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )


def validate_source_topology(
    base_territories: list[Territory],
    borders: list[tuple[str, str, bool, bool]],
    shared_borders: dict[tuple[str, str], int],
) -> list[str]:
    base_names = {territory.name for territory in base_territories}
    split_location = re.compile(r" \((?:North|South) Coast\)$")

    def base_name(name: str) -> str:
        return split_location.sub("", name)

    source_pairs = {
        tuple(sorted((base_name(origin), base_name(destination))))
        for origin, destination, fleets, armies in borders
        if fleets or armies
    }
    visual_pairs = {
        pair
        for pair, length in shared_borders.items()
        if length >= 2 and pair[0] in base_names and pair[1] in base_names
    }
    expected_nonvisual = {
        tuple(sorted(pair))
        for pair in (
            ("North Atlantic", "North Sea"),
            ("Gwynedd", "Anglesey"),
            ("Hampshire", "Isle of Wight"),
        )
    }
    missing = sorted(source_pairs - visual_pairs - expected_nonvisual)
    extra = sorted(visual_pairs - source_pairs)
    diagnostics = []
    if missing:
        diagnostics.append(f"Source adjacencies without a visual border: {missing}")
    if extra:
        diagnostics.append(f"Visual borders absent from source topology: {extra}")
    return diagnostics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-map", type=Path, required=True)
    parser.add_argument("--names-map", type=Path, required=True)
    parser.add_argument("--install-data", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()

    source_territories, borders = parse_install(args.install_data)
    base_territories = [
        territory for territory in source_territories if not territory.is_split_coast_location
    ]
    if len(base_territories) != 74:
        raise ValueError(f"Expected 74 playable territories, found {len(base_territories)}")
    if set(ABBREVIATIONS) != {territory.name for territory in base_territories}:
        missing = {territory.name for territory in base_territories} - set(ABBREVIATIONS)
        extra = set(ABBREVIATIONS) - {territory.name for territory in base_territories}
        raise ValueError(f"Abbreviation mismatch; missing={missing}, extra={extra}")
    folded = [value.casefold() for value in ABBREVIATIONS.values()]
    if len(folded) != len(set(folded)) or any(len(value) != 3 or not value.isascii() for value in folded):
        raise ValueError("Abbreviations must be unique three-letter ASCII values")

    width, height, pixels = decode_png(args.base_map)
    names_width, names_height, names_pixels = decode_png(args.names_map)
    if (names_width, names_height) != (width, height):
        raise ValueError("Base and names maps have different dimensions")
    grid, labels = partition_regions(pixels, source_territories)
    label_ids = {name: index for index, name in enumerate(labels)}
    paths = {name: path_data(trace_region(grid, label_ids[name])) for name in labels}
    supply_anchors = supply_centres_from_names(names_pixels, grid, labels)
    expected_supply = {territory.name for territory in base_territories if territory.supply_centre}
    if set(supply_anchors) != expected_supply:
        raise ValueError(
            f"Supply-centre assignment mismatch; missing={expected_supply - set(supply_anchors)}, "
            f"extra={set(supply_anchors) - expected_supply}"
        )
    if set(LABEL_ANCHORS) != {territory.name for territory in base_territories}:
        raise ValueError("Label anchors do not cover the complete playable map")
    label_anchors = dict(LABEL_ANCHORS)

    diagnostics = validate_source_topology(
        base_territories,
        borders,
        shared_border_pairs(grid, labels),
    )
    if diagnostics:
        raise ValueError("\n".join(diagnostics))

    args.output_directory.mkdir(parents=True, exist_ok=True)
    (args.output_directory / "map.svg").write_text(
        svg_document(
            width,
            height,
            base_territories,
            labels,
            paths,
            label_anchors,
            supply_anchors,
            review=False,
        ),
        encoding="utf-8",
    )
    (args.output_directory / "map-review.svg").write_text(
        svg_document(
            width,
            height,
            base_territories,
            labels,
            paths,
            label_anchors,
            supply_anchors,
            review=True,
        ),
        encoding="utf-8",
    )
    (args.output_directory / "map.yaml").write_text(
        yaml_document(base_territories, source_territories, label_anchors, supply_anchors),
        encoding="utf-8",
    )
    print(f"Wrote 74 territories, 34 supply centres and 6 powers to {args.output_directory}")


if __name__ == "__main__":
    main()
