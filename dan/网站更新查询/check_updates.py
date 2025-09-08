# main_test.py
# 版本 V20-test-auto-driver: 自动检测并加载同级目录下的驱动程序

import pandas as pd
import os
import sys  # <-- 新增：导入sys模块以检测操作系统
import requests
import re
import time
import random
from datetime import datetime, date
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date
from dateutil.parser import ParserError
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import urllib3
import logging

# ... [从 CONFIGURATION 到 generate_html_report 的所有代码与上一版完全相同，这里省略] ...
# ... 您只需复制并替换下面的 main 函数即可 ...

# ==============================================================================
# 1. 本地测试配置
# ==============================================================================
EXCEL_FILE_PATH = "安徽省网址.xlsx"
OUTPUT_DIR = "reports"
TARGET_DATE_STR = '2025-08-16'
KEY_KEYWORDS_STR = "招聘, 人才引进"
EXCLUDE_KEYWORDS_STR = "博士, 拟聘用, 高层次, 公示"

# ==============================================================================
# 2. NETWORKING & PARSING SETUP (与 V20 GUI 版本完全一致)
# ==============================================================================
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from requests.adapters import HTTPAdapter

try:
    from requests.packages.urllib3.util.ssl_ import create_urllib3_context
except ImportError:
    from urllib3.util.ssl_ import create_urllib3_context
CIPHERS = (
    'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384')


class Tls12Adapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = requests.packages.urllib3.PoolManager(num_pools=connections, maxsize=maxsize, block=block,
                                                                 ssl_context=create_urllib3_context(ciphers=CIPHERS))


DATE_REGEX = re.compile(
    r'\[?(\d{4}[-年/\.]\s*\d{1,2}[-月/\.]\s*\d{1,2})\]?|(\d{1,2}\s*[A-Za-z]{3,}\s*,?\s*\d{4})|([A-Za-z]{3,}\s*\d{1,2},?\s*\d{4})|\[?(\d{1,2}[-月/\.]\d{1,2})\]?')


# ==============================================================================
# 3. CORE FUNCTIONS (与 V20 GUI 版本完全一致)
# ==============================================================================

def handle_yearless_date(date_str: str) -> str:
    try:
        date_str_normalized = date_str.replace('月', '-').replace('日', '').strip('[]/')
        if re.match(r'^\d{4}[-/]\d{1,2}$', date_str_normalized): date_str_normalized += '-01'
        parsed_date = parse_date(date_str_normalized).date()
        today = date.today()
        if parsed_date.year == today.year and (parsed_date - today).days > 60: return parsed_date.replace(
            year=today.year - 1).strftime('%Y-%m-%d')
        return parsed_date.strftime('%Y-%m-%d')
    except (ParserError, ValueError):
        today = date.today()
        full_date_str = f"{today.year}-{date_str_normalized}"
        try:
            parsed_date = parse_date(full_date_str).date()
            if (parsed_date - today).days > 60: return parsed_date.replace(year=today.year - 1).strftime('%Y-%m-%d')
            return parsed_date.strftime('%Y-%m-%d')
        except (ParserError, ValueError):
            return None


