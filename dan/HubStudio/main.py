import pandas as pd
import time
import requests
import sys
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

# ================= 配置区 =================
EXCEL_PATH = "澳大利亚总表_WhatsApp待深挖清零版.xlsx"
ENV_ID = "1514886159"
API_PORT = "6873"


# =========================================

def start_hub_browser(env_id):
    url = f"http://127.0.0.1:{API_PORT}/api/v1/browser/start?containerCode={env_id}"
    try:
        res = requests.get(url).json()
        if res.get("code") == 0:
            data = res.get("data")
            port = data.get("debuggingPort")
            return f"127.0.0.1:{port}" if port else data.get("debugAddr")
    except:
        pass
    print("❌ 无法启动 HubStudio 环境。")
    sys.exit(1)


def parse_phone(phone_str):
    if pd.isna(phone_str): return None, None
    clean_phone = "".join(filter(str.isdigit, str(phone_str)))
    if clean_phone.startswith("61"):
        return "61", clean_phone[2:]
    return "61", clean_phone


def run_automation():
    debug_addr = start_hub_browser(ENV_ID)
    options = Options()
    options.add_experimental_option("debuggerAddress", debug_addr)

    # 强制匹配 HubStudio 142 版本驱动
    service = Service(ChromeDriverManager(driver_version="142.0.7444.168").install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 10)

    try:
        df = pd.read_excel(EXCEL_PATH)
        print(f"📖 成功读取 Excel，共 {len(df)} 条数据")
    except Exception as e:
        print(f"❌ Excel读取失败: {e}")
        return

    current_date = datetime.now().strftime("%Y/%m/%d")

    for index, row in df.iterrows():
        whatsapp_raw = row.get('whatsapp号1')
        if not whatsapp_raw: continue
        country_code, phone_num = parse_phone(whatsapp_raw)
        print(f"\n🚀 [{index + 1}/{len(df)}] 目标: {whatsapp_raw}")

        try:
            # --- 状态重置：确保没有打开的侧边栏 ---
            try:
                # 寻找并点击侧边栏的“返回”或“关闭”按钮
                back_icons = driver.find_elements(By.XPATH, '//span[@data-icon="back"] | //span[@data-icon="x"]')
                if back_icons:
                    back_icons[0].click()
                    time.sleep(1)
            except:
                pass

            # 1. 点击加号 (New Chat)
            wait.until(EC.element_to_be_clickable((By.XPATH, '//span[@data-icon="new-chat-outline"]'))).click()

            # 2. 点击“添加联系人”
            add_xpath = '//span[contains(text(), "添加联系人")] | //span[contains(text(), "Add contact")]'
            wait.until(EC.element_to_be_clickable((By.XPATH, add_xpath))).click()

            # 3. 填写姓名和姓氏
            wait.until(EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true"]')))
            name_inputs = driver.find_elements(By.XPATH, '//div[@contenteditable="true"]')
            if len(name_inputs) >= 2:
                name_inputs[0].send_keys("澳大利亚")
                name_inputs[1].send_keys(current_date)

            # 4. 选择国家：澳大利亚
            cc_button_xpath = '//div[text()="国家/地区" or text()="Country/region"]/..//div[@role="button"]'
            cc_button = wait.until(EC.element_to_be_clickable((By.XPATH, cc_button_xpath)))
            cc_button.click()
            time.sleep(1)

            search_input = wait.until(
                EC.presence_of_element_located((By.XPATH, '//div[@role="textbox" and @contenteditable="true"]')))
            search_input.send_keys("61")
            time.sleep(1.5)

            aus_item_xpath = '//button[contains(@aria-label, "澳大利亚") or contains(@aria-label, "Australia")]'
            aus_item = wait.until(EC.element_to_be_clickable((By.XPATH, aus_item_xpath)))
            aus_item.click()
            print("✅ 已选中澳大利亚")

            # 5. 填写电话号码
            # 先清空再输入
            phone_xpath = '//input[@aria-label="电话号码" or @aria-label="Phone number"]'
            phone_field = wait.until(EC.presence_of_element_located((By.XPATH, phone_xpath)))
            phone_field.send_keys(Keys.COMMAND + "a")
            phone_field.send_keys(Keys.BACKSPACE)
            phone_field.send_keys(phone_num)

            # 6. 等待检测与保存
            print("正在检测号码有效性并保存...")
            time.sleep(5)  # 稍微多等一秒，确保勾号变色

            page_src = driver.page_source
            # 检查跳过逻辑
            if any(x in page_src for x in
                   ["已经在通讯录中", "Already in contacts", "此电话号码未注册", "not on WhatsApp"]):
                print(f"⚠️ 跳过结果: 号码状态不符或已存在")
                driver.find_element(By.XPATH, '//span[@data-icon="back"]').click()
            else:
                try:
                    # 【核心修正】：基于你提供的 HTML 源码定位保存按钮
                    # 定位 aria-label 为 "保存联系人" 的 div 按钮
                    submit_xpath = '//div[@role="button" and (@aria-label="保存联系人" or @aria-label="Save contact")]'
                    submit_btn = wait.until(EC.element_to_be_clickable((By.XPATH, submit_xpath)))
                    submit_btn.click()
                    print(f"✨ 成功添加并保存！")
                    time.sleep(2)
                except Exception as e:
                    print(f"❗ 无法点击保存按钮，可能检测未通过")
                    # 尝试点击返回
                    try:
                        driver.find_element(By.XPATH, '//span[@data-icon="back"]').click()
                    except:
                        pass

        except Exception as e:
            print(f"❗ 本条失败: {str(e)[:100]}")
            # 发生严重错误时重置页面
            driver.get("https://web.whatsapp.com")
            time.sleep(5)


if __name__ == "__main__":
    run_automation()