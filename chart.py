import pyqtgraph as pg
from PyQt5 import QtWidgets
from PyQt5.QtGui import QFont, QColor

# --- Theme borrowed from dashboard.py ---
THEME = {
    "bg": "k",                 # black background
    "axis_text": "w",          # white
    "grid_alpha": 0.3,
    "bar": "#FF8C00",          # dark orange
    "bar_pen": None,           # no border to match dashboard bars
    "axis_font_pt": 14,
    "label_font_pt": 16,
}


def _apply_plot_style(plot: pg.PlotWidget):
    plot.setBackground(THEME["bg"])
    plot.setMouseEnabled(x=False, y=False)
    plot.hideButtons()

    vb = plot.getViewBox()
    vb.setMenuEnabled(False)
    vb.setMouseMode(pg.ViewBox.RectMode)

    # --- Bigger label fonts ---
    font_label = QFont()
    font_label.setPointSize(THEME["label_font_pt"])
    font_label.setBold(True)

    plot.setLabel("left", "<b>Entries</b>", color=THEME["axis_text"])
    plot.setLabel("bottom", "<b>Date</b>", color=THEME["axis_text"])
    plot.getAxis("left").label.setFont(font_label)
    plot.getAxis("bottom").label.setFont(font_label)

    # --- Axis pens ---
    plot.getAxis("bottom").setTextPen(pg.mkPen(THEME["axis_text"]))
    plot.getAxis("left").setTextPen(pg.mkPen(THEME["axis_text"]))

    # --- Bigger tick fonts ---
    f = QFont()
    f.setPointSize(THEME["axis_font_pt"])
    plot.getAxis("left").setTickFont(f)
    plot.getAxis("bottom").setTickFont(f)

    # --- Grid ---
    plot.showGrid(x=False, y=True, alpha=THEME["grid_alpha"])


def init_bar_chart(container: QtWidgets.QWidget, y_max=40):
    layout = container.layout()
    if layout is None:
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

    plot = pg.PlotWidget(container)
    plot.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    _apply_plot_style(plot)
    plot.setYRange(0, y_max, padding=0.0)

    layout.addWidget(plot)
    container._bar_plot = plot
    container._bar_item = None


def update_bar_chart(container: QtWidgets.QWidget, dates, counts, y_max=40):
    try:
        if not hasattr(container, "_bar_plot"):
            init_bar_chart(container, y_max=y_max)

        plot = container._bar_plot
        plot.clear()

        xs = list(range(len(dates)))
        bar = pg.BarGraphItem(
            x=xs,
            height=[float(c or 0) for c in counts],
            width=0.6,
            brush=QColor(THEME["bar"]),
            pen=THEME["bar_pen"],
        )
        plot.addItem(bar)
        container._bar_item = bar

        max_labels = 16
        step = max(1, int(len(dates) / max_labels)) if len(dates) > max_labels else 1
        ticks = [(i, dates[i]) for i in range(0, len(dates), step)]
        plot.getAxis("bottom").setTicks([ticks])

        plot.setXRange(-0.5, len(xs) - 0.5, padding=0.02)
        plot.setYRange(0, y_max, padding=0.0)

    except Exception as e:
        print(f"update_bar_chart error: {e}")