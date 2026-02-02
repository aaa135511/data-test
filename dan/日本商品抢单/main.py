import os
import sys
import time
import threading
import random
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager


# --- 数据模型 ---
class ProductItem:
    def __init__(self, uid, name):
        self.uid = uid
        self.name = name
        self.status = "等待"
        self.monitor = True  # 默认监控
        self.added = False  # 是否已加购


class RakutenBotGUI:
    def __init__(self, root):
        self.root = root
        self.instance_id = random.randint(1000, 9999)
        self.root.title(f"Rakuten RMS 抢单系统 v6.1 (确认页修复版) [ID: {self.instance_id}]")
        self.root.geometry("1050x900")

        self.default_r_user = "suntakuraku0068"
        self.default_r_pass = "santaku74603"
        self.default_m_email = "hagoogi_k.k@outlook.com"
        self.default_m_pass = "K8302h0826"

        self.product_map = {}
        self.driver = None
        self.is_running = False
        self.wait_obj = None
        self.favorites_url = "https://ad.rms.rakuten.co.jp/ec/favorite"
        self.current_stage = "IDLE"

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
        group_ctrl = tk.LabelFrame(frame_top, text="极速控制台", padx=5, pady=5)
        group_ctrl.pack(side="left", fill="both", expand=True, padx=5)

        self.mode_var = tk.StringVar(value="TEST")
        tk.Radiobutton(group_ctrl, text="测试模式 (停在购物车)", variable=self.mode_var, value="TEST", fg="blue").grid(
            row=0, column=0, sticky="w")
        tk.Radiobutton(group_ctrl, text="正式抢单 (全自动提交)", variable=self.mode_var, value="REAL", fg="red").grid(
            row=1, column=0, sticky="w")

        frame_speed = tk.Frame(group_ctrl)
        frame_speed.grid(row=2, column=0, sticky="w", pady=2)
        tk.Label(frame_speed, text="防漏单间隔(秒):").pack(side="left")
        self.click_interval_var = tk.DoubleVar(value=2.0)
        sp_interval = tk.Spinbox(frame_speed, from_=0.1, to=10.0, increment=0.1, textvariable=self.click_interval_var,
                                 width=5)
        sp_interval.pack(side="left", padx=2)

        btn_login = tk.Button(group_ctrl, text="1. 登录并初始化", bg="#e1f5fe", font=("Arial", 10), height=2,
                              command=self.action_login_and_scan)
        btn_login.grid(row=0, column=1, rowspan=3, padx=5, sticky="nsew")

        btn_monitor = tk.Button(group_ctrl, text="2. 开始/继续 抢单\n(自动复购)", bg="#c8e6c9",
                                font=("Arial", 10, "bold"), height=2, command=self.action_monitor_control)
        btn_monitor.grid(row=0, column=2, rowspan=3, padx=5, sticky="nsew")

        btn_stop = tk.Button(group_ctrl, text="紧急停止", bg="#ffcdd2", fg="red", height=2, command=self.action_stop)
        btn_stop.grid(row=0, column=3, rowspan=3, padx=5, sticky="nsew")

        group_ctrl.grid_columnconfigure(1, weight=1)
        group_ctrl.grid_columnconfigure(2, weight=1)

        # === 列表区域 ===
        frame_list = tk.Frame(self.root)
        frame_list.pack(fill="both", expand=True, padx=10, pady=5)

        frame_tools = tk.Frame(frame_list)
        frame_tools.pack(fill="x", pady=2)
        tk.Button(frame_tools, text="全部勾选", command=lambda: self.toggle_all_monitor(True)).pack(side="left")
        tk.Button(frame_tools, text="全部取消", command=lambda: self.toggle_all_monitor(False)).pack(side="left",
                                                                                                     padx=5)
        tk.Label(frame_tools, text="提示：建议间隔设为 1.0~2.0 秒。").pack(side="right")

        columns = ("uid", "monitor", "status", "name")
        self.tree = ttk.Treeview(frame_list, columns=columns, show="headings")
        self.tree.heading("uid", text="ID")
        self.tree.column("uid", width=80, anchor="center")
        self.tree.heading("monitor", text="监控")
        self.tree.column("monitor", width=50, anchor="center")
        self.tree.heading("status", text="实时状态")
        self.tree.column("status", width=120, anchor="center")
        self.tree.heading("name", text="商品名称")
        self.tree.column("name", width=600, anchor="w")

        scrollbar = ttk.Scrollbar(frame_list, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self.on_tree_click)

        # === 日志区域 ===
        group_log = tk.LabelFrame(self.root, text="运行日志", padx=10, pady=5)
        group_log.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(group_log, height=10, state='disabled')
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

    def on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region == "heading": return
        item_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if item_id and col_id == "#2":
            vals = self.tree.item(item_id, "values")
            uid = vals[0]
            if uid in self.product_map:
                p = self.product_map[uid]
                p.monitor = not p.monitor
                self.refresh_tree_item(uid)

    def toggle_all_monitor(self, enable):
        for uid, item in self.product_map.items():
            item.monitor = enable
            self.refresh_tree_item(uid)

    def refresh_tree_item(self, uid):
        if uid not in self.product_map: return
        p = self.product_map[uid]
        target_item = None
        for item in self.tree.get_children():
            if str(self.tree.item(item, "values")[0]) == str(uid):
                target_item = item
                break

        monitor_str = "☑" if p.monitor else "☐"
        tags = ("gray",) if not p.monitor else (
            ("green",) if p.added else ("red",) if "已开售" in p.status else ("normal",))
        if target_item:
            self.tree.item(target_item, values=(uid, monitor_str, p.status, p.name), tags=tags)

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

    def action_monitor_control(self):
        if not self.driver:
            messagebox.showerror("错误", "浏览器未启动，请先执行步骤1")
            return

        if self.current_stage == "CHECKOUT":
            self.log("🔄 复购指令：立即重置状态，极速返回监控...")
            self.is_running = True
            t = threading.Thread(target=self.thread_reset_and_monitor)
            t.daemon = True
            t.start()
        elif self.product_map:
            self.log(f"🚀 启动监控抢单 (点击间隔: {self.click_interval_var.get()}s)...")
            self.is_running = True
            t = threading.Thread(target=self.thread_monitor_loop)
            t.daemon = True
            t.start()
        else:
            messagebox.showerror("错误", "列表为空，请先执行步骤1")

    # --- 线程实现 ---

    def thread_login_scan(self):
        try:
            self.log(">>> [Phase 1] 启动登录与初始化...")
            service = Service(ChromeDriverManager().install())
            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_argument("--disable-blink-features=AutomationControlled")

            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait_obj = WebDriverWait(self.driver, 30)

            if not self._login_logic():
                self.is_running = False
                return

            if not self._navigate_logic():
                self.is_running = False
                return

            self._scan_logic()
            self.current_stage = "LOGGED_IN"
            self.log("✅ 初始化完成！请点击 [开始/继续 抢单]")

        except Exception as e:
            self.log(f"❌ 初始化失败: {e}")
            self.is_running = False

    def thread_reset_and_monitor(self):
        try:
            self.log("🔙 利用 Token 闪回收藏夹...")
            self.driver.get(self.favorites_url)

            for uid, item in self.product_map.items():
                if item.monitor:
                    item.added = False
                    item.status = "等待下一轮"
                    self.refresh_tree_item(uid)

            self.thread_monitor_loop()

        except Exception as e:
            self.log(f"❌ 复购重置失败: {e}")
            self.is_running = False

    def thread_monitor_loop(self):
        """核心监控循环 (性能优化版)"""
        self.current_stage = "MONITORING"
        click_interval = self.click_interval_var.get()

        loop_count = 0
        while self.is_running:
            loop_count += 1
            try:
                target_items = [p for p in self.product_map.values() if p.monitor]
                not_added = [p for p in target_items if not p.added]

                if not target_items:
                    self.log("⚠️ 无监控目标，脚本暂停。")
                    self.is_running = False
                    return

                if not not_added:
                    self.log("🎉 目标全部达成！瞬切结算...")
                    self._checkout_logic()
                    return

                if loop_count > 1:
                    try:
                        self.driver.refresh()
                        self.wait_obj.until(
                            EC.presence_of_element_located((By.ID, "prmm-ec-fav-search-result-container")))
                    except (TimeoutException, WebDriverException):
                        self.log("🔥 页面超时/崩溃！触发光速重连...")
                        self._emergency_recover()
                        continue

                try:
                    icons = self.driver.find_elements(By.CSS_SELECTOR, ".prmm-ec-fav-expand-details.fa-plus-square")
                    if icons:
                        for icon in icons: self.driver.execute_script("arguments[0].click();", icon)
                        time.sleep(0.1)
                except:
                    pass

                any_action = False
                for item in not_added:
                    btn_id = f"cart-btn-{item.uid}"
                    try:
                        btn = self.driver.find_element(By.ID, btn_id)
                        if btn.get_attribute("disabled"):
                            if item.status != "等待开售":
                                item.status = "等待开售"
                                self.refresh_tree_item(item.uid)
                        else:
                            self.log(f"🚀 {item.uid} 开售！JS Click...")
                            self.driver.execute_script("arguments[0].click();", btn)
                            self.log(f"⏳ 防漏单等待 ({click_interval}s)...")
                            time.sleep(click_interval)
                            item.added = True
                            item.status = "已加入购物车"
                            self.refresh_tree_item(item.uid)
                            any_action = True
                    except NoSuchElementException:
                        pass
                    except Exception:
                        pass

                if not any_action:
                    self.log(f"#{loop_count} 扫描未果，刷新...")
                else:
                    self.log("✅ 本轮操作成功！")

            except Exception as e:
                self.log(f"⚠️ 监控异常: {e}")
                time.sleep(1)
                self._emergency_recover()

        self.log("🛑 监控线程退出。")

    # --- 辅助逻辑 ---

    def _emergency_recover(self):
        try:
            self.log("🚑 URL 直连恢复...")
            self.driver.get(self.favorites_url)
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.ID, "prmm-ec-fav-search-result-container")))
                self.log("✅ 恢复成功！")
            except:
                if "glogin" in self.driver.current_url:
                    self.log("❌ Session 失效，需重新登录。")
                    self.is_running = False
        except Exception as e:
            self.log(f"❌ 恢复失败: {e}")

    def _scan_logic(self):
        self.log("正在解析商品列表...")
        self.tree.delete(*self.tree.get_children())
        self.product_map.clear()

        self.tree.tag_configure("gray", foreground="#999999")
        self.tree.tag_configure("green", foreground="green", font=("bold",))
        self.tree.tag_configure("red", foreground="red", font=("bold",))
        self.tree.tag_configure("normal", foreground="black")

        try:
            self.wait_obj.until(EC.presence_of_element_located((By.ID, "prmm-ec-fav-search-result-container")))
            time.sleep(1.5)
            tbodies = self.driver.find_elements(By.XPATH, "//tbody[contains(@ng-repeat, 'result in resultSet')]")

            count = 0
            for tbody in tbodies:
                try:
                    try:
                        btn = tbody.find_element(By.XPATH, ".//button[contains(@id, 'cart-btn-')]")
                        uid = btn.get_attribute("id").replace("cart-btn-", "")
                    except:
                        continue

                    try:
                        name_el = tbody.find_element(By.XPATH, ".//li[contains(@id, 'menu-name')]//span")
                        name = name_el.text.strip()
                    except:
                        name = "未知"

                    if uid not in self.product_map:
                        p = ProductItem(uid, name)
                        self.product_map[uid] = p
                        monitor_str = "☑" if p.monitor else "☐"
                        self.tree.insert("", "end", values=(uid, monitor_str, "等待", name), tags=("normal",))
                        count += 1
                except:
                    pass
            self.log(f"扫描完成，共 {count} 个商品。")
        except Exception as e:
            self.log(f"扫描出错: {e}")

    def _checkout_logic(self):
        """结算流程 (v6.1: 修复复选框检测超时问题)"""
        try:
            self.log(">>> 进入结算流程 <<<")

            # 1. 进购物车
            self.wait_obj.until(EC.element_to_be_clickable((By.ID, "prmm-shopping-cart-top"))).click()

            # 2. 查找第一步结算按钮
            checkout_btn = self.wait_obj.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., '購入する')]")))
            self.driver.execute_script("arguments[0].scrollIntoView();", checkout_btn)

            if self.mode_var.get() == "TEST":
                self.log("🟡 [测试模式] 停在购物车页面。任务完成。")
            else:
                self.log("🔴 [正式模式] 提交订单...")
                checkout_btn.click()

                # 3. 处理最终确认页 (修复核心)
                try:
                    self.log("等待确认页加载...")
                    time.sleep(1.5)  # 必须等待页面跳转，否则找不到元素

                    # === A. 精确勾选协议 (必须步骤) ===
                    self.log("正在签署协议...")
                    term_ids = ["agreeAdvertisementTerms", "agreeCancellationTerms"]

                    # 轮询尝试勾选 (最多试3秒)
                    for _ in range(3):
                        checked_count = 0
                        for term_id in term_ids:
                            try:
                                cb = self.driver.find_element(By.ID, term_id)
                                if not cb.is_selected():
                                    self.driver.execute_script("arguments[0].click();", cb)
                                checked_count += 1
                            except:
                                pass

                        # 兜底：勾选所有 checkbox
                        if checked_count < 2:
                            try:
                                all_cbs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                                for cb in all_cbs:
                                    if not cb.is_selected(): self.driver.execute_script("arguments[0].click();", cb)
                            except:
                                pass

                        time.sleep(0.5)

                    # === B. 寻找并点击最终按钮 ===
                    self.log("寻找最终提交按钮...")
                    # 使用更精确的 XPath，包含你提供的文字 "購入を確定する"
                    final_btn = self.wait_obj.until(EC.element_to_be_clickable((By.XPATH,
                                                                                "//button[contains(., '購入を確定する') or contains(., '申し込む')]"
                                                                                )))

                    self.driver.execute_script("arguments[0].scrollIntoView();", final_btn)

                    # 确保按钮不再 disabled (Angular 响应时间)
                    if final_btn.get_attribute("disabled"):
                        self.log("等待按钮激活...")
                        time.sleep(0.5)

                    self.log("✅✅✅ 执行最终点击！")
                    self.driver.execute_script("arguments[0].click();", final_btn)

                    # 4. 快速检测完成
                    try:
                        WebDriverWait(self.driver, 5).until(
                            lambda d: "完了" in d.page_source or "complete" in d.current_url)
                        self.log("🎉🎉🎉 抢单完成！")
                    except:
                        self.log("⚠️ 提交动作已执行，请人工确认结果。")

                except Exception as ex:
                    self.log(f"⚠️ 确认步异常: {ex}")

            self.current_stage = "CHECKOUT"
            self.is_running = False

        except Exception as e:
            self.log(f"结算出错: {e}")
            self.is_running = False

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
            try:
                self.wait_obj.until(EC.element_to_be_clickable((By.XPATH,
                                                                "//a[contains(@href, '/ec/top') and contains(text(), '楽天市場広告')]"))).click(); time.sleep(
                    2)
            except:
                self.driver.get("https://ad.rms.rakuten.co.jp/ec/top")
            try:
                self.wait_obj.until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/ec/favorite')]"))).click()
            except:
                self.driver.get(self.favorites_url)
            return True
        except:
            return False


if __name__ == "__main__":
    root = tk.Tk()
    app = RakutenBotGUI(root)
    root.mainloop()