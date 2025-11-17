import os
import base64
import json
import logging
import time
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime

try:
    import requests
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.chrome.service import Service as ChromeService
except ImportError as e:
    print(f"--- [严重错误] 缺少必要的库: {e} ---")
    print(f"--- [严重错误] 请在您的环境中运行: pip install selenium requests ---")
    sys.exit(1)


# ==================================================================
# 1. 核心抢单逻辑 (OrderSnatcher 类)
#    这部分代码与之前基本相同，只做微小调整以适应GUI
# ==================================================================
class OrderSnatcher:
    BASE_URL = "http://222.132.55.178:8190"
    JFYBM_API_URL = "http://api.jfbym.com/api/YmServer/customApi"
    JFYBM_TOKEN = "Sq83S53mcjz1AkA54_SXfYvrXxiTNVnya8bfIKe-ITE"
    JFYBM_CAPTCHA_TYPE = "30340"

    def __init__(self, order_data, login_info, stop_event):
        self.order_id = order_data["order_id"]
        self.rob_time_str = order_data["rob_time"]
        self.weight = order_data["weight"]
        self.quantity = order_data["quantity"]
        self.username = login_info["username"]
        self.password = login_info["password"]
        self.driver = None
        self.stop_event = stop_event  # 用于接收停止信号

        try:
            # PyInstaller 打包后寻找 chromedriver 的路径
            if getattr(sys, 'frozen', False):
                # 如果是打包后的 exe
                base_path = sys._MEIPASS
            else:
                # 如果是正常运行的 .py
                base_path = os.path.dirname(os.path.abspath(__file__))

            chromedriver_path = os.path.join(base_path, "chromedriver")

            service = ChromeService(executable_path=chromedriver_path)
            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_argument("--log-level=3")
            # 禁用 "Chrome is being controlled by automated test software" 提示
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)

            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait = WebDriverWait(self.driver, 20)
            logging.info("[诊断] WebDriver 初始化成功")
        except Exception as e:
            logging.error(f"❌ [严重错误] 在初始化WebDriver时发生致命错误: {e}")
            # 这里不再 sys.exit，而是让主线程知道出错了
            raise

    def login(self):
        logging.info("正在打开登录页面...")
        self.driver.get(f"{self.BASE_URL}/system/login")
        self.wait.until(
            EC.presence_of_element_located((By.XPATH, '//input[@placeholder="请输入您的用户名或手机号码"]'))).send_keys(
            self.username)
        self.driver.find_element(By.XPATH, '//input[@placeholder="输入您的密码"]').send_keys(self.password)
        self.driver.find_element(By.XPATH, '//button[contains(text(),"登")]').click()
        self.wait.until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "新货源单管理")))
        logging.info("✅ 登录成功！")
        return True

    def navigate_to_order_page(self):
        target_url = f"{self.BASE_URL}/newgoods/listSocietyPage"
        logging.info(f"正在通过URL直接导航到: {target_url}")
        self.driver.get(target_url)
        self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '查询')]")))
        logging.info("✅ 已成功进入'新货源单(社会提单)'页面。")
        return True

    def _solve_captcha(self, image_bytes):
        logging.info("开始请求 jfbym.com 【定制 API - 30340】服务...")
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        payload = {'image': base64_image, 'token': self.JFYBM_TOKEN, 'type': self.JFYBM_CAPTCHA_TYPE}
        start_time = time.time()
        response = requests.post(self.JFYBM_API_URL, data=payload, timeout=15)
        response.raise_for_status()
        duration = time.time() - start_time
        logging.info(f"⏱️ API 响应耗时: {duration:.3f} 秒")
        result = response.json()
        if result.get('code') != 10000 or result.get('data', {}).get('code') != 0:
            logging.error(f"API 识别失败: {result.get('msg')} / {result.get('data', {}).get('data')}")
            return None
        coordinates_str = result['data']['data']
        logging.info(f"✅ 识别成功! 原始坐标字符串: '{coordinates_str}'")
        return [{'x': int(p.split(',')[0]), 'y': int(p.split(',')[1])} for p in coordinates_str.split('|')]

    def run(self):
        try:
            if not self.login() or not self.navigate_to_order_page():
                return

            rob_time = datetime.strptime(self.rob_time_str, "%Y-%m-%d %H:%M:%S")
            logging.info(f"🎯 目标订单: {self.order_id}, 设定抢单时间: {self.rob_time_str}")

            while not self.stop_event.is_set():
                now = datetime.now()
                wait_seconds = (rob_time - now).total_seconds()
                if wait_seconds <= 0.1:
                    logging.info("抢单时间已到，开始执行！")
                    break
                logging.info(f"距离抢单还有 {wait_seconds:.2f} 秒，等待中...")
                # 使用 stop_event.wait 实现可中断的等待
                self.stop_event.wait(min(wait_seconds, 5))

            if self.stop_event.is_set():
                logging.warning("任务被用户手动停止。")
                return

            self.handle_robbery()
        except Exception as e:
            logging.error(f"抢单主流程发生错误: {e}")
            if self.driver:
                self.driver.save_screenshot("main_error.png")
        finally:
            if self.driver:
                logging.info("流程结束，浏览器将自动关闭。")
                self.driver.quit()

    def handle_robbery(self):
        target_source_id = self.order_id
        logging.info(f"正在页面上寻找【货源单号】为 {target_source_id} 的'抢单'链接...")
        rob_link_xpath = f"//tr[contains(., '货源单号：{target_source_id}')]/following-sibling::tr[1]//a[text()='抢单']"
        rob_link = self.wait.until(EC.element_to_be_clickable((By.XPATH, rob_link_xpath)))
        rob_link.click()
        logging.info("✅ 已点击抢单链接！")

        logging.info("等待'信息'确认框出现...")
        info_confirm_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@class='layui-layer-btn0']")))
        info_confirm_button.click()
        logging.info("已点击'信息'确认框。")

        logging.info("等待'货物明细'弹窗内的 iframe 出现...")
        self.wait.until(
            EC.frame_to_be_available_and_switch_to_it((By.XPATH, "//div[@class='layui-layer-content']/iframe")))
        logging.info("✅ 已成功切换到 iframe 内部。")

        weight_cell = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//td[@data-field='grabWeight']")))
        weight_cell.click()
        weight_cell.find_element(By.XPATH, ".//input").send_keys(str(self.weight))
        logging.info(f"已输入抢单重量: {self.weight}")

        quantity_cell = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//td[@data-field='grabQuantity']")))
        quantity_cell.click()
        quantity_cell.find_element(By.XPATH, ".//input").send_keys(str(self.quantity))
        logging.info(f"已输入抢单件数: {self.quantity}")

        self.driver.switch_to.default_content()
        logging.info("已从 iframe 切换回主页面。")

        confirm_rob_button = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//a[@class='layui-layer-btn0' and text()='确定抢单']")))
        confirm_rob_button.click()
        logging.info("已点击'确定抢单'按钮。")

        logging.info("等待最终的图片验证码弹窗...")
        captcha_dialog = self.wait.until(
            EC.visibility_of_element_located((By.XPATH, "//*[div[contains(text(), '安全验证')]]")))
        captcha_image_element = captcha_dialog.find_element(By.XPATH, ".//div[contains(@class, 'verify-img-panel')]")

        coordinates = self._solve_captcha(captcha_image_element.screenshot_as_png)
        if not coordinates:
            raise Exception("验证码识别失败")

        actions = ActionChains(self.driver)
        for point in coordinates:
            actions.move_to_element_with_offset(captcha_image_element, point['x'], point['y']).click()
        actions.perform()
        logging.info("所有坐标已点击完毕。")

        captcha_dialog.find_element(By.XPATH, ".//button[contains(text(), '确定')]").click()
        logging.info("✅ 已点击最终确认按钮，抢单请求已发送！")
        time.sleep(5)


