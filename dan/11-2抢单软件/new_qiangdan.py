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
    print(f"--- [严重错误] 请在您的环境中运行: pip install selenium requests ---")
    sys.exit(1)

# --- 配置日志输出 ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logging.info("[诊断] 日志系统配置完成")


class OrderSnatcher:
    BASE_URL = "http://222.132.55.178:8190"

    # --- 【已更新】使用 jfbym.com 的高速定制 API 配置 ---
    JFYBM_API_URL = "http://api.jfbym.com/api/YmServer/customApi"
    JFYBM_TOKEN = "Sq83S53mcjz1AkA54_SXfYvrXxiTNVnya8bfIKe-ITE"  # 【重要】请务必填写
    JFYBM_CAPTCHA_TYPE = "30340"  # 使用定制模型接口

    def __init__(self, order_data, login_info):
        self.order_id = order_data["order_id"]
        self.rob_time_str = order_data["rob_time"]
        self.weight = order_data["weight"]
        self.quantity = order_data["quantity"]

        self.username = login_info["username"]
        self.password = login_info["password"]
        self.driver = None

        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            chromedriver_path = os.path.join(current_dir, "chromedriver")
            service = ChromeService(executable_path=chromedriver_path)
            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_argument("--log-level=3")
            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait = WebDriverWait(self.driver, 20)
            logging.info("[诊断] WebDriver 初始化成功")
        except Exception as e:
            logging.error(f"❌ [严重错误] 在初始化WebDriver时发生致命错误: {e}")
            sys.exit(1)

    def login(self):
        """使用 Selenium 登录网站"""
        logging.info("正在打开登录页面...")
        self.driver.get(f"{self.BASE_URL}/system/login")
        try:
            self.wait.until(EC.presence_of_element_located(
                (By.XPATH, '//input[@placeholder="请输入您的用户名或手机号码"]'))).send_keys(self.username)
            self.driver.find_element(By.XPATH, '//input[@placeholder="输入您的密码"]').send_keys(self.password)
            self.driver.find_element(By.XPATH, '//button[contains(text(),"登")]').click()
            self.wait.until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "新货源单管理")))
            logging.info("✅ 登录成功！")
            return True
        except Exception as e:
            logging.error(f"登录失败: {e}")
            self.driver.save_screenshot("login_error.png")
            return False

    def navigate_to_order_page(self):
        """导航到社会提单页面"""
        try:
            target_url = f"{self.BASE_URL}/newgoods/listSocietyPage"
            logging.info(f"正在通过URL直接导航到: {target_url}")
            self.driver.get(target_url)
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '查询')]")))
            logging.info("✅ 已成功进入'新货源单(社会提单)'页面。")
            return True
        except Exception as e:
            logging.error(f"导航到订单页面失败: {e}")
            self.driver.save_screenshot("navigation_error.png")
            return False

    def _solve_captcha(self, image_bytes):
        """【已更新】使用 jfbym.com 的高速定制 API 解决点选验证码"""
        logging.info("开始请求 jfbym.com 【定制 API - 30340】服务...")
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        payload = {
            'image': base64_image,
            'token': self.JFYBM_TOKEN,
            'type': self.JFYBM_CAPTCHA_TYPE
        }

        start_time = time.time()
        try:
            response = requests.post(self.JFYBM_API_URL, data=payload, timeout=15)
            response.raise_for_status()
            duration = time.time() - start_time
            logging.info(f"⏱️ API 响应耗时: {duration:.3f} 秒")

            result = response.json()
            if result.get('code') != 10000:
                logging.error(f"API 请求失败: {result.get('msg')}")
                return None

            recognition_data = result.get('data', {})
            if recognition_data.get('code') != 0:
                logging.error(f"打码服务出错: {recognition_data.get('data')}")
                return None

            coordinates_str = recognition_data.get('data')
            logging.info(f"✅ 识别成功! 原始坐标字符串: '{coordinates_str}'")

            parsed_coordinates = []
            for part in coordinates_str.split('|'):
                x, y = part.split(',')
                parsed_coordinates.append({'x': int(x), 'y': int(y)})
            return parsed_coordinates
        except Exception as e:
            logging.error(f"请求 jfbym API 时发生异常: {e}")
            return None

    def run(self):
        """主运行函数，包含定时和抢单逻辑"""
        if self.JFYBM_TOKEN == "在此处粘贴您的jfbym.com用户中心Token":
            logging.error("致命错误：请在代码中填入您在 jfbym.com 的 Token！")
            return

        try:
            if not self.login() or not self.navigate_to_order_page():
                return

            rob_time = datetime.strptime(self.rob_time_str, "%Y-%m-%d %H:%M:%S")
            logging.info(f"🎯 目标订单: {self.order_id}, 设定抢单时间: {self.rob_time_str}")

            while True:
                now = datetime.now()
                wait_seconds = (rob_time - now).total_seconds()
                if wait_seconds <= 0.1:  # 稍微提前一点以应对延迟
                    logging.info("抢单时间已到，开始执行！")
                    break
                if wait_seconds > 2:
                    logging.info(f"距离抢单还有 {wait_seconds:.2f} 秒，等待中...")
                    time.sleep(2)
                else:
                    time.sleep(0.05)  # 最后2秒高频检查

            self.handle_robbery()
        finally:
            if self.driver:
                logging.info("流程结束，将在15秒后自动关闭浏览器。")
                time.sleep(15)
                self.driver.quit()

    def handle_robbery(self):
        """处理抢单的完整流程"""
        try:
            target_source_id = self.order_id
            logging.info(f"正在页面上寻找【货源单号】为 {target_source_id} 的'抢单'链接...")
            rob_link_xpath = f"//tr[contains(., '货源单号：{target_source_id}')]/following-sibling::tr[1]//a[text()='抢单']"

            rob_link = self.wait.until(EC.element_to_be_clickable((By.XPATH, rob_link_xpath)))
            rob_link.click()
            logging.info("✅ 已点击抢单链接！")

            # 步骤1: 处理信息确认框
            logging.info("等待'信息'确认框出现...")
            info_confirm_button_xpath = "//a[@class='layui-layer-btn0']"
            info_confirm_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, info_confirm_button_xpath)))
            info_confirm_button.click()
            logging.info("已点击'信息'确认框。")

            # 步骤2: 在 iframe 内输入重量和件数
            logging.info("等待'货物明细'弹窗内的 iframe 出现...")
            iframe_xpath = "//div[@class='layui-layer-content']/iframe"
            self.wait.until(EC.frame_to_be_available_and_switch_to_it((By.XPATH, iframe_xpath)))
            logging.info("✅ 已成功切换到 iframe 内部。")

            weight_input_cell = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//td[@data-field='grabWeight']")))
            weight_input_cell.click()
            weight_input_cell.find_element(By.XPATH, ".//input[contains(@class, 'layui-table-edit')]").send_keys(
                str(self.weight))
            logging.info(f"已输入抢单重量: {self.weight}")

            quantity_input_cell = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//td[@data-field='grabQuantity']")))
            quantity_input_cell.click()
            quantity_input_cell.find_element(By.XPATH, ".//input[contains(@class, 'layui-table-edit')]").send_keys(
                str(self.quantity))
            logging.info(f"已输入抢单件数: {self.quantity}")

            self.driver.switch_to.default_content()
            logging.info("已从 iframe 切换回主页面。")

            confirm_rob_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[@class='layui-layer-btn0' and text()='确定抢单']")))
            confirm_rob_button.click()
            logging.info("已点击'确定抢单'按钮。")

            # 步骤3: 高速处理最终的图片验证码
            logging.info("等待最终的图片验证码弹窗...")
            captcha_dialog = self.wait.until(
                EC.visibility_of_element_located((By.XPATH, "//*[div[contains(text(), '安全验证')]]")))

            captcha_image_element = captcha_dialog.find_element(By.XPATH,
                                                                ".//div[contains(@class, 'verify-img-panel')]")

            image_bytes = captcha_image_element.screenshot_as_png

            # 调用新的高速识别接口
            coordinates = self._solve_captcha(image_bytes)

            if not coordinates:
                logging.error("验证码识别失败，抢单流程中止。")
                return

            actions = ActionChains(self.driver)
            for point in coordinates:
                actions.move_to_element_with_offset(captcha_image_element, int(point['x']), int(point['y'])).click()
            actions.perform()
            logging.info("所有坐标已点击完毕。")

            final_confirm_button = captcha_dialog.find_element(By.XPATH, ".//button[contains(text(), '确定')]")
            final_confirm_button.click()
            logging.info("✅ 已点击最终确认按钮，抢单请求已发送！")

            logging.info("等待5秒查看抢单结果...")
            time.sleep(5)

        except Exception as e:
            logging.error(f"抢单过程中出现严重错误: {e}")
            self.driver.save_screenshot("robbery_error.png")


if __name__ == "__main__":
    print("--- [诊断] 进入 __main__ 执行块 ---")

    # ==================================================================
    # --- 请在这里填写您的配置信息 ---
    # ==================================================================
    order_config = {
        "order_id": "HYD000000024825284",
        "rob_time": "2025-11-17 09:24:00",
        "weight": 1,
        "quantity": 0
    }

    login_credentials = {
        "username": "QD0029",
        "password": "gcjt56788"
    }
    # ==================================================================

    print("--- [诊断] 配置信息加载完毕 ---")

    try:
        snatcher = OrderSnatcher(order_config, login_credentials)
        snatcher.run()

    except Exception as e:
        print(f"--- [严重错误] 在主程序块中捕获到未处理的异常: {e} ---")