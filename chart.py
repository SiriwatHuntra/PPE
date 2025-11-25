import pyqtgraph as pg
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QBrush
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtWidgets import QWidget

# --- Theme borrowed from dashboard.py ---
THEME = {
    "bg": "k",                 # black background
    "axis_text": "w",          # white
    "grid_alpha": 0.3,
    "bar": "#FF8C00",          # Default single color
    "bar_colors": ["#FF8C00","#BD3333","#3376BD","#00798C","#52489C"],  # Colors for each task
    "bar_pen": None,           # no border to match dashboard bars
    "axis_font_pt": 14,
    "label_font_pt": 16,
    "pie": ["#28C220","#E6394A"],  # Green for Pass, Red for Timeout
}


def _apply_plot_style(plot: pg.PlotWidget):
    plot.setBackground(THEME["bg"])
    plot.setMouseEnabled(x=True, y=True)
    plot.hideButtons()

    vb = plot.getViewBox()
    vb.setMenuEnabled(False)
    vb.setMouseMode(pg.ViewBox.RectMode)

    # --- Bigger label fonts ---
    font_label = QFont()
    font_label.setPointSize(THEME["label_font_pt"])
    font_label.setBold(True)

    plot.setLabel("left", "<b>Entries (times)</b>", color=THEME["axis_text"])
    plot.setLabel("bottom", "<b>Date (DD/MM)</b>", color=THEME["axis_text"])
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


def update_bar_chart_by_task(container: QtWidgets.QWidget, data_dict, y_max=40):
    """
    Update bar chart with 7 days of data as stacked bars by task
    }
    """
    try:
        if not hasattr(container, "_bar_plot"):
            init_bar_chart(container, y_max=y_max)

        plot = container._bar_plot
        plot.clear()

        dates = data_dict.get("dates", [])
        tasks = data_dict.get("tasks", {})
        
        if not dates or not tasks:
            return

        num_dates = len(dates)
        
        # Calculate stacked totals for dynamic y_max
        stacked_totals = [0] * num_dates
        for counts in tasks.values():
            for i, count in enumerate(counts):
                if i < num_dates:
                    stacked_totals[i] += count
        
        max_stack = max(stacked_totals) if stacked_totals else 0
        
        dynamic_y_max = max(40, y_max)
        while max_stack > dynamic_y_max:
            dynamic_y_max += 20

        # Bar width
        bar_width = 0.6
        x_positions = list(range(num_dates))
        
        # Create stacked bars - start from bottom
        bottom_heights = [0] * num_dates
        
        for task_idx, (task_name, counts) in enumerate(tasks.items()):
            # Get color for this task
            color = THEME["bar_colors"][task_idx % len(THEME["bar_colors"])]
            
            # Calculate y0 (bottom) and heights for this layer
            y0_values = bottom_heights.copy()
            heights = counts.copy()
            
            # Create bars for this task layer
            bar = pg.BarGraphItem(
                x=x_positions,
                height=heights,
                width=bar_width,
                y0=y0_values,
                brush=QColor(color),
                pen=THEME["bar_pen"],
                name=task_name
            )
            plot.addItem(bar)
            
            # Update bottom heights for next layer
            for i in range(num_dates):
                bottom_heights[i] += counts[i]

        # Set x-axis labels (dates)
        ticks = [(i, dates[i]) for i in range(num_dates)]
        plot.getAxis("bottom").setTicks([ticks])

        # Set ranges
        plot.setXRange(-0.5, num_dates - 0.5, padding=0.05)
        plot.setYRange(0, dynamic_y_max, padding=0.0)
        
        plot.addLegend(offset=(790, 5))

    except Exception as e:
        print(f"update_bar_chart_by_task error: {e}")


def update_bar_chart(container: QtWidgets.QWidget, labels, counts, y_max=40):
    """
    Original function - Update bar chart with simple labels and counts
    This is kept for backward compatibility
    """
    try:
        if not hasattr(container, "_bar_plot"):
            init_bar_chart(container, y_max=y_max)

        plot = container._bar_plot
        plot.clear()

        xs = list(range(len(labels)))
        
        # Calculate dynamic y_max based on data
        max_count = max([float(c or 0) for c in counts]) if counts else 0
        
        # Ensure minimum y_max of 40
        dynamic_y_max = max(40, y_max)
        
        # If data exceeds current y_max, increase by 20 until it fits
        while max_count > dynamic_y_max:
            dynamic_y_max += 20
        
        # Create individual bars with different colors
        for i, (x, height) in enumerate(zip(xs, counts)):
            color_idx = i % len(THEME["bar_colors"])
            bar = pg.BarGraphItem(
                x=[x],
                height=[float(height or 0)],
                width=0.6,
                brush=QColor(THEME["bar_colors"][color_idx]),
                pen=THEME["bar_pen"],
            )
            plot.addItem(bar)

        # Set x-axis labels
        ticks = [(i, labels[i]) for i in range(len(labels))]
        plot.getAxis("bottom").setTicks([ticks])

        plot.setXRange(-0.5, len(xs) - 0.5, padding=0.02)
        plot.setYRange(0, dynamic_y_max, padding=0.0)

    except Exception as e:
        print(f"update_bar_chart error: {e}")


