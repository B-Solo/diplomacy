"""Warm, map-table-inspired application styling."""

from PySide6.QtGui import QColor, QPalette

STYLE = """
QWidget { font-size: 10pt; color: #292820; }
QMainWindow { background: #e9e4d6; }
QToolBar { background: #f6f1e3; color: #292820; border: 0; border-bottom: 1px solid #b7ae97; spacing: 4px; padding: 4px; }
QPushButton, QToolButton, QComboBox, QSpinBox { background: #fffaf0; color: #292820; border: 1px solid #a89d83; border-radius: 3px; padding: 4px 7px; }
QPushButton, QToolButton { padding: 5px 9px; }
QPushButton:disabled, QToolButton:disabled { background: #ddd8cb; color: #777165; border-color: #c2baa8; }
QPushButton[seasonNavigation="true"]:disabled { background: #eeeae0; color: #b8b1a3; border-color: #d8d1c2; }
QComboBox { padding-right: 30px; selection-background-color: #42584b; selection-color: #fffdf5; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; background: #e8dec7; border: 0; border-left: 1px solid #b8ad94; width: 24px; }
QComboBox::down-arrow { image: none; width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid #39372f; }
QComboBox:disabled, QSpinBox:disabled { background: #ddd8cb; color: #777165; border-color: #c2baa8; }
QComboBox QAbstractItemView { background: #fffaf0; color: #292820; border: 1px solid #a89d83; selection-background-color: #42584b; selection-color: #fffdf5; outline: 0; }
QComboBox QAbstractItemView::item { background: #fffaf0; color: #292820; padding: 3px 6px; }
QComboBox QAbstractItemView::item:hover { background: #f0e5ca; color: #292820; }
QComboBox QAbstractItemView::item:selected { background: #42584b; color: #fffdf5; }
QPushButton:hover, QToolButton:hover { background: #f0e5ca; border-color: #756a52; }
QPushButton:pressed, QToolButton:pressed { background: #dfd1af; }
QPushButton[primary="true"] { background: #42584b; color: #fffdf5; border-color: #2f4237; font-weight: 600; }
QPushButton[primary="true"]:disabled { background: #94a198; color: #f8f5ea; border-color: #7d8b82; }
QPushButton[danger="true"] { background: #8a403a; color: white; border-color: #6c2d29; }
QPushButton[danger="true"]:disabled { background: #a77b77; color: #fffaf0; border-color: #92706c; }
QCheckBox { color: #292820; spacing: 6px; }
QCheckBox:disabled { color: #777165; }
QTabBar::tab { background: #ded7c6; color: #4f4b40; padding: 6px 12px; border: 1px solid #c2b9a5; border-bottom: 2px solid #9f9683; font-weight: 600; }
QTabBar::tab:hover:!selected { background: #eee6d3; color: #292820; }
QTabBar::tab:selected { background: #fffaf0; color: #31483b; border-color: #a99d83; border-bottom-color: #9a7438; }
QTabWidget::pane { border: 0; }
QGroupBox { background: #fbf7eb; color: #292820; border: 1px solid #b9b09b; border-radius: 4px; margin-top: 8px; padding: 8px; font-weight: 600; }
QGroupBox::title { background: #fbf7eb; color: #292820; subcontrol-origin: margin; left: 9px; padding: 0 4px; }
QPlainTextEdit, QTextEdit, QLineEdit, QListWidget, QTableWidget, QTreeWidget { background: #fffdf7; color: #171714; border: 1px solid #aaa18e; border-radius: 2px; selection-background-color: #42584b; selection-color: #fffdf5; placeholder-text-color: #777165; }
QHeaderView::section { background: #e8e0cc; color: #292820; border: 0; border-right: 1px solid #b9b09b; border-bottom: 1px solid #a89d83; padding: 4px 6px; font-weight: 600; }
QTableCornerButton::section { background: #e8e0cc; border: 0; border-right: 1px solid #b9b09b; border-bottom: 1px solid #a89d83; }
QScrollBar { background: #eee8da; border: 0; margin: 0; }
QScrollBar:vertical { width: 10px; }
QScrollBar:horizontal { height: 10px; }
QScrollBar::handle { background: #817b6c; border-radius: 4px; }
QScrollBar::handle:vertical { min-height: 28px; }
QScrollBar::handle:horizontal { min-width: 28px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: #eee8da; }
QStatusBar { background: #f4eedf; color: #292820; border-top: 1px solid #b7ae97; }
QScrollArea { border: 0; background: transparent; }
QLabel[muted="true"] { color: #6f6a5d; }
QLabel[fog="true"] { background: #f1d7a9; color: #694817; border: 1px solid #b8873b; border-radius: 5px; padding: 3px 7px; font-weight: 700; }
QToolTip { background: #fffaf0; color: #171714; border: 1px solid #756a52; padding: 3px; }
"""


def light_palette() -> QPalette:
    """Return a complete light palette that is independent of the desktop theme."""
    palette = QPalette()
    colours = {
        QPalette.ColorRole.Window: "#e9e4d6",
        QPalette.ColorRole.WindowText: "#292820",
        QPalette.ColorRole.Base: "#fffdf7",
        QPalette.ColorRole.AlternateBase: "#f4eedf",
        QPalette.ColorRole.ToolTipBase: "#fffaf0",
        QPalette.ColorRole.ToolTipText: "#171714",
        QPalette.ColorRole.Text: "#171714",
        QPalette.ColorRole.Button: "#fffaf0",
        QPalette.ColorRole.ButtonText: "#292820",
        QPalette.ColorRole.BrightText: "#fffdf5",
        QPalette.ColorRole.Highlight: "#42584b",
        QPalette.ColorRole.HighlightedText: "#fffdf5",
        QPalette.ColorRole.Link: "#315b78",
        QPalette.ColorRole.PlaceholderText: "#777165",
    }
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, colour in colours.items():
            palette.setColor(group, role, QColor(colour))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#777165"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, QColor("#e9e4d6"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#eee9dd"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor("#ddd8cb"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#9da89f"))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.HighlightedText,
        QColor("#fffdf5"),
    )
    return palette
