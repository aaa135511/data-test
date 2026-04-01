import sys
import os
import sqlite3
import io
import re
import zipfile
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, QLabel,
    QFileDialog, QScrollArea, QFrame, QSplitter, QProgressBar, QMessageBox,
    QTextEdit, QGridLayout, QCheckBox, QDialog, QHeaderView
)
from PyQt6.QtGui import QPixmap, QImage, QFont, QColor
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PIL import Image

# --- 试用期限设置 ---
EXPIRY_DATE = datetime(2026, 4, 7)
DB_PATH = "products_pro_v2.db"


class DatabaseManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT, model TEXT, name TEXT, oe_no TEXT, sku TEXT, 
                desc_zh TEXT, desc_en TEXT, price TEXT, link TEXT, 
                size TEXT, inventory TEXT, records TEXT, supplier TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                image_blob BLOB,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sku ON products(sku)")
        conn.commit()
        conn.close()

    def execute_query(self, sql, params=()):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        res = cursor.fetchall()
        conn.commit()
        conn.close()
        return res


# --- 多图管理对话框 ---
class ImageGalleryDialog(QDialog):
    def __init__(self, images, parent=None):
        super().__init__(parent)
        self.setWindowTitle("产品图片库管理")
        self.resize(700, 500)
        self.all_blobs = [img['image_blob'] for img in images] if images else []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        btn_add = QPushButton("➕ 批量添加本地图片")
        btn_add.clicked.connect(self.add_images)
        layout.addWidget(btn_add)

        self.scroll = QScrollArea()
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        btn_ok = QPushButton("保存修改并退出")
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok)
        self.refresh_grid()

    def add_images(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择图片", "", "Images (*.png *.jpg *.jpeg)")
        for p in paths:
            with open(p, 'rb') as f: self.all_blobs.append(f.read())
        self.refresh_grid()

    def refresh_grid(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w: w.deleteLater()
        for i, blob in enumerate(self.all_blobs):
            lbl = QLabel()
            pix = QPixmap()
            pix.loadFromData(blob)
            lbl.setPixmap(pix.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio))
            del_btn = QPushButton("移除")
            del_btn.clicked.connect(lambda ch, idx=i: (self.all_blobs.pop(idx), self.refresh_grid()))
            v = QVBoxLayout()
            v.addWidget(lbl)
            v.addWidget(del_btn)
            w = QWidget();
            w.setLayout(v)
            self.grid.addWidget(w, i // 3, i % 3)


# --- 主界面 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.current_product_id = None
        self.current_blobs = []
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("产品检录信息管理系统 Pro (试用版)")
        self.resize(1400, 900)

        self.setStyleSheet("""
            QMainWindow { background-color: #f5f5f5; }
            QLineEdit, QTextEdit { border: 1px solid #ccc; border-radius: 2px; padding: 4px; background: white; }
            QLabel#Title { color: #1890ff; font-weight: bold; }
            QPushButton#SaveBtn { background-color: #1890ff; color: white; border-radius: 4px; font-weight: bold; }
            QPushButton#DelBtn { background-color: #ff4d4f; color: white; border-radius: 4px; }
            QFrame#Line { background-color: #e8e8e8; }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 1. 顶部操作栏
        top_bar = QHBoxLayout()
        self.search_in = QLineEdit()
        self.search_in.setPlaceholderText("🔍 输入关键词搜索...")
        self.search_in.setFixedWidth(400)
        self.search_in.textChanged.connect(self.do_search)

        top_bar.addWidget(self.search_in)
        top_bar.addWidget(QPushButton("清除搜索", clicked=lambda: self.search_in.clear()))
        top_bar.addStretch()

        btn_add = QPushButton("新增产品", clicked=self.add_new)
        self.btn_save = QPushButton("保存修改", clicked=self.save_data)
        self.btn_save.setObjectName("SaveBtn")
        btn_del = QPushButton("删除产品", clicked=self.del_data)
        btn_del.setObjectName("DelBtn")
        btn_imp = QPushButton("批量导入", clicked=self.imp_data)
        btn_exp = QPushButton("导出数据", clicked=self.exp_data)

        for b in [btn_add, self.btn_save, btn_del, btn_imp, btn_exp]:
            b.setFixedSize(90, 32)
            top_bar.addWidget(b)
        main_layout.addLayout(top_bar)

        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(4);
        self.pbar.hide()
        main_layout.addWidget(self.pbar)

        # 2. 内容区 (左树右编辑)
        content_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["产品目录结构"])
        self.tree.itemClicked.connect(self.on_tree_click)
        content_splitter.addWidget(self.tree)

        # 右侧编辑容器
        right_panel = QSplitter(Qt.Orientation.Vertical)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.edit_container = QWidget()
        self.grid = QGridLayout(self.edit_container)
        self.grid.setSpacing(10)
        self.setup_edit_fields()
        self.scroll.setWidget(self.edit_container)

        # 日志区
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("操作日志显示于此...")
        self.log_area.setStyleSheet(
            "background: #fdfdfd; color: #666; font-size: 11px; border: none; border-top: 1px solid #ddd;")

        right_panel.addWidget(self.scroll)
        right_panel.addWidget(self.log_area)
        right_panel.setSizes([700, 150])

        content_splitter.addWidget(right_panel)
        content_splitter.setSizes([300, 1100])
        main_layout.addWidget(content_splitter)

        self.do_search()

    def setup_edit_fields(self):
        """重新排版，严格遵循图 2 的逻辑"""
        # 图片区域 (左上)
        self.img_label = QLabel("🖼️ 预览图")
        self.img_label.setFixedSize(220, 220)
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("border: 1px dashed #bbb; background: #fff;")
        self.grid.addWidget(self.img_label, 0, 0, 4, 2)

        self.btn_gallery = QPushButton("📂 管理/多图添加 (0)")
        self.btn_gallery.clicked.connect(self.open_gallery)
        self.grid.addWidget(self.btn_gallery, 4, 0, 1, 2)

        # 核心信息 (右上)
        self.grid.addWidget(QLabel("🔹 核心信息"), 0, 2, 1, 4)

        self.edit_brand = QLineEdit()
        self.edit_model = QLineEdit()
        self.edit_name = QLineEdit()
        self.edit_price = QLineEdit()
        self.edit_inv = QLineEdit()
        self.edit_sku = QLineEdit()
        self.edit_oe = QLineEdit()
        self.edit_link = QLineEdit()

        # 第一行：品牌 + 车型
        self.grid.addWidget(QLabel("品牌:"), 1, 2)
        self.grid.addWidget(self.edit_brand, 1, 3)
        self.grid.addWidget(QLabel("车型:"), 1, 4)
        self.grid.addWidget(self.edit_model, 1, 5)

        # 第二行：产品名称 (跨列)
        self.grid.addWidget(QLabel("产品名称:"), 2, 2)
        self.grid.addWidget(self.edit_name, 2, 3, 1, 3)

        # 第三行：价格 + 库存
        self.grid.addWidget(QLabel("产品价格:"), 3, 2)
        self.grid.addWidget(self.edit_price, 3, 3)
        self.grid.addWidget(QLabel("库存数量:"), 3, 4)
        self.grid.addWidget(self.edit_inv, 3, 5)

        # 第四行：货号 + OE (下方对齐)
        self.grid.addWidget(QLabel("产品货号:"), 4, 2)
        self.grid.addWidget(self.edit_sku, 4, 3)
        self.grid.addWidget(QLabel("OE号:"), 4, 4)
        self.grid.addWidget(self.edit_oe, 4, 5)

        # 第五行：同款链接
        self.grid.addWidget(QLabel("同款链接:"), 5, 0)
        self.grid.addWidget(self.edit_link, 5, 1, 1, 5)

        # 描述与规格区
        line = QFrame();
        line.setFrameShape(QFrame.Shape.HLine);
        line.setObjectName("Line")
        self.grid.addWidget(line, 6, 0, 1, 6)
        self.grid.addWidget(QLabel("🔹 描述与规格"), 7, 0, 1, 6)

        self.edit_zh = QTextEdit();
        self.edit_zh.setFixedHeight(100)
        self.edit_en = QTextEdit();
        self.edit_en.setFixedHeight(100)
        self.grid.addWidget(QLabel("中文描述:"), 8, 0)
        self.grid.addWidget(self.edit_zh, 8, 1, 1, 2)
        self.grid.addWidget(QLabel("英文描述:"), 8, 3)
        self.grid.addWidget(self.edit_en, 8, 4, 1, 2)

        self.edit_specs = QLineEdit()
        self.edit_sup = QLineEdit()
        self.grid.addWidget(QLabel("尺寸重量:"), 9, 0)
        self.grid.addWidget(self.edit_specs, 9, 1, 1, 2)
        self.grid.addWidget(QLabel("供应商:"), 9, 3)
        self.grid.addWidget(self.edit_sup, 9, 4, 1, 2)

        # 出货记录
        self.grid.addWidget(QLabel("🔹 记录信息"), 10, 0, 1, 6)
        self.edit_rec = QTextEdit();
        self.edit_rec.setFixedHeight(80)
        self.grid.addWidget(QLabel("出货记录:"), 11, 0)
        self.grid.addWidget(self.edit_rec, 11, 1, 1, 5)

    def write_log(self, text):
        self.log_area.append(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")

    def do_search(self):
        txt = self.search_in.text().strip()
        sql = "SELECT id, brand, model, name, sku FROM products WHERE 1=1"
        params = []
        if txt:
            sql += " AND (name LIKE ? OR sku LIKE ? OR oe_no LIKE ? OR brand LIKE ? OR model LIKE ?)"
            p = f"%{txt}%";
            params = [p, p, p, p, p]
        rows = self.db.execute_query(sql, params)
        self.tree.clear()
        d_map = {}
        for r in rows:
            b, m = r['brand'] or "未分类", r['model'] or "通用"
            if b not in d_map: d_map[b] = {}
            if m not in d_map[b]: d_map[b][m] = []
            d_map[b][m].append((f"{r['name'] or '未命名'} ({r['sku'] or '无货号'})", r['id']))
        for b in sorted(d_map.keys()):
            bi = QTreeWidgetItem(self.tree, [b])
            for m in sorted(d_map[b].keys()):
                mi = QTreeWidgetItem(bi, [m])
                for n, pid in d_map[b][m]:
                    pi = QTreeWidgetItem(mi, [n]);
                    pi.setData(0, Qt.ItemDataRole.UserRole, pid)
        if txt: self.tree.expandAll()

    def on_tree_click(self, item, col):
        pid = item.data(0, Qt.ItemDataRole.UserRole)
        if pid: self.load_data(pid)

    def load_data(self, pid):
        res = self.db.execute_query("SELECT * FROM products WHERE id=?", (pid,))
        if not res: return
        p = res[0];
        self.current_product_id = pid
        self.edit_brand.setText(p['brand'] or "");
        self.edit_model.setText(p['model'] or "")
        self.edit_name.setText(p['name'] or "");
        self.edit_oe.setText(p['oe_no'] or "")
        self.edit_sku.setText(p['sku'] or "");
        self.edit_price.setText(p['price'] or "")
        self.edit_zh.setText(p['desc_zh'] or "");
        self.edit_en.setText(p['desc_en'] or "")
        self.edit_specs.setText(p['size'] or "");
        self.edit_sup.setText(p['supplier'] or "")
        self.edit_rec.setText(p['records'] or "");
        self.edit_link.setText(p['link'] or "")
        self.edit_inv.setText(p['inventory'] or "")

        imgs = self.db.execute_query("SELECT image_blob FROM product_images WHERE product_id=?", (pid,))
        self.current_blobs = [r['image_blob'] for r in imgs]
        self.btn_gallery.setText(f"📂 管理/多图添加 ({len(self.current_blobs)})")
        if self.current_blobs:
            pix = QPixmap();
            pix.loadFromData(self.current_blobs[0])
            self.img_label.setPixmap(pix.scaled(210, 210, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            self.img_label.setText("🖼️ 暂无图片")

    def open_gallery(self):
        gallery_data = [{'image_blob': b} for b in self.current_blobs]
        dlg = ImageGalleryDialog(gallery_data, self)
        if dlg.exec():
            self.current_blobs = dlg.all_blobs
            self.btn_gallery.setText(f"📂 管理/多图添加 ({len(self.current_blobs)})")
            if self.current_blobs:
                pix = QPixmap();
                pix.loadFromData(self.current_blobs[0])
                self.img_label.setPixmap(pix.scaled(210, 210, Qt.AspectRatioMode.KeepAspectRatio))
            else:
                self.img_label.setText("🖼️ 暂无图片")

    def save_data(self):
        if not self.edit_name.text().strip(): return QMessageBox.warning(self, "！", "产品名称不能为空")
        data = (self.edit_brand.text(), self.edit_model.text(), self.edit_name.text(), self.edit_oe.text(),
                self.edit_sku.text(), self.edit_zh.toPlainText(), self.edit_en.toPlainText(), self.edit_price.text(),
                self.edit_link.text(), self.edit_specs.text(), self.edit_inv.text(), self.edit_rec.toPlainText(),
                self.edit_sup.text())

        if self.current_product_id:
            self.db.execute_query('''UPDATE products SET brand=?, model=?, name=?, oe_no=?, sku=?, desc_zh=?, desc_en=?, 
                                    price=?, link=?, size=?, inventory=?, records=?, supplier=? WHERE id=?''',
                                  data + (self.current_product_id,))
            pid = self.current_product_id
        else:
            self.db.execute_query('''INSERT INTO products (brand, model, name, oe_no, sku, desc_zh, desc_en, price, link, size, inventory, records, supplier)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', data)
            pid = self.db.execute_query("SELECT last_insert_rowid() as id")[0]['id']

        self.db.execute_query("DELETE FROM product_images WHERE product_id=?", (pid,))
        for b in self.current_blobs:
            self.db.execute_query("INSERT INTO product_images (product_id, image_blob) VALUES (?,?)",
                                  (pid, sqlite3.Binary(b)))

        self.write_log(f"✅ 保存成功: {self.edit_name.text()}")
        self.do_search()

    def add_new(self):
        self.current_product_id = None;
        self.current_blobs = []
        for w in self.edit_container.findChildren((QLineEdit, QTextEdit)): w.clear()
        self.img_label.setText("🖼️ 预览图");
        self.btn_gallery.setText("📂 管理/多图添加 (0)")

    def del_data(self):
        if not self.current_product_id: return
        if QMessageBox.question(self, "?", "确定删除？") == QMessageBox.StandardButton.Yes:
            self.db.execute_query("DELETE FROM products WHERE id=?", (self.current_product_id,))
            self.write_log("🗑️ 已删除记录");
            self.add_new();
            self.do_search()

    def imp_data(self):
        from openpyxl import load_workbook
        p, _ = QFileDialog.getOpenFileName(self, "选择Excel", "", "Excel (*.xlsx)")
        if not p: return
        self.pbar.show();
        self.pbar.setValue(10)
        try:
            wb = load_workbook(p, data_only=True);
            ws = wb.active
            rows = list(ws.iter_rows(min_row=2, values_only=True))
            for r in rows:
                if not r[2]: continue
                self.db.execute_query('''INSERT INTO products (brand, model, name, oe_no, sku, desc_zh, price, link, size, inventory, records, supplier)
                                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                                      (r[0], r[1], r[2], r[3], r[4], r[5], r[7], r[8], r[9], r[11], r[12], r[13]))
            self.write_log(f"🏁 导入完成: {len(rows)}条");
            self.do_search()
        except Exception as e:
            self.write_log(f"❌ 导入失败: {e}")
        finally:
            self.pbar.hide()

    def exp_data(self):
        p, _ = QFileDialog.getSaveFileName(self, "导出", "产品导出.xlsx", "Excel (*.xlsx)")
        if p:
            from openpyxl import Workbook
            wb = Workbook();
            ws = wb.active
            ws.append(["品牌", "车型", "名称", "OE", "货号", "描述", "价格", "链接", "尺寸", "库存", "记录", "供应商"])
            rows = self.db.execute_query(
                "SELECT brand,model,name,oe_no,sku,desc_zh,price,link,size,inventory,records,supplier FROM products")
            for r in rows: ws.append(list(r))
            wb.save(p);
            self.write_log("📤 导出成功")


if __name__ == "__main__":
    if datetime.now() > EXPIRY_DATE:
        app = QApplication(sys.argv)
        QMessageBox.critical(None, "版本过期", f"本试用版已于 {EXPIRY_DATE.strftime('%Y-%m-%d')} 到期。")
        sys.exit(0)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())