# ============================================================
# PIE CHART WIDGET 
# ============================================================

class PieChartWidget(QWidget):
    """Custom widget to draw a pie chart with legend for Pass/Timeout"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = {}
        self.colors = THEME["pie"]
        # Define order: Pass (Green), Timeout (Red)
        self.result_order = ["PASS", "TIMEOUT"]
        self.setMinimumSize(300, 300)
        
        # Background color
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor("black"))
        self.setAutoFillBackground(True)
        self.setPalette(palette)
    
    def set_data(self, data_dict):
        """
        Set data for pie chart
        data_dict: {"PASS": count, "Timeout": count}
        """
        self.data = data_dict
        self.update()  # Trigger repaint
    
    def paintEvent(self, event):
        if not self.data or sum(self.data.values()) == 0:
            # Draw "No Data" message
            painter = QPainter(self)
            painter.setPen(QPen(QColor("white")))
            font = QFont()
            font.setPointSize(20)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, "No Data")
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate pie chart area (left 60% for pie, right 40% for legend)
        width = self.width()
        height = self.height()
        pie_width = int(width * 0.6)
        
        # Pie chart rectangle (square, centered vertically)
        pie_size = min(pie_width - 40, height - 40)
        pie_rect = QRectF(
            20,
            (height - pie_size) / 2,
            pie_size,
            pie_size
        )
        
        # Calculate total
        total = sum(self.data.values())
        color_map = {
            "PASS": QColor(self.colors[0]),      # สีเขียว #28C220
            "TIMEOUT": QColor(self.colors[1])    # สีแดง #E6394A
        }
        
        # Sort data according to result_order for consistent display
        sorted_items = []
        for result in self.result_order:
            if result in self.data and self.data[result] > 0:
                sorted_items.append((result, self.data[result]))
        
        # Draw pie slices
        start_angle = 0
        
        for result, count in sorted_items:  # ✅ ไม่ใช้ enumerate
            # Calculate span angle (in 1/16th of a degree)
            span_angle = int((count / total) * 360 * 16)
            color = color_map.get(result, QColor(self.colors[0]))
            
            # Draw slice
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("black"), 1))
            painter.drawPie(pie_rect, start_angle, span_angle)
            
            start_angle += span_angle
        
        # Draw legend on the right side
        legend_x = pie_width
        legend_y = height // 2 - 40  # Center vertically
        legend_spacing = 50
        
        font = QFont()
        font.setPointSize(12)
        # font.setBold(True)
        painter.setFont(font)
        
        for result, count in sorted_items:  
            color = color_map.get(result, QColor(self.colors[0]))
            
            # Draw color box
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("white"), 1))
            painter.drawRect(legend_x, legend_y - 12, 24, 24)
            
            # Draw text
            painter.setPen(QPen(QColor("white")))
            percentage = (count / total) * 100
            
            text = f"{result}: {count} ({percentage:.1f}%)"
            painter.drawText(legend_x + 30, legend_y + 5, text)
            
            legend_y += legend_spacing


def init_pie_chart(container: QtWidgets.QWidget):
    """Initialize pie chart widget for Pass/Timeout results"""
    layout = container.layout()
    if layout is None:
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
    
    # Clear existing widgets
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
    
    # Create pie chart widget
    pie_widget = PieChartWidget(container)
    pie_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    
    layout.addWidget(pie_widget)
    container._pie_widget = pie_widget


def update_pie_chart(container: QtWidgets.QWidget, data_dict):
    """
    Update pie chart with new data for Pass/Timeout
    data_dict: {"Pass": count, "Timeout": count} or task distribution
    """
    try:
        if not hasattr(container, "_pie_widget"):
            init_pie_chart(container)
        
        container._pie_widget.set_data(data_dict)
        
    except Exception as e:
        print(f"update_pie_chart error: {e}")