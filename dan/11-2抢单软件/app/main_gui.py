import os
import base64
import json
import logging
import time
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
import io

try:
    import requests
    import pyautogui
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.chrome.service import Service as ChromeService

    # [优化] 设置 PyAutoGUI 的默认暂停时间为极短，提高点击速度
    pyautogui.PAUSE = 0.01
    pyautogui.FAILSAFE = False
except ImportError as e:
    print(f"--- [严重错误] 缺少必要的库: {e} ---")
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("依赖错误", f"缺少必要的库: {e}\n请联系软件提供商。")
    except:
        pass
    sys.exit(1)


# ==================================================================
# 1. 配置管理类 (保持不变)
# ==================================================================
class ConfigManager:
    def __init__(self, app_name="OrderSnatcherApp"):
        if sys.platform == "win32":
            self.config_path = os.path.join(os.getenv('APPDATA'), app_name)
        elif sys.platform == "darwin":
            self.config_path = os.path.join(os.path.expanduser('~/Library/Application Support'), app_name)
        else:
            self.config_path = os.path.join(os.path.expanduser('~'), f".{app_name.lower()}")
        os.makedirs(self.config_path, exist_ok=True)
        self.config_file = os.path.join(self.config_path, "config.json")

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def save_config(self, config_data):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
            logging.info("配置已成功保存。")
        except IOError:
            logging.error("保存配置失败！")


