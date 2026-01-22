import os
import sys
import time
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager


# --- 数据类 ---
class ProductItem:
    def __init__(self, uid, name):
        self.uid = uid
        self.name = name
        self.status = "等待扫描"
        self.monitor = True  # 默认勾选
        self.added = False  # 是否已成功加购


class RakutenBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Rakuten RMS 智能抢单系统 (防漏单稳定版)")
        self.root.geometry("1000x850")

        self.default_r_user = "suntakuraku0068"
        self.default_r_pass = "santaku74603"
        self.default_m_email = "hagoogi_k.k@outlook.com"
        self.default_m_pass = "K8302h0826"

        self.product_map = {}
        self.driver = None
        self.is_running = False
        self.wait_obj = None

        self._create_widgets()

    def _create_widgets(self):
        # === 1. 顶部设置 ===
        frame_top = tk.Frame(self.root)
        frame_top.pack(fill="x", padx=10, pady=5)

        # 账号
        group_account = tk.LabelFrame(frame_top, text="账号设置", padx=5, pady=5)
        group_account.pack(side="left", fill="y", padx=5)

        tk.Label(group_account, text="R-Login:").grid(row=0, column=0, sticky="e")
        self.entry_r_user = tk.Entry(group_account, width=15)
        self.entry_r_user.insert(0, self.default_r_user)
        self.entry_r_user.grid(row=0, column=1)

        tk.Label(group_account, text="Pass:").grid(row=1, column=0, sticky="e")
        self.entry_r_pass = tk.Entry(group_account, width=15)
        self.entry_r_pass.insert(0, self.default_r_pass)
        self.entry_r_pass.grid(row=1, column=1)

        tk.Label(group_account, text="Email:").grid(row=0, column=2, sticky="e")
        self.entry_m_email = tk.Entry(group_account, width=15)
        self.entry_m_email.insert(0, self.default_m_email)
        self.entry_m_email.grid(row=0, column=3)

        tk.Label(group_account, text="E-Pass:").grid(row=1, column=2, sticky="e")
        self.entry_m_pass = tk.Entry(group_account, width=15)
        self.entry_m_pass.insert(0, self.default_m_pass)
        self.entry_m_pass.grid(row=1, column=3)

        # 流程控制
        group_ctrl = tk.LabelFrame(frame_top, text="流程控制", padx=5, pady=5)
        group_ctrl.pack(side="left", fill="both", expand=True, padx=5)

        self.mode_var = tk.StringVar(value="TEST")
        tk.Radiobutton(group_ctrl, text="测试模式 (不结算)", variable=self.mode_var, value="TEST", fg="blue").grid(
            row=0, column=0, sticky="w")
        tk.Radiobutton(group_ctrl, text="正式抢单 (真实购买)", variable=self.mode_var, value="REAL", fg="red").grid(
            row=1, column=0, sticky="w")

        tk.Button(group_ctrl, text="1. 登录并进入收藏夹", bg="#f0f0f0", command=self.action_login).grid(row=0, column=1,
                                                                                                        rowspan=2,
                                                                                                        padx=5,
                                                                                                        sticky="ns")
        tk.Button(group_ctrl, text="2. 扫描列表", bg="#f0f0f0", command=self.action_scan).grid(row=0, column=2,
                                                                                               rowspan=2, padx=5,
                                                                                               sticky="ns")
        tk.Button(group_ctrl, text="3. 启动死循环监控", bg="green", fg="white", font=("bold", 12),
                  command=self.action_start_monitor).grid(row=0, column=3, rowspan=2, padx=5, sticky="ns")
        tk.Button(group_ctrl, text="停止", bg="red", fg="white", command=self.action_stop).grid(row=0, column=4,
                                                                                                rowspan=2, padx=5,
                                                                                                sticky="ns")

        # === 2. 列表工具栏 ===
        frame_list_tools = tk.Frame(self.root)
        frame_list_tools.pack(fill="x", padx=10, pady=(5, 0))
        tk.Button(frame_list_tools, text="全部勾选", command=lambda: self.toggle_all_monitor(True)).pack(side="left",
                                                                                                         padx=2)
        tk.Button(frame_list_tools, text="全部取消", command=lambda: self.toggle_all_monitor(False)).pack(side="left",
                                                                                                          padx=2)
        tk.Label(frame_list_tools, text="提示：单击 '监控' 列的复选框可切换状态。").pack(side="right")

        # === 3. 商品列表 (Treeview) ===
        columns = ("uid", "monitor", "status", "name")
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings", height=12)

        self.tree.heading("uid", text="ID")
        self.tree.column("uid", width=80, anchor="center")

        self.tree.heading("monitor", text="监控")
        self.tree.column("monitor", width=50, anchor="center")

        self.tree.heading("status", text="实时状态")
        self.tree.column("status", width=120, anchor="center")

        self.tree.heading("name", text="商品名称")
        self.tree.column("name", width=500, anchor="w")

        scrollbar = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        scrollbar.pack(side="right", fill="y")

        # 绑定点击事件
        self.tree.bind("<Button-1>", self.on_tree_click)

        # === 4. 日志 ===
        group_log = tk.LabelFrame(self.root, text="系统日志", padx=10, pady=5)
        group_log.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(group_log, height=10, state='disabled')
        self.log_text.pack(fill="both", expand=True)

    # --- 辅助功能 ---
    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        try:
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        except:
            pass
        print(f"[{timestamp}] {message}")

    def on_tree_click(self, event):
        """处理复选框点击"""
        region = self.tree.identify("region", event.x, event.y)
        if region == "heading": return

        item_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)

        # 如果点击的是第2列 (监控列)
        if item_id and col_id == "#2":
            vals = self.tree.item(item_id, "values")
            uid = vals[0]
            if uid in self.product_map:
                p_item = self.product_map[uid]
                p_item.monitor = not p_item.monitor  # 切换状态
                self.refresh_tree_item(uid)

    def toggle_all_monitor(self, enable):
        for uid, item in self.product_map.items():
            item.monitor = enable
            self.refresh_tree_item(uid)

    def refresh_tree_item(self, uid):
        """刷新表格某一行的数据和颜色"""
        if uid not in self.product_map: return
        p_item = self.product_map[uid]

        target_item = None
        for item in self.tree.get_children():
            if str(self.tree.item(item, "values")[0]) == str(uid):
                target_item = item
                break

        # 使用 Unicode 模拟复选框
        monitor_str = "☑" if p_item.monitor else "☐"

        # 颜色逻辑
        tags = []
        if not p_item.monitor:
            tags = ("gray",)
        elif p_item.added:
            tags = ("green",)
        elif "已开售" in p_item.status:
            tags = ("red",)
        else:
            tags = ("normal",)

        if target_item:
            self.tree.item(target_item, values=(uid, monitor_str, p_item.status, p_item.name), tags=tags)

    # --- 按钮动作 ---
    def action_login(self):
        if self.is_running: return
        self.is_running = True
        t = threading.Thread(target=self.thread_login)
        t.daemon = True
        t.start()

    def action_scan(self):
        if not self.driver:
            messagebox.showerror("错误", "请先登录")
            return
        t = threading.Thread(target=self.thread_scan)
        t.daemon = True
        t.start()

    def action_start_monitor(self):
        if not self.product_map:
            messagebox.showerror("错误", "列表为空，请先扫描")
            return
        self.is_running = True
        t = threading.Thread(target=self.thread_monitor_loop)
        t.daemon = True
        t.start()

    def action_stop(self):
        self.is_running = False
        self.log("🛑 正在停止...")

    # --- 线程逻辑 ---
    def thread_login(self):
        try:
            self.log(">>> [1] 启动浏览器并登录...")
            service = Service(ChromeDriverManager().install())
            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_argument("--disable-blink-features=AutomationControlled")
            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait_obj = WebDriverWait(self.driver, 30)

            if self._login_logic() and self._navigate_logic():
                self.log("✅ 登录完成，请点击 [2. 扫描列表]")
            else:
                self.log("❌ 登录或导航失败")
                self.is_running = False
        except Exception as e:
            self.log(f"异常: {e}")
            self.is_running = False

    def thread_scan(self):
        try:
            self.log(">>> [2] 正在扫描页面商品...")
            self.tree.delete(*self.tree.get_children())
            self.product_map.clear()
            self.tree.tag_configure("gray", foreground="#999999")
            self.tree.tag_configure("green", foreground="green", font=("bold",))
            self.tree.tag_configure("red", foreground="red", font=("bold",))
            self.tree.tag_configure("normal", foreground="black")

            try:
                self.wait_obj.until(EC.presence_of_element_located((By.ID, "prmm-ec-fav-search-result-container")))
                time.sleep(2)
            except:
                self.log("未找到列表容器，请确保在收藏夹页面")
                return

            product_blocks = self.driver.find_elements(By.XPATH, "//tbody[contains(@ng-repeat, 'result in resultSet')]")
            count = 0
            for tbody in product_blocks:
                try:
                    try:
                        btn = tbody.find_element(By.XPATH, ".//button[contains(@id, 'cart-btn-')]")
                        full_id = btn.get_attribute("id")
                        uid = full_id.replace("cart-btn-", "")
                    except NoSuchElementException:
                        continue

                    try:
                        name_el = tbody.find_element(By.XPATH, ".//li[contains(@id, 'menu-name')]//span")
                        name = name_el.text.strip()
                    except:
                        name = "未知名称"

                    if uid not in self.product_map:
                        p = ProductItem(uid, name)
                        self.product_map[uid] = p
                        monitor_str = "☑" if p.monitor else "☐"
                        self.tree.insert("", "end", values=(uid, monitor_str, "等待中", name), tags=("normal",))
                        count += 1
                except:
                    pass

            self.log(f"✅ 扫描完成：共 {count} 个商品。请勾选需要抢的商品。")
        except Exception as e:
            self.log(f"扫描异常: {e}")

    def thread_monitor_loop(self):
        """修复漏单的核心逻辑"""
        self.log(">>> [3] 启动防漏单监控 <<<")
        self.log("策略：刷新 -> 展开 -> 逐个点击并等待 -> 结算")

        loop_count = 0
        while self.is_running:
            loop_count += 1
            try:
                # 筛选需要监控且未完成的商品
                target_items = [p for p in self.product_map.values() if p.monitor]
                not_added = [p for p in target_items if not p.added]

                if not target_items:
                    self.log("⚠️ 未勾选任何商品！脚本停止。")
                    return

                if not not_added:
                    self.log("🎉 所有目标商品均已加入购物车！前往结算...")
                    self._checkout_logic()
                    return

                    # 1. 刷新
                if loop_count > 1:
                    self.driver.refresh()
                    try:
                        self.wait_obj.until(
                            EC.presence_of_element_located((By.ID, "prmm-ec-fav-search-result-container")))
                    except:
                        pass

                # 2. 智能展开
                try:
                    closed_icons = self.driver.find_elements(By.CSS_SELECTOR,
                                                             ".prmm-ec-fav-expand-details.fa-plus-square")
                    for icon in closed_icons:
                        self.driver.execute_script("arguments[0].click();", icon)
                    if closed_icons: time.sleep(0.5)
                except:
                    pass

                # 3. 逐个处理 (关键修改：增加间隔)
                any_action = False

                for item in not_added:
                    btn_id = f"cart-btn-{item.uid}"
                    try:
                        btn = self.driver.find_element(By.ID, btn_id)
                        is_disabled = btn.get_attribute("disabled")

                        if is_disabled:
                            if item.status != "等待开售":
                                item.status = "等待开售"
                                self.refresh_tree_item(item.uid)
                        else:
                            # 发现可买！
                            self.log(f"🚀 商品 {item.uid} 开售！尝试加购...")

                            # JS 点击
                            self.driver.execute_script("arguments[0].click();", btn)

                            # === 关键修复：点击后强制等待，防止并发请求丢失 ===
                            self.log(f"⏳ 已发送点击，等待服务器响应 (2秒)...")
                            time.sleep(2.0)

                            item.added = True
                            item.status = "已发送请求"
                            self.refresh_tree_item(item.uid)
                            any_action = True

                    except NoSuchElementException:
                        pass
                    except Exception:
                        pass

                if not any_action:
                    self.log(f"#{loop_count} 监控中... 剩余 {len(not_added)} 个未开售")
                    time.sleep(1)  # 刷新间隔
                else:
                    self.log(f"✅ 本轮操作结束。")

            except Exception as e:
                self.log(f"监控异常: {e}，重试...")
                time.sleep(2)

    # --- 内部逻辑函数 ---
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
            while time.time() - start < 60:
                if "mainmenu.rms.rakuten.co.jp" in self.driver.current_url: return True
                try:
                    links = self.driver.find_elements(By.XPATH,
                                                      "//a[contains(text(), 'RMS') or contains(text(), 'ＲＭＳ')]")
                    for l in links:
                        if l.is_displayed(): l.click(); time.sleep(2); break
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
                self.driver.get("https://ad.rms.rakuten.co.jp/ec/favorite")
            return True
        except:
            return False

    def _checkout_logic(self):
        try:
            self.log(">>> [4] 结算流程 <<<")
            self.wait_obj.until(EC.element_to_be_clickable((By.ID, "prmm-shopping-cart-top"))).click()
            time.sleep(2)
            checkout_btn = self.wait_obj.until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(., '購入する')]")))
            self.driver.execute_script("arguments[0].scrollIntoView();", checkout_btn)

            if self.mode_var.get() == "TEST":
                self.log("🟡 [测试模式] 停止。")
                messagebox.showinfo("完成", "测试结束，所有商品已加购。")
            else:
                if checkout_btn.is_enabled():
                    checkout_btn.click()
                    self.log("✅✅✅ 真实下单成功！")
                    messagebox.showwarning("购买完成", "订单已提交！")
                else:
                    self.log("❌ 结算按钮不可用")
        except Exception as e:
            self.log(f"结算错: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = RakutenBotGUI(root)
    root.mainloop()