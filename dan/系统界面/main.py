import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QGridLayout,
    QVBoxLayout, QHBoxLayout, QGroupBox, QSpacerItem, QSizePolicy
)
from PyQt6.QtGui import QPalette, QBrush, QLinearGradient, QColor
from PyQt6.QtCore import Qt, QTimer, QDateTime


# --- KEY CHANGE: A completely new, robust custom QLineEdit class ---
class PlaceholderLineEdit(QLineEdit):
    def __init__(self, placeholder_text="", parent=None):
        super().__init__(parent)
        self.placeholder_text = placeholder_text

        # Define colors for the two states
        self.placeholder_color = QColor('#AAAAAA')  # Light gray for placeholder
        self.default_color = QColor('white')  # Normal input text color

        self.is_placeholder_active = False
        self.show_placeholder()

    def show_placeholder(self):
        """Sets the widget to its placeholder state: read-only, no cursor, gray text."""
        self.is_placeholder_active = True
        self.setReadOnly(True)  # This is the key to hiding the cursor
        self.setText(self.placeholder_text)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Text, self.placeholder_color)
        self.setPalette(palette)

    def hide_placeholder(self):
        """Sets the widget to its normal input state: editable, cursor visible, white text."""
        self.is_placeholder_active = False
        self.setReadOnly(False)
        self.setText("")
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Text, self.default_color)
        self.setPalette(palette)
        self.setFocus()  # Ensure it gets focus and the cursor appears

    def mousePressEvent(self, event):
        """When the user clicks on the widget, switch to normal input mode."""
        if self.is_placeholder_active:
            self.hide_placeholder()
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        """When the widget loses focus, check if it's empty and show placeholder if needed."""
        if not self.text():
            self.show_placeholder()
        super().focusOutEvent(event)

    def text(self):
        """Overrides the default text() method to return empty if it's a placeholder."""
        if self.is_placeholder_active:
            return ""
        return super().text()


