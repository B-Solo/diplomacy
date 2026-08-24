"""Interactive SVG map canvas with pointer-centred zooming and bounded panning."""

from __future__ import annotations

import math

from PySide6.QtCore import QByteArray, QEvent, QPoint, QPointF, QRectF, Qt, Signal
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
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

from diplomacy_app.domain.models import MapBounds, MapHotspot, MapScene, Point
from diplomacy_app.rendering.labels import label_lines

_SCROLLBAR_STYLE = """
QScrollBar { background: transparent; border: 0; margin: 0; }
QScrollBar:vertical { width: 8px; }
QScrollBar:horizontal { height: 8px; }
QScrollBar::handle { background: rgba(92, 88, 78, 145); border-radius: 4px; }
QScrollBar::handle:vertical { min-height: 32px; }
QScrollBar::handle:horizontal { min-width: 32px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


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
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#d7d1c2"))
        self.horizontalScrollBar().setStyleSheet(_SCROLLBAR_STYLE)
        self.verticalScrollBar().setStyleSheet(_SCROLLBAR_STYLE)
        self._item: QGraphicsSvgItem | None = None
        self._renderer: QSvgRenderer | None = None
        self._highlight: QGraphicsSvgItem | None = None
        self._scene_bounds = QRectF()
        self._hotspots: tuple[MapHotspot, ...] = ()
        self._fit_active = False
        self.setMouseTracking(True)

    def set_svg(self, svg: bytes, bounds: MapBounds | None = None, fit: bool = True) -> None:
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

    def set_scene(self, scene: MapScene, fit: bool = True) -> None:
        self._hotspots = scene.hotspots
        self.set_svg(scene.svg, scene.map_bounds, fit)
        self._hotspots = scene.hotspots

    def fit_map(self) -> None:
        if not self._scene_bounds.isEmpty():
            self._fit_active = True
            self.fitInView(self._scene_bounds, Qt.AspectRatioMode.KeepAspectRatio)
            self._emit_zoom()

    def set_standard_zoom(self) -> None:
        self._fit_active = False
        self.resetTransform()
        self._emit_zoom()

    def set_zoom_percentage(self, percentage: int) -> None:
        """Set an exact bounded zoom percentage."""
        self.zoom_by(max(8, min(1200, percentage)) / 100 / self.transform().m11())

    def zoom_by(self, factor: float, position: QPointF | None = None) -> None:
        self._fit_active = False
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
        device_type = device.type() if device is not None else QInputDevice.DeviceType.Unknown
        pixel_delta = event.pixelDelta()
        angle_delta = event.angleDelta()
        if device_type == QInputDevice.DeviceType.TouchPad:
            delta = (
                pixel_delta
                if not pixel_delta.isNull()
                else QPoint(round(angle_delta.x() / 8), round(angle_delta.y() / 8))
            )
            self.pan_by(delta)
        elif device_type == QInputDevice.DeviceType.Mouse:
            vertical = angle_delta.y() or pixel_delta.y()
            if vertical:
                self.zoom_by(1.2 if vertical > 0 else 1 / 1.2)
        elif not pixel_delta.isNull():
            self.pan_by(pixel_delta)
        elif angle_delta.y():
            self.zoom_by(1.2 if angle_delta.y() > 0 else 1 / 1.2)
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
            self._fit_active = False
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            self.centerOn(rect.center())
            self._emit_zoom()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit_active:
            self.fit_map()

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
    """Compact controls overlaid in the top-right corner of a map canvas."""

    def __init__(self, canvas: MapCanvas) -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.setObjectName("mapZoomControls")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(
            "#mapZoomControls { background: rgba(255, 250, 240, 220); "
            "border: 1px solid #8f846d; border-radius: 5px; } "
            "#mapZoomControls QPushButton, #mapZoomControls QLineEdit { "
            "min-width: 0; padding: 3px 6px; "
            "border-radius: 3px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self.zoom_out = QPushButton("−")
        self.zoom_out.setAccessibleName("Zoom out")
        self.zoom_out.setToolTip("Zoom out one level")
        self.zoom_out.setFixedWidth(28)
        self.zoom_out.clicked.connect(lambda: canvas.zoom_by(1 / 1.2))
        layout.addWidget(self.zoom_out)
        self.percentage = ZoomPercentageEdit(f"{round(canvas.transform().m11() * 100)}%")
        self.percentage.setAccessibleName("Zoom percentage")
        self.percentage.setToolTip("Enter a zoom percentage from 8% to 1200%")
        self.percentage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.percentage.setFixedWidth(54)
        self.percentage.editingFinished.connect(self._apply_percentage)
        layout.addWidget(self.percentage)
        self.zoom_in = QPushButton("+")
        self.zoom_in.setAccessibleName("Zoom in")
        self.zoom_in.setToolTip("Zoom in one level")
        self.zoom_in.setFixedWidth(28)
        self.zoom_in.clicked.connect(lambda: canvas.zoom_by(1.2))
        layout.addWidget(self.zoom_in)
        self.fit = QPushButton("Fit")
        self.fit.setToolTip("Fit the complete map in this pane")
        self.fit.clicked.connect(canvas.fit_map)
        layout.addWidget(self.fit)
        canvas.zoom_changed.connect(self._zoom_changed)
        canvas.installEventFilter(self)
        self.adjustSize()
        self._position_overlay()
        self.show()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.canvas and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Show,
        }:
            self._position_overlay()
        return super().eventFilter(watched, event)

    def _zoom_changed(self, value: int) -> None:
        self.percentage.setText(f"{value}%")
        self._position_overlay()

    def _apply_percentage(self) -> None:
        value = self.percentage.text().strip().removesuffix("%").strip()
        try:
            percentage = int(value)
        except ValueError:
            self._zoom_changed(round(self.canvas.transform().m11() * 100))
            return
        self.canvas.set_zoom_percentage(percentage)

    def _position_overlay(self) -> None:
        self.adjustSize()
        self.move(max(8, self.canvas.width() - self.width() - 12), 8)
        self.raise_()


class ZoomPercentageEdit(QLineEdit):
    """Compact percentage field that replaces its value on click."""

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.selectAll()

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.selectAll()


class AnchorItem(QGraphicsEllipseItem):
    """Draggable anchor marker that commits only after a completed drag."""

    def __init__(self, point: Point, colour: str, callback) -> None:
        super().__init__(-6, -6, 12, 12)
        self.setPos(QPointF(point.x, point.y))
        self.setBrush(QBrush(QColor(colour)))
        self.setPen(QPen(QColor("#fffdf7"), 2))
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable)
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
        glyph = QGraphicsTextItem()
        font = QFont("Georgia", size)
        font.setBold(bold)
        glyph.setFont(font)
        glyph.setDefaultTextColor(QColor(colour))
        glyph.document().setDocumentMargin(0)
        glyph.setPlainText("\n".join(label_lines(text)))
        self.glyph = glyph
        bounds = glyph.boundingRect()
        glyph.setPos(-bounds.center())
        self.addToGroup(glyph)
        self.setPos(QPointF(point.x, point.y))
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsMovable)
        self.setZValue(50)
        self.callback = callback

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        position = self.pos()
        self.callback(Point(position.x(), position.y()))
