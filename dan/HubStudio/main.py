import sys
import os
import sqlite3
import hashlib
import uuid
import platform
import subprocess
import time
import random
import pandas as pd
import requests
from datetime import datetime

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QFileDialog, QTableWidget,
                             QTableWidgetItem, QTabWidget, QTextEdit, QSpinBox, QMessageBox,
                             QFormLayout, QHeaderView)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager


# ================= 1. 机器码获取 (增强兼容性) =================

def get_machine_code():
    """获取跨平台唯一机器码 - 优先使用系统UUID解决Win10识别问题"""
    try:
        if platform.system() == "Windows":
            # 使用 csproduct uuid 比 baseboard serialnumber 在Win10上更稳定
            cmd = "wmic csproduct get uuid"
            res = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
            code = res.split('\n')[1].strip()
            # 如果获取到的是无效字符串，尝试备用方案
            if not code or "Default" in code or "O.E.M" in code:
                cmd = "wmic baseboard get serialnumber"
                res = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                code = res.split('\n')[1].strip()
            return code.upper()
        else:  # MacOS
            cmd = "ioreg -l | grep IOPlatformSerialNumber"
            res = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
            return res.split('"')[-2].upper()
    except:
        # 最终保底方案：使用网卡物理地址的哈希
        return hashlib.md5(str(uuid.getnode()).encode()).hexdigest()[:20].upper()


# ================= 2. 数据库管理 =================