class IndustrialUI(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """初始化主窗口UI"""
        self.setWindowTitle("累计量监控界面")
        self.setGeometry(100, 100, 840, 532)

        palette = QPalette()
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor(100, 150, 220))
        gradient.setColorAt(1.0, QColor(130, 180, 250))
        palette.setBrush(QPalette.ColorRole.Window, QBrush(gradient))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        main_layout.addLayout(self.create_top_bar())
        main_layout.addLayout(self.create_main_panels())
        main_layout.addLayout(self.create_bottom_bar())

        self.setLayout(main_layout)
        self.start_clock()

    def create_top_bar(self):
        """创建顶部信息栏"""
        top_bar_layout = QHBoxLayout()
        left_info = QLabel("CREC796 Ver 2.1.4 17437   中铁工程装备集团")
        left_info.setStyleSheet("color: white; font-size: 14px;")
        plc_status = QLabel(" PLC连接正常 ")
        plc_status.setStyleSheet("background-color: yellow; color: black; font-size: 14px;")

        # --- KEY CHANGE: Using the new, robust PlaceholderLineEdit class. ---
        self.project_input = PlaceholderLineEdit(placeholder_text="西松区间左线")
        self.project_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.project_input.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.3); 
            border: 1px solid #ADD8E6;
            font-size: 14px; 
            font-weight: bold;
            padding: 4px; 
            min-width: 150px; 
            border-radius: 4px;
        """)

        self.time_label = QLabel()
        self.time_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")

        top_bar_layout.addWidget(left_info)
        top_bar_layout.addWidget(plc_status)
        top_bar_layout.addStretch(1)
        top_bar_layout.addWidget(self.project_input)
        top_bar_layout.addStretch(1)
        top_bar_layout.addWidget(self.time_label)
        return top_bar_layout

    def create_main_panels(self):
        """创建主要的三个内容面板"""
        panels_layout = QHBoxLayout()
        panels_layout.setSpacing(15)

        panels_layout.addWidget(self.create_left_panel(), 3)

        mid_column_layout = QVBoxLayout()
        mid_column_layout.setSpacing(15)
        mid_column_layout.addWidget(self.create_middle_panel())

        grouting_and_button_layout = QHBoxLayout()
        grouting_and_button_layout.setSpacing(15)

        grouting_and_button_layout.addWidget(self.create_right_panel())

        clear_button_v_layout = QVBoxLayout()
        clear_button = QPushButton("总累计量\n清零")
        clear_button.setStyleSheet("""
            QPushButton { background-color: #E0E0E0; color: black; font-size: 14px; font-weight: bold;
                        border: 1px solid #708090; border-radius: 5px; padding: 8px; min-height: 50px; min-width: 70px;}
            QPushButton:hover { background-color: #F0F0F0; }
        """)
        clear_button_v_layout.addStretch()
        clear_button_v_layout.addWidget(clear_button)
        clear_button_v_layout.addStretch()

        grouting_and_button_layout.addLayout(clear_button_v_layout)

        grouting_and_button_layout.setStretch(0, 1)
        grouting_and_button_layout.setStretch(1, 0)

        mid_column_layout.addLayout(grouting_and_button_layout)

        panels_layout.addLayout(mid_column_layout, 6)

        return panels_layout

    def create_left_panel(self):
        """创建左侧“累计量”面板"""
        group_box = QGroupBox("累计量")
        layout = QGridLayout()
        layout.setVerticalSpacing(12)
        layout.setHorizontalSpacing(4)

        ring_header = QLabel("环累计量")
        ring_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        total_header = QLabel("总累计量")
        total_header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(ring_header, 0, 1, 1, 2)
        layout.addWidget(total_header, 0, 3, 1, 2)

        data = [
            ("泡沫原液", "54.8", "L", "32291", "L"), ("泡沫工业水", "3633.8", "L", "1300443", "L"),
            ("泡沫混合液", "2858.4", "L", "350935", "L"), ("膨润土", "0.0", "m³", "559", "m³"),
            ("盾壳膨润土", "0.0", "m³", "0", "m³"), ("HDP密封油脂", "0.0", "L", "6", "L"),
            ("EP2润滑油脂", "0.0", "L", "0", "L"), ("盾尾密封", "0.0", "L", "0", "L"),
            ("刀盘喷水", "0.0", "m³", "0", "m³")
        ]

        for i, (name, val1, unit1, val2, unit2) in enumerate(data, start=1):
            name_label = QLabel(f"{name}")
            layout.addWidget(name_label, i, 0)
            layout.addWidget(self.create_data_input(val1, width=80), i, 1)
            layout.addWidget(QLabel(unit1), i, 2)
            layout.addWidget(self.create_data_input(val2, width=80), i, 3)
            layout.addWidget(QLabel(unit2), i, 4)

        layout.setColumnStretch(0, 1)
        group_box.setLayout(layout)
        group_box.setStyleSheet(self.get_groupbox_style())
        return group_box

    def create_middle_panel(self):
        """创建中间“砂浆称重”面板"""
        group_box = QGroupBox("砂浆称重")
        main_v_layout = QVBoxLayout(group_box)
        main_v_layout.setSpacing(10)

        def create_right_aligned_label(text):
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return label

        top_grid = QGridLayout()
        top_grid.setHorizontalSpacing(8)
        top_grid.setVerticalSpacing(8)

        top_grid.addWidget(create_right_aligned_label("净重"), 0, 0)
        top_grid.addWidget(self.create_data_input("0.00", width=75), 0, 1)
        top_grid.addWidget(QLabel("T"), 0, 2)
        top_grid.addWidget(create_right_aligned_label("毛重"), 0, 4)
        top_grid.addWidget(self.create_data_input("0.00", width=75), 0, 5)
        top_grid.addWidget(QLabel("T"), 0, 6)
        top_grid.addWidget(create_right_aligned_label("环耗给重量"), 1, 0)
        top_grid.addWidget(self.create_data_input("0.00", width=75), 1, 1)
        top_grid.addWidget(QLabel("T"), 1, 2)
        top_grid.addWidget(create_right_aligned_label("环结束重量"), 1, 4)
        top_grid.addWidget(self.create_data_input("0.00", width=75), 1, 5)
        top_grid.addWidget(QLabel("T"), 1, 6)
        top_grid.addWidget(create_right_aligned_label("环耗给量"), 2, 0)
        top_grid.addWidget(self.create_data_input("0.00", width=75), 2, 1)
        top_grid.addWidget(QLabel("T"), 2, 2)
        top_grid.addWidget(create_right_aligned_label("密度"), 2, 4)
        top_grid.addWidget(self.create_data_input("1.80", width=75), 2, 5)
        top_grid.addWidget(QLabel("T/m³"), 2, 6)
        top_grid.setColumnStretch(3, 1)

        bottom_h_layout = QHBoxLayout()
        cumulative_grid = QGridLayout()
        cumulative_grid.setHorizontalSpacing(8)
        cumulative_grid.setVerticalSpacing(6)
        cumulative_grid.addWidget(QLabel("环累计量", alignment=Qt.AlignmentFlag.AlignCenter), 0, 0, 1, 2)
        cumulative_grid.addWidget(QLabel("总累计量", alignment=Qt.AlignmentFlag.AlignCenter), 0, 2, 1, 2)
        cumulative_grid.addWidget(self.create_data_input("0.00", width=75), 1, 0)
        cumulative_grid.addWidget(QLabel("T"), 1, 1)
        cumulative_grid.addWidget(self.create_data_input("29", width=75), 1, 2)
        cumulative_grid.addWidget(QLabel("T"), 1, 3)
        cumulative_grid.addWidget(self.create_data_input("0.00", width=75), 2, 0)
        cumulative_grid.addWidget(QLabel("m³"), 2, 1)
        cumulative_grid.addWidget(self.create_data_input("16", width=75), 2, 2)
        cumulative_grid.addWidget(QLabel("m³"), 2, 3)

        tare_button = QPushButton("砂浆罐\n去皮")
        tare_button.setStyleSheet("""
            QPushButton { background-color: #E0E0E0; color: black; font-size: 14px; border-radius: 5px; padding: 8px; min-height: 45px;}
            QPushButton:hover { background-color: #F0F0F0; }
        """)

        bottom_h_layout.addStretch(1)
        bottom_h_layout.addLayout(cumulative_grid)
        bottom_h_layout.addStretch(1)
        bottom_h_layout.addWidget(tare_button)

        main_v_layout.addLayout(top_grid)
        main_v_layout.addLayout(bottom_h_layout)

        group_box.setStyleSheet(self.get_groupbox_style())
        return group_box

    def create_right_panel(self):
        """创建右侧“注浆累计量”面板"""
        group_box = QGroupBox("注浆累计量")
        main_layout = QVBoxLayout(group_box)
        main_layout.setSpacing(10)

        def create_right_aligned_label(text):
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return label

        top_layout = QGridLayout()
        top_layout.setVerticalSpacing(8)
        top_layout.addWidget(QLabel("环累计量", alignment=Qt.AlignmentFlag.AlignCenter), 0, 1, 1, 2)
        top_layout.addWidget(QLabel("总累计量", alignment=Qt.AlignmentFlag.AlignCenter), 0, 3, 1, 2)
        top_layout.addWidget(create_right_aligned_label("注浆A液总和"), 1, 0)
        top_layout.addWidget(self.create_data_input("4512.0", width=75), 1, 1)
        top_layout.addWidget(QLabel("L"), 1, 2)
        top_layout.addWidget(self.create_data_input("457752", width=75), 1, 3)
        top_layout.addWidget(QLabel("L"), 1, 4)
        main_layout.addLayout(top_layout)

        bottom_group = QGroupBox("注浆A液环累计量")
        bottom_group.setStyleSheet(
            "QGroupBox { border: none; margin-top: 1ex; } QGroupBox::title { color: white; subcontrol-origin: margin; left: 10px; }")
        bottom_layout = QGridLayout()
        bottom_layout.setVerticalSpacing(8)
        bottom_layout.addWidget(create_right_aligned_label("左上"), 0, 0)
        bottom_layout.addWidget(self.create_data_input("804.0", width=75), 0, 1)
        bottom_layout.addWidget(QLabel("L"), 0, 2)
        bottom_layout.addWidget(create_right_aligned_label("右上"), 0, 4)
        bottom_layout.addWidget(self.create_data_input("1452.0", width=75), 0, 5)
        bottom_layout.addWidget(QLabel("L"), 0, 6)
        bottom_layout.addWidget(create_right_aligned_label("左下"), 1, 0)
        bottom_layout.addWidget(self.create_data_input("804.0", width=75), 1, 1)
        bottom_layout.addWidget(QLabel("L"), 1, 2)
        bottom_layout.addWidget(create_right_aligned_label("右下"), 1, 4)
        bottom_layout.addWidget(self.create_data_input("1452.0", width=75), 1, 5)
        bottom_layout.addWidget(QLabel("L"), 1, 6)
        bottom_layout.setColumnStretch(3, 1)
        bottom_group.setLayout(bottom_layout)

        main_layout.addWidget(bottom_group)

        group_box.setStyleSheet(self.get_groupbox_style())
        return group_box

    def create_bottom_bar(self):
        """创建底部导航栏"""
        bottom_bar_layout = QHBoxLayout()
        bottom_bar_layout.setSpacing(0)

        buttons = ["主监控页", "泡沫系统", "注浆系统", "变频驱动", "辅助系统", "盾尾密封",
                   "渣土检测", "启动条件", "参数设置", "累计量", "报警系统", "历史记录", "返回"]
        for i, btn_text in enumerate(buttons):
            button = QPushButton(btn_text)
            is_last = (i == len(buttons) - 1)
            button.setStyleSheet(self.get_button_style(active=(btn_text == "累计量"), last=is_last))
            bottom_bar_layout.addWidget(button)
        return bottom_bar_layout

    def create_data_input(self, value, width=None):
        """创建并样式化一个数据输入框"""
        line_edit = QLineEdit(value)
        line_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        line_edit.setStyleSheet("""
            QLineEdit { background-color: black; color: #39FF14; border: 1px solid #4A4A4A;
                        font-size: 18px; font-weight: bold; padding: 5px; }
        """)
        if width:
            line_edit.setFixedWidth(width)
        return line_edit

    def get_groupbox_style(self):
        """返回面板的统一样式"""
        return """
            QGroupBox {
                background-color: rgba(85, 135, 225, 0.7);
                border: 1px solid #ADD8E6; border-radius: 8px; margin-top: 1ex;
                font-size: 18px; font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin; subcontrol-position: top center;
                padding: 0 8px; color: yellow;
            }
            QLabel { color: white; font-size: 16px; background-color: transparent; }
        """

    def get_button_style(self, active=False, last=False):
        """返回底部按钮的样式"""
        if active:
            return """
                QPushButton { background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #87CEEB, stop:1 #4682B4);
                            color: white; border: 1px solid #FFFFFF; padding: 8px 10px;
                            font-size: 12px; font-weight: bold; border-radius: 4px; }
            """
        else:
            style = """
                QPushButton {
                    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4682B4, stop:1 #2E5880);
                    color: #E0E0E0;
                    border: 1px solid #708090;
                    padding: 8px 10px;
                    font-size: 12px;
                    border-radius: 0px;
            """
            if not last:
                style += "border-right: 1px solid #2E5880;\n"

            style += """
                }
                QPushButton:hover {
                    background-color: #5A98D2;
                }
            """
            return style

    def start_clock(self):
        """启动一个定时器，每秒更新时间标签"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()

    def update_time(self):
        """获取当前时间并更新标签"""
        current_time = QDateTime.currentDateTime()
        formatted_time = current_time.toString("yyyy/MM/dd hh:mm:ss")
        self.time_label.setText(formatted_time)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = IndustrialUI()
    window.show()
    sys.exit(app.exec())