"""Everyday map presentation, saved views, and clipboard output."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from diplomacy_app.domain.models import (
    DisplayMode,
    ImageArtifact,
    LabelMode,
    MapBounds,
    Perspective,
    PerspectiveKind,
    PixelSize,
    RenderRequest,
    SavedView,
    SavedViewId,
    game_folder_name,
)
from diplomacy_app.presentation import aspect_fitted_size
from diplomacy_app.ui.map_canvas import MapCanvas, MapZoomControls

_CUSTOM_VIEW = "custom"
_DEFAULT_IMAGE_EXPORT_SCALE = 2
_LAST_IMAGE_DIRECTORY_KEY = "imageSharing/lastDirectory"


class MapWorkspace(QWidget):
    perspective_requested = Signal(object)
    view_saved = Signal(object)
    message = Signal(str)

    def __init__(self, service, parent=None, settings: QSettings | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.settings = settings if settings is not None else QSettings()
        self.session: Any = None
        self.scene = None
        self._first_scene = True
        self._loaded_game_location = None
        self._applying_viewport = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 3, 4, 3)
        outer.setSpacing(3)
        self.outer_layout = outer
        controls = QHBoxLayout()
        controls.setSpacing(4)
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
        self.preview_orders = QPushButton("Preview orders on map")
        self.preview_orders.setToolTip(
            "Show order arrows and markers over the current position without resolving the phase"
        )
        self.preview_orders.clicked.connect(self._preview_orders)
        self.labels = QComboBox()
        self.labels.addItem("Display names", LabelMode.FULL_NAME)
        self.labels.addItem("Three-letter codes", LabelMode.ABBREVIATION)
        self.labels.currentIndexChanged.connect(self.schedule_refresh)
        controls.addWidget(self.labels)
        controls.addWidget(self.preview_orders)
        controls.addStretch()
        controls.addWidget(QLabel("View"))
        self.views = QComboBox()
        self.views.setObjectName("savedViewSelector")
        self.views.setMinimumWidth(240)
        self.views.setMinimumContentsLength(26)
        self.views.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
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
        self.save_image_button = QPushButton("Save image…")
        self.save_image_button.clicked.connect(self._save_image)
        controls.addWidget(self.save_image_button)
        outer.addLayout(controls)
        self.canvas = MapCanvas()
        outer.addWidget(self.canvas, 1)
        self.fog_badge = QLabel()
        self.fog_badge.setParent(self.canvas)
        self.fog_badge.setProperty("fog", True)
        self.fog_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fog_badge.setVisible(False)
        self.zoom_controls = MapZoomControls(self.canvas)
        self.zoom = self.zoom_controls.percentage
        self.outcomes = QLabel(self.canvas)
        self.outcomes.setStyleSheet(
            "background: rgba(255, 250, 240, 220); color: #292820; "
            "border-radius: 3px; padding: 2px 5px"
        )
        self.outcomes.setVisible(False)
        self.canvas.outcome_hovered.connect(self._outcome_hovered)
        self.canvas.resized.connect(self._position_overlays)
        self.canvas.viewport_changed.connect(self._viewport_changed)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(60)
        self.refresh_timer.timeout.connect(self.refresh)

    def _preview_orders(self) -> None:
        """Switch the map to its non-adjudicating order-overlay display."""
        index = self.mode.findData(DisplayMode.ORDERS)
        if self.mode.currentIndex() == index:
            self.schedule_refresh()
        else:
            self.mode.setCurrentIndex(index)

    def _outcome_hovered(self, text: str) -> None:
        self.outcomes.setText(text)
        self.outcomes.setVisible(bool(text))
        self._position_overlays()

    def _position_overlays(self) -> None:
        if self.fog_badge.isVisible():
            self.fog_badge.adjustSize()
            self.fog_badge.move(8, 8)
            self.fog_badge.raise_()
        if self.outcomes.isVisible():
            self.outcomes.adjustSize()
            self.outcomes.move(8, max(8, self.canvas.height() - self.outcomes.height() - 8))
            self.outcomes.raise_()

    def set_session(self, session) -> None:
        self.session = session
        if not session.game:
            return
        if session.game.location != self._loaded_game_location:
            self._loaded_game_location = session.game.location
            self.scene = None
            self._first_scene = True
            self.labels.blockSignals(True)
            self.labels.setCurrentIndex(self.labels.findData(LabelMode.FULL_NAME))
            self.labels.blockSignals(False)
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
        self.views.setItemData(0, "Full map", Qt.ItemDataRole.ToolTipRole)
        for view in session.game.saved_views:
            self.views.addItem(view.name, view)
            self.views.setItemData(
                self.views.count() - 1,
                view.name,
                Qt.ItemDataRole.ToolTipRole,
            )
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
            self.canvas.setStyleSheet(f"border: 2px solid {power.colour}")
        else:
            self.copy_button.setText("Copy map")
            self.canvas.setStyleSheet("")
        self._position_overlays()

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
        return RenderRequest(
            DisplayMode(self.mode.currentData()),
            LabelMode(self.labels.currentData()),
            bounds,
            size,
        )

    def refresh(self) -> None:
        if not self.session or not self.session.game:
            return
        try:
            visible = self.canvas.visible_bounds() if self.scene else None
            new_scene = self.service.compose_map(self._request())
            self.scene = new_scene
            self._applying_viewport = True
            try:
                self.canvas.set_scene(new_scene, fit=self._first_scene)
                self._first_scene = False
                if visible and visible.width > 0:
                    self.canvas.show_bounds(visible)
            finally:
                self._applying_viewport = False
        except Exception as exc:
            self.message.emit(f"Could not render map: {exc}")

    def _view_changed(self) -> None:
        view = self.views.currentData()
        if view == _CUSTOM_VIEW:
            return
        self._applying_viewport = True
        try:
            if view is None:
                self.canvas.fit_map()
            else:
                self.canvas.show_bounds(view.bounds)
        finally:
            self._applying_viewport = False

    def _viewport_changed(self) -> None:
        if self._applying_viewport or self.views.currentData() == _CUSTOM_VIEW:
            return
        self._applying_viewport = True
        try:
            index = self.views.findData(_CUSTOM_VIEW)
            if index < 0:
                self.views.insertItem(0, "Custom view", _CUSTOM_VIEW)
                self.views.setItemData(
                    0, "Viewport differs from a saved view", Qt.ItemDataRole.ToolTipRole
                )
                index = 0
            self.views.setCurrentIndex(index)
        finally:
            self._applying_viewport = False

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
        size = aspect_fitted_size(bounds, size)
        identifier = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or uuid.uuid4().hex[:8]
        view = SavedView(SavedViewId(identifier), name, bounds, bounds.width / bounds.height, size)
        try:
            self.service.save_view(view)
            self.views.addItem(view.name, view)
            self.views.setItemData(
                self.views.count() - 1,
                view.name,
                Qt.ItemDataRole.ToolTipRole,
            )
            self.views.setCurrentIndex(self.views.count() - 1)
            self._end_save_view()
        except Exception as exc:
            self.message.emit(f"Could not save view: {exc}")

    def _export_current_view(self) -> ImageArtifact:
        selected = self.views.currentData()
        bounds = self.canvas.visible_bounds()
        size = PixelSize(
            max(1, self.canvas.viewport().width()), max(1, self.canvas.viewport().height())
        )
        if isinstance(selected, SavedView):
            bounds, size = selected.bounds, selected.output_size
        size = aspect_fitted_size(bounds, size)
        size = PixelSize(
            size.width * _DEFAULT_IMAGE_EXPORT_SCALE,
            size.height * _DEFAULT_IMAGE_EXPORT_SCALE,
        )
        return self.service.export_map(self._request(bounds, size))

    def _copy(self) -> None:
        try:
            artifact = self._export_current_view()
            image = QImage.fromData(artifact.data)
            if image.isNull():
                raise ValueError("Exported image could not be loaded")
            QApplication.clipboard().setImage(image)
            self.copy_button.setText("Copied")
            QTimer.singleShot(1300, self._update_fog)
        except Exception as exc:
            self.message.emit(f"Could not copy map: {exc}")

    def _save_image(self) -> None:
        game_name = self.session.game.name if self.session and self.session.game else "map"
        phase = self.session.phase.phase_id.label if self.session and self.session.phase else ""
        suggested = game_folder_name(f"{game_name} {phase}") + ".png"
        last_directory = self.settings.value(_LAST_IMAGE_DIRECTORY_KEY, "")
        initial_path = Path(str(last_directory)) / suggested if last_directory else Path(suggested)
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save map image",
            str(initial_path),
            "PNG images (*.png)",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.casefold() != ".png":
            path = path.with_suffix(".png")
        try:
            artifact = self._export_current_view()
            path.write_bytes(artifact.data)
            self.settings.setValue(_LAST_IMAGE_DIRECTORY_KEY, str(path.resolve().parent))
            self.settings.sync()
            self.save_image_button.setText("Saved")
            QTimer.singleShot(1300, lambda: self.save_image_button.setText("Save image…"))
        except Exception as exc:
            self.message.emit(f"Could not save map image: {exc}")