def parse_html_for_articles(html_content: str, base_url: str, target_date: datetime.date,
                            key_keywords: list, exclude_keywords: list):
    soup = BeautifulSoup(html_content, 'lxml')
    key_updates, other_updates = [], []
    processed_urls = set()

    def process_article(title, link_href, date_str):
        if any(keyword in title for keyword in exclude_keywords if keyword): return
        final_date = None
        try:
            clean_date_str = date_str.strip('[]')
            if re.search(r'\d{4}', clean_date_str):
                final_date = parse_date(clean_date_str).date()
            else:
                processed_date_str = handle_yearless_date(clean_date_str)
                if processed_date_str: final_date = datetime.strptime(processed_date_str, '%Y-%m-%d').date()
            if final_date and final_date >= target_date:
                absolute_url = urljoin(base_url, link_href)
                if absolute_url in processed_urls: return
                processed_urls.add(absolute_url)
                article_data = {'title': title, 'date': final_date.strftime('%Y-%m-%d'), 'url': absolute_url}
                if any(keyword in title for keyword in key_keywords if keyword):
                    key_updates.append(article_data)
                else:
                    other_updates.append(article_data)
        except (ParserError, ValueError):
            pass

    main_content_area = soup.find('div', class_=re.compile(r'PicList|content2|zpgw_box|list_box', re.I))
    search_scope = main_content_area if main_content_area else soup
    containers = search_scope.find_all(['li', 'tr', 'dd', 'article'])
    if not containers: containers = search_scope.find_all('div',
                                                          class_=re.compile(r'item|post|list|news|row|col', re.I))
    for item in containers:
        link_tag = item.find('a', href=True)
        if not link_tag: continue
        raw_title_text = link_tag.get_text(strip=True)
        title = raw_title_text.split('来源：')[0].split('时间：')[0].strip()
        title_tag = link_tag.find(['h1', 'h2', 'h3', 'h4', 'div', 'p'],
                                  class_=re.compile(r'title|list|name|text', re.I))
        title = title_tag.get_text(strip=True) if title_tag and title_tag.get_text(strip=True) else title
        if len(title.split()) < 2 and len(title) < 8: continue
        date_str = None
        date_tag = item.find('time')
        if date_tag:
            date_str = date_tag.get_text(strip=True)
        else:
            time_div = item.find(class_=re.compile(r'time|date', re.I))
            if time_div:
                match = DATE_REGEX.search(' '.join(time_div.stripped_strings).replace('/', '-'))
                if match: date_str = match.group(0)
        if not date_str:
            match = DATE_REGEX.search(item.get_text(separator=' ', strip=True))
            if match: date_str = match.group(0)
        if date_str: process_article(title, link_tag['href'], date_str)
    return {'status': 'success', 'key_updates': key_updates, 'other_updates': other_updates}


def find_updates_dynamic_selenium(driver, base_url: str, target_date: datetime.date, key_keywords: list,
                                  exclude_keywords: list):
    try:
        driver.get(base_url)
        WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(random.uniform(2, 4))
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(random.uniform(1, 2))
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(1, 2))
        except Exception:
            pass
        html_content = driver.page_source
        initial_parse_result = parse_html_for_articles(html_content, base_url, target_date, key_keywords,
                                                       exclude_keywords)
        if not initial_parse_result['key_updates'] and not initial_parse_result['other_updates'] and len(
            html_content) < 20000:
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            if iframes:
                try:
                    driver.switch_to.frame(iframes[0])
                    time.sleep(2)
                    html_content = driver.page_source
                    driver.switch_to.default_content()
                except Exception:
                    pass
        return parse_html_for_articles(html_content, base_url, target_date, key_keywords, exclude_keywords)
    except TimeoutException:
        html_content = driver.page_source if driver else ""
        if len(html_content) < 500: return {'status': 'error', 'reason': "Selenium错误: 页面加载超时且内容为空"}
        return parse_html_for_articles(html_content, base_url, target_date, key_keywords, exclude_keywords)
    except Exception as e:
        return {'status': 'error', 'reason': f"Selenium错误: {type(e).__name__}: {str(e)}".strip()}


def find_updates_static(base_url: str, target_date: datetime.date, key_keywords: list, exclude_keywords: list):
    session = requests.Session()
    session.mount('https://', Tls12Adapter())
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}
        response = session.get(base_url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        return parse_html_for_articles(response.text, base_url, target_date, key_keywords, exclude_keywords)
    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'reason': f"网络错误: {type(e).__name__}"}


def load_urls_from_excel(file_path):
    try:
        df = pd.read_excel(file_path, header=0)
        return [(row.iloc[0], row.iloc[1]) for index, row in df.iterrows()]
    except FileNotFoundError:
        print(f"错误: Excel文件未找到 '{file_path}'。")
        return None
    except Exception as e:
        print(f"错误: 读取Excel失败: {e}")
        return None