# ==================================================================
# 2. GUI 界面逻辑
# ==================================================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("潍钢抢单助手")
        self.root.geometry("650x550")
        self.snatcher_thread = None
        self.stop_event = threading.Event()

        # --- 创建界面组件 ---
        self.create_widgets()
        # --- 配置日志重定向 ---
        self.setup_logging()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- 参数输入区 ---
        params_frame = ttk.LabelFrame(main_frame, text="配置参数", padding="10")
        params_frame.pack(fill=tk.X, pady=5)
        params_frame.columnconfigure(1, weight=1)
        params_frame.columnconfigure(3, weight=1)

        # 默认值
        self.username = tk.StringVar(value="QD0029")
        self.password = tk.StringVar(value="gcjt56788")
        self.order_id = tk.StringVar(value="HYD000000024825284")
        self.rob_time = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.weight = tk.StringVar(value="1")
        self.quantity = tk.StringVar(value="0")

        # 布局
        ttk.Label(params_frame, text="账号:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(params_frame, textvariable=self.username).grid(row=0, column=1, sticky=tk.EW)

        ttk.Label(params_frame, text="密码:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        pw_frame = ttk.Frame(params_frame)
        pw_frame.grid(row=1, column=1, sticky=tk.EW)
        self.pw_entry = ttk.Entry(pw_frame, textvariable=self.password, show="*")
        self.pw_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.eye_button = ttk.Button(pw_frame, text="👁", width=3, command=self.toggle_password)
        self.eye_button.pack(side=tk.LEFT)

        ttk.Label(params_frame, text="货源单号:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(params_frame, textvariable=self.order_id).grid(row=2, column=1, columnspan=3, sticky=tk.EW)

        ttk.Label(params_frame, text="抢单时间:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(params_frame, textvariable=self.rob_time).grid(row=3, column=1, columnspan=3, sticky=tk.EW)

        ttk.Label(params_frame, text="抢单重量:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(params_frame, textvariable=self.weight).grid(row=4, column=1, sticky=tk.EW)

        ttk.Label(params_frame, text="抢单件数:").grid(row=4, column=2, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(params_frame, textvariable=self.quantity).grid(row=4, column=3, sticky=tk.EW)

        # --- 控制按钮区 ---
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        self.start_button = ttk.Button(button_frame, text="开始抢单", command=self.start_snatching)
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.stop_button = ttk.Button(button_frame, text="停止任务", command=self.stop_snatching, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # --- 日志显示区 ---
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def toggle_password(self):
        if self.pw_entry.cget('show') == '*':
            self.pw_entry.config(show='')
            self.eye_button.config(text='🙈')
        else:
            self.pw_entry.config(show='*')
            self.eye_button.config(text='👁')

    def setup_logging(self):
        # 创建一个 Handler，用于将日志写入 Text 组件
        text_handler = TextHandler(self.log_text)
        # 设置日志格式
        formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S")
        text_handler.setFormatter(formatter)
        # 获取 root logger 并添加 handler
        logging.getLogger().addHandler(text_handler)
        logging.getLogger().setLevel(logging.INFO)

    def start_snatching(self):
        self.stop_event.clear()
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        order_data = {
            "order_id": self.order_id.get(),
            "rob_time": self.rob_time.get(),
            "weight": self.weight.get(),
            "quantity": self.quantity.get()
        }
        login_info = {
            "username": self.username.get(),
            "password": self.password.get()
        }

        # 在新线程中运行抢单逻辑
        self.snatcher_thread = threading.Thread(target=self.run_snatcher_thread, args=(order_data, login_info))
        self.snatcher_thread.daemon = True
        self.snatcher_thread.start()

        # 启动一个定时器检查线程是否结束
        self.check_thread()

    def run_snatcher_thread(self, order_data, login_info):
        try:
            snatcher = OrderSnatcher(order_data, login_info, self.stop_event)
            snatcher.run()
        except Exception as e:
            logging.error(f"抢单线程启动失败: {e}")

    def stop_snatching(self):
        logging.warning("正在发送停止信号...")
        self.stop_event.set()
        self.stop_button.config(state=tk.DISABLED)

    def check_thread(self):
        if self.snatcher_thread and self.snatcher_thread.is_alive():
            # 如果线程还在运行，100毫秒后再次检查
            self.root.after(100, self.check_thread)
        else:
            # 线程已结束，恢复按钮状态
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            logging.info("任务线程已结束。")


# ==================================================================
# 3. 用于将日志重定向到 Tkinter Text 组件的辅助类
# ==================================================================
class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        logging.Handler.__init__(self)
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)

        def append():
            self.text_widget.configure(state='normal')
            self.text_widget.insert(tk.END, msg + '\n')
            self.text_widget.configure(state='disabled')
            self.text_widget.yview(tk.END)

        # 使用 after 确保在主线程中更新 GUI
        self.text_widget.after(0, append)


# ==================================================================
# 4. 主程序启动入口
# ==================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()