# ==================================================================
# 2. 核心抢单逻辑 (OrderSnatcher 类)
# ==================================================================
class OrderSnatcher:
    BASE_URL = "http://222.132.55.178:8190"
    JFYBM_API_URL = "http://api.jfbym.com/api/YmServer/customApi"
    JFYBM_CAPTCHA_TYPE = "30340"

    def __init__(self, order_data, login_info, api_token, captcha_coords, stop_event):
        self.order_data = order_data
        self.login_info = login_info
        self.api_token = api_token
        self.captcha_coords = captcha_coords
        self.stop_event = stop_event
        self.driver = None
        self.wait = None
        # [优化] 创建 requests Session 对象，复用 TCP 连接，加快打码 API 请求速度
        self.session = requests.Session()

        # 将配置参数解包到 self
        self.order_id = order_data["order_id"]
        self.weight = order_data["weight"]
        self.quantity = order_data["quantity"]
        self.screenshot_delay = order_data["screenshot_delay"]
        self.refresh_advance_time = order_data["refresh_advance_time"]
        self.username = login_info["username"]
        self.password = login_info["password"]
        self.jfybm_token = api_token

    def _create_driver(self):
        """创建一个新的 WebDriver 实例"""
        try:
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))
            chromedriver_path = os.path.join(base_path,
                                             "chromedriver.exe" if sys.platform == "win32" else "chromedriver")
            service = ChromeService(executable_path=chromedriver_path)
            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_argument("--log-level=3")

            # [修复] 暂时注释掉 eager 模式，因为它导致了登录页面的超时崩溃
            # 如果您的网络非常快且稳定，可以尝试取消注释，否则建议保持注释以确保稳定
            # options.page_load_strategy = 'eager'

            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)

            self.driver = webdriver.Chrome(service=service, options=options)

            # [修复] 将超时时间从 10秒 增加到 30秒，防止网页加载慢导致程序报错退出
            self.wait = WebDriverWait(self.driver, 30)

            logging.info("[诊断] WebDriver 初始化成功 (稳定模式)")
            return True
        except Exception as e:
            logging.error(f"❌ [严重错误] 在初始化WebDriver时发生致命错误: {e}")
            return False

    def _quit_driver(self):
        """安全地关闭 WebDriver 实例"""
        if self.driver:
            try:
                self.driver.quit()
                logging.info("浏览器已成功关闭。")
            except Exception as e:
                logging.warning(f"关闭浏览器时发生错误: {e}")
            finally:
                self.driver = None
                self.wait = None

    def login(self):
        logging.info("正在打开登录页面...")
        try:
            self.driver.get(f"{self.BASE_URL}/system/login")
            # 增加显式等待，确保输入框真的出现了
            username_input = self.wait.until(
                EC.presence_of_element_located((By.XPATH, '//input[@placeholder="请输入您的用户名或手机号码"]'))
            )
            username_input.send_keys(self.username)

            self.driver.find_element(By.XPATH, '//input[@placeholder="输入您的密码"]').send_keys(self.password)
            self.driver.find_element(By.XPATH, '//button[contains(text(),"登")]').click()

            # 等待登录完成
            self.wait.until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "新货源单管理")))
            logging.info("✅ 登录成功！")
            return True
        except TimeoutException:
            logging.error("❌ 登录超时！页面加载过慢或元素未找到。")
            return False
        except Exception as e:
            logging.error(f"❌ 登录失败: {e}")
            return False

    def navigate_to_order_page(self):
        target_url = f"{self.BASE_URL}/newgoods/listSocietyPage"
        logging.info(f"正在通过URL直接导航到: {target_url}")
        try:
            self.driver.get(target_url)
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '查询')]")))
            logging.info("✅ 已成功进入'新货源单(社会提单)'页面。")
            return True
        except TimeoutException:
            logging.error("❌ 导航超时！无法进入订单页面。")
            return False

    def _solve_captcha(self, image_bytes):
        logging.info("开始请求 jfbym.com 【定制 API - 30340】服务...")
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        payload = {'image': base64_image, 'token': self.jfybm_token, 'type': self.JFYBM_CAPTCHA_TYPE}
        start_time = time.time()

        # [优化] 使用 self.session 发送请求，复用连接
        try:
            response = self.session.post(self.JFYBM_API_URL, data=payload, timeout=15)
            response.raise_for_status()
        except requests.RequestException as e:
            logging.error(f"API 网络请求异常: {e}")
            return None

        duration = time.time() - start_time
        logging.info(f"⏱️ API 响应耗时: {duration:.3f} 秒")

        try:
            result = response.json()
        except json.JSONDecodeError:
            logging.error("API 返回非 JSON 数据")
            return None

        if result.get('code') != 10000: logging.error(f"API 请求失败: {result.get('msg')}"); return None
        data_payload = result.get('data')
        if not isinstance(data_payload, dict): logging.error(f"API 返回的 data 格式不正确: {data_payload}"); return None
        if data_payload.get('code') != 0: logging.error(f"打码服务出错: {data_payload.get('data')}"); return None
        coordinates_str = data_payload.get('data')
        logging.info(f"✅ 识别成功! 原始坐标字符串: '{coordinates_str}'")
        return [{'x': int(p.split(',')[0]), 'y': int(p.split(',')[1])} for p in coordinates_str.split('|')]

    def run(self):
        """主运行函数，包含重启机制"""
        max_retries = 3
        for attempt in range(max_retries):
            if self.stop_event.is_set():
                logging.warning("任务被用户手动停止。");
                break

            try:
                logging.info(f"--- 开始第 {attempt + 1}/{max_retries} 次抢单尝试 ---")
                if not self._create_driver(): return  # 创建 driver

                if not self.login() or not self.navigate_to_order_page():
                    self._quit_driver();
                    continue  # 如果登录或导航失败，重启

                # 核心抢单循环
                success = self._snatching_loop()
                if success:
                    logging.info("🎉🎉🎉 抢单流程执行完毕！ 🎉🎉🎉")
                    break  # 成功则跳出重试循环

            except Exception as e:
                logging.error(f"第 {attempt + 1} 次尝试中发生严重错误: {e}")
                if self.driver:
                    try:
                        self.driver.save_screenshot(f"main_error_attempt_{attempt + 1}.png")
                    except:
                        pass
            finally:
                self._quit_driver()  # 每次尝试结束后都清理 driver
        else:
            logging.error(f"已达到最大重试次数 ({max_retries}次)，任务终止。")

    def _snatching_loop(self):
        """包含自动获取时间、智能刷新和抢单的内部循环"""
        logging.info(f"正在页面上寻找订单 {self.order_id} 并获取抢单时间...")
        rob_time_str = None
        title_row_xpath = f"//tr[contains(., '货源单号：{self.order_id}')]"
        time_element_relative_xpath = "./following-sibling::tr[1]//span[preceding-sibling::em[text()='抢单开始时间：']]"

        while not self.stop_event.is_set():
            try:
                title_row = self.wait.until(EC.presence_of_element_located((By.XPATH, title_row_xpath)))
                time_element = title_row.find_element(By.XPATH, time_element_relative_xpath)
                rob_time_str = time_element.text
                if rob_time_str: logging.info(f"✅ 成功获取抢单时间: {rob_time_str}"); break
            except Exception:
                logging.warning(f"未在当前页面找到订单 {self.order_id}，将在3秒后刷新重试...")
                self.stop_event.wait(3)
                if self.stop_event.is_set(): return False
                self.driver.refresh()

        rob_time = datetime.strptime(rob_time_str, "%Y-%m-%d %H:%M:%S")
        logging.info(f"🎯 目标订单: {self.order_id}, 自动设定抢单时间: {rob_time_str}")
        rob_link_xpath = f"//tr[contains(., '货源单号：{self.order_id}')]/following-sibling::tr[1]//a[text()='抢单']"

        # 预先定义好 Wait 对象，避免循环内重复创建
        health_check_wait = WebDriverWait(self.driver, 2)
        short_wait = WebDriverWait(self.driver, 1.5)

        while not self.stop_event.is_set():
            now = datetime.now()
            wait_seconds = (rob_time - now).total_seconds()
            if wait_seconds > self.refresh_advance_time:
                logging.info(f"距离抢单还有 {wait_seconds:.0f} 秒，智能等待中...")
                self.stop_event.wait(5);
                continue

            logging.info(f"进入最后 {wait_seconds:.1f} 秒，开始高频刷新捕捉抢单按钮！")
            self.driver.refresh()

            try:
                health_check_wait.until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '查询')]")))
            except TimeoutException:
                logging.error("页面健康检查失败！检测到页面已崩溃，将触发浏览器重启。")
                return False  # 返回 False，让外层循环知道需要重启

            try:
                rob_link = short_wait.until(EC.element_to_be_clickable((By.XPATH, rob_link_xpath)))
                logging.info("🔥🔥🔥 抢单按钮已捕获，立即抢占！ 🔥🔥🔥")
                rob_link.click()
                self.handle_robbery_steps()
                return True  # 抢单流程执行完毕，返回 True
            except TimeoutException:
                if wait_seconds <= -2: logging.error(
                    "抢单时间已过超过2秒，按钮仍未出现，任务终止。"); return True  # 同样视为任务结束
                continue
        return False  # 用户手动停止

    def handle_robbery_steps(self):
        logging.info("✅ 已点击抢单链接！")
        self.wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@class='layui-layer-btn0']"))).click()
        logging.info("已点击'信息'确认框。")
        self.wait.until(EC.frame_to_be_available_and_switch_to_it(
            (By.XPATH, "//div[contains(@class, 'layui-layer-iframe')]//iframe")))
        logging.info("✅ 已成功切换到 iframe 内部。")
        weight_cell = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//td[@data-field='grabWeight']")))
        weight_cell.click()
        weight_cell.find_element(By.XPATH, ".//input").send_keys(str(self.weight))
        quantity_cell = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//td[@data-field='grabQuantity']")))
        quantity_cell.click()
        quantity_cell.find_element(By.XPATH, ".//input").send_keys(str(self.quantity))
        self.driver.switch_to.default_content()
        self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//a[@class='layui-layer-btn0' and text()='确定抢单']"))).click()
        logging.info("已点击'确定抢单'按钮。")
        logging.info(f"等待验证码弹窗加载 (延时 {self.screenshot_delay} 秒)...")
        time.sleep(self.screenshot_delay)
        x1, y1 = self.captcha_coords['top_left']
        x2, y2 = self.captcha_coords['bottom_right']
        width = x2 - x1
        height = y2 - y1
        logging.info(f"将在屏幕区域 ({x1},{y1}) -> ({x2},{y2}) 进行截图。")
        screenshot = pyautogui.screenshot(region=(x1, y1, width, height))
        img_byte_arr = io.BytesIO()
        screenshot.save(img_byte_arr, format='PNG')
        image_bytes = img_byte_arr.getvalue()
        coordinates = self._solve_captcha(image_bytes)
        if not coordinates: raise Exception("验证码识别失败")

        logging.info("计算绝对坐标并模拟极速点击...")
        for point in coordinates:
            absolute_x = x1 + point['x']
            absolute_y = y1 + point['y']
            # [优化] 移除循环内的 sleep，利用 pyautogui 全局设置实现快速点击
            pyautogui.click(absolute_x, absolute_y)

        confirm_x, confirm_y = self.captcha_coords['confirm_button']
        logging.info(f"模拟点击最终确认按钮，坐标: ({confirm_x}, {confirm_y})")
        pyautogui.click(confirm_x, confirm_y)

        logging.info("✅ 抢单动作完成！")

        # [重要优化] 延长等待时间，确保结算页面完全加载和服务器响应
        wait_time_final = 20
        logging.info(f"⏳ 保持浏览器开启 {wait_time_final} 秒，等待结算画面显示，请勿手动关闭...")
        time.sleep(wait_time_final)


