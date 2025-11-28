import os
import base64
import json
import logging
import time
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime, timedelta  # 引入 timedelta 处理时间差
import io

try:
    import requests
    import pyautogui
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
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
# 1. 配置管理类
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

    # [优化4] 服务器时间偏移量 (秒)
    SERVER_OFFSET = 25

    def __init__(self, order_data, login_info, api_token, captcha_coords, stop_event):
        self.order_data = order_data
        self.login_info = login_info
        self.api_token = api_token
        self.captcha_coords = captcha_coords
        self.stop_event = stop_event
        self.driver = None
        self.wait = None
        self.session = requests.Session()

        self.order_id = order_data["order_id"]
        self.weight = order_data["weight"]
        self.quantity = order_data["quantity"]
        self.screenshot_delay = order_data["screenshot_delay"]
        self.refresh_advance_time = order_data["refresh_advance_time"]
        self.username = login_info["username"]
        self.password = login_info["password"]
        self.jfybm_token = api_token

    def _get_server_time(self):
        """获取估算的服务器时间"""
        return datetime.now() + timedelta(seconds=self.SERVER_OFFSET)

    def _create_driver(self):
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
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)

            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait = WebDriverWait(self.driver, 30)

            logging.info("[诊断] WebDriver 初始化成功")
            return True
        except Exception as e:
            logging.error(f"❌ [严重错误] WebDriver 初始化失败: {e}")
            return False

    def _quit_driver(self):
        if self.driver:
            try:
                self.driver.quit()
                logging.info("浏览器已关闭。")
            except Exception as e:
                logging.warning(f"关闭浏览器错误: {e}")
            finally:
                self.driver = None
                self.wait = None

    def login(self):
        logging.info("正在打开登录页面...")
        try:
            self.driver.get(f"{self.BASE_URL}/system/login")
            username_input = self.wait.until(
                EC.presence_of_element_located((By.XPATH, '//input[@placeholder="请输入您的用户名或手机号码"]'))
            )
            username_input.send_keys(self.username)
            self.driver.find_element(By.XPATH, '//input[@placeholder="输入您的密码"]').send_keys(self.password)
            self.driver.find_element(By.XPATH, '//button[contains(text(),"登")]').click()
            self.wait.until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "新货源单管理")))
            logging.info("✅ 登录成功！")
            return True
        except Exception as e:
            logging.error(f"❌ 登录失败: {e}")
            return False

    def navigate_to_order_page(self):
        target_url = f"{self.BASE_URL}/newgoods/listSocietyPage"
        logging.info(f"导航至: {target_url}")
        try:
            self.driver.get(target_url)
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '查询')]")))
            logging.info("✅ 已进入订单页面。")
            return True
        except TimeoutException:
            logging.error("❌ 导航超时。")
            return False

    def _solve_captcha(self, image_bytes):
        logging.info("请求打码 API...")
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        payload = {'image': base64_image, 'token': self.jfybm_token, 'type': self.JFYBM_CAPTCHA_TYPE}

        try:
            response = self.session.post(self.JFYBM_API_URL, data=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
        except Exception as e:
            logging.error(f"API 请求异常: {e}")
            return None

        if result.get('code') != 10000:
            logging.error(f"API 错误: {result.get('msg')}")
            return None

        data_payload = result.get('data')
        if data_payload.get('code') != 0:
            logging.error(f"识别失败: {data_payload.get('data')}")
            return None

        coordinates_str = data_payload.get('data')
        logging.info(f"✅ 识别成功: {coordinates_str}")
        return [{'x': int(p.split(',')[0]), 'y': int(p.split(',')[1])} for p in coordinates_str.split('|')]

    def run(self):
        max_retries = 3
        for attempt in range(max_retries):
            if self.stop_event.is_set(): break
            try:
                logging.info(f"--- 第 {attempt + 1} 次尝试 ---")
                if not self._create_driver(): return
                if not self.login() or not self.navigate_to_order_page():
                    self._quit_driver()
                    continue

                if self._snatching_loop():
                    logging.info("🎉 任务完成！")
                    break
            except Exception as e:
                logging.error(f"运行时错误: {e}")
            finally:
                self._quit_driver()

    def _snatching_loop(self):
        logging.info(f"寻找订单 {self.order_id}...")
        rob_time_str = None
        title_row_xpath = f"//tr[contains(., '货源单号：{self.order_id}')]"

        while not self.stop_event.is_set():
            try:
                title_row = self.wait.until(EC.presence_of_element_located((By.XPATH, title_row_xpath)))
                time_element = title_row.find_element(By.XPATH,
                                                      "./following-sibling::tr[1]//span[preceding-sibling::em[text()='抢单开始时间：']]")
                rob_time_str = time_element.text
                if rob_time_str: break
            except Exception:
                logging.warning(f"未找到订单，3秒后刷新...")
                self.stop_event.wait(3)
                if self.stop_event.is_set(): return False
                self.driver.refresh()

        rob_time = datetime.strptime(rob_time_str, "%Y-%m-%d %H:%M:%S")
        logging.info(f"🎯 抢单时间: {rob_time_str}")

        rob_link_xpath = f"//tr[contains(., '货源单号：{self.order_id}')]/following-sibling::tr[1]//a[text()='抢单']"
        short_wait = WebDriverWait(self.driver, 1.0)  # 缩短等待时间

        while not self.stop_event.is_set():
            # [优化4] 使用服务器校准时间
            server_now = self._get_server_time()
            wait_seconds = (rob_time - server_now).total_seconds()

            if wait_seconds > self.refresh_advance_time:
                # [优化3] 缩短刷新间隔为 1 秒
                if int(wait_seconds) % 5 == 0:  # 每5秒打印一次日志，避免刷屏
                    logging.info(f"服务器时间: {server_now.strftime('%H:%M:%S')} | 倒计时: {wait_seconds:.0f} 秒")
                self.stop_event.wait(1)
                continue

            logging.info(f"⚡ 倒计时 {wait_seconds:.1f} 秒，高频刷新中...")
            self.driver.refresh()

            try:
                # 检查页面是否崩溃
                WebDriverWait(self.driver, 2).until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '查询')]")))
            except:
                logging.error("页面加载异常，重启...")
                return False

            try:
                rob_link = short_wait.until(EC.element_to_be_clickable((By.XPATH, rob_link_xpath)))
                logging.info("🔥🔥🔥 发现按钮！")

                # [优化1] 循环点击直到弹窗出现
                if self._click_until_popup(rob_link):
                    self.handle_robbery_steps()
                    return True
                else:
                    logging.error("多次点击未弹出窗口，继续刷新...")
                    continue

            except TimeoutException:
                if wait_seconds <= -3:
                    logging.error("超时未出现按钮，停止。")
                    return True
                continue
        return False

    def _click_until_popup(self, rob_link):
        """[优化1] 尝试点击按钮，直到确认框弹出"""
        for i in range(3):  # 最多尝试3次
            try:
                rob_link.click()
                # 检测确认框的“信息”按钮是否出现
                WebDriverWait(self.driver, 0.5).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[@class='layui-layer-btn0']"))
                )
                logging.info("✅ 抢单弹窗已打开！")
                return True
            except (TimeoutException, StaleElementReferenceException):
                logging.warning(f"第 {i + 1} 次点击未触发弹窗，立即重试...")
                # 如果元素过期，重新获取一下（虽然在短时间内不太可能，但为了健壮性）
                try:
                    rob_link = self.driver.find_element(By.XPATH,
                                                        f"//tr[contains(., '货源单号：{self.order_id}')]/following-sibling::tr[1]//a[text()='抢单']")
                except:
                    pass
        return False

    def handle_robbery_steps(self):
        # 1. 点击“信息”确认框
        self.wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@class='layui-layer-btn0']"))).click()

        # 2. 切换 iframe 填写入参
        self.wait.until(EC.frame_to_be_available_and_switch_to_it(
            (By.XPATH, "//div[contains(@class, 'layui-layer-iframe')]//iframe")))

        w_cell = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//td[@data-field='grabWeight']")))
        w_cell.click()
        w_cell.find_element(By.XPATH, ".//input").send_keys(str(self.weight))

        q_cell = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//td[@data-field='grabQuantity']")))
        q_cell.click()
        q_cell.find_element(By.XPATH, ".//input").send_keys(str(self.quantity))

        self.driver.switch_to.default_content()

        # 3. 点击“确定抢单”
        confirm_btn = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//a[@class='layui-layer-btn0' and text()='确定抢单']")))
        confirm_btn.click()
        logging.info("已提交抢单申请，准备验证码...")

        # [优化2] 验证码重试循环 (最多8次)
        max_captcha_retries = 8
        for i in range(max_captcha_retries):
            logging.info(f"🔄 验证码识别尝试: {i + 1}/{max_captcha_retries}")

            # 等待验证码加载 (如果是重试，可能需要多等一点时间让图片刷新)
            time.sleep(self.screenshot_delay if i == 0 else 1.0)

            try:
                # 截图
                x1, y1 = self.captcha_coords['top_left']
                x2, y2 = self.captcha_coords['bottom_right']
                screenshot = pyautogui.screenshot(region=(x1, y1, x2 - x1, y2 - y1))
                img_byte_arr = io.BytesIO()
                screenshot.save(img_byte_arr, format='PNG')

                # 识别
                coords = self._solve_captcha(img_byte_arr.getvalue())
                if not coords:
                    logging.warning("识别失败，重试...")
                    continue

                # 点击坐标
                for point in coords:
                    pyautogui.click(x1 + point['x'], y1 + point['y'])

                # 点击确认
                cx, cy = self.captcha_coords['confirm_button']
                pyautogui.click(cx, cy)
                logging.info("已点击验证码确认。")

                # 检测结果：如果验证码窗口消失，或者出现成功提示，则认为成功
                # 这里简单判断：等待2秒，如果还能找到“确定抢单”按钮或者验证码层，说明失败了
                time.sleep(2)

                # 检查是否还有验证码相关的元素存在，或者是否有错误提示
                # 注意：这里逻辑取决于失败时网页的具体表现。
                # 假设：如果成功，页面会跳转或弹窗消失。如果失败，弹窗还在。
                try:
                    # 尝试找回“确定抢单”按钮，如果还能找到且可见，说明还在原界面
                    btn = self.driver.find_element(By.XPATH, "//a[@class='layui-layer-btn0' and text()='确定抢单']")
                    if btn.is_displayed():
                        logging.warning("⚠️ 验证码窗口未关闭，可能验证失败或频繁，准备重试...")
                        # 尝试点击一下刷新验证码（如果有刷新按钮的话），或者直接下一轮截图
                        continue
                except:
                    # 找不到按钮了，说明窗口关闭了，大概率成功
                    logging.info("✅ 验证码窗口已关闭，抢单可能成功！")
                    break

            except Exception as e:
                logging.error(f"验证过程异常: {e}")
                continue

        logging.info("⏳ 等待结算页面 (20秒)...")
        time.sleep(20)


