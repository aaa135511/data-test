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
    QTextEdit, QGridLayout, QCheckBox, QDialog
)
from PyQt6.QtGui import QPixmap, QColor, QFont
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PIL import Image  # 用于清洗图片，解决Windows兼容性

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


# --- 导入线程 (带全量校验逻辑) ---
class ImportThread(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal(int)
    error = pyqtSignal(str)  # 新增错误信号

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            from openpyxl import load_workbook
            wb = load_workbook(self.file_path, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(min_row=2, values_only=True))

            # 1. 第一步：预检查 (查重)
            self.log.emit("🔍 正在启动全量数据安全检查...")
            excel_skus = []
            db_mgr = DatabaseManager()
            existing_skus_rows = db_mgr.execute_query("SELECT sku FROM products")
            db_skus = [str(r['sku']).strip() for r in existing_skus_rows if r['sku']]

            for i, row in enumerate(rows):
                sku = str(row[4]).strip() if row[4] else None
                if not sku:
                    continue

                # 检查 Excel 内部是否重复
                if sku in excel_skus:
                    self.error.emit(f"❌ 导入失败！Excel 第 {i + 2} 行货号 [{sku}] 在文件中重复出现。")
                    return
                # 检查是否与数据库已有货号重复
                if sku in db_skus:
                    self.error.emit(f"❌ 导入失败！货号 [{sku}] 已存在于系统中，请先修改或删除旧数据。")
                    return

                excel_skus.append(sku)

            # 2. 第二步：提取并清洗图片 (解决 Windows 兼容性)
            self.log.emit("🖼️ 正在处理并转换图片格式以适配 Windows...")
            images_cleaned = []
            with zipfile.ZipFile(self.file_path, 'r') as z:
                img_files = [f for f in z.namelist() if
                             f.startswith('xl/media/') and f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                img_files.sort(key=lambda x: [int(t) if t.isdigit() else t.lower() for t in re.split('([0-9]+)', x)])

                for f in img_files:
                    raw_data = z.read(f)
                    try:
                        # 使用 PIL 重新处理图片流，确保 Windows 兼容
                        img = Image.open(io.BytesIO(raw_data))
                        output = io.BytesIO()
                        img.save(output, format="PNG")  # 统一转为 PNG
                        images_cleaned.append(output.getvalue())
                    except:
                        images_cleaned.append(raw_data)  # 降级处理

            # 3. 第三步：正式写入 (事务处理)
            self.log.emit("📝 检查通过，正在写入数据库...")
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            img_ptr = 0
            success_count = 0

            for i, row in enumerate(rows):
                if len(row) < 13: continue
                # 0品牌 1车型 2产品名 3OE 4货号 5描述 7价格 8链接 9尺寸 11库存 12记录 13供应商
                cursor.execute('''
                    INSERT INTO products (brand, model, name, oe_no, sku, desc_zh, price, link, size, inventory, records, supplier)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                row[0], row[1], row[2], row[3], row[4], row[5], row[7], row[8], row[9], row[11], row[12], row[13]))

                new_id = cursor.lastrowid
                if img_ptr < len(images_cleaned):
                    cursor.execute("INSERT INTO product_images (product_id, image_blob) VALUES (?, ?)",
                                   (new_id, sqlite3.Binary(images_cleaned[img_ptr])))
                    img_ptr += 1

                success_count += 1
                self.progress.emit(int((i + 1) / len(rows) * 100))

            conn.commit()
            conn.close()
            self.finished.emit(success_count)

        except Exception as e:
            self.error.emit(f"❌ 系统错误: {str(e)}")


# --- 主界面 (布局回归与功能增强) ---
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
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 顶部工具栏
        top_bar = QHBoxLayout()
        self.search_in = QLineEdit()
        self.search_in.setPlaceholderText("🔍 输入关键词搜索（品牌、车型、货号、OE号）...")
        self.search_in.textChanged.connect(self.do_search)
        top_bar.addWidget(self.search_in, 5)

        for t, f, o in [("新增", self.add_new, ""), ("保存修改", self.save_data, "SaveBtn"),
                        ("删除", self.del_data, "DelBtn"), ("批量导入", self.imp_data, ""),
                        ("导出数据", self.exp_data, "")]:
            b = QPushButton(t);
            b.clicked.connect(f);
            b.setFixedSize(85, 32)
            if o: b.setObjectName(o)
            top_bar.addWidget(b)
        main_layout.addLayout(top_bar)

        self.pbar = QProgressBar();
        self.pbar.setFixedHeight(4);
        self.pbar.hide();
        main_layout.addWidget(self.pbar)

        # 主体分割
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget();
        self.tree.setHeaderLabels(["产品层级结构"]);
        self.tree.itemClicked.connect(self.on_tree_click)
        splitter.addWidget(self.tree)

        # 右侧编辑
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.scroll = QScrollArea();
        self.scroll.setWidgetResizable(True)
        self.edit_container = QWidget()
        self.grid = QGridLayout(self.edit_container)
        self.setup_edit_fields()
        self.scroll.setWidget(self.edit_container)

        log_v = QVBoxLayout()
        log_v.addWidget(QLabel("📝 操作日志 / 报错提示："))
        self.log_area = QTextEdit();
        self.log_area.setReadOnly(True);
        self.log_area.setStyleSheet("background:#f9f9f9; font-size:11px;")
        log_v.addWidget(self.log_area)
        log_w = QWidget();
        log_w.setLayout(log_v)

        right_splitter.addWidget(self.scroll);
        right_splitter.addWidget(log_w)
        right_splitter.setSizes([700, 200])
        splitter.addWidget(right_splitter)
        splitter.setSizes([300, 1100]);
        main_layout.addWidget(splitter)
        self.do_search()

    def setup_edit_fields(self):
        # 图片区 (左上)
        self.img_label = QLabel("🖼️ 预览图")
        self.img_label.setFixedSize(220, 220);
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("border: 1px dashed #bbb; background: #fff;")
        self.grid.addWidget(self.img_label, 0, 0, 4, 2)
        self.btn_gallery = QPushButton("📂 图片库管理 (0)");
        self.btn_gallery.clicked.connect(self.open_gallery)
        self.grid.addWidget(self.btn_gallery, 4, 0, 1, 2)

        # 核心信息 (右上)
        self.edit_brand = QLineEdit();
        self.edit_model = QLineEdit()
        self.edit_name = QLineEdit();
        self.edit_price = QLineEdit()
        self.edit_inv = QLineEdit();
        self.edit_sku = QLineEdit()
        self.edit_oe = QLineEdit();
        self.edit_link = QLineEdit()

        self.grid.addWidget(QLabel("品牌:"), 0, 2);
        self.grid.addWidget(self.edit_brand, 0, 3)
        self.grid.addWidget(QLabel("车型:"), 0, 4);
        self.grid.addWidget(self.edit_model, 0, 5)
        self.grid.addWidget(QLabel("产品名称:"), 1, 2);
        self.grid.addWidget(self.edit_name, 1, 3, 1, 3)
        self.grid.addWidget(QLabel("产品价格:"), 2, 2);
        self.grid.addWidget(self.edit_price, 2, 3)
        self.grid.addWidget(QLabel("库存数量:"), 2, 4);
        self.grid.addWidget(self.edit_inv, 2, 5)
        self.grid.addWidget(QLabel("产品货号:"), 3, 2);
        self.grid.addWidget(self.edit_sku, 3, 3)
        self.grid.addWidget(QLabel("OE号:"), 3, 4);
        self.grid.addWidget(self.edit_oe, 3, 5)
        self.grid.addWidget(QLabel("同款链接:"), 4, 2);
        self.grid.addWidget(self.edit_link, 4, 3, 1, 3)

        # 描述与规格
        self.grid.addWidget(QLabel("🔹 描述与规格"), 5, 0, 1, 6)
        self.edit_zh = QTextEdit();
        self.edit_zh.setFixedHeight(100)
        self.edit_en = QTextEdit();
        self.edit_en.setFixedHeight(100)
        self.grid.addWidget(QLabel("中文描述:"), 6, 0);
        self.grid.addWidget(self.edit_zh, 6, 1, 1, 2)
        self.grid.addWidget(QLabel("英文描述:"), 6, 3);
        self.grid.addWidget(self.edit_en, 6, 4, 1, 2)
        self.edit_specs = QLineEdit();
        self.edit_sup = QLineEdit()
        self.grid.addWidget(QLabel("尺寸重量:"), 7, 0);
        self.grid.addWidget(self.edit_specs, 7, 1, 1, 2)
        self.grid.addWidget(QLabel("供应商:"), 7, 3);
        self.grid.addWidget(self.edit_sup, 7, 4, 1, 2)

        # 记录
        self.grid.addWidget(QLabel("🔹 出货记录"), 8, 0, 1, 6)
        self.edit_rec = QTextEdit();
        self.edit_rec.setFixedHeight(80)
        self.grid.addWidget(self.edit_rec, 9, 1, 1, 5)

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
            d_map[b][m].append((f"{r['name']} ({r['sku']})", r['id']))
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
        self.btn_gallery.setText(f"📂 图片库管理 ({len(self.current_blobs)})")
        if self.current_blobs:
            pix = QPixmap();
            pix.loadFromData(self.current_blobs[0])
            self.img_label.setPixmap(pix.scaled(210, 210, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            self.img_label.setText("🖼️ 暂无图片")

    def open_gallery(self):
        gallery_data = [{'image_blob': b} for b in self.current_blobs]
        from __main__ import ImageGalleryDialog
        dlg = ImageGalleryDialog(gallery_data, self)
        if dlg.exec():
            self.current_blobs = dlg.all_blobs
            self.btn_gallery.setText(f"📂 图片库管理 ({len(self.current_blobs)})")
            if self.current_blobs:
                pix = QPixmap();
                pix.loadFromData(self.current_blobs[0])
                self.img_label.setPixmap(pix.scaled(210, 210, Qt.AspectRatioMode.KeepAspectRatio))
            else:
                self.img_label.setText("🖼️ 暂无图片")

    def save_data(self):
        if not self.edit_name.text().strip(): return QMessageBox.warning(self, "！", "名称必填")
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
        self.write_log(f"✅ 保存成功: {self.edit_name.text()}");
        self.do_search()

    def add_new(self):
        self.current_product_id = None;
        self.current_blobs = []
        for w in self.edit_container.findChildren((QLineEdit, QTextEdit)): w.clear()
        self.img_label.setText("🖼️ 预览图");
        self.btn_gallery.setText("📂 图片库管理 (0)")

    def del_data(self):
        if not self.current_product_id: return
        if QMessageBox.question(self, "?", "确定删除记录？") == QMessageBox.StandardButton.Yes:
            self.db.execute_query("DELETE FROM products WHERE id=?", (self.current_product_id,))
            self.write_log("🗑️ 已删除");
            self.add_new();
            self.do_search()

    def imp_data(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择Excel", "", "Excel (*.xlsx)")
        if not p: return
        self.log_area.clear()
        self.pbar.show();
        self.task = ImportThread(p)
        self.task.progress.connect(self.pbar.setValue)
        self.task.log.connect(self.write_log)
        self.task.error.connect(self.on_import_error)
        self.task.finished.connect(self.on_import_success)
        self.task.start()

    def on_import_error(self, msg):
        self.pbar.hide()
        QMessageBox.critical(self, "导入失败", msg)
        self.write_log(msg)

    def on_import_success(self, n):
        self.pbar.hide()
        QMessageBox.information(self, "导入成功", f"安全检查通过，成功录入 {n} 条新数据。")
        self.do_search()

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
            self.write_log("📤 导出完成")


# --- 图片库画廊窗体 ---
class ImageGalleryDialog(QDialog):
    def __init__(self, images, parent=None):
        super().__init__(parent)
        self.setWindowTitle("产品图片画廊")
        self.resize(700, 500)
        self.all_blobs = [img['image_blob'] for img in images] if images else []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        btn_add = QPushButton("➕ 添加本地图片");
        btn_add.clicked.connect(self.add_images)
        layout.addWidget(btn_add)
        self.scroll = QScrollArea();
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.scroll.setWidgetResizable(True);
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)
        btn_ok = QPushButton("应用并保存");
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
            lbl = QLabel();
            pix = QPixmap()
            pix.loadFromData(blob)
            lbl.setPixmap(pix.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio))
            del_btn = QPushButton("移除");
            del_btn.clicked.connect(lambda ch, idx=i: (self.all_blobs.pop(idx), self.refresh_grid()))
            v = QVBoxLayout();
            v.addWidget(lbl);
            v.addWidget(del_btn)
            w = QWidget();
            w.setLayout(v);
            self.grid.addWidget(w, i // 3, i % 3)


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