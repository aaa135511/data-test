import os
import sys
import time
import platform
import tkinter as tk
from tkinter import messagebox
import threading

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 引入自动管理驱动的库
from webdriver_manager.chrome import ChromeDriverManager


class RakutenBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Rakuten RMS 自动抢单助手 (Mac/Win通用版)")
        self.root.geometry("450x400")

        # 默认账号信息
        self.default_r_user = "suntakuraku0068"
        self.default_r_pass = "santaku74603"
        self.default_m_email = "hagoogi_k.k@outlook.com"
        self.default_m_pass = "K8302h0826"

        self._create_widgets()

    def _create_widgets(self):
        # R-Login 区域
        tk.Label(self.root, text="=== R-Login (企业账号) ===", font=("Arial", 10, "bold")).pack(pady=5)

        frame_r = tk.Frame(self.root)
        frame_r.pack(pady=5)

        tk.Label(frame_r, text="R-ID: ").grid(row=0, column=0, sticky="e")
        self.entry_r_user = tk.Entry(frame_r, width=30)
        self.entry_r_user.insert(0, self.default_r_user)
        self.entry_r_user.grid(row=0, column=1)

        tk.Label(frame_r, text="R-Pass:").grid(row=1, column=0, sticky="e")
        self.entry_r_pass = tk.Entry(frame_r, width=30)
        self.entry_r_pass.insert(0, self.default_r_pass)
        self.entry_r_pass.grid(row=1, column=1)

        # Member Login 区域
        tk.Label(self.root, text="=== Rakuten Member (邮箱账号) ===", font=("Arial", 10, "bold")).pack(pady=10)

        frame_m = tk.Frame(self.root)
        frame_m.pack(pady=5)

        tk.Label(frame_m, text="Email:").grid(row=0, column=0, sticky="e")
        self.entry_m_email = tk.Entry(frame_m, width=30)
        self.entry_m_email.insert(0, self.default_m_email)
        self.entry_m_email.grid(row=0, column=1)

        tk.Label(frame_m, text="Pass:").grid(row=1, column=0, sticky="e")
        self.entry_m_pass = tk.Entry(frame_m, width=30)
        self.entry_m_pass.insert(0, self.default_m_pass)
        self.entry_m_pass.grid(row=1, column=1)

        # 状态显示
        self.status_label = tk.Label(self.root, text="就绪", fg="blue")
        self.status_label.pack(pady=5)

        # 按钮
        tk.Button(self.root, text="开始执行 (Start)", bg="green", fg="white", command=self.start_bot).pack(pady=15)

    def log(self, message):
        print(message)
        self.status_label.config(text=message)

    def start_bot(self):
        r_user = self.entry_r_user.get()
        r_pass = self.entry_r_pass.get()
        m_email = self.entry_m_email.get()
        m_pass = self.entry_m_pass.get()

        t = threading.Thread(target=self.run_automation, args=(r_user, r_pass, m_email, m_pass))
        t.daemon = True  # 设置为守护线程，关闭窗口时自动结束
        t.start()

    def run_automation(self, r_user, r_pass, m_email, m_pass):
        driver = None
        try:
            self.log("正在自动下载/配置 ChromeDriver...")
            service = Service(ChromeDriverManager().install())

            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-blink-features=AutomationControlled")

            self.log("启动浏览器...")
            driver = webdriver.Chrome(service=service, options=options)
            wait = WebDriverWait(driver, 30)

            # --- 阶段 1: 登录流程 ---
            self.log("1. 打开登录页面...")
            driver.get("https://glogin.rms.rakuten.co.jp/")

            self.log("2. R-Login 认证...")
            try:
                r_user_input = wait.until(EC.element_to_be_clickable((By.ID, "rlogin-username-ja")))
                r_user_input.clear()
                r_user_input.send_keys(r_user)

                r_pass_input = driver.find_element(By.ID, "rlogin-password-ja")
                r_pass_input.clear()
                r_pass_input.send_keys(r_pass)

                driver.find_element(By.NAME, "submit").click()
            except Exception as e:
                self.log(f"R-Login 失败: {e}")
                return

            self.log("3. 邮箱认证...")
            try:
                email_input = wait.until(EC.visibility_of_element_located((By.ID, "user_id")))
                time.sleep(1)
                email_input.clear()
                email_input.send_keys(m_email)
                driver.find_element(By.ID, "cta001").click()
            except Exception as e:
                self.log(f"邮箱输入失败: {e}")
                return

            self.log("4. 密码认证...")
            try:
                password_input = wait.until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
                time.sleep(1)
                password_input.clear()
                password_input.send_keys(m_pass)

                time.sleep(1)
                # 尝试点击登录 (包含 cta011 / class 等多种情况)
                try:
                    driver.find_element(By.ID, "cta011").click()
                except:
                    try:
                        driver.find_element(By.CLASS_NAME, "h4k5-e2e-button__submit").click()
                    except:
                        driver.find_element(By.XPATH, "//div[@role='button'][.//div[contains(text(), 'Next')]]").click()

                self.log("已点击登录，等待后续跳转...")
            except Exception as e:
                self.log(f"密码点击失败，请手动处理: {e}")

            # --- 阶段 2: 处理中间拦截页面 ---
            time.sleep(3)  # 等待页面加载

            # 拦截页 1: 须知页面 (次へ)
            try:
                self.log("检测拦截页1 (安全须知)...")
                # 查找 name="submit" 且包含文本 "次へ" 的按钮
                btn_next = driver.find_element(By.XPATH, "//button[@name='submit'][contains(text(), '次へ')]")
                btn_next.click()
                self.log(">>> 已点击‘次へ’")
                time.sleep(3)
            except:
                self.log("未检测到拦截页1，跳过。")

            # 拦截页 2: 服务选择 (RMS)
            try:
                self.log("检测拦截页2 (选择服务)...")
                # 查找 href 中包含 mainmenu 的链接，或者文本包含 RMS
                # 注意：这里使用模糊匹配，因为全角半角符号可能不同
                btn_rms = driver.find_element(By.XPATH, "//a[contains(@href, 'mainmenu.rms.rakuten.co.jp')]")
                btn_rms.click()
                self.log(">>> 已点击‘RMS’")
                time.sleep(3)
            except:
                self.log("未检测到拦截页2，跳过。")

            # 拦截页 3: 遵守事项确认 (红色按钮)
            try:
                self.log("检测拦截页3 (合规确认)...")
                # 查找 class 包含 btn-red 的 submit 按钮
                # 使用 CSS Selector 定位 class="btn-reset btn-round btn-red"
                btn_confirm = driver.find_element(By.CSS_SELECTOR, "button.btn-red")
                btn_confirm.click()
                self.log(">>> 已点击‘确认并使用’")
                time.sleep(3)
            except:
                self.log("未检测到拦截页3，跳过。")

            # --- 阶段 3: 准备抢单 ---
            self.log(">>> 登录全流程结束 <<<")
            self.log("请确认是否已进入 RMS 后台主页。")
            self.log("下一步：请手动进入【广告收藏夹】，然后按 F12 获取列表 HTML 发给我。")

            while True:
                time.sleep(2)

        except Exception as e:
            self.log(f"发生严重错误: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = RakutenBotGUI(root)
    root.mainloop()