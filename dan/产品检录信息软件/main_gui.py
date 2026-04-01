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
from PyQt6.QtGui import QPixmap, QColor, QFont, QCursor, QImage
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from openpyxl import load_workbook
from lxml import etree

# --- 试用期限 ---
EXPIRY_DATE = datetime(2026, 4, 7)
DB_PATH = "products_pro_v3.db"


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
                id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER,
                image_blob BLOB, FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
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


# --- 深度优化：无损高清查看器 ---
class BigImageViewer(QDialog):
    def __init__(self, image_blob, product_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"高清原图 - {product_name}")
        self.resize(1100, 850)
        layout = QVBoxLayout(self)

        # 提示文字
        tip = QLabel("💡 提示：当前显示为原图尺寸。若图片过大，请拖动滚动条查看细节。")
        tip.setStyleSheet("color: #666; font-size: 12px; margin-bottom: 5px;")
        layout.addWidget(tip)

        # 滚动区域
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background-color: #333; border: 1px solid #111;")

        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 加载图片原始数据
        pix = QPixmap()
        pix.loadFromData(image_blob)

        # 核心逻辑：如果图片分辨率大于屏幕，支持滚动查看原图；否则居中显示
        self.img_label.setPixmap(pix)
        self.img_label.adjustSize()  # 关键：根据原图调整标签大小

        self.scroll.setWidget(self.img_label)
        layout.addWidget(self.scroll)

        # 底部操作
        btns = QHBoxLayout()
        fit_btn = QPushButton("适应窗口高度")
        fit_btn.clicked.connect(lambda: self.scale_to_fit(pix))
        orig_btn = QPushButton("查看 1:1 原始大小")
        orig_btn.clicked.connect(lambda: self.show_original(pix))
        btns.addWidget(fit_btn)
        btns.addWidget(orig_btn)
        btns.addStretch()
        layout.addLayout(btns)

    def scale_to_fit(self, pix):
        scaled = pix.scaled(self.scroll.width() - 30, self.scroll.height() - 30,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
        self.img_label.setPixmap(scaled)

    def show_original(self, pix):
        self.img_label.setPixmap(pix)
        self.img_label.adjustSize()


# --- 核心导入线程 (保持 100% 匹配 + 无损提取) ---
class ImportThread(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            self.log.emit("🔍 正在扫描 Excel 内部原图库...")
            # 1. 深度 ZIP 扫描：提取嵌入式原图
            wps_map = self.extract_wps_images(self.file_path)
            self.log.emit(f"📷 提取到无损嵌入资源: {len(wps_map)}个")

            # 2. 备用扫描：提取浮动图片坐标
            wb_images = load_workbook(self.file_path, data_only=True)
            ws_images = wb_images.active
            anchor_map = {}
            if hasattr(ws_images, '_images'):
                for img in ws_images._images:
                    try:
                        row = img.anchor._from.row + 1
                        anchor_map[row] = img._data()  # 这里拿到的也是原始字节流
                    except:
                        continue

            # 3. 开启公式模式读取数据
            wb_data = load_workbook(self.file_path, data_only=False)
            ws_data = wb_data.active
            rows = list(ws_data.iter_rows(min_row=2))

            # 4. 货号查重
            db_mgr = DatabaseManager()
            db_skus = set(r['sku'] for r in db_mgr.execute_query("SELECT sku FROM products"))
            excel_skus = set()

            # 5. 正式录入
            conn = sqlite3.connect(DB_PATH);
            cursor = conn.cursor()
            imported_count = 0

            for i, row_cells in enumerate(rows):
                sku_val = row_cells[4].value
                sku = str(sku_val).strip() if sku_val else None
                if not sku or sku in excel_skus or sku in db_skus:
                    continue
                excel_skus.add(sku)

                # 价格位移修复
                price_cell = row_cells[8].value
                price = str(price_cell) if price_cell is not None else ""
                if "DISPIMG" in price: price = "0"

                cursor.execute('''
                    INSERT INTO products (brand, model, name, oe_no, sku, desc_zh, desc_en, price, link, size, inventory, records, supplier)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (row_cells[0].value, row_cells[1].value, row_cells[2].value, row_cells[3].value, sku,
                      row_cells[5].value, row_cells[6].value, price, row_cells[9].value, row_cells[10].value,
                      row_cells[12].value, row_cells[13].value, row_cells[14].value))

                product_id = cursor.lastrowid

                # --- 多重图片匹配逻辑 ---
                img_blob = None
                row_num = i + 2

                # A: 查找 DISPIMG 公式绑定
                for cell in row_cells:
                    val = str(cell.value) if cell.value else ""
                    if "DISPIMG" in val:
                        match = re.search(r'DISPIMG\("(.+?)"', val)
                        if match and match.group(1) in wps_map:
                            img_blob = wps_map[match.group(1)]
                            break

                # B: 坐标备用匹配
                if not img_blob and row_num in anchor_map:
                    img_blob = anchor_map[row_num]

                if img_blob:
                    cursor.execute("INSERT INTO product_images (product_id, image_blob) VALUES (?, ?)",
                                   (product_id, sqlite3.Binary(img_blob)))

                imported_count += 1
                if i % 10 == 0: self.progress.emit(int((i + 1) / len(rows) * 100))

            conn.commit();
            conn.close()
            self.finished.emit(imported_count)
        except Exception as e:
            self.error.emit(f"❌ 错误: {str(e)}")

    def extract_wps_images(self, path):
        """核心：解析 XML 提取无损图片映射"""
        img_map = {}
        try:
            with zipfile.ZipFile(path, 'r') as z:
                # 解析 rid 和 路径
                rels_path = 'xl/_rels/cellimages.xml.rels'
                if rels_path not in z.namelist(): return {}
                rel_root = etree.fromstring(z.read(rels_path))
                rid_to_path = {r.get('Id'): r.get('Target') for r in rel_root.xpath('//*[local-name()="Relationship"]')}

                # 解析 ID 和 rid
                xml_path = 'xl/cellimages.xml'
                if xml_path not in z.namelist(): return {}
                xml_root = etree.fromstring(z.read(xml_path))

                for entry in xml_root.xpath('//*[local-name()="cellImage"]'):
                    try:
                        name_id = entry.xpath('.//*[local-name()="cNvPr"]/@name')[0]
                        rid = entry.xpath('.//*[local-name()="blip"]/@*[local-name()="embed"]')[0]
                        full_path = f"xl/{rid_to_path[rid]}"
                        if full_path in z.namelist():
                            img_map[name_id] = z.read(full_path)  # 存储最原始的二进制流
                    except:
                        continue
        except:
            pass
        return img_map


# --- 主界面 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.current_product_id = None
        self.current_blobs = []
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("产品库 Pro (试用版)")
        self.resize(1450, 950)
        self.setStyleSheet("""
            QMainWindow { background-color: #f2f2f2; }
            QLineEdit, QTextEdit { border: 1px solid #ccc; border-radius: 2px; padding: 5px; background: white; }
            QPushButton#SaveBtn { background-color: #1890ff; color: white; font-weight: bold; }
            QPushButton#DelBtn { background-color: #ff4d4f; color: white; }
        """)

        central = QWidget();
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 顶部工具
        top = QHBoxLayout()
        self.search_in = QLineEdit();
        self.search_in.setPlaceholderText("🔍 全文搜索：品名、货号、车型、描述...")
        self.search_in.textChanged.connect(self.do_search)
        top.addWidget(self.search_in, 6)

        for t, f, o in [("新增", self.add_new, ""), ("保存修改", self.save_data, "SaveBtn"),
                        ("删除", self.del_data, "DelBtn"), ("批量导入", self.imp_data, ""),
                        ("导出勾选", self.exp_data, "")]:
            b = QPushButton(t);
            b.clicked.connect(f);
            b.setFixedSize(90, 35)
            if o: b.setObjectName(o)
            top.addWidget(b)
        main_layout.addLayout(top)

        self.pbar = QProgressBar();
        self.pbar.setFixedHeight(4);
        self.pbar.hide();
        main_layout.addWidget(self.pbar)

        # 布局
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget();
        self.tree.setHeaderLabels(["产品目录结构"]);
        self.tree.itemClicked.connect(self.on_tree_click)
        self.tree.itemChanged.connect(self.on_tree_changed)
        splitter.addWidget(self.tree)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.scroll = QScrollArea();
        self.scroll.setWidgetResizable(True)
        self.edit_container = QWidget();
        self.grid = QGridLayout(self.edit_container)
        self.setup_edit_fields();
        self.scroll.setWidget(self.edit_container)

        self.log_area = QTextEdit();
        self.log_area.setReadOnly(True);
        self.log_area.setStyleSheet("background:#f9f9f9; font-size:11px;")
        right_splitter.addWidget(self.scroll);
        right_splitter.addWidget(self.log_area)
        right_splitter.setSizes([750, 150]);
        splitter.addWidget(right_splitter)
        splitter.setSizes([350, 1100]);
        main_layout.addWidget(splitter)
        self.do_search()

    def setup_edit_fields(self):
        # 预览图
        self.img_label = QLabel("🖼️ 预览图");
        self.img_label.setFixedSize(240, 240);
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor));
        self.img_label.mousePressEvent = self.show_big_image
        self.img_label.setStyleSheet("border: 1px dashed #aaa; background: #fff;")
        self.grid.addWidget(self.img_label, 0, 0, 4, 2)
        self.btn_gallery = QPushButton("📂 多图管理 (0)");
        self.btn_gallery.clicked.connect(self.open_gallery)
        self.grid.addWidget(self.btn_gallery, 4, 0, 1, 2)

        # 字段排列
        self.edit_brand = QLineEdit();
        self.edit_model = QLineEdit();
        self.edit_name = QLineEdit()
        self.edit_price = QLineEdit();
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

        self.grid.addWidget(QLabel("🔹 描述与规格"), 5, 0, 1, 6)
        self.edit_zh = QTextEdit();
        self.edit_zh.setFixedHeight(120);
        self.edit_en = QTextEdit();
        self.edit_en.setFixedHeight(120)
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
        self.edit_rec = QTextEdit();
        self.edit_rec.setFixedHeight(80)
        self.grid.addWidget(QLabel("🔹 出货记录"), 8, 0, 1, 6);
        self.grid.addWidget(self.edit_rec, 9, 1, 1, 5)

    def write_log(self, text):
        self.log_area.append(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")

    def show_big_image(self, event):
        if self.current_blobs:
            # 传递品名，用于窗口标题
            p_name = self.edit_name.text() or "未命名"
            BigImageViewer(self.current_blobs[0], p_name, self).exec()

    def do_search(self):
        txt = self.search_in.text().strip()
        sql = "SELECT id, brand, model, name, sku FROM products WHERE 1=1"
        params = []
        if txt:
            sql += " AND (name LIKE ? OR sku LIKE ? OR oe_no LIKE ? OR brand LIKE ? OR model LIKE ? OR desc_zh LIKE ? OR desc_en LIKE ?)"
            p = f"%{txt}%";
            params = [p, p, p, p, p, p, p]
        rows = self.db.execute_query(sql, params)
        self.update_tree(rows)

    def update_tree(self, data):
        self.tree.blockSignals(True);
        self.tree.clear()
        d_map = {}
        for r in data:
            b, m = r['brand'] or "未分类", r['model'] or "通用"
            display_name = f"{r['name'] or '未命名'} ({r['sku']})"
            if b not in d_map: d_map[b] = {}
            if m not in d_map[b]: d_map[b][m] = []
            d_map[b][m].append((display_name, r['id']))
        for b in sorted(d_map.keys()):
            bi = QTreeWidgetItem(self.tree, [b]);
            bi.setCheckState(0, Qt.CheckState.Unchecked);
            bi.setFlags(bi.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            for m in sorted(d_map[b].keys()):
                mi = QTreeWidgetItem(bi, [m]);
                mi.setCheckState(0, Qt.CheckState.Unchecked);
                mi.setFlags(mi.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                for n, pid in d_map[b][m]:
                    pi = QTreeWidgetItem(mi, [n]);
                    pi.setCheckState(0, Qt.CheckState.Unchecked);
                    pi.setFlags(pi.flags() | Qt.ItemFlag.ItemIsUserCheckable);
                    pi.setData(0, Qt.ItemDataRole.UserRole, pid)
        self.tree.blockSignals(False);
        if self.search_in.text(): self.tree.expandAll()

    def on_tree_changed(self, item, col):
        self.tree.blockSignals(True);
        state = item.checkState(0)

        def check_all(it, st):
            for i in range(it.childCount()):
                child = it.child(i);
                child.setCheckState(0, st);
                check_all(child, st)

        check_all(item, state);
        self.tree.blockSignals(False)

    def on_tree_click(self, item, col):
        pid = item.data(0, Qt.ItemDataRole.UserRole)
        if pid: self.load_data(pid)

    def load_data(self, pid):
        res = self.db.execute_query("SELECT * FROM products WHERE id=?", (pid,))
        if not res: return
        p = res[0];
        self.current_product_id = pid
        self.edit_brand.setText(p['brand'] or "");
        self.edit_model.setText(p['model'] or "");
        self.edit_name.setText(p['name'] or "")
        self.edit_sku.setText(p['sku'] or "");
        self.edit_price.setText(p['price'] or "");
        self.edit_zh.setText(p['desc_zh'] or "")
        self.edit_en.setText(p['desc_en'] or "");
        self.edit_specs.setText(p['size'] or "");
        self.edit_sup.setText(p['supplier'] or "")
        self.edit_inv.setText(p['inventory'] or "");
        self.edit_rec.setText(p['records'] or "");
        self.edit_oe.setText(p['oe_no'] or "");
        self.edit_link.setText(p['link'] or "")

        imgs = self.db.execute_query("SELECT image_blob FROM product_images WHERE product_id=?", (pid,))
        self.current_blobs = [r['image_blob'] for r in imgs]
        self.btn_gallery.setText(f"📂 多图管理 ({len(self.current_blobs)})")
        if self.current_blobs:
            px = QPixmap();
            px.loadFromData(self.current_blobs[0])
            # 高品质预览渲染
            self.img_label.setPixmap(
                px.scaled(235, 235, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.img_label.setText("🖼️ 暂无图片")

    def save_data(self):
        if not self.edit_name.text().strip(): return QMessageBox.warning(self, "！", "名称必填")
        d = (self.edit_brand.text(), self.edit_model.text(), self.edit_name.text(), self.edit_oe.text(),
             self.edit_sku.text(), self.edit_zh.toPlainText(), self.edit_en.toPlainText(), self.edit_price.text(),
             self.edit_link.text(), self.edit_specs.text(), self.edit_inv.text(), self.edit_rec.toPlainText(),
             self.edit_sup.text())
        if self.current_product_id:
            self.db.execute_query(
                "UPDATE products SET brand=?,model=?,name=?,oe_no=?,sku=?,desc_zh=?,desc_en=?,price=?,link=?,size=?,inventory=?,records=?,supplier=? WHERE id=?",
                d + (self.current_product_id,))
            pid = self.current_product_id
        else:
            self.db.execute_query(
                "INSERT INTO products(brand,model,name,oe_no,sku,desc_zh,desc_en,price,link,size,inventory,records,supplier) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                d)
            pid = self.db.execute_query("SELECT last_insert_rowid() as id")[0]['id']
        self.db.execute_query("DELETE FROM product_images WHERE product_id=?", (pid,))
        for b in self.current_blobs: self.db.execute_query(
            "INSERT INTO product_images(product_id,image_blob) VALUES(?,?)", (pid, sqlite3.Binary(b)))
        self.write_log(f"✅ 已更新：{self.edit_name.text()}内容");
        self.do_search()

    def imp_data(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择Excel", "", "Excel (*.xlsx)")
        if p:
            self.log_area.clear();
            self.pbar.show();
            self.task = ImportThread(p)
            self.task.progress.connect(self.pbar.setValue);
            self.task.log.connect(self.write_log)
            self.task.error.connect(lambda m: (self.pbar.hide(), QMessageBox.critical(self, "失败", m)))
            self.task.finished.connect(
                lambda n: (self.pbar.hide(), self.do_search(), QMessageBox.information(self, "完成", f"录入{n}条。")))
            self.task.start()

    def exp_data(self):
        ids = []

        def get_checked(it):
            pid = it.data(0, Qt.ItemDataRole.UserRole)
            if pid and it.checkState(0) == Qt.CheckState.Checked: ids.append(pid)
            for i in range(it.childCount()): get_checked(it.child(i))

        for i in range(self.tree.topLevelItemCount()): get_checked(self.tree.topLevelItem(i))
        if not ids: return QMessageBox.warning(self, "！", "请勾选。")
        p, _ = QFileDialog.getSaveFileName(self, "导出已选", "导出.xlsx", "Excel (*.xlsx)")
        if p:
            from openpyxl import Workbook
            wb = Workbook();
            ws = wb.active;
            ws.append(["品牌", "车型", "名称", "OE", "货号", "中描述", "英描述", "价格", "链接", "尺寸", "库存", "记录",
                       "供应商"])
            rows = self.db.execute_query(
                f"SELECT brand,model,name,oe_no,sku,desc_zh,desc_en,price,link,size,inventory,records,supplier FROM products WHERE id IN ({','.join(['?'] * len(ids))})",
                tuple(ids))
            for r in rows: ws.append(list(r))
            wb.save(p);
            self.write_log("📤 导出成功")

    def add_new(self):
        self.current_product_id = None;
        self.current_blobs = []
        for w in self.edit_container.findChildren((QLineEdit, QTextEdit)): w.clear()
        self.img_label.setText("🖼️ 预览图");
        self.btn_gallery.setText("📂 多图管理 (0)")

    def del_data(self):
        if self.current_product_id and QMessageBox.question(self, "?",
                                                            "彻底删除记录？") == QMessageBox.StandardButton.Yes:
            self.db.execute_query("DELETE FROM products WHERE id=?", (self.current_product_id,));
            self.add_new();
            self.do_search()

    def open_gallery(self):
        dlg = ImageGalleryDialog([{'image_blob': b} for b in self.current_blobs], self)
        if dlg.exec():
            self.current_blobs = dlg.all_blobs;
            self.btn_gallery.setText(f"📂 多图管理 ({len(self.current_blobs)})")
            if self.current_blobs:
                px = QPixmap();
                px.loadFromData(self.current_blobs[0])
                self.img_label.setPixmap(
                    px.scaled(235, 235, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


class ImageGalleryDialog(QDialog):
    def __init__(self, images, parent=None):
        super().__init__(parent)
        self.setWindowTitle("产品图库");
        self.resize(700, 500)
        self.all_blobs = [img['image_blob'] for img in images] if images else []
        layout = QVBoxLayout(self)
        btn = QPushButton("➕ 添加");
        btn.clicked.connect(self.add);
        layout.addWidget(btn)
        self.scroll = QScrollArea();
        self.container = QWidget();
        self.grid = QGridLayout(self.container)
        self.scroll.setWidgetResizable(True);
        self.scroll.setWidget(self.container);
        layout.addWidget(self.scroll)
        b2 = QPushButton("确认应用");
        b2.clicked.connect(self.accept);
        layout.addWidget(b2)
        self.refresh()

    def add(self):
        ps, _ = QFileDialog.getOpenFileNames(self, "选图", "", "Img (*.png *.jpg *.jpeg)")
        for p in ps:
            with open(p, 'rb') as f: self.all_blobs.append(f.read())
        self.refresh()

    def refresh(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget();
            if w: w.deleteLater()
        for i, b in enumerate(self.all_blobs):
            l = QLabel();
            px = QPixmap();
            px.loadFromData(b);
            l.setPixmap(
                px.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            db = QPushButton("移除");
            db.clicked.connect(lambda ch, idx=i: (self.all_blobs.pop(idx), self.refresh()))
            v = QVBoxLayout();
            v.addWidget(l);
            v.addWidget(db);
            w = QWidget();
            w.setLayout(v);
            self.grid.addWidget(w, i // 3, i % 3)


if __name__ == "__main__":
    if datetime.now() > EXPIRY_DATE:
        app = QApplication(sys.argv);
        QMessageBox.critical(None, "过期", "版本到期");
        sys.exit(0)
    app = QApplication(sys.argv);
    app.setStyle("Fusion");
    window = MainWindow();
    window.show();
    sys.exit(app.exec())