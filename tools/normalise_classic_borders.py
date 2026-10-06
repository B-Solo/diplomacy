"""Replace the variable-width border bands in the supplied Classic SVG.

The source's Borders layer is a collection of filled ribbons.  Rasterising and
skeletonising that layer provides one centre-line per ribbon, which is then
written back as a uniform SVG stroke.  Territory paths remain fill-only.
"""

from __future__ import annotations

import argparse
import struct
import subprocess
import tempfile
import zlib
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree

import numpy


SVG = "http://www.w3.org/2000/svg"
INKSCAPE = "http://www.inkscape.org/namespaces/inkscape"
ElementTree.register_namespace("", SVG)


def read_png(path: Path) -> numpy.ndarray:
    """Read the RGBA data emitted by Inkscape without adding a Pillow dependency."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Expected an Inkscape PNG")
    chunks: list[bytes] = []
    offset = 8
    width = height = colour_type = None
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += length + 12
        if kind == b"IHDR":
            width, height, bit_depth, colour_type, compression, filter_type, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if (bit_depth, colour_type, compression, filter_type, interlace) != (8, 6, 0, 0, 0):
                raise ValueError("Expected an 8-bit non-interlaced RGBA PNG")
        elif kind == b"IDAT":
            chunks.append(payload)
    if width is None or height is None:
        raise ValueError("PNG header was not found")
    raw = zlib.decompress(b"".join(chunks))
    stride = width * 4
    rows = numpy.empty((height, stride), dtype=numpy.uint8)
    previous = numpy.zeros(stride, dtype=numpy.uint8)
    cursor = 0
    for row_index in range(height):
        filter_kind = raw[cursor]
        cursor += 1
        row = numpy.frombuffer(raw[cursor : cursor + stride], dtype=numpy.uint8).copy()
        cursor += stride
        if filter_kind == 1:
            for index in range(4, stride):
                row[index] = (int(row[index]) + int(row[index - 4])) & 0xFF
        elif filter_kind == 2:
            row = (row.astype(numpy.uint16) + previous.astype(numpy.uint16)).astype(numpy.uint8)
        elif filter_kind == 3:
            for index in range(stride):
                left = row[index - 4] if index >= 4 else 0
                row[index] = (int(row[index]) + (int(left) + int(previous[index])) // 2) & 0xFF
        elif filter_kind == 4:
            for index in range(stride):
                left = int(row[index - 4]) if index >= 4 else 0
                up = int(previous[index])
                upper_left = int(previous[index - 4]) if index >= 4 else 0
                estimate = left + up - upper_left
                nearest = min((left, up, upper_left), key=lambda value: abs(estimate - value))
                row[index] = (int(row[index]) + nearest) & 0xFF
        elif filter_kind != 0:
            raise ValueError(f"Unsupported PNG filter: {filter_kind}")
        rows[row_index] = row
        previous = row
    return rows.reshape(height, width, 4)


def skeletonise(mask: numpy.ndarray) -> numpy.ndarray:
    """Return the Zhang-Suen one-pixel skeleton of a boolean border mask."""
    result = mask.copy()
    while True:
        changed = False
        for phase in range(2):
            padded = numpy.pad(result, 1)
            p2 = padded[:-2, 1:-1]
            p3 = padded[:-2, 2:]
            p4 = padded[1:-1, 2:]
            p5 = padded[2:, 2:]
            p6 = padded[2:, 1:-1]
            p7 = padded[2:, :-2]
            p8 = padded[1:-1, :-2]
            p9 = padded[:-2, :-2]
            neighbours = (p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9)
            sequence = (p2, p3, p4, p5, p6, p7, p8, p9, p2)
            transitions = sum((~before) & after for before, after in zip(sequence, sequence[1:]))
            deletion = result & (neighbours >= 2) & (neighbours <= 6) & (transitions == 1)
            if phase == 0:
                deletion &= ~(p2 & p4 & p6) & ~(p4 & p6 & p8)
            else:
                deletion &= ~(p2 & p4 & p8) & ~(p2 & p6 & p8)
            if deletion.any():
                result[deletion] = False
                changed = True
        if not changed:
            return result


def simplify(points: list[tuple[float, float]], tolerance: float = 0.6) -> list[tuple[float, float]]:
    """Simplify a traced pixel line while retaining coast and province detail."""
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    scale = dx * dx + dy * dy
    farthest, distance = 0, -1.0
    for index, point in enumerate(points[1:-1], start=1):
        if scale:
            projection = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / scale
            nearest = (start[0] + projection * dx, start[1] + projection * dy)
            candidate = (point[0] - nearest[0]) ** 2 + (point[1] - nearest[1]) ** 2
        else:
            candidate = (point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2
        if candidate > distance:
            farthest, distance = index, candidate
    if distance <= tolerance * tolerance:
        return [start, end]
    return simplify(points[: farthest + 1], tolerance)[:-1] + simplify(points[farthest:], tolerance)


def trace_lines(skeleton: numpy.ndarray, scale: float) -> str:
    points = {tuple(value) for value in numpy.argwhere(skeleton)}
    neighbours: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for y, x in points:
        for delta_y in (-1, 0, 1):
            for delta_x in (-1, 0, 1):
                candidate = (y + delta_y, x + delta_x)
                if not (delta_y or delta_x) or candidate not in points:
                    continue
                # A rasterised diagonal usually appears as a tiny staircase.
                # Linking all eight neighbouring pixels turns each staircase
                # into a chain of triangles, producing hundreds of thousands
                # of two-pixel paths.  Retain a diagonal only when neither
                # of its orthogonal bridges exists.
                if delta_y and delta_x and (
                    (y, x + delta_x) in points or (y + delta_y, x) in points
                ):
                    continue
                neighbours[(y, x)].append(candidate)
    visited: set[frozenset[tuple[int, int]]] = set()
    lines: list[list[tuple[int, int]]] = []

    def follow(start: tuple[int, int], next_point: tuple[int, int]) -> list[tuple[int, int]]:
        line = [start, next_point]
        previous, current = start, next_point
        while len(neighbours[current]) == 2:
            options = [item for item in neighbours[current] if item != previous]
            if not options:
                break
            following = options[0]
            edge = frozenset((current, following))
            if edge in visited:
                break
            visited.add(edge)
            line.append(following)
            previous, current = current, following
        return line

    starts = sorted(point for point, adjacent in neighbours.items() if len(adjacent) != 2)
    for start in starts:
        for next_point in neighbours[start]:
            edge = frozenset((start, next_point))
            if edge not in visited:
                visited.add(edge)
                lines.append(follow(start, next_point))
    for start, adjacent in neighbours.items():
        for next_point in adjacent:
            edge = frozenset((start, next_point))
            if edge not in visited:
                visited.add(edge)
                lines.append(follow(start, next_point))

    commands: list[str] = []
    for line in lines:
        converted = simplify([(x / scale, y / scale) for y, x in line])
        if len(converted) < 2:
            continue
        commands.append("M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in converted))
    return " ".join(commands)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--inkscape", type=Path, default=Path(r"C:\Program Files\Inkscape\bin\inkscape.com"))
    parser.add_argument("--scale", type=int, default=2)
    args = parser.parse_args()

    source = ElementTree.parse(args.source)
    source_root = source.getroot()
    border = source.find(".//*[@id='Selection-6']")
    if border is None:
        raise ValueError("Source map has no Borders layer")
    view_box = source_root.attrib["viewBox"].split()
    root_transform = source.find(".//*[@id='g7772']").attrib["transform"]
    local_width = float(view_box[2]) / 1.4979998
    local_height = float(view_box[3]) / 1.4979998
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        raster_source = folder / "borders.svg"
        raster = folder / "borders.png"
        raster_source.write_text(
            f'<svg xmlns="{SVG}" viewBox="0 0 {local_width} {local_height}"><path d="{border.attrib["d"]}" fill="#000"/></svg>',
            encoding="utf-8",
        )
        subprocess.run(
            [
                str(args.inkscape), str(raster_source), "--export-type=png", f"--export-filename={raster}",
                f"--export-width={round(local_width * args.scale)}", "--export-background-opacity=0",
            ],
            check=True,
        )
        mask = read_png(raster)[:, :, 3] > 127
    centre_lines = trace_lines(skeletonise(mask), args.scale)
    if not centre_lines:
        raise ValueError("Could not trace a border centre-line")

    document = ElementTree.parse(args.map)
    root = document.getroot()
    map_border = root.find(".//*[@id='map-borders']")
    if map_border is None:
        raise ValueError("Generated map has no map-borders path")
    map_border.attrib["d"] = centre_lines
    style = root.find(f"{{{SVG}}}style")
    if style is None or style.text is None:
        raise ValueError("Generated map has no stylesheet")
    style.text = style.text.replace(
        ".map-borders { display:none; }",
        ".map-borders { fill:none; stroke:#343a3a; stroke-width:1; stroke-linejoin:round; stroke-linecap:round; }",
    ).replace(
        ".territory { fill-rule:evenodd; stroke:#343a3a; stroke-width:1.35; stroke-linejoin:round; }",
        ".territory { fill-rule:evenodd; }",
    ).replace(
        ".impassable { fill:#777870; stroke:#343a3a; stroke-width:1.35; stroke-linejoin:round; }",
        ".impassable { fill:#777870; }",
    )
    document.write(args.map, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {args.map} with {len(centre_lines)} characters of uniform border paths")


if __name__ == "__main__":
    main()
