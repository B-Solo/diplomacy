"""Everyday map presentation, saved views, and clipboard output."""

from __future__ import annotations

import re
import uuid
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from diplomacy_app.domain.models import (
    DisplayMode,
    LabelMode,
    MapBounds,
    Perspective,
    PerspectiveKind,
    PixelSize,
    RenderRequest,
    SavedView,
    SavedViewId,
)
from diplomacy_app.ui.map_canvas import MapCanvas, MapZoomControls


class MapWorkspace(QWidget):
    perspective_requested = Signal(object)
    view_saved = Signal(object)
    message = Signal(str)

    def __init__(self, service, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.session: Any = None
        self.scene = None
        self._first_scene = True
        self._loaded_game_location = None
        outer = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.perspective_label = QLabel("Viewing as")
        self.perspective = QComboBox()
        self.perspective.currentIndexChanged.connect(self._perspective_changed)
        controls.addWidget(self.perspective_label)
        controls.addWidget(self.perspective)
        self.mode = QComboBox()
        self.mode.addItem("Position", DisplayMode.POSITION)
        self.mode.addItem("Orders", DisplayMode.ORDERS)
        self.mode.currentIndexChanged.connect(self.schedule_refresh)
        controls.addWidget(self.mode)
        self.labels = QComboBox()
        self.labels.addItem("Territory names", LabelMode.FULL_NAME)
        self.labels.addItem("Three-letter codes", LabelMode.ABBREVIATION)
        self.labels.currentIndexChanged.connect(self.schedule_refresh)
        controls.addWidget(self.labels)
        controls.addStretch()
        controls.addWidget(QLabel("View"))
        self.views = QComboBox()
        self.views.currentIndexChanged.connect(self._view_changed)
        controls.addWidget(self.views)
        save = QPushButton("Save current")
        save.clicked.connect(self._begin_save_view)
        controls.addWidget(save)
        self.save_name = QLineEdit()
        self.save_name.setPlaceholderText("View name")
        self.save_name.setMaximumWidth(170)
        self.save_name.returnPressed.connect(self._save_view)
        self.save_name.setVisible(False)
        controls.addWidget(self.save_name)
        self.save_confirm = QPushButton("Save")
        self.save_confirm.clicked.connect(self._save_view)
        self.save_confirm.setVisible(False)
        controls.addWidget(self.save_confirm)
        self.save_cancel = QPushButton("Cancel")
        self.save_cancel.clicked.connect(self._end_save_view)
        self.save_cancel.setVisible(False)
        controls.addWidget(self.save_cancel)
        copy = QPushButton("Copy map")
        copy.setProperty("primary", True)
        copy.clicked.connect(self._copy)
        self.copy_button = copy
        controls.addWidget(copy)
        outer.addLayout(controls)
        self.fog_badge = QLabel()
        self.fog_badge.setProperty("fog", True)
        self.fog_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fog_badge.setVisible(False)
        outer.addWidget(self.fog_badge)
        self.canvas = MapCanvas()
        outer.addWidget(self.canvas, 1)
        self.zoom_controls = MapZoomControls(self.canvas)
        self.zoom = self.zoom_controls.percentage
        footer = QHBoxLayout()
        self.outcomes = QLabel()
        self.outcomes.setProperty("muted", True)
        footer.addWidget(self.outcomes)
        outer.addLayout(footer)
        self.canvas.outcome_hovered.connect(self.outcomes.setText)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(60)
        self.refresh_timer.timeout.connect(self.refresh)

    def set_session(self, session) -> None:
        self.session = session
        if not session.game:
            return
        if session.game.location != self._loaded_game_location:
            self._loaded_game_location = session.game.location
            self.scene = None
            self._first_scene = True
        fog = session.game.settings.visibility_policy.enabled
        self.perspective_label.setVisible(fog)
        self.perspective.setVisible(fog)
        self.perspective.blockSignals(True)
        self.perspective.clear()
        self.perspective.addItem("Gamemaster", Perspective(PerspectiveKind.GAMEMASTER))
        for power in session.game.map_definition.powers:
            self.perspective.addItem(power.name, Perspective(PerspectiveKind.POWER, power.id))
        index = self.perspective.findData(session.selected_perspective)
        self.perspective.setCurrentIndex(max(0, index))
        self.perspective.blockSignals(False)
        self.views.blockSignals(True)
        self.views.clear()
        self.views.addItem("Full map", None)
        for view in session.game.saved_views:
            self.views.addItem(view.name, view)
        self.views.blockSignals(False)
        self._update_fog()
        self.schedule_refresh()

    def _update_fog(self) -> None:
        perspective = self.perspective.currentData()
        power = None
        if perspective and perspective.kind is PerspectiveKind.POWER and self.session.game:
            power = next(
                item
                for item in self.session.game.map_definition.powers
                if item.id == perspective.power_id
            )
        self.fog_badge.setVisible(power is not None)
        if power:
            self.fog_badge.setText(f"Fog of War preview — {power.name}")
            self.copy_button.setText(f"Copy {power.name} view")
            self.canvas.setStyleSheet(f"border: 4px solid {power.colour}")
        else:
            self.copy_button.setText("Copy map")
            self.canvas.setStyleSheet("")

    def _perspective_changed(self) -> None:
        perspective = self.perspective.currentData()
        if perspective is None:
            return
        try:
            self.session = self.service.select_perspective(perspective)
            self._update_fog()
            self.schedule_refresh()
        except Exception as exc:
            self.message.emit(f"Could not change perspective: {exc}")

    def schedule_refresh(self) -> None:
        self.refresh_timer.start()

    def _full_bounds(self) -> MapBounds:
        if self.scene:
            return self.scene.map_bounds
        return MapBounds(0, 0, 1000, 1000)

    def _request(
        self, bounds: MapBounds | None = None, size: PixelSize | None = None
    ) -> RenderRequest:
        if bounds is None:
            bounds = self._full_bounds()
        if size is None:
            size = PixelSize(
                max(1, self.canvas.viewport().width()), max(1, self.canvas.viewport().height())
            )
        return RenderRequest(self.mode.currentData(), self.labels.currentData(), bounds, size)

    def refresh(self) -> None:
        if not self.session or not self.session.game:
            return
        try:
            visible = self.canvas.visible_bounds() if self.scene else None
            new_scene = self.service.compose_map(self._request())
            self.scene = new_scene
            self.canvas.set_scene(new_scene, fit=self._first_scene)
            self._first_scene = False
            if visible and visible.width > 0:
                self.canvas.show_bounds(visible)
        except Exception as exc:
            self.message.emit(f"Could not render map: {exc}")

    def _view_changed(self) -> None:
        view = self.views.currentData()
        if view is None:
            self.canvas.fit_map()
        else:
            self.canvas.show_bounds(view.bounds)

    def _begin_save_view(self) -> None:
        self.save_name.setVisible(True)
        self.save_confirm.setVisible(True)
        self.save_cancel.setVisible(True)
        self.save_name.setFocus()

    def _end_save_view(self) -> None:
        self.save_name.clear()
        self.save_name.setVisible(False)
        self.save_confirm.setVisible(False)
        self.save_cancel.setVisible(False)

    def _save_view(self) -> None:
        name = self.save_name.text().strip()
        if not name:
            return
        bounds = self.canvas.visible_bounds()
        size = PixelSize(
            max(1, self.canvas.viewport().width()), max(1, self.canvas.viewport().height())
        )
        identifier = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or uuid.uuid4().hex[:8]
        view = SavedView(SavedViewId(identifier), name, bounds, bounds.width / bounds.height, size)
        try:
            self.service.save_view(view)
            self.views.addItem(view.name, view)
            self.views.setCurrentIndex(self.views.count() - 1)
            self._end_save_view()
        except Exception as exc:
            self.message.emit(f"Could not save view: {exc}")

    def _copy(self) -> None:
        try:
            selected = self.views.currentData()
            bounds = self.canvas.visible_bounds()
            size = PixelSize(
                max(1, self.canvas.viewport().width()), max(1, self.canvas.viewport().height())
            )
            if selected is not None:
                bounds, size = selected.bounds, selected.output_size
            artifact = self.service.export_map(self._request(bounds, size))
            image = QImage.fromData(artifact.data, b"PNG")
            if image.isNull():
                raise ValueError("Exported image could not be loaded")
            QApplication.clipboard().setImage(image)
            self.copy_button.setText("Copied")
            QTimer.singleShot(1300, self._update_fog)
        except Exception as exc:
            self.message.emit(f"Could not copy map: {exc}")