class DBManager:
    def __init__(self):
        self.conn = sqlite3.connect("system.db", check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                            (username TEXT PRIMARY KEY, password TEXT, hwid TEXT, is_admin INTEGER)''')
        admin_pwd = hashlib.sha256("whatsappadmin_5566".encode()).hexdigest()
        self.cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)",
                            ("admin", admin_pwd, "", 1))
        self.conn.commit()


# ================= 3. 自动化任务线程 =================

class TaskThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.is_running = True

    def stop(self):
        self.is_running = False

    def log(self, msg):
        self.log_signal.emit(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def safe_click(self, driver, element):
        try:
            element.click()
        except:
            driver.execute_script("arguments[0].click();", element)

    def run(self):
        stop_reason = "任务正常结束"
        driver = None
        try:
            self.log(f"🚀 正在启动 HubStudio 环境: {self.config['env_id']}...")
            start_url = f"http://127.0.0.1:{self.config['api_port']}/api/v1/browser/start?containerCode={self.config['env_id']}"

            try:
                res = requests.get(start_url).json()
                if res.get("code") != 0: raise Exception(res.get("msg"))
            except Exception as e:
                self.log(f"❌ 启动失败: {e}")
                return

            data = res.get("data")
            port = data.get("debuggingPort") or data.get("debugAddr").split(':')[-1]
            debug_addr = f"127.0.0.1:{port}"

            options = Options()
            options.add_experimental_option("debuggerAddress", debug_addr)
            service = Service(ChromeDriverManager(driver_version="142.0.7444.168").install())
            driver = webdriver.Chrome(service=service, options=options)
            wait = WebDriverWait(driver, 20)

            self.log("🌐 正在进入 WhatsApp Web...")
            driver.get("https://web.whatsapp.com")
            wait.until(EC.presence_of_element_located((By.XPATH, '//span[@data-icon="new-chat-outline"]')))
            self.log("✅ 登录验证通过")

            df = pd.read_excel(self.config['file_path'])
            df.columns = [str(c).strip().lower().replace(" ", "") for c in df.columns]
            if '是否完成' not in df.columns:
                df['是否完成'] = "否"

            for index, row in df.iterrows():
                if not self.is_running: stop_reason = "用户手动停止"; break

                if str(row.get('是否完成', '否')).strip() == "是":
                    self.log(f"📑 第 {index + 1} 行已完成，跳过。")
                    continue

                remark = str(row.get('备注', '')) if pd.notna(row.get('备注')) else ""
                website = str(row.get('网站', '')) if pd.notna(row.get('网站')) else ""
                p1 = self.clean_phone(row.get('whatsapp1'))
                p2 = self.clean_phone(row.get('whatsapp2'))
                phones = [p for p in [p1, p2] if p]

                self.log(f"📑 处理第 {index + 1} 行: {phones}")
                row_success = False

                for phone in phones:
                    if not self.is_running: break
                    self.log(f"📍 尝试号码: {phone}")
                    try:
                        result = self.process_single_phone(driver, wait, phone, remark, website)
                        if result == "SUCCESS":
                            self.log(f"✨ 成功添加: {phone}")
                            row_success = True
                        elif result == "SKIP":
                            self.log(f"⚠️ 跳过号码: {phone}")

                        delay = random.randint(self.config['d_min'], self.config['d_max'])
                        self.log(f"⏱️ 休息 {delay} 秒...")
                        time.sleep(delay)
                    except Exception as e:
                        self.log(f"❌ 本条号码处理异常: {str(e)[:50]}")
                        if "intercepted" in str(e):
                            self.log("🔄 发现界面拦截，正在刷新页面...")
                            driver.refresh()
                            time.sleep(10)
                            wait.until(
                                EC.presence_of_element_located((By.XPATH, '//span[@data-icon="new-chat-outline"]')))

                df.at[index, '是否完成'] = "是" if row_success else "否"
                df.to_excel(self.config['file_path'], index=False)

            self.log("🏁 任务处理完成")

        except Exception as e:
            stop_reason = f"程序异常中断: {str(e)}"
        finally:
            self.finished_signal.emit(stop_reason)

    def clean_phone(self, val):
        if pd.isna(val): return None
        s = str(val).strip()
        if s.endswith('.0'): s = s[:-2]
        cleaned = "".join(filter(str.isdigit, s))
        return cleaned if cleaned else None

    def process_single_phone(self, driver, wait, phone, name, surname):
        try:
            self.reset_to_main(driver)
            new_chat_icon = wait.until(EC.element_to_be_clickable((By.XPATH, '//span[@data-icon="new-chat-outline"]')))
            self.safe_click(driver, new_chat_icon)

            add_xp = '//span[contains(text(), "添加联系人")]'
            add_btn = wait.until(EC.element_to_be_clickable((By.XPATH, add_xp)))
            self.safe_click(driver, add_btn)

            wait.until(EC.presence_of_all_elements_located((By.XPATH, '//div[@contenteditable="true"]')))
            time.sleep(1)
            fields = driver.find_elements(By.XPATH, '//div[@contenteditable="true"]')
            if len(fields) >= 2:
                fields[0].send_keys(name)
                fields[1].send_keys(surname)
            else:
                raise Exception("无法定位姓名输入框")

            cc_btn_xp = '//div[text()="国家/地区"]/..//div[@role="button"]'
            cc_btn = wait.until(EC.element_to_be_clickable((By.XPATH, cc_btn_xp)))
            self.safe_click(driver, cc_btn)

            time.sleep(0.8)
            search_xp = '//div[@role="textbox" and @contenteditable="true"]'
            search_input = wait.until(EC.presence_of_element_located((By.XPATH, search_xp)))
            search_input.send_keys(self.config['c_code'])
            time.sleep(1.5)

            aus_xp = f'//button[contains(@aria-label, "{self.config["c_name"]}")]'
            aus_item = wait.until(EC.element_to_be_clickable((By.XPATH, aus_xp)))
            self.safe_click(driver, aus_item)

            p_xp = '//input[@aria-label="电话号码"]'
            p_input = wait.until(EC.presence_of_element_located((By.XPATH, p_xp)))
            p_input.send_keys(phone)

            time.sleep(5)

            src = driver.page_source
            skip_kw = ["已在你的联系人中", "已经在通讯录", "没有注册", "not on WhatsApp", "邀请对方"]
            if any(k in src for k in skip_kw):
                return "SKIP"
            else:
                submit_xp = '//div[@role="button" and @aria-label="保存联系人"]'
                try:
                    submit_btn = wait.until(EC.element_to_be_clickable((By.XPATH, submit_xp)))
                    self.safe_click(driver, submit_btn)
                    time.sleep(2)
                    return "SUCCESS"
                except:
                    return "SKIP"
        finally:
            self.reset_to_main(driver)

    def reset_to_main(self, driver):
        try:
            back_xp = '//span[@data-icon="back-refreshed"]'
            for _ in range(3):
                back_btns = driver.find_elements(By.XPATH, back_xp)
                if not back_btns: break
                self.safe_click(driver, back_btns[0])
                time.sleep(1)
        except:
            pass


# ================= 4. GUI 主界面 =================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DBManager()
        self.hwid = get_machine_code()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("WhatsApp 智能助手")
        self.resize(1100, 750)

        font_family = "Arial" if platform.system() == "Darwin" else "Consolas"
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: #f0f2f5; }}
            QPushButton {{ background-color: #075e54; color: white; border-radius: 6px; padding: 10px; font-weight: bold; border: none; }}
            QPushButton:hover {{ background-color: #128c7e; }}
            QPushButton:disabled {{ background-color: #bdc3c7; }}
            QLineEdit {{ border: 1px solid #ced4da; border-radius: 4px; padding: 8px; }}
            QTextEdit {{ background: #262d31; color: #d1d7db; font-family: '{font_family}'; border-radius: 6px; padding: 10px; }}
            QTabWidget::pane {{ border: 1px solid #dfe1e5; background: white; }}
        """)

        self.tabs = QTabWidget();
        self.setCentralWidget(self.tabs)
        self.login_w = QWidget();
        self.setup_login_ui()
        self.task_w = QWidget();
        self.setup_task_ui()
        self.admin_w = QWidget();
        self.setup_admin_ui()
        self.tabs.addTab(self.login_w, "安全登录")

    def setup_login_ui(self):
        layout = QVBoxLayout(self.login_w)
        container = QWidget();
        container.setFixedWidth(350);
        v = QVBoxLayout(container)
        self.u_in = QLineEdit();
        self.u_in.setPlaceholderText("账号")
        self.p_in = QLineEdit();
        self.p_in.setPlaceholderText("密码");
        self.p_in.setEchoMode(QLineEdit.EchoMode.Password)
        btn = QPushButton("开启系统");
        btn.clicked.connect(self.handle_login)
        v.addWidget(QLabel("<h2 style='color:#075e54; text-align:center;'>WhatsApp Pro</h2>"),
                    alignment=Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.u_in);
        v.addWidget(self.p_in);
        v.addWidget(btn)
        v.addWidget(QLabel(f"设备机器码: {self.hwid}"), alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignCenter)

    def handle_login(self):
        u, p = self.u_in.text(), self.p_in.text()
        ph = hashlib.sha256(p.encode()).hexdigest()
        self.db.cursor.execute("SELECT hwid, is_admin FROM users WHERE username=? AND password=?", (u, ph))
        res = self.db.cursor.fetchone()
        if res:
            db_hwid, admin = res
            # --- 权限逻辑修复：严格校验普通账户机器码 ---
            if not admin:
                if not db_hwid or db_hwid.strip() == "":
                    return QMessageBox.critical(self, "鉴权失败", "该账户尚未绑定机器码，请联系管理员授权！")
                if db_hwid.strip().upper() != self.hwid.strip().upper():
                    return QMessageBox.critical(self, "鉴权失败",
                                                f"机器码不匹配！\n授权码: {db_hwid}\n本机码: {self.hwid}")

            self.tabs.addTab(self.task_w, "自动化加人");
            if admin: self.tabs.addTab(self.admin_w, "管理后台")
            self.tabs.setCurrentIndex(1);
            self.tabs.removeTab(0)
        else:
            QMessageBox.warning(self, "登录失败", "账号或密码错误")

    def setup_task_ui(self):
        layout = QHBoxLayout(self.task_w)
        left = QWidget();
        left.setFixedWidth(320);
        form = QFormLayout(left)
        self.c_env = QLineEdit("1514886159");
        self.c_port = QLineEdit("6873")
        self.c_name = QLineEdit("澳大利亚");
        self.c_code = QLineEdit("61")
        self.s_min = QSpinBox();
        self.s_min.setRange(1, 100);
        self.s_min.setValue(10)
        self.s_max = QSpinBox();
        self.s_max.setRange(1, 100);
        self.s_max.setValue(20)
        f_btn = QPushButton("📂 上传联系人 Excel");
        f_btn.clicked.connect(self.select_excel)
        self.f_label = QLabel("未载入表格")
        self.run_btn = QPushButton("▶ 启动批量任务");
        self.run_btn.clicked.connect(self.start_task)
        self.stop_btn = QPushButton("⏹ 强制停止任务");
        self.stop_btn.setEnabled(False);
        self.stop_btn.clicked.connect(self.force_stop)
        export_btn = QPushButton("💾 导出结果 Excel");
        export_btn.clicked.connect(self.export_excel)
        form.addRow("环境 ID:", self.c_env);
        form.addRow("API 端口:", self.c_port)
        form.addRow("国家名称:", self.c_name);
        form.addRow("国家区号:", self.c_code)
        form.addRow("最小延迟:", self.s_min);
        form.addRow("最大延迟:", self.s_max)
        form.addRow(f_btn);
        form.addRow(self.f_label)
        form.addRow(self.run_btn);
        form.addRow(self.stop_btn);
        form.addRow(export_btn)
        self.log_v = QTextEdit();
        self.log_v.setReadOnly(True)
        layout.addWidget(left);
        layout.addWidget(self.log_v)

    def select_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择Excel", "", "*.xlsx")
        if path: self.excel_path = path; self.f_label.setText(os.path.basename(path))

    def start_task(self):
        if not hasattr(self, 'excel_path'): return QMessageBox.warning(self, "提示", "请先上传 Excel")
        config = {'env_id': self.c_env.text(), 'api_port': self.c_port.text(), 'c_name': self.c_name.text(),
                  'c_code': self.c_code.text(), 'd_min': self.s_min.value(), 'd_max': self.s_max.value(),
                  'file_path': self.excel_path}
        self.run_btn.setEnabled(False);
        self.stop_btn.setEnabled(True)
        self.worker = TaskThread(config)
        self.worker.log_signal.connect(lambda m: self.log_v.append(m))
        self.worker.finished_signal.connect(self.on_task_finished)
        self.worker.start()

    def force_stop(self):
        if self.worker:
            self.worker.stop()
            self.log_v.append("<b style='color:red;'>[系统] 正在请求停止...</b>")

    def on_task_finished(self, reason):
        self.run_btn.setEnabled(True);
        self.stop_btn.setEnabled(False)
        QMessageBox.information(self, "任务状态", f"任务已结束\n原因: {reason}")

    def export_excel(self):
        if not hasattr(self, 'excel_path'): return
        path, _ = QFileDialog.getSaveFileName(self, "导出结果", "", "*.xlsx")
        if path:
            try:
                import shutil
                shutil.copy(self.excel_path, path)
                QMessageBox.information(self, "成功", "结果已导出！")
            except Exception as e:
                QMessageBox.critical(self, "失败", f"导出失败: {e}")

    def setup_admin_ui(self):
        layout = QVBoxLayout(self.admin_w)
        admin_pwd_box = QHBoxLayout()
        self.new_adm_p = QLineEdit();
        self.new_adm_p.setPlaceholderText("管理员新密码")
        ap_btn = QPushButton("修改并重启");
        ap_btn.clicked.connect(self.update_admin_pwd)
        admin_pwd_box.addWidget(self.new_adm_p);
        admin_pwd_box.addWidget(ap_btn)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["用户账号", "授权机器码", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        add_box = QHBoxLayout()
        self.nu = QLineEdit();
        self.nu.setPlaceholderText("新账号")
        self.np = QLineEdit();
        self.np.setPlaceholderText("密码")
        self.nh = QLineEdit();
        self.nh.setPlaceholderText("机器码")
        ab = QPushButton("增加授权用户");
        ab.clicked.connect(self.add_user)
        add_box.addWidget(self.nu);
        add_box.addWidget(self.np);
        add_box.addWidget(self.nh);
        add_box.addWidget(ab)
        layout.addWidget(QLabel("<h3>管理员安全设置</h3>"))
        layout.addLayout(admin_pwd_box);
        layout.addSpacing(10)
        layout.addWidget(QLabel("<h3>账户授权列表</h3>"))
        layout.addWidget(self.table);
        layout.addLayout(add_box)
        self.refresh_users()

    def update_admin_pwd(self):
        new_p = self.new_adm_p.text()
        if len(new_p) < 6: return QMessageBox.warning(self, "错误", "密码至少6位")
        ph = hashlib.sha256(new_p.encode()).hexdigest()
        self.db.cursor.execute("UPDATE users SET password=? WHERE username='admin'", (ph,))
        self.db.conn.commit()
        QMessageBox.information(self, "成功", "请重新登录");
        sys.exit(0)

    def add_user(self):
        u, p, h = self.nu.text().strip(), self.np.text().strip(), self.nh.text().strip().upper()
        if u and p:
            ph = hashlib.sha256(p.encode()).hexdigest()
            self.db.cursor.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, 0)", (u, ph, h))
            self.db.conn.commit();
            self.refresh_users()

    def refresh_users(self):
        self.table.setRowCount(0)
        self.db.cursor.execute("SELECT username, hwid FROM users WHERE is_admin=0")
        for u, h in self.db.cursor.fetchall():
            r = self.table.rowCount();
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(u))
            self.table.setItem(r, 1, QTableWidgetItem(h))
            b = QPushButton("删除");
            b.setStyleSheet("background-color: #e74c3c;")
            b.clicked.connect(lambda ch, user=u: self.del_user(user))
            self.table.setCellWidget(r, 2, b)

    def del_user(self, u):
        self.db.cursor.execute("DELETE FROM users WHERE username=?", (u,))
        self.db.conn.commit();
        self.refresh_users()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow();
    window.show()
    sys.exit(app.exec())