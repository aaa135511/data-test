import os
import sys
import time
import threading
import random
import re
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk, simpledialog

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager


# --- 数据模型 ---
class CampaignItem:
    def __init__(self, uid, name, current_budget):
        self.uid = uid
        self.name = name
        self.current_budget = current_budget  # 当前预算
        self.bid_step = 5000  # 每次加价幅度，默认 5000
        self.max_limit = 1000000  # 预算上限，默认 100万
        self.status = "监控中"
        self.monitor = True  # 默认监控


class RakutenBotGUI:
    def __init__(self, root):
        self.root = root
        self.instance_id = random.randint(1000, 9999)
        self.root.title(f"Rakuten RMS 自动竞价系统 [ID: {self.instance_id}]")
        self.root.geometry("1100x850")

        # 默认账号配置
        self.default_r_user = "suntakuraku0068"
        self.default_r_pass = "santaku74603"
        self.default_m_email = "hagoogi_k.k@outlook.com"
        self.default_m_pass = "K8302h0826"

        # 核心变量
        self.campaign_map = {}
        self.driver = None
        self.is_running = False
        self.wait_obj = None
        self.campaign_url = "https://ad.rms.rakuten.co.jp/rpp/campaigns"

        self._create_widgets()

    def _create_widgets(self):
        # === 顶部区域 ===
        frame_top = tk.Frame(self.root)
        frame_top.pack(fill="x", padx=10, pady=5)

        # 1. 账号面板
        group_account = tk.LabelFrame(frame_top, text="账号凭证", padx=5, pady=5)
        group_account.pack(side="left", fill="y", padx=5)

        tk.Label(group_account, text="R-Login:").grid(row=0, column=0, sticky="e")
        self.entry_r_user = tk.Entry(group_account, width=16)
        self.entry_r_user.insert(0, self.default_r_user)
        self.entry_r_user.grid(row=0, column=1)

        tk.Label(group_account, text="Pass:").grid(row=1, column=0, sticky="e")
        self.entry_r_pass = tk.Entry(group_account, width=16)
        self.entry_r_pass.insert(0, self.default_r_pass)
        self.entry_r_pass.grid(row=1, column=1)

        tk.Label(group_account, text="Email:").grid(row=0, column=2, sticky="e")
        self.entry_m_email = tk.Entry(group_account, width=16)
        self.entry_m_email.insert(0, self.default_m_email)
        self.entry_m_email.grid(row=0, column=3)

        tk.Label(group_account, text="E-Pass:").grid(row=1, column=2, sticky="e")
        self.entry_m_pass = tk.Entry(group_account, width=16)
        self.entry_m_pass.insert(0, self.default_m_pass)
        self.entry_m_pass.grid(row=1, column=3)

        # 2. 智能控制台
        group_ctrl = tk.LabelFrame(frame_top, text="竞价控制台", padx=5, pady=5)
        group_ctrl.pack(side="left", fill="both", expand=True, padx=5)

        # 核心按钮
        btn_login = tk.Button(group_ctrl, text="1. 登录并提取有效商品", bg="#e1f5fe", font=("Arial", 10), height=2,
                              command=self.action_login_and_scan)
        btn_login.grid(row=0, column=0, rowspan=2, padx=5, sticky="nsew")

        btn_monitor = tk.Button(group_ctrl, text="2. 开始竞拍监控\n(自动加价)", bg="#c8e6c9",
                                font=("Arial", 10, "bold"), height=2, command=self.action_start_monitor)
        btn_monitor.grid(row=0, column=1, rowspan=2, padx=5, sticky="nsew")

        btn_stop = tk.Button(group_ctrl, text="停止监控", bg="#ffcdd2", fg="red", height=2, command=self.action_stop)
        btn_stop.grid(row=0, column=2, rowspan=2, padx=5, sticky="nsew")

        # === 新增：刷新间隔设置 ===
        frame_settings = tk.Frame(group_ctrl)
        frame_settings.grid(row=2, column=0, columnspan=3, pady=(8, 0), sticky="w")

        tk.Label(frame_settings, text="刷新间隔(秒):", font=("Arial", 9, "bold")).pack(side="left", padx=(5, 2))
        self.refresh_interval_var = tk.IntVar(value=20)  # 默认20秒
        sp_refresh = tk.Spinbox(frame_settings, from_=1, to=300, increment=1, textvariable=self.refresh_interval_var,
                                width=5)
        sp_refresh.pack(side="left", padx=2)
        tk.Label(frame_settings, text="（设置越小刷新越快，建议5-20秒）", fg="gray", font=("Arial", 8)).pack(side="left",
                                                                                                          padx=5)

        group_ctrl.grid_columnconfigure(0, weight=1)
        group_ctrl.grid_columnconfigure(1, weight=1)

        # === 列表区域 ===
        frame_list = tk.Frame(self.root)
        frame_list.pack(fill="both", expand=True, padx=10, pady=5)

        # 工具栏
        frame_tools = tk.Frame(frame_list)
        frame_tools.pack(fill="x", pady=2)
        tk.Button(frame_tools, text="全部勾选", command=lambda: self.toggle_all_monitor(True)).pack(side="left")
        tk.Button(frame_tools, text="全部取消", command=lambda: self.toggle_all_monitor(False)).pack(side="left",
                                                                                                     padx=5)
        tk.Label(frame_tools, text="提示：双击【每次加价】或【上限】列可单独修改金额。双击【监控】列可切换状态。",
                 fg="blue").pack(side="right")

        # 表格 (更新列结构)
        columns = ("uid", "monitor", "current_budget", "bid_step", "max_limit", "status", "name")
        self.tree = ttk.Treeview(frame_list, columns=columns, show="headings")

        self.tree.heading("uid", text="ID")
        self.tree.column("uid", width=80, anchor="center")
        self.tree.heading("monitor", text="监控")
        self.tree.column("monitor", width=50, anchor="center")
        self.tree.heading("current_budget", text="当前月预算")
        self.tree.column("current_budget", width=100, anchor="e")
        self.tree.heading("bid_step", text="每次加价(円) ✎")
        self.tree.column("bid_step", width=100, anchor="center")
        self.tree.heading("max_limit", text="上限(円) ✎")
        self.tree.column("max_limit", width=100, anchor="center")
        self.tree.heading("status", text="实时状态")
        self.tree.column("status", width=100, anchor="center")
        self.tree.heading("name", text="Campaign 名称")
        self.tree.column("name", width=500, anchor="w")

        scrollbar = ttk.Scrollbar(frame_list, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # === 日志区域 ===
        group_log = tk.LabelFrame(self.root, text="运行日志", padx=10, pady=5)
        group_log.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(group_log, height=12, state='disabled')
        self.log_text.pack(fill="both", expand=True)

    # --- GUI 交互逻辑 ---
    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        try:
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        except:
            pass
        print(f"[Bot-{self.instance_id}] {message}")

    def on_tree_double_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region == "heading": return
        item_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)

        if not item_id: return
        vals = self.tree.item(item_id, "values")
        uid = vals[0]
        if uid not in self.campaign_map: return
        c_item = self.campaign_map[uid]

        # 如果点击的是第2列 (监控)
        if col_id == "#2":
            c_item.monitor = not c_item.monitor
            if c_item.monitor and c_item.status == "已达上限":
                c_item.status = "监控中"  # 如果手动恢复监控，重置状态
            self.refresh_tree_item(uid)
            self.log(f"商品 {uid} 监控状态切换为: {'是' if c_item.monitor else '否'}")

        # 如果点击的是第4列 (加价金额)
        elif col_id == "#4":
            new_step = simpledialog.askinteger("修改加价金额",
                                               f"请输入 [{c_item.name[:10]}...] 的每次加价金额：",
                                               initialvalue=c_item.bid_step, minvalue=1, parent=self.root)
            if new_step is not None:
                c_item.bid_step = new_step
                self.refresh_tree_item(uid)
                self.log(f"商品 {uid} 加价金额已修改为: {new_step} 円")

        # 修改预算上限
        elif col_id == "#5":
            new_limit = simpledialog.askinteger("修改预算上限",
                                                f"请输入 [{c_item.name[:10]}...] 的总预算上限：\n(最低不可低于5000)",
                                                initialvalue=c_item.max_limit, minvalue=5000, parent=self.root)
            if new_limit is not None:
                c_item.max_limit = new_limit
                self.refresh_tree_item(uid)
                self.log(f"商品 {uid} 预算上限修改为: {new_limit} 円")

    def toggle_all_monitor(self, enable):
        for uid, item in self.campaign_map.items():
            item.monitor = enable
            if enable and item.status == "已达上限":
                item.status = "监控中"
            self.refresh_tree_item(uid)

    def refresh_tree_item(self, uid):
        if uid not in self.campaign_map: return
        c = self.campaign_map[uid]
        target_item = None
        for item in self.tree.get_children():
            if str(self.tree.item(item, "values")[0]) == str(uid):
                target_item = item
                break

        monitor_str = "☑" if c.monitor else "☐"

        # 状态颜色逻辑
        if not c.monitor:
            tags = ("gray",)
        elif c.status == "已达上限":
            tags = ("red",)
        else:
            tags = ("normal",)

        if target_item:
            self.tree.item(target_item,
                           values=(uid, monitor_str, c.current_budget, c.bid_step, c.max_limit, c.status, c.name),
                           tags=tags)

    def action_stop(self):
        self.is_running = False
        self.log("🛑 用户触发停止指令...")

    # ==========================
    # 核心业务流程
    # ==========================

    def action_login_and_scan(self):
        if self.is_running:
            messagebox.showwarning("提示", "当前有任务正在运行")
            return
        self.is_running = True
        t = threading.Thread(target=self.thread_login_scan)
        t.daemon = True
        t.start()

    def action_start_monitor(self):
        if not self.driver:
            messagebox.showerror("错误", "浏览器未启动，请先执行步骤1")
            return
        if not self.campaign_map:
            messagebox.showerror("错误", "列表为空，没有可监控的商品")
            return

        refresh_time = self.refresh_interval_var.get()
        self.log(f"🚀 启动竞价自动监控 ({refresh_time}秒刷新)...")
        self.is_running = True
        t = threading.Thread(target=self.thread_bidding_loop)
        t.daemon = True
        t.start()

    # --- 线程实现 ---

    def thread_login_scan(self):
        try:
            self.log(">>>[Phase 1] 启动登录与提取...")
            service = Service(ChromeDriverManager().install())
            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_argument("--disable-blink-features=AutomationControlled")

            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait_obj = WebDriverWait(self.driver, 30)

            # 1. 登录
            if not self._login_logic():
                self.is_running = False
                return

            # 2. 导航至 Campaign
            if not self._navigate_logic():
                self.is_running = False
                return

            # 3. 扫描提取
            self._scan_campaigns()
            self.is_running = False
            self.log("✅ 提取完成！请配置参数并点击 [开始竞拍监控]")

        except Exception as e:
            self.log(f"❌ 初始化失败: {e}")
            self.is_running = False

    def thread_bidding_loop(self):
        """核心竞拍监控循环"""
        self.log(">>> [Phase 2] 自动竞价引擎启动 <<<")

        loop_count = 0
        while self.is_running:
            loop_count += 1
            try:
                # 获取最新的刷新间隔设置
                refresh_sec = self.refresh_interval_var.get()
                if refresh_sec < 1: refresh_sec = 1  # 兜底防止异常输入

                # 0. 刷新页面
                self.log(f"--- 第 {loop_count} 轮扫描 ---")
                self.driver.refresh()

                # 确认页面加载完成
                try:
                    self.wait_obj.until(EC.presence_of_element_located((By.ID, "budget")))
                    WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "tr.table-row")))
                except TimeoutException:
                    self.log("⚠️ 页面加载超时，跳过本轮")
                    time.sleep(2)
                    continue

                # 1. 寻找是否出现铃铛警报 (精准探测)
                bell_found = False
                try:
                    bells = self.driver.find_elements(By.CSS_SELECTOR, "th#budget .notification-bell")
                    if len(bells) > 0:
                        bell_found = True
                except:
                    pass

                # 2. 判断并加价
                action_taken = False

                if bell_found:
                    self.log("🔔 检测到真实的预算警报！准备评估加价...")

                    for uid, item in self.campaign_map.items():
                        if not item.monitor: continue

                        try:
                            # 搜索整行的文本以匹配 UID
                            row = self.driver.find_element(By.XPATH,
                                                           f"//tr[contains(@class, 'table-row') and contains(., '{uid}')]")
                            budget_input = row.find_element(By.XPATH, ".//td[6]//input[@type='text']")

                            current_val_str = budget_input.get_attribute("value")
                            current_val = int(re.sub(r'[^\d]', '', current_val_str)) if current_val_str else 0

                            # === 安全保护判断 ===
                            if current_val >= item.max_limit:
                                if item.status != "已达上限":
                                    self.log(
                                        f"🛑 拦截: [{item.name[:10]}] 当前预算({current_val}) 已达设定的上限({item.max_limit})，系统取消监控。")
                                    item.status = "已达上限"
                                    item.monitor = False
                                    self.refresh_tree_item(uid)
                                continue

                                # 计算新预算
                            new_budget = current_val + item.bid_step

                            # 溢出截断保护
                            if new_budget > item.max_limit:
                                self.log(f"⚠️ 提示: [{item.name[:10]}] 预计金额超限，强制截断为 {item.max_limit}")
                                new_budget = item.max_limit

                            self.log(f"💰 执行加价: [{item.name[:10]}] {current_val} -> {new_budget}")

                            # 核心交互：清空并输入回车
                            budget_input.click()  # 先聚焦
                            budget_input.send_keys(Keys.CONTROL + "a")
                            budget_input.send_keys(Keys.COMMAND + "a")
                            budget_input.send_keys(Keys.BACKSPACE)
                            budget_input.send_keys(str(new_budget))
                            budget_input.send_keys(Keys.RETURN)

                            item.current_budget = f"{new_budget:,} 円"
                            item.status = "加价成功"
                            self.refresh_tree_item(uid)
                            action_taken = True

                            time.sleep(1)  # 给前端留出保存接口的时间

                        except NoSuchElementException:
                            self.log(f"⚠️ 页面未找到商品ID: {uid}，可能已被移除或分页")
                        except Exception as e:
                            self.log(f"❌ 修改 {uid} 时报错: {e}")

                else:
                    self.log("🟢 状态正常，无铃铛警报")
                    for item in self.campaign_map.values():
                        if item.monitor and item.status == "加价成功":
                            item.status = "监控中"
                            self.refresh_tree_item(item.uid)

                # 3. 自定义等待时间
                if not action_taken:
                    time.sleep(refresh_sec)
                else:
                    # 如果执行了操作，稍微少等一点时间，但最少等1秒
                    time.sleep(max(1, refresh_sec - 1))

            except Exception as e:
                self.log(f"⚠️ 监控异常: {e}")
                time.sleep(self.refresh_interval_var.get())

        self.log("🛑 竞价监控已退出。")

    # --- 辅助逻辑 ---

    def _scan_campaigns(self):
        self.log("正在解析竞拍列表，仅提取[有効]的条目...")
        self.tree.delete(*self.tree.get_children())
        self.campaign_map.clear()

        self.tree.tag_configure("gray", foreground="#999999")
        self.tree.tag_configure("red", foreground="red")
        self.tree.tag_configure("normal", foreground="black")

        try:
            self.wait_obj.until(EC.presence_of_element_located((By.ID, "budget")))
            WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "tr.table-row")))
            time.sleep(1)

            rows = self.driver.find_elements(By.CSS_SELECTOR, "tr.table-row")
            count = 0

            for row in rows:
                try:
                    status_switch = row.find_element(By.XPATH, "./td[5]//input[@role='switch']")
                    is_active = status_switch.get_attribute("aria-checked") == "true"

                    if not is_active:
                        continue

                    uid = row.find_element(By.XPATH, "./td[2]//span[1]").text.strip()
                    name = row.find_element(By.XPATH, "./td[3]//input").get_attribute("value")
                    budget = row.find_element(By.XPATH, "./td[6]//input").get_attribute("value")

                    if uid and uid not in self.campaign_map:
                        c = CampaignItem(uid, name, budget)
                        self.campaign_map[uid] = c
                        self.tree.insert("", "end", values=(uid, "☑", budget, c.bid_step, c.max_limit, c.status, name),
                                         tags=("normal",))
                        count += 1
                except Exception:
                    pass

            self.log(f"扫描完成，共提取 {count} 个有効商品。")
        except Exception as e:
            self.log(f"扫描出错: {e}")

    def _login_logic(self):
        try:
            self.driver.get("https://glogin.rms.rakuten.co.jp/")
            self.wait_obj.until(EC.element_to_be_clickable((By.ID, "rlogin-username-ja"))).send_keys(
                self.entry_r_user.get())
            self.driver.find_element(By.ID, "rlogin-password-ja").send_keys(self.entry_r_pass.get())
            self.driver.find_element(By.NAME, "submit").click()

            self.wait_obj.until(EC.visibility_of_element_located((By.ID, "user_id"))).send_keys(
                self.entry_m_email.get())
            self.driver.find_element(By.ID, "cta001").click()

            self.wait_obj.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password']"))).send_keys(
                self.entry_m_pass.get())
            time.sleep(1)

            for sel in [(By.ID, "cta011"), (By.CLASS_NAME, "h4k5-e2e-button__submit"),
                        (By.XPATH, "//div[@role='button'][.//div[contains(text(),'Next')]]")]:
                try:
                    self.driver.find_element(*sel).click(); break
                except:
                    continue

            start = time.time()
            self.log("处理登录拦截...")
            while time.time() - start < 60:
                current_url = self.driver.current_url
                try:
                    if "mainmenu" in current_url:
                        if len(self.driver.find_elements(By.XPATH, "//a[contains(., '広告・アフィリ')]")) > 0:
                            return True
                except:
                    pass

                try:
                    rms_next_btns = self.driver.find_elements(By.XPATH,
                                                              "//*[contains(text(), 'RMSメインメニューへ進む')]")
                    if rms_next_btns and rms_next_btns[0].is_displayed():
                        checkboxes = self.driver.find_elements(By.XPATH, "//input[@type='checkbox']")
                        for cb in checkboxes:
                            if not cb.is_selected(): self.driver.execute_script("arguments[0].click();", cb)
                        self.driver.execute_script("arguments[0].click();", rms_next_btns[0])
                        time.sleep(3)
                        continue
                except:
                    pass

                try:
                    links = self.driver.find_elements(By.XPATH,
                                                      "//a[contains(text(), 'RMS') or contains(text(), 'ＲＭＳ')]")
                    for l in links:
                        if l.is_displayed() and "mainmenu" not in l.text: l.click(); time.sleep(2); break
                except:
                    pass

                try:
                    self.driver.find_element(By.XPATH, "//button[contains(text(), '次へ')]").click(); time.sleep(
                        2); continue
                except:
                    pass
                try:
                    self.driver.find_element(By.CSS_SELECTOR, "button.btn-red").click(); time.sleep(2); continue
                except:
                    pass
                time.sleep(1)
            return False
        except:
            return False

    def _navigate_logic(self):
        try:
            try:
                self.wait_obj.until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(., '広告・アフィリ')]"))).click(); time.sleep(1)
            except:
                pass
            try:
                self.wait_obj.until(EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(., 'プロモーション') and contains(., 'メニュー')]"))).click()
            except:
                pass
            if len(self.driver.window_handles) > 1: self.driver.switch_to.window(self.driver.window_handles[-1])

            self.log("跳转至竞拍 Campaign 页...")
            self.driver.get(self.campaign_url)
            time.sleep(2)
            return True
        except:
            return False


if __name__ == "__main__":
    root = tk.Tk()
    app = RakutenBotGUI(root)
    root.mainloop()