def generate_html_report(updated_sites, no_update_sites, error_sites, target_date_str, output_dir):
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_filename = os.path.join(output_dir, f"网页更新报告-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html")
    key_sites_html, other_sites_html = [], []
    for site in updated_sites:
        if site['key_updates']: key_sites_html.append(
            f'''<div class="site-block"><div class="site-title">{site['name']}</div><div class="site-url"><a href="{site['url']}" target="_blank">{site['url']}</a></div><ul>{''.join([f'<li class="key-update-item"><span class="date">[{update["date"]}]</span> <a href="{update["url"]}" target="_blank">{update["title"]}</a></li>' for update in site["key_updates"]])}</ul></div>''')
        if site['other_updates']: other_sites_html.append(
            f'''<div class="site-block"><div class="site-title">{site['name']}</div><div class="site-url"><a href="{site['url']}" target="_blank">{site['url']}</a></div><ul>{''.join([f'<li class="update-item"><span class="date">[{update["date"]}]</span> <a href="{update["url"]}" target="_blank">{update["title"]}</a></li>' for update in site["other_updates"]])}</ul></div>''')
    html_template = f"""
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>网页更新检查报告</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;margin:0 auto;max-width:1000px;padding:20px;color:#333}}h1,h2{{color:#1a73e8;border-bottom:2px solid #e0e0e0;padding-bottom:10px}}h2.key-title{{color:#ff8f00}}h2.other-title{{color:#1e8e3e}}.summary{{background-color:#f8f9fa;border-left:5px solid #1a73e8;padding:15px;margin:20px 0}}.site-block{{margin-bottom:25px;padding:15px;border:1px solid #ddd;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.05)}}.site-title{{font-size:1.2em;font-weight:bold;color:#202124}}.site-url{{font-size:0.9em;color:#5f6368;word-break:break-all}}ul{{list-style-type:none;padding-left:0}}li.update-item{{margin-top:10px;padding:10px;background-color:#f1f8e9;border-radius:5px}}li.key-update-item{{margin-top:10px;padding:10px;background-color:#fff8e1;border-left:3px solid #ff8f00;border-radius:5px}}li.no-update-item,li.error-item{{margin-top:5px;padding:5px;background-color:#f3f3f3;border-radius:5px}}.date{{font-weight:bold;color:#1e8e3e}}.error-reason{{color:#d93025;font-style:italic}}a{{color:#1a73e8;text-decoration:none}}a:hover{{text-decoration:underline}}</style></head><body>
    <h1>网页更新检查报告</h1><div class="summary"><strong>报告生成时间:</strong> {now}<br><strong>监控起始日期:</strong> {target_date_str} 之后<br><strong>结果概要:</strong> <span style="color:#1e8e3e;">{len(updated_sites)}</span> 个网站有更新 | <span style="color:#5f6368;">{len(no_update_sites)}</span> 个无更新 | <span style="color:#d93025;">{len(error_sites)}</span> 个访问失败</div>
    <h2 class="key-title">⭐ 重点关注更新</h2>{''.join(key_sites_html) if key_sites_html else "<p>本次没有检测到相关的重点更新。</p>"}
    <h2 class="other-title">📄 其他更新</h2>{''.join(other_sites_html) if other_sites_html else "<p>本次没有检测到其他类型的更新。</p>"}
    <h2>ℹ️ 无更新的网站</h2><ul>{''.join([f'<li class="no-update-item"><span class="site-title">{site["name"]}</span> - <a href="{site["url"]}" target="_blank">{site["url"]}</a></li>' for site in no_update_sites]) if no_update_sites else "<p>所有网站均有更新或访问失败。</p>"}</ul>
    <h2>❌ 无法访问的网站</h2><ul>{''.join([f'<li class="error-item"><span class="site-title">{site["name"]}</span> - {site["url"]}<br><span class="error-reason">原因: {site["reason"]}</span></li>' for site in error_sites]) if error_sites else "<p>所有网站均可正常访问。</p>"}</ul>
    </body></html>"""
    try:
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(html_template)
        print(f"\n报告生成成功！已保存至: {report_filename}")
    except Exception as e:
        print(f"\n错误: 写入报告文件失败: {e}")


