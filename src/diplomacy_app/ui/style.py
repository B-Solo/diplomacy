"""Warm, map-table-inspired application styling."""

STYLE = """
QWidget { font-family: "Segoe UI", sans-serif; font-size: 10pt; color: #292820; }
QMainWindow { background: #e9e4d6; }
QToolBar { background: #f6f1e3; border: 0; border-bottom: 1px solid #b7ae97; spacing: 7px; padding: 7px; }
QPushButton, QToolButton, QComboBox, QSpinBox { background: #fffaf0; border: 1px solid #a89d83; border-radius: 4px; padding: 6px 10px; }
QComboBox { color: #292820; }
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox::down-arrow { width: 9px; height: 6px; }
QComboBox QAbstractItemView { background: #fffaf0; color: #292820; border: 1px solid #a89d83; selection-background-color: #42584b; selection-color: #fffdf5; outline: 0; }
QComboBox QAbstractItemView::item { background: #fffaf0; color: #292820; padding: 5px 8px; }
QComboBox QAbstractItemView::item:hover { background: #f0e5ca; color: #292820; }
QComboBox QAbstractItemView::item:selected { background: #42584b; color: #fffdf5; }
QPushButton:hover, QToolButton:hover { background: #f0e5ca; border-color: #756a52; }
QPushButton:pressed, QToolButton:pressed { background: #dfd1af; }
QPushButton[primary="true"] { background: #42584b; color: #fffdf5; border-color: #2f4237; font-weight: 600; }
QPushButton[danger="true"] { background: #8a403a; color: white; border-color: #6c2d29; }
QTabBar::tab { background: transparent; padding: 10px 20px; border-bottom: 3px solid transparent; font-weight: 600; }
QTabBar::tab:selected { color: #31483b; border-bottom-color: #9a7438; }
QTabWidget::pane { border: 0; }
QGroupBox { background: #fbf7eb; border: 1px solid #b9b09b; border-radius: 6px; margin-top: 11px; padding: 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 9px; padding: 0 4px; }
QPlainTextEdit, QTextEdit, QLineEdit, QListWidget, QTableWidget, QTreeWidget { background: #fffdf7; border: 1px solid #aaa18e; border-radius: 4px; selection-background-color: #698273; }
QStatusBar { background: #f4eedf; border-top: 1px solid #b7ae97; }
QScrollArea { border: 0; background: transparent; }
QLabel[muted="true"] { color: #6f6a5d; }
QLabel[fog="true"] { background: #f1d7a9; color: #694817; border: 1px solid #b8873b; border-radius: 8px; padding: 5px 10px; font-weight: 700; }
"""
