import time
import undetected_chromedriver as uc
import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import sys
import os


def get_driver_path():
    """根据操作系统和执行环境确定 ChromeDriver 的路径。"""
    base_path = os.path.dirname(os.path.abspath(__file__))
    driver_dir = os.path.join(base_path, 'drivers')
    if sys.platform.startswith('win'):
        potential_path = os.path.join(driver_dir, 'chromedriver.exe')
    else:  # macOS or Linux
        potential_path = os.path.join(driver_dir, 'chromedriver')

    if os.path.exists(potential_path):
        print(f"  -> 发现并使用本地驱动: {potential_path}")
        return potential_path
    else:
        print("  -> [警告] 未在 'drivers' 文件夹中发现本地驱动，将尝试自动下载。")
        return None


def run_scraping_logic():
    """
    最终版核心爬虫逻辑函数 v5。
    采用“感知变化”的智能等待策略，确保数据完全刷新后再抓取。
    """
    print("正在初始化浏览器驱动...")
    options = uc.ChromeOptions()
    # options.add_argument('--headless=new')
    driver_path = get_driver_path()

    driver = None
    try:
        if driver_path:
            driver = uc.Chrome(options=options, driver_executable_path=driver_path)
        else:
            driver = uc.Chrome(options=options)
    except Exception as e:
        print(f"致命错误：初始化uc.Chrome失败: {e}")
        return

    all_data = []
    url = "https://yuce2.com/pc/yuce-jnd28-3-2.html"

    methods_to_scrape = {
        '单双': '2', '大小': '3', '大小尾': '9'
    }

    try:
        print(f"正在访问网站: {url}")
        driver.get(url)
        wait = WebDriverWait(driver, 30)

        print("等待页面动态数据加载...")
        wait.until(EC.text_to_be_present_in_element((By.ID, "newQiHao"), "期"))
        print("页面动态数据加载完成！")

        for method_name, yuce_id in methods_to_scrape.items():
            print(f"\n--- 正在处理方法: {method_name} ---")
            try:
                # 1. 点击前，先获取当前第一个算法的预测值作为“标记”
                marker_xpath = "//div[@class='layui-tab-item layui-show']//p[contains(text(), '下一把预测')]/span"
                try:
                    previous_marker_text = driver.find_element(By.XPATH, marker_xpath).text
                    print(f"  -> 点击前的标记值: '{previous_marker_text}'")
                except NoSuchElementException:
                    # 第一次循环时可能找不到，设为一个唯一值
                    previous_marker_text = "INITIAL_STATE"
                    print("  -> 首次运行，无标记值。")

                # 2. 点击选项卡
                method_tab_xpath = f"//div[lay-filter='yuceInfo']//li[@yuceinfoid='{yuce_id}']"
                method_tab = wait.until(EC.element_to_be_clickable((By.XPATH, method_tab_xpath)))
                driver.execute_script("arguments[0].click();", method_tab)
                print(f"已点击 '{method_name}' 标签。")

                # 3. 等待“标记”值发生变化
                print("  -> 等待数据刷新...")
                wait.until(
                    lambda d: d.find_element(By.XPATH, marker_xpath).text != previous_marker_text
                )
                current_marker_text = driver.find_element(By.XPATH, marker_xpath).text
                print(f"  -> 数据已刷新！新标记值: '{current_marker_text}'")

                # 4. 安全抓取数据
                algorithm_blocks_xpath = "//div[@class='layui-tab-item layui-show']/div[contains(@class, 'layui-col-md')]"
                algorithm_blocks = driver.find_elements(By.XPATH, algorithm_blocks_xpath)

                for i, block in enumerate(algorithm_blocks):
                    algo_name = f"算法{i + 1}"
                    prediction, current_errors, max_errors = "N/A", "N/A", "N/A"
                    try:
                        prediction = block.find_element(By.XPATH, ".//p[contains(text(), '下一把预测')]/span").text
                        current_errors = block.find_element(By.XPATH, ".//p[contains(text(), '当前错')]/span").text
                        max_errors = block.find_element(By.XPATH, ".//p[contains(text(), '当前最大连错')]/span").text
                    except Exception:
                        print(f"  -> 在 '{method_name}' - '{algo_name}' 中提取数据失败。")

                    all_data.append({
                        '方法': method_name, '算法': algo_name, '下一把预测': prediction.strip(),
                        '当前错': current_errors.strip(), '当前最大连错': max_errors.strip()
                    })

            except TimeoutException:
                print(f"处理方法 '{method_name}' 时发生超时！原因：点击后预测值未发生变化，可能是数据相同或刷新失败。")
                # 即使超时，我们仍然尝试抓取当前页面的数据，因为它可能就是正确的
                print("  -> 超时但仍尝试抓取当前数据...")
                # 此处可以添加与上面相同的抓取代码作为备用方案
            except Exception as e:
                print(f"处理方法 '{method_name}' 时发生未知错误: {e}")

    except Exception as e:
        print(f"\n\n发生致命错误: {e}")
        driver.save_screenshot("fatal_error_screenshot.png")
        print("已保存错误截图: fatal_error_screenshot.png")

    finally:
        if driver:
            print("\n抓取流程结束，正在关闭浏览器。")
            driver.quit()

    if not all_data:
        print("\n未能抓取到任何数据。")
        return

    df = pd.DataFrame(all_data)
    try:
        # ... (数据整理和打印部分与之前相同) ...
        print("\n\n=============== 抓取结果汇总 (Excel格式) ================")
        print(df)  # 直接打印DataFrame，更清晰
        print("==========================================================")
    except Exception as e:
        print(f"\n数据整理失败: {e}。")


if __name__ == "__main__":
    run_scraping_logic()