# ==================================================================
# 3. GUI 界面逻辑 (保持不变)
# ==================================================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("潍钢抢单助手 V7.5 (稳定修复版)")
        self.root.geometry("650x750")
        self.snatcher_thread = None
        self.stop_event = threading.Event()
        self.picking_coords = False
        self.config_manager = ConfigManager()
        self.create_widgets()
        self.setup_logging()
        self.load_settings()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        params_frame = ttk.LabelFrame(main_frame, text="配置参数", padding="10")
        params_frame.pack(fill=tk.X, pady=5)
        params_frame.columnconfigure(1, weight=1)
        params_frame.columnconfigure(3, weight=1)
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.api_token = tk.StringVar()
        self.order_id = tk.StringVar()
        self.weight = tk.StringVar()
        self.quantity = tk.StringVar()
        self.x1 = tk.StringVar()
        self.y1 = tk.StringVar()
        self.x2 = tk.StringVar()
        self.y2 = tk.StringVar()
        self.confirm_x = tk.StringVar()
        self.confirm_y = tk.StringVar()
        self.screenshot_delay = tk.StringVar()
        self.refresh_advance_time = tk.StringVar()
        self.mouse_pos = tk.StringVar(value="鼠标坐标: (-, -)")
        row = 0
        ttk.Label(params_frame, text="网站账号:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=3)
        ttk.Entry(params_frame, textvariable=self.username).grid(row=row, column=1, columnspan=3, sticky=tk.EW)
        row += 1
        ttk.Label(params_frame, text="网站密码:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=3)
        pw_frame = ttk.Frame(params_frame)
        pw_frame.grid(row=row, column=1, columnspan=3, sticky=tk.EW)
        self.pw_entry = ttk.Entry(pw_frame, textvariable=self.password, show="*")
        self.pw_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.eye_button = ttk.Button(pw_frame, text="👁", width=3, command=self.toggle_password)
        self.eye_button.pack(side=tk.LEFT)
        row += 1
        ttk.Label(params_frame, text="API Token:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=3)
        ttk.Entry(params_frame, textvariable=self.api_token).grid(row=row, column=1, columnspan=3, sticky=tk.EW)
        row += 1
        ttk.Label(params_frame, text="货源单号:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=3)
        ttk.Entry(params_frame, textvariable=self.order_id).grid(row=row, column=1, columnspan=3, sticky=tk.EW)
        row += 1
        ttk.Label(params_frame, text="抢单重量:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=3)
        ttk.Entry(params_frame, textvariable=self.weight).grid(row=row, column=1, sticky=tk.EW)
        ttk.Label(params_frame, text="抢单件数:").grid(row=row, column=2, sticky=tk.W, padx=5, pady=3)
        ttk.Entry(params_frame, textvariable=self.quantity).grid(row=row, column=3, sticky=tk.EW)
        row += 1
        ttk.Label(params_frame, text="截图前延时(秒):").grid(row=row, column=0, sticky=tk.W, padx=5, pady=3)
        ttk.Entry(params_frame, textvariable=self.screenshot_delay).grid(row=row, column=1, sticky=tk.EW)
        ttk.Label(params_frame, text="提前刷新(秒):").grid(row=row, column=2, sticky=tk.W, padx=5, pady=3)
        ttk.Entry(params_frame, textvariable=self.refresh_advance_time).grid(row=row, column=3, sticky=tk.EW)
        coords_frame = ttk.LabelFrame(main_frame, text="坐标拾取工具", padding="10")
        coords_frame.pack(fill=tk.X, pady=10)
        pos_label = ttk.Label(coords_frame, textvariable=self.mouse_pos, font=("", 12, "bold"), foreground="blue")
        pos_label.pack()
        picker_buttons = ttk.Frame(coords_frame)
        picker_buttons.pack(pady=5)
        self.pick_btn = ttk.Button(picker_buttons, text="开始拾取", command=self.start_picking)
        self.pick_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(picker_buttons, text="设为左上角", command=self.set_top_left).pack(side=tk.LEFT, padx=5)
        ttk.Button(picker_buttons, text="设为右下角", command=self.set_bottom_right).pack(side=tk.LEFT, padx=5)
        ttk.Button(picker_buttons, text="设为确认按钮", command=self.set_confirm_btn).pack(side=tk.LEFT, padx=5)
        self.stop_pick_btn = ttk.Button(picker_buttons, text="停止拾取", command=self.stop_picking, state=tk.DISABLED)
        self.stop_pick_btn.pack(side=tk.LEFT, padx=5)
        input_coords_frame = ttk.Frame(coords_frame)
        input_coords_frame.pack(pady=5)
        ttk.Label(input_coords_frame, text="截图区 左上(X,Y):").pack(side=tk.LEFT)
        ttk.Entry(input_coords_frame, textvariable=self.x1, width=5).pack(side=tk.LEFT)
        ttk.Entry(input_coords_frame, textvariable=self.y1, width=5).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(input_coords_frame, text="右下(X,Y):").pack(side=tk.LEFT)
        ttk.Entry(input_coords_frame, textvariable=self.x2, width=5).pack(side=tk.LEFT)
        ttk.Entry(input_coords_frame, textvariable=self.y2, width=5).pack(side=tk.LEFT)
        confirm_coords_frame = ttk.Frame(coords_frame)
        confirm_coords_frame.pack()
        ttk.Label(confirm_coords_frame, text="确认按钮 (X,Y):").pack(side=tk.LEFT)
        ttk.Entry(confirm_coords_frame, textvariable=self.confirm_x, width=5).pack(side=tk.LEFT)
        ttk.Entry(confirm_coords_frame, textvariable=self.confirm_y, width=5).pack(side=tk.LEFT)
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        self.start_button = ttk.Button(button_frame, text="开始抢单", command=self.start_snatching)
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.stop_button = ttk.Button(button_frame, text="停止任务", command=self.stop_snatching, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def update_mouse_pos(self):
        if self.picking_coords:
            x, y = pyautogui.position()
            self.mouse_pos.set(f"鼠标坐标: ({x}, {y})")
            self.root.after(50, self.update_mouse_pos)

    def start_picking(self):
        self.picking_coords = True;
        self.pick_btn.config(state=tk.DISABLED);
        self.stop_pick_btn.config(state=tk.NORMAL)
        logging.info("坐标拾取已开始，请移动鼠标...");
        self.update_mouse_pos()

    def stop_picking(self):
        self.picking_coords = False;
        self.pick_btn.config(state=tk.NORMAL);
        self.stop_pick_btn.config(state=tk.DISABLED)
        self.mouse_pos.set("鼠标坐标: (-, -)");
        logging.info("坐标拾取已停止。")

    def set_top_left(self):
        if self.picking_coords:
            x, y = pyautogui.position();
            self.x1.set(str(x));
            self.y1.set(str(y));
            logging.info(
                f"已设定左上角坐标为: ({x}, {y})")
        else:
            logging.warning("请先点击'开始拾取'。")

    def set_bottom_right(self):
        if self.picking_coords:
            x, y = pyautogui.position();
            self.x2.set(str(x));
            self.y2.set(str(y));
            logging.info(
                f"已设定右下角坐标为: ({x}, {y})")
        else:
            logging.warning("请先点击'开始拾取'。")

    def set_confirm_btn(self):
        if self.picking_coords:
            x, y = pyautogui.position();
            self.confirm_x.set(str(x));
            self.confirm_y.set(str(y));
            logging.info(
                f"已设定确认按钮坐标为: ({x}, {y})")
        else:
            logging.warning("请先点击'开始拾取'。")

    def toggle_password(self):
        if self.pw_entry.cget('show') == '*':
            self.pw_entry.config(show='');
            self.eye_button.config(text='🙈')
        else:
            self.pw_entry.config(show='*');
            self.eye_button.config(text='👁')

    def setup_logging(self):
        text_handler = TextHandler(self.log_text)
        formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S")
        text_handler.setFormatter(formatter)
        logging.getLogger().addHandler(text_handler)
        logging.getLogger().setLevel(logging.INFO)

    def start_snatching(self):
        self.stop_event.clear();
        self.start_button.config(state=tk.DISABLED);
        self.stop_button.config(state=tk.NORMAL)
        try:
            order_data = {
                "order_id": self.order_id.get(), "weight": self.weight.get(), "quantity": self.quantity.get(),
                "screenshot_delay": float(self.screenshot_delay.get()),
                "refresh_advance_time": int(self.refresh_advance_time.get())
            }
            login_info = {"username": self.username.get(), "password": self.password.get()}
            api_token = self.api_token.get()
            captcha_coords = {
                "top_left": (int(self.x1.get()), int(self.y1.get())),
                "bottom_right": (int(self.x2.get()), int(self.y2.get())),
                "confirm_button": (int(self.confirm_x.get()), int(self.confirm_y.get()))
            }
        except ValueError:
            logging.error("输入无效，请确保重量、件数、延时和坐标均为有效数字！")
            self.stop_snatching();
            return

        self.snatcher_thread = threading.Thread(target=self.run_snatcher_thread,
                                                args=(order_data, login_info, api_token, captcha_coords))
        self.snatcher_thread.daemon = True
        self.snatcher_thread.start()
        self.check_thread()

    def run_snatcher_thread(self, order_data, login_info, api_token, captcha_coords):
        snatcher = None
        try:
            snatcher = OrderSnatcher(order_data, login_info, api_token, captcha_coords, self.stop_event)
            snatcher.run()
        except Exception as e:
            logging.error(f"抢单线程启动失败: {e}")
        finally:
            if snatcher:
                snatcher._quit_driver()  # 确保即使run方法启动失败，driver也被清理

    def stop_snatching(self):
        logging.warning("正在发送停止信号...");
        self.stop_event.set();
        self.stop_button.config(state=tk.DISABLED)

    def check_thread(self):
        if self.snatcher_thread and self.snatcher_thread.is_alive():
            self.root.after(100, self.check_thread)
        else:
            self.start_button.config(state=tk.NORMAL);
            self.stop_button.config(state=tk.DISABLED);
            logging.info(
                "任务线程已结束。")

    def load_settings(self):
        config = self.config_manager.load_config()
        self.username.set(config.get("username", "QD0029"))
        self.password.set(config.get("password", "gcjt56788"))
        self.api_token.set(config.get("api_token", "Sq83S53mcjz1AkA54_SXfYvrXxiTNVnya8bfIKe-ITE"))
        self.order_id.set(config.get("order_id", ""))
        self.weight.set(config.get("weight", "1"))
        self.quantity.set(config.get("quantity", "0"))
        self.x1.set(config.get("x1", "772"))
        self.y1.set(config.get("y1", "446"))
        self.x2.set(config.get("x2", "1068"))
        self.y2.set(config.get("y2", "770"))
        self.confirm_x.set(config.get("confirm_x", "920"))
        self.confirm_y.set(config.get("confirm_y", "740"))
        self.screenshot_delay.set(config.get("screenshot_delay", "1.5"))
        self.refresh_advance_time.set(config.get("refresh_advance_time", "15"))
        logging.info("已从本地加载配置（或使用默认值）。")

    def save_settings(self):
        config = {
            "username": self.username.get(), "password": self.password.get(),
            "api_token": self.api_token.get(), "order_id": self.order_id.get(),
            "weight": self.weight.get(), "quantity": self.quantity.get(),
            "x1": self.x1.get(), "y1": self.y1.get(),
            "x2": self.x2.get(), "y2": self.y2.get(),
            "confirm_x": self.confirm_x.get(), "confirm_y": self.confirm_y.get(),
            "screenshot_delay": self.screenshot_delay.get(),
            "refresh_advance_time": self.refresh_advance_time.get()
        }
        self.config_manager.save_config(config)

    def on_closing(self):
        self.save_settings()
        self.root.destroy()


# ==================================================================
# 4. 日志重定向辅助类
# ==================================================================
class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        logging.Handler.__init__(self);
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)

        def append():
            self.text_widget.configure(state='normal')
            self.text_widget.insert(tk.END, msg + '\n')
            self.text_widget.configure(state='disabled')
            self.text_widget.yview(tk.END)

        self.text_widget.after(0, append)


# ==================================================================
# 5. 主程序启动入口
# ==================================================================
def check_trial_period():
    try:
        start_time = datetime.strptime("2025-11-17 12:00:00", "%Y-%m-%d %H:%M:%S")
        # [修改] 试用期延长至 12月1日
        end_time = datetime.strptime("2025-12-01 12:00:00", "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        if not (start_time <= now <= end_time):
            return False, f"试用期已于 {end_time.strftime('%Y-%m-%d %H:%M')} 结束。"
        remaining_time = end_time - now
        return True, f"试用期剩余: {remaining_time.days} 天 {remaining_time.seconds // 3600} 小时"
    except Exception:
        return False, "无法验证试用期，程序无法启动。"


if __name__ == "__main__":
    is_valid, message = check_trial_period()
    temp_root = tk.Tk()
    temp_root.withdraw()
    if not is_valid:
        messagebox.showerror("试用结束", message + "\n请联系软件提供商获取正式版。")
        temp_root.destroy()
        sys.exit()
    temp_root.destroy()

    if getattr(sys, 'frozen', False):
        if sys.platform == 'win32':
            __import__("pyautogui._pyautogui_win")
        elif sys.platform == 'darwin':
            __import__("pyautogui._pyautogui_osx")

    root = tk.Tk()
    app = App(root)
    original_title = app.root.title()
    app.root.title(f"{original_title} - [{message}]")
    root.mainloop()