# ==================================================================
# 3. GUI 界面逻辑
# ==================================================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("潍钢抢单助手 V7.6 (优化增强版)")
        self.root.geometry("650x780")  # 稍微加高一点
        self.snatcher_thread = None
        self.stop_event = threading.Event()
        self.picking_coords = False
        self.config_manager = ConfigManager()
        self.create_widgets()
        self.setup_logging()
        self.load_settings()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # [优化4] 启动时间更新定时器
        self.update_server_time_display()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 参数区
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
        self.server_time_var = tk.StringVar(value="服务器时间: --:--:--")

        row = 0
        ttk.Label(params_frame, text="网站账号:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=3)
        ttk.Entry(params_frame, textvariable=self.username).grid(row=row, column=1, columnspan=3, sticky=tk.EW)
        row += 1
        ttk.Label(params_frame, text="网站密码:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=3)
        pw_frame = ttk.Frame(params_frame)
        pw_frame.grid(row=row, column=1, columnspan=3, sticky=tk.EW)
        self.pw_entry = ttk.Entry(pw_frame, textvariable=self.password, show="*")
        self.pw_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(pw_frame, text="👁", width=3, command=self.toggle_password).pack(side=tk.LEFT)
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

        # 坐标工具
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

        # 按钮区
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        self.start_button = ttk.Button(button_frame, text="开始抢单", command=self.start_snatching)
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.stop_button = ttk.Button(button_frame, text="停止任务", command=self.stop_snatching, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # [优化4] 时间显示
        time_label = ttk.Label(main_frame, textvariable=self.server_time_var, font=("Arial", 10), foreground="green")
        time_label.pack(pady=2)

        # 日志区
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def update_server_time_display(self):
        # [优化4] 实时更新界面上的服务器时间
        server_time = datetime.now() + timedelta(seconds=OrderSnatcher.SERVER_OFFSET)
        self.server_time_var.set(f"服务器估算时间 (本地+25s): {server_time.strftime('%H:%M:%S')}")
        self.root.after(1000, self.update_server_time_display)

    def update_mouse_pos(self):
        if self.picking_coords:
            x, y = pyautogui.position()
            self.mouse_pos.set(f"鼠标坐标: ({x}, {y})")
            self.root.after(50, self.update_mouse_pos)

    def start_picking(self):
        self.picking_coords = True
        self.pick_btn.config(state=tk.DISABLED)
        self.stop_pick_btn.config(state=tk.NORMAL)
        self.update_mouse_pos()

    def stop_picking(self):
        self.picking_coords = False
        self.pick_btn.config(state=tk.NORMAL)
        self.stop_pick_btn.config(state=tk.DISABLED)
        self.mouse_pos.set("鼠标坐标: (-, -)")

    def set_top_left(self):
        if self.picking_coords:
            x, y = pyautogui.position()
            self.x1.set(str(x));
            self.y1.set(str(y))
            logging.info(f"左上角: ({x}, {y})")

    def set_bottom_right(self):
        if self.picking_coords:
            x, y = pyautogui.position()
            self.x2.set(str(x));
            self.y2.set(str(y))
            logging.info(f"右下角: ({x}, {y})")

    def set_confirm_btn(self):
        if self.picking_coords:
            x, y = pyautogui.position()
            self.confirm_x.set(str(x));
            self.confirm_y.set(str(y))
            logging.info(f"确认按钮: ({x}, {y})")

    def toggle_password(self):
        if self.pw_entry.cget('show') == '*':
            self.pw_entry.config(show='')
        else:
            self.pw_entry.config(show='*')

    def setup_logging(self):
        text_handler = TextHandler(self.log_text)
        formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S")
        text_handler.setFormatter(formatter)
        logging.getLogger().addHandler(text_handler)
        logging.getLogger().setLevel(logging.INFO)

    def start_snatching(self):
        self.stop_event.clear()
        self.start_button.config(state=tk.DISABLED)
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
            logging.error("参数错误：请检查数字格式！")
            self.stop_snatching()
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
            logging.error(f"线程异常: {e}")
        finally:
            if snatcher: snatcher._quit_driver()

    def stop_snatching(self):
        logging.warning("正在停止...")
        self.stop_event.set()
        self.stop_button.config(state=tk.DISABLED)

    def check_thread(self):
        if self.snatcher_thread and self.snatcher_thread.is_alive():
            self.root.after(100, self.check_thread)
        else:
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            logging.info("任务结束。")

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

        self.text_widget.after(0, append)


def check_trial_period():
    try:
        start_time = datetime.strptime("2025-11-17 12:00:00", "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime("2025-12-01 12:00:00", "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        if not (start_time <= now <= end_time):
            return False, f"试用期已于 {end_time.strftime('%Y-%m-%d %H:%M')} 结束。"
        remaining_time = end_time - now
        return True, f"试用期剩余: {remaining_time.days} 天 {remaining_time.seconds // 3600} 小时"
    except Exception:
        return False, "无法验证试用期。"


if __name__ == "__main__":
    is_valid, message = check_trial_period()
    temp_root = tk.Tk()
    temp_root.withdraw()
    if not is_valid:
        messagebox.showerror("试用结束", message)
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
    root.mainloop()