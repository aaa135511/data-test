# ==================================================================
# --- 诊断日志: 检查脚本是否开始执行 ---
print("--- [诊断] 脚本文件已开始执行 ---")
# ==================================================================

import os
import base64
import json
import logging
import time
import sys
from datetime import datetime

# ==================================================================
print("--- [诊断] Python标准库导入完成 ---")
# ==================================================================

try:
    import requests
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.chrome.service import Service as ChromeService

    print("--- [诊断] 第三方库 (requests, selenium) 导入成功 ---")
except ImportError as e:
    print(f"--- [严重错误] 缺少必要的库: {e} ---")
    print("--- [严重错误] 请在您的环境中运行: pip install selenium requests ---")
    sys.exit(1)  # 缺少库则直接退出

# --- 配置日志输出 ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logging.info("[诊断] 日志系统配置完成")


class OrderSnatcher:
    BASE_URL = "http://222.132.55.178:8190"
    CAPTCHA_API_KEY = "458052ad6cbd988616664b8e13a67c0b"

    def __init__(self, order_data, login_info):
        logging.info("[诊断] OrderSnatcher类的 __init__ 方法开始执行")
        self.order_id = order_data["order_id"]
        self.weight = order_data["weight"]
        self.sleep = order_data["sleep"]

        self.username = login_info["username"]
        self.password = login_info["password"]
        self.driver = None  # 先初始化为 None

        try:
            logging.info("[诊断] 准备初始化 Selenium WebDriver...")

            current_dir = os.path.dirname(os.path.abspath(__file__))
            chromedriver_path = os.path.join(current_dir, "chromedriver")
            logging.info(f"--- [诊断] 动态获取到的 chromedriver 路径为: {chromedriver_path} ---")

            service = ChromeService(executable_path=chromedriver_path)
            logging.info(f"[诊断] ChromeService 对象创建成功, 将使用驱动: {service.path}")

            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_argument("--log-level=3")

            logging.info("[诊断] 即将执行关键步骤: webdriver.Chrome(...)")
            self.driver = webdriver.Chrome(service=service, options=options)

            logging.info("✅ [诊断] WebDriver 实例创建成功！浏览器应该已经启动。")

            self.wait = WebDriverWait(self.driver, 20)
            logging.info("[诊断] WebDriverWait 初始化成功")

        except Exception as e:
            logging.error("❌ [严重错误] 在初始化WebDriver时发生致命错误!")
            logging.error(f"错误类型: {type(e).__name__}")
            logging.error(f"错误详情: {e}")
            sys.exit(1)

        logging.info("[诊断] OrderSnatcher类的 __init__ 方法执行完毕")

    def login(self):
        """使用 Selenium 登录网站"""
        logging.info("正在打开登录页面...")
        self.driver.get(f"{self.BASE_URL}/system/login")
        try:
            user_input = self.wait.until(
                EC.presence_of_element_located((By.XPATH, '//input[@placeholder="请输入您的用户名或手机号码"]')))
            user_input.send_keys(self.username)
            logging.info(f"已输入用户名: {self.username}")

            pass_input = self.driver.find_element(By.XPATH, '//input[@placeholder="输入您的密码"]')
            pass_input.send_keys(self.password)
            logging.info("已输入密码")

            login_button = self.driver.find_element(By.XPATH, '//button[contains(text(),"登")]')
            login_button.click()

            self.wait.until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "新货源单管理")))
            logging.info("✅ 登录成功！")
            return True
        except TimeoutException:
            logging.error("登录超时或登录后页面跳转失败。请检查您的账号密码或网络连接。")
            self.driver.save_screenshot("login_error.png")
            return False
        except Exception as e:
            logging.error(f"登录时发生未预料的错误: {e}")
            return False

    def navigate_to_order_page(self):
        """导航到抢单采购页面"""
        try:
            # --- 【核心修改】放弃模拟点击，直接通过URL跳转 ---
            target_url = f"{self.BASE_URL}/newgoods/listPurchasePage"
            logging.info(f"正在通过URL直接导航到: {target_url}")

            self.driver.get(target_url)

            # 等待页面加载完成的标志，例如“查询”按钮出现
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '查询')]")))
            logging.info("✅ 已成功进入'新货源单(抢单采购)'页面。")
            return True

        except Exception as e:
            logging.error(f"通过URL直接导航到订单页面失败: {e}")
            self.driver.save_screenshot("navigation_error.png")
            return False

    def _solve_coordinates_captcha(self, image_bytes, instructions):
        """使用 2Captcha 的 CoordinatesTask 解决点选验证码"""
        logging.info(f"开始请求 2Captcha 服务解决点选验证码, 指令: '{instructions}'")
        task_payload = {
            "clientKey": self.CAPTCHA_API_KEY,
            "task": {
                "type": "CoordinatesTask",
                "body": base64.b64encode(image_bytes).decode('utf-8'),
                "comment": instructions
            }
        }
        try:
            create_response = requests.post("https://api.2captcha.com/createTask", json=task_payload, timeout=20)
            create_result = create_response.json()
            if create_result.get("errorId") != 0:
                logging.error(f"2Captcha 创建任务失败: {create_result.get('errorDescription')}")
                return None
            task_id = create_result["taskId"]
            logging.info(f"2Captcha 任务创建成功, Task ID: {task_id}. 等待识别结果...")
            result_payload = {"clientKey": self.CAPTCHA_API_KEY, "taskId": task_id}
            for _ in range(60):
                time.sleep(2)
                result_response = requests.post("https://api.2captcha.com/getTaskResult", json=result_payload,
                                                timeout=20)
                result = result_response.json()
                if result.get("status") == "ready":
                    coordinates = result["solution"]["coordinates"]
                    logging.info(f"✅ 验证码识别成功! 获得坐标: {coordinates}")
                    return coordinates
                elif result.get("status") != "processing":
                    logging.error(f"2Captcha 任务处理失败: {result}")
                    return None
            logging.warning("等待 2Captcha 结果超时。")
            return None
        except Exception as e:
            logging.error(f"请求 2Captcha 服务时发生异常: {e}")
            return None

    def handle_robbery(self):
        """处理抢单，包括切换iframe、输入重量和最终的验证码"""
        try:
            target_order_id = self.order_id
            logging.info(f"正在页面上寻找【订单号】为 {target_order_id} 的'抢单'链接...")

            rob_link_xpath = f"//tr[contains(., '订单号：{target_order_id}')]/following-sibling::tr[1]//a[text()='抢单']"

            while True:
                try:
                    rob_link = self.wait.until(EC.element_to_be_clickable((By.XPATH, rob_link_xpath)))
                    logging.info("✅ 找到目标订单的抢单链接！")
                    rob_link.click()
                    break
                except TimeoutException:
                    logging.info("未找到抢单链接，1秒后刷新页面重试...")
                    self.driver.refresh()
                    time.sleep(1)

            logging.info("已点击抢单链接，判断弹出的窗口类型...")

            # 步骤1: 处理可能出现的信息提示框
            try:
                info_popup_wait = WebDriverWait(self.driver, 5)
                confirm_button_xpath = "//a[@class='layui-layer-btn0']"
                confirm_button = info_popup_wait.until(EC.element_to_be_clickable((By.XPATH, confirm_button_xpath)))
                logging.info("检测到'信息'提示框，点击'确定'按钮继续...")
                confirm_button.click()
            except TimeoutException:
                logging.info("未检测到'信息'提示框，直接进入下一步。")

            # 步骤2: 处理货物明细弹窗，【切换到 iframe】 并输入抢单重量
            logging.info("等待'货物明细'弹窗内的 iframe 出现...")

            # --- 【核心修改】等待并切换到 iframe ---
            # 首先等待 iframe 元素本身加载出来
            iframe_xpath = "//div[@class='layui-layer-content']/iframe"
            self.wait.until(EC.frame_to_be_available_and_switch_to_it((By.XPATH, iframe_xpath)))
            logging.info("✅ 已成功切换到货物明细 iframe 内部。")

            # --- 现在我们已经在 iframe 内部，可以正常定位元素了 ---
            logging.info("在 iframe 内部寻找'抢单重量'单元格...")
            weight_input_cell_xpath = "//td[@data-field='grabWeight']"
            weight_input_cell = self.wait.until(EC.element_to_be_clickable((By.XPATH, weight_input_cell_xpath)))

            weight_input_cell.click()
            logging.info("已点击'抢单重量'单元格，使其进入编辑状态。")

            weight_input_box_xpath = ".//input[contains(@class, 'layui-table-edit')]"
            weight_input_box = weight_input_cell.find_element(By.XPATH, weight_input_box_xpath)

            rob_weight = str(self.weight)
            weight_input_box.send_keys(rob_weight)
            logging.info(f"已在'抢单重量'栏输入: {rob_weight}")

            # --- 操作完成后，必须切换回主页面，才能点击 iframe 外的按钮 ---
            self.driver.switch_to.default_content()
            logging.info("已从 iframe 切换回主页面。")

            # 点击弹窗底部的“确定抢单”按钮 (这个按钮在主页面里)
            confirm_rob_button_xpath = "//a[@class='layui-layer-btn0' and text()='确定抢单']"
            confirm_rob_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, confirm_rob_button_xpath)))
            confirm_rob_button.click()
            logging.info("已点击'确定抢单'按钮。")

            # 步骤3: 等待并处理最终的图片验证码
            logging.info("等待最终的图片验证码弹窗...")
            captcha_dialog = self.wait.until(
                EC.visibility_of_element_located((By.XPATH, "//*[div[contains(text(), '安全验证')]]")))

            captcha_image_element = captcha_dialog.find_element(By.XPATH,
                                                                ".//div[contains(@class, 'verify-img-panel')]")
            instructions_element = captcha_dialog.find_element(By.XPATH, ".//div[contains(@class, 'verify-msg')]")
            instructions_text = instructions_element.text

            image_bytes = captcha_image_element.screenshot_as_png
            coordinates = self._solve_coordinates_captcha(image_bytes, instructions_text)

            if not coordinates:
                logging.error("无法从 2Captcha 获取坐标，抢单流程中止。")
                return

            actions = ActionChains(self.driver)
            for point in coordinates:
                x = int(point['x'])
                y = int(point['y'])
                logging.info(f"正在点击坐标: (x={x}, y={y})")
                actions.move_to_element_with_offset(captcha_image_element, x, y).click()

            actions.perform()
            logging.info("所有坐标已点击完毕。")

            confirm_button = captcha_dialog.find_element(By.XPATH, ".//button[span[text()='确定']]")
            confirm_button.click()
            logging.info("✅ 已点击最终确认按钮，抢单请求已发送！")

            logging.info("等待5秒查看抢单结果...")
            time.sleep(5)

        except Exception as e:
            logging.error(f"抢单过程中出现严重错误: {e}")
            self.driver.save_screenshot("robbery_error.png")


    def run(self):
        """主运行函数"""
        logging.info("[诊断] OrderSnatcher类的 run 方法开始执行")
        try:
            if not self.login():
                return
            if not self.navigate_to_order_page():
                return
            logging.info("程序准备就绪，即将开始抢单流程。")
            self.handle_robbery()
        finally:
            if self.driver:
                logging.info("流程结束，将在10秒后自动关闭浏览器。")
                time.sleep(10)
                self.driver.quit()
            else:
                logging.warning("[诊断] Driver实例不存在，无需关闭。")


if __name__ == "__main__":
    print("--- [诊断] 进入 __main__ 执行块 ---")

    # ==================================================================
    # --- 请在这里填写您的配置信息 ---
    # ==================================================================
    order_config = {
        "order_id": "CD25092500722",  # 【必填】请换成您要抢的真实订单号
        "weight": 100,
        "sleep": 0.5
    }

    # 使用您提供的最新账号信息
    login_credentials = {
        "username": "QD0029",  # 【必填】您的登录名
        "password": "gcjt56788"  # 【必填】您的密码
    }
    # ==================================================================

    print("--- [诊断] 配置信息加载完毕 ---")

    try:
        print("--- [诊断] 即将创建 OrderSnatcher 实例 ---")
        snatcher = OrderSnatcher(order_config, login_credentials)
        print("--- [诊断] OrderSnatcher 实例创建成功 ---")

        print("--- [诊断] 即将调用 run 方法 ---")
        snatcher.run()
        print("--- [诊断] run 方法执行完毕 ---")

    except Exception as e:
        print(f"--- [严重错误] 在主程序块中捕获到未处理的异常: {e} ---")