# ==============================================================================
# 4. MAIN EXECUTION LOGIC (MODIFIED FOR AUTO DRIVER DETECTION)
# ==============================================================================
def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    print("--- 网页更新检查脚本 (V20-test-auto-driver) ---")
    key_list = [k.strip() for k in KEY_KEYWORDS_STR.split(',') if k.strip()]
    exclude_list = [k.strip() for k in EXCLUDE_KEYWORDS_STR.split(',') if k.strip()]

    print(f"关键词: {key_list if key_list else '无'}")
    print(f"排除词: {exclude_list if exclude_list else '无'}")

    sites_to_check = load_urls_from_excel(EXCEL_FILE_PATH)
    if not sites_to_check: return
    try:
        target_date = datetime.strptime(TARGET_DATE_STR, '%Y-%m-%d').date()
    except ValueError:
        print(f"错误: 日期格式不正确，请使用 'YYYY-MM-DD'。")
        return

    print(f"目标日期: >= {TARGET_DATE_STR}\n待检查网站: {len(sites_to_check)}\n")
    updated_sites, no_update_sites, error_sites = [], [], []

    dynamic_driver = None
    try:
        total_sites = len(sites_to_check)
        for i, (name, url) in enumerate(sites_to_check):
            print(f"[{i + 1}/{total_sites}] 检查: {name} (快速模式)...")
            result = find_updates_static(url, target_date, key_list, exclude_list)

            is_static_empty = (
                    result['status'] == 'success' and not result['key_updates'] and not result['other_updates'])
            if result['status'] == 'error' or is_static_empty:
                reason = result.get('reason', '未发现更新')
                print(f"  -> 快速模式失败({reason})，尝试动态模式...")

                if dynamic_driver is None:
                    print("  -> [LOG] 准备初始化动态浏览器实例 (只需一次)...")

                    # --- 核心修改：自动检测并构建驱动路径 ---
                    driver_path = None
                    # 获取当前脚本所在的目录
                    base_path = os.path.dirname(os.path.abspath(__file__))

                    if sys.platform.startswith('win'):
                        # Windows系统
                        potential_path = os.path.join(base_path, 'chromedriver.exe')
                        if os.path.exists(potential_path):
                            driver_path = potential_path
                    elif sys.platform.startswith('darwin') or sys.platform.startswith('linux'):
                        # macOS 或 Linux 系统
                        potential_path = os.path.join(base_path, 'chromedriver')
                        if os.path.exists(potential_path):
                            driver_path = potential_path

                    # --- 初始化浏览器 ---
                    options = uc.ChromeOptions()
                    options.add_argument('--headless=new')
                    # ... 其他 options ...

                    try:
                        print("  -> [LOG] 准备调用 uc.Chrome()...")
                        if driver_path:
                            print(f"  -> [LOG] 发现并使用同级目录下的驱动: {driver_path}")
                            dynamic_driver = uc.Chrome(options=options, driver_executable_path=driver_path)
                        else:
                            print("  -> [LOG] 未在同级目录发现驱动，将尝试自动下载和管理...")
                            dynamic_driver = uc.Chrome(options=options)

                        print("  -> [LOG] uc.Chrome() 调用成功！浏览器实例已创建。")
                        dynamic_driver.set_page_load_timeout(30)
                        print("  -> 动态浏览器已启动。")
                    except Exception as e:
                        print("\n\n" + "=" * 20 + " 初始化浏览器时发生致命错误! " + "=" * 20)
                        print(f"  -> [ERROR] 错误类型: {type(e).__name__}")
                        print(f"  -> [ERROR] 错误信息: {e}")
                        print("=" * 65 + "\n")
                        break

                if not dynamic_driver:
                    print("  -> 动态浏览器初始化失败，跳过后续所有动态检查。")
                    error_sites.append({'name': name, 'url': url, 'reason': "动态浏览器初始化失败"})
                    continue

                result = find_updates_dynamic_selenium(dynamic_driver, url, target_date, key_list, exclude_list)

            if result['status'] == 'success':
                key_updates, other_updates = result.get('key_updates', []), result.get('other_updates', [])
                if key_updates or other_updates:
                    sorted_key = sorted(key_updates, key=lambda x: x['date'], reverse=True)
                    sorted_other = sorted(other_updates, key=lambda x: x['date'], reverse=True)
                    updated_sites.append(
                        {'name': name, 'url': url, 'key_updates': sorted_key, 'other_updates': sorted_other})
                    print(f"  -> ✅ 发现 {len(sorted_key)} 条重点更新, {len(sorted_other)} 条其他更新！")
                else:
                    no_update_sites.append({'name': name, 'url': url})
                    print("  -> ℹ️ 未发现有效更新。")
            else:
                error_sites.append({'name': name, 'url': url, 'reason': result['reason']})
                print(f"  -> ❌ 访问失败: {result['reason']}")

            if i < total_sites - 1:
                sleep_time = random.uniform(2, 5)
                print(f"--- (延时 {sleep_time:.1f} 秒) ---\n")
                time.sleep(sleep_time)

    finally:
        if dynamic_driver:
            print("\n正在关闭动态浏览器实例...")
            dynamic_driver.quit()
            print("浏览器已关闭。")

    generate_html_report(updated_sites, no_update_sites, error_sites, TARGET_DATE_STR, OUTPUT_DIR)


if __name__ == "__main__":
    main()