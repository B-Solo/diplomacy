"""Interactive SVG map canvas with pointer-centred zooming and bounded panning."""

from __future__ import annotations

import math

from PySide6.QtCore import QByteArray, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QInputDevice,
    QNativeGestureEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from PySide6.QtWidgets import (
    QGraphicsColorizeEffect,
    QGraphicsEllipseItem,
    QGraphicsItemGroup,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from diplomacy_app.domain.models import MapBounds, MapHotspot, MapScene, Point


class MapCanvas(QGraphicsView):
    zoom_changed = Signal(int)
    outcome_hovered = Signal(str)
    scene_hovered = Signal(float, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#d7d1c2"))
        self._item: QGraphicsSvgItem | None = None
        self._renderer: QSvgRenderer | None = None
        self._highlight: QGraphicsSvgItem | None = None
        self._scene_bounds = QRectF()
        self._hotspots: tuple[MapHotspot, ...] = ()
        self.setMouseTracking(True)

    def set_svg(self, svg: bytes, bounds: MapBounds | None = None, fit: bool = False) -> None:
        renderer = QSvgRenderer(QByteArray(svg), self)
        if not renderer.isValid():
            raise ValueError("Invalid SVG scene")
        self.scene().clear()
        item = QGraphicsSvgItem()
        item.setSharedRenderer(renderer)
        self.scene().addItem(item)
        self._item = item
        self._renderer = renderer
        self._highlight = None
        if bounds:
            self._scene_bounds = QRectF(bounds.x, bounds.y, bounds.width, bounds.height)
        else:
            self._scene_bounds = renderer.viewBoxF()
        self.scene().setSceneRect(self._scene_bounds)
        if fit:
            self.fit_map()

    def set_scene(self, scene: MapScene, fit: bool = False) -> None:
        self._hotspots = scene.hotspots
        self.set_svg(scene.svg, scene.map_bounds, fit)
        self._hotspots = scene.hotspots

    def fit_map(self) -> None:
        if not self._scene_bounds.isEmpty():
            self.fitInView(self._scene_bounds, Qt.AspectRatioMode.KeepAspectRatio)
            self._emit_zoom()

    def set_standard_zoom(self) -> None:
        self.resetTransform()
        self._emit_zoom()

    def zoom_by(self, factor: float, position: QPointF | None = None) -> None:
        current = self.transform().m11()
        target = max(0.08, min(12.0, current * factor))
        if position is not None:
            scene_position = self.mapToScene(position.toPoint())
            anchor = self.transformationAnchor()
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.scale(target / current, target / current)
        if position is not None:
            moved_position = self.mapToScene(position.toPoint())
            offset = moved_position - scene_position
            self.translate(offset.x(), offset.y())
            self.setTransformationAnchor(anchor)
        self._emit_zoom()

    def viewportEvent(self, event) -> bool:
        if (
            isinstance(event, QNativeGestureEvent)
            and event.gestureType() is Qt.NativeGestureType.ZoomNativeGesture
        ):
            self.zoom_by(math.exp(event.value()), event.position())
            event.accept()
            return True
        return super().viewportEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        device = event.device()
        touchpad = device is not None and device.type() is QInputDevice.DeviceType.TouchPad
        pixel_delta = event.pixelDelta()
        if touchpad or not pixel_delta.isNull():
            angle_delta = event.angleDelta()
            delta = (
                pixel_delta
                if not pixel_delta.isNull()
                else QPoint(round(angle_delta.x() / 8), round(angle_delta.y() / 8))
            )
            self.pan_by(delta)
        elif event.angleDelta().y():
            self.zoom_by(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
        event.accept()

    def pan_by(self, delta: QPoint) -> None:
        """Pan by a trackpad-style pixel delta without changing zoom."""
        horizontal = self.horizontalScrollBar()
        vertical = self.verticalScrollBar()
        horizontal.setValue(horizontal.value() - delta.x())
        vertical.setValue(vertical.value() - delta.y())

    def _emit_zoom(self) -> None:
        self.zoom_changed.emit(round(self.transform().m11() * 100))

    def visible_bounds(self) -> MapBounds:
        rect = (
            self.mapToScene(self.viewport().rect()).boundingRect().intersected(self._scene_bounds)
        )
        return MapBounds(rect.x(), rect.y(), rect.width(), rect.height())

    def show_bounds(self, bounds: MapBounds) -> None:
        rect = QRectF(bounds.x, bounds.y, bounds.width, bounds.height).intersected(
            self._scene_bounds
        )
        if not rect.isEmpty():
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            self.centerOn(rect.center())
            self._emit_zoom()

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        point = self.mapToScene(event.position().toPoint())
        self.scene_hovered.emit(point.x(), point.y())
        message = ""
        for hotspot in self._hotspots:
            for start, end in zip(hotspot.path, hotspot.path[1:], strict=False):
                dx, dy = end.x - start.x, end.y - start.y
                length_squared = dx * dx + dy * dy
                if not length_squared:
                    continue
                t = max(
                    0.0,
                    min(
                        1.0,
                        ((point.x() - start.x) * dx + (point.y() - start.y) * dy) / length_squared,
                    ),
                )
                distance = math.hypot(
                    point.x() - (start.x + t * dx), point.y() - (start.y + t * dy)
                )
                if distance <= hotspot.hit_width:
                    message = ", ".join(hotspot.outcome_codes)
                    break
            if message:
                break
        self.outcome_hovered.emit(message)

    def highlight_element(self, element_id: str | None) -> None:
        """Overlay one SVG element without rebuilding or refitting the scene."""
        if self._highlight is not None:
            self.scene().removeItem(self._highlight)
            self._highlight = None
        if not element_id or self._renderer is None or not self._renderer.elementExists(element_id):
            return
        highlight = QGraphicsSvgItem()
        highlight.setSharedRenderer(self._renderer)
        highlight.setElementId(element_id)
        effect = QGraphicsColorizeEffect(highlight)
        effect.setColor(QColor("#e2a92f"))
        effect.setStrength(0.82)
        highlight.setGraphicsEffect(effect)
        highlight.setOpacity(0.78)
        highlight.setZValue(40)
        highlight.setPos(self._renderer.boundsOnElement(element_id).topLeft())
        self.scene().addItem(highlight)
        self._highlight = highlight


class MapZoomControls(QWidget):
    """Visible, platform-independent controls for a map canvas transform."""

    def __init__(self, canvas: MapCanvas, parent=None) -> None:
        super().__init__(parent)
        self.canvas = canvas
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Zoom"))
        self.zoom_out = QPushButton("Zoom out")
        self.zoom_out.setToolTip("Zoom out one level")
        self.zoom_out.clicked.connect(lambda: canvas.zoom_by(1 / 1.2))
        layout.addWidget(self.zoom_out)
        self.percentage = QPushButton("100%")
        self.percentage.setToolTip("Return to 100% zoom")
        self.percentage.clicked.connect(canvas.set_standard_zoom)
        layout.addWidget(self.percentage)
        self.zoom_in = QPushButton("Zoom in")
        self.zoom_in.setToolTip("Zoom in one level")
        self.zoom_in.clicked.connect(lambda: canvas.zoom_by(1.2))
        layout.addWidget(self.zoom_in)
        self.fit = QPushButton("Fit map")
        self.fit.setToolTip("Fit the complete map in this pane")
        self.fit.clicked.connect(canvas.fit_map)
        layout.addWidget(self.fit)
        canvas.zoom_changed.connect(lambda value: self.percentage.setText(f"{value}%"))


class AnchorItem(QGraphicsEllipseItem):
    """Draggable anchor marker that commits only after a completed drag."""

    def __init__(self, point: Point, colour: str, callback) -> None:
        super().__init__(-6, -6, 12, 12)
        self.setPos(QPointF(point.x, point.y))
        self.setBrush(QBrush(QColor(colour)))
        self.setPen(QPen(QColor("#fffdf7"), 2))
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(50)
        self.callback = callback

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        position = self.pos()
        self.callback(Point(position.x(), position.y()))


class UnitAnchorItem(QGraphicsItemGroup):
    """Draggable unit-symbol preview centred on its presentation anchor."""

    def __init__(self, point: Point, svg: bytes, callback) -> None:
        super().__init__()
        self._renderer = QSvgRenderer(QByteArray(svg))
        if not self._renderer.isValid():
            raise ValueError("Invalid unit SVG")
        symbol = QGraphicsSvgItem()
        symbol.setSharedRenderer(self._renderer)
        bounds = self._renderer.viewBoxF()
        scale = min(32 / max(bounds.width(), 1), 22 / max(bounds.height(), 1))
        symbol.setScale(scale)
        symbol.setPos(-bounds.center().x() * scale, -bounds.center().y() * scale)
        self.addToGroup(symbol)
        self.setPos(QPointF(point.x, point.y))
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(50)
        self.callback = callback

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        position = self.pos()
        self.callback(Point(position.x(), position.y()))


class TextAnchorItem(QGraphicsItemGroup):
    """Draggable rendered label or supply-centre glyph."""

    def __init__(
        self,
        point: Point,
        text: str,
        colour: str,
        callback,
        *,
        size: int = 11,
        bold: bool = False,
    ) -> None:
        super().__init__()
        glyph = QGraphicsSimpleTextItem(text)
        font = QFont("Georgia", size)
        font.setBold(bold)
        glyph.setFont(font)
        glyph.setBrush(QBrush(QColor(colour)))
        bounds = glyph.boundingRect()
        glyph.setPos(-bounds.center())
        self.addToGroup(glyph)
        self.setPos(QPointF(point.x, point.y))
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(50)
        self.callback = callback

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        position = self.pos()
        self.callback(Point(position.x(), position.y()))
