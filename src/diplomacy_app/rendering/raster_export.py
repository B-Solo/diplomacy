"""Qt SVG raster export isolated from domain and composition code."""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from diplomacy_app.domain.errors import RenderingError
from diplomacy_app.domain.models import ImageArtifact, MapBounds, MapScene, RenderRequest


def export_scene(scene: MapScene, request: RenderRequest) -> ImageArtifact:
    source = scene.map_bounds
    requested = request.bounds
    left = max(source.x, requested.x)
    top = max(source.y, requested.y)
    right = min(source.x + source.width, requested.x + requested.width)
    bottom = min(source.y + source.height, requested.y + requested.height)
    if right <= left or bottom <= top:
        raise RenderingError("The selected view does not intersect the map")
    bounds = MapBounds(left, top, right - left, bottom - top)
    renderer = QSvgRenderer(QByteArray(scene.svg))
    if not renderer.isValid():
        raise RenderingError("Composed SVG could not be rasterised")
    renderer.setViewBox(QRectF(bounds.x, bounds.y, bounds.width, bounds.height))
    image = QImage(
        request.output_size.width, request.output_size.height, QImage.Format.Format_ARGB32
    )
    image.fill(QColor("transparent"))
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):  # type: ignore[call-overload]
        raise RenderingError("Qt failed to encode the map as PNG")
    return ImageArtifact("image/png", data.data(), request.output_size)
