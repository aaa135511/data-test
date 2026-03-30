import sys
import os
import sqlite3
import io
import re
import zipfile
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, QLabel,
    QFileDialog, QScrollArea, QFrame, QSplitter, QProgressBar, QMessageBox
)
from PyQt6.QtGui import QPixmap, QImage, QFont, QIcon, QColor
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PIL import Image

# --- 数据库路径 ---
DB_PATH = "products_data.db"


class DatabaseManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # 关键改进：设置 row_factory，允许通过名称访问列，如 row['name']
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT, model TEXT, name TEXT, sku TEXT, 
                description TEXT, price TEXT, size TEXT, weight TEXT,
                inventory TEXT, records TEXT, supplier TEXT,
                image_blob BLOB
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search ON products(name, sku, model)")
        conn.commit()
        conn.close()

    def search_products(self, query):
        conn = self._get_conn()
        cursor = conn.cursor()
        terms = query.strip().split()
        sql = "SELECT brand, model, name, sku, id FROM products WHERE 1=1"
        params = []
        for term in terms:
            sql += " AND (name LIKE ? OR sku LIKE ? OR model LIKE ? OR description LIKE ?)"
            t = f"%{term}%"
            params.extend([t, t, t, t])

        cursor.execute(sql, params)
        res = cursor.fetchall()
        conn.close()
        return res

    def get_product_detail(self, pid):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (pid,))
        res = cursor.fetchone()
        conn.close()
        return res


# --- 后台导入线程 ---
class ImportThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            from openpyxl import load_workbook
            wb = load_workbook(self.file_path, data_only=True)
            ws = wb.active

            images = []
            with zipfile.ZipFile(self.file_path, 'r') as z:
                img_files = [f for f in z.namelist() if
                             f.startswith('xl/media/') and f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                img_files.sort(key=lambda x: [int(t) if t.isdigit() else t.lower() for t in re.split('([0-9]+)', x)])
                for f in img_files:
                    images.append(z.read(f))

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM products")

            rows = list(ws.iter_rows(min_row=2, values_only=True))
            img_ptr = 0

            for i, row in enumerate(rows):
                # 严格对应你的 Excel 表头索引
                brand, model, name, sku, desc = row[0], row[1], row[2], row[3], row[4]
                price = row[6]
                size = row[8]
                weight = row[9]
                inventory = row[10]
                records = row[11]
                supplier = row[12]

                img_blob = None
                if img_ptr < len(images):
                    img_blob = images[img_ptr]
                    img_ptr += 1

                cursor.execute('''
                    INSERT INTO products (brand, model, name, sku, description, price, size, weight, inventory, records, supplier, image_blob)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (brand, model, name, sku, desc, price, size, weight, inventory, records, supplier,
                      sqlite3.Binary(img_blob) if img_blob else None))

                if i % 5 == 0: self.progress.emit(int((i + 1) / len(rows) * 100))

            conn.commit()
            conn.close()
            self.finished.emit(len(rows))
        except Exception as e:
            self.error.emit(str(e))


# --- 主界面 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("产品库管理系统")
        self.resize(1300, 850)
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f7f9; }
            QLineEdit { padding: 10px; border: 1px solid #ccc; border-radius: 5px; font-size: 14px; background: #fff; }
            QPushButton#ImportBtn { padding: 10px 20px; background-color: #2ecc71; color: white; border-radius: 5px; font-weight: bold; }
            QTreeWidget { border: 1px solid #ddd; background: #fff; border-radius: 5px; }
            QScrollArea { border: 1px solid #ddd; border-radius: 5px; background: #fff; }
        """)

        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)

        # 搜索栏
        nav = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 快速搜索：雅马哈 R25 灯...")
        self.search_box.textChanged.connect(self.do_search)
        btn_imp = QPushButton("导入数据")
        btn_imp.setObjectName("ImportBtn")
        btn_imp.clicked.connect(self.start_import)
        nav.addWidget(self.search_box, 8)
        nav.addWidget(btn_imp, 1)
        layout.addLayout(nav)

        self.pbar = QProgressBar()
        self.pbar.hide()
        layout.addWidget(self.pbar)

        # 内容区
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["品牌 > 车型 > 产品"])
        self.tree.itemClicked.connect(self.on_click_item)
        splitter.addWidget(self.tree)

        self.detail_area = QScrollArea()
        self.detail_area.setWidgetResizable(True)
        self.detail_content = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_content)
        self.detail_area.setWidget(self.detail_content)
        splitter.addWidget(self.detail_area)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)
        layout.addWidget(splitter)
        self.do_search()

    def start_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择Excel", "", "Excel (*.xlsx)")
        if path:
            self.pbar.show()
            self.task = ImportThread(path)
            self.task.progress.connect(self.pbar.setValue)
            self.task.finished.connect(self.import_done)
            self.task.start()

    def import_done(self, n):
        self.pbar.hide()
        QMessageBox.information(self, "提示", f"导入成功，共 {n} 条。")
        self.do_search()

    def do_search(self):
        txt = self.search_box.text()
        rows = self.db.search_products(txt)
        self.tree.clear()
        data_tree = {}
        for r in rows:
            b, m, n, s, pid = r['brand'], r['model'], r['name'], r['sku'], r['id']
            b, m = b or "未分类", m or "通用"
            if b not in data_tree: data_tree[b] = {}
            if m not in data_tree[b]: data_tree[b][m] = []
            data_tree[b][m].append((f"{n} ({s})", pid))

        for b in sorted(data_tree.keys()):
            b_node = QTreeWidgetItem(self.tree, [b])
            for m in sorted(data_tree[b].keys()):
                m_node = QTreeWidgetItem(b_node, [m])
                for name, pid in data_tree[b][m]:
                    p_node = QTreeWidgetItem(m_node, [name])
                    p_node.setData(0, Qt.ItemDataRole.UserRole, pid)

    def on_click_item(self, item, col):
        pid = item.data(0, Qt.ItemDataRole.UserRole)
        if pid: self.render_detail(pid)

    def render_detail(self, pid):
        # 清理旧视图
        while self.detail_layout.count():
            child = self.detail_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

        row = self.db.get_product_detail(pid)
        if not row: return

        # 标题
        title = QLabel(f"<h2>{row['name']}</h2>")
        self.detail_layout.addWidget(title)

        # 图片逻辑 (修复点：明确访问 image_blob 列)
        img_label = QLabel()
        img_label.setFixedSize(400, 400)
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_label.setStyleSheet("border:1px solid #ddd; background:#fff;")

        blob = row['image_blob']
        if blob and isinstance(blob, bytes):
            pix = QPixmap()
            if pix.loadFromData(blob):
                img_label.setPixmap(pix.scaled(380, 380, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
            else:
                img_label.setText("图片损坏")
        else:
            img_label.setText("暂无图片")
        self.detail_layout.addWidget(img_label)

        # 数据展示
        info_box = QWidget()
        info_lay = QVBoxLayout(info_box)
        items = [
            ("货号", row['sku']), ("价格", row['price']),
            ("品牌/车型", f"{row['brand']} / {row['model']}"),
            ("库存", row['inventory']), ("供应商", row['supplier']),
            ("描述", row['description']), ("尺寸重量", f"{row['size']} / {row['weight']}")
        ]
        for k, v in items:
            line = QLabel(f"<b>{k}:</b> {v if v else '-'}")
            line.setWordWrap(True)
            info_lay.addWidget(line)

        self.detail_layout.addWidget(info_box)
        self.detail_layout.addStretch()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())