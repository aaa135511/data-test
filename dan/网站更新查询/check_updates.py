import pandas as pd
import os
import requests
import re
import time
from datetime import datetime, date
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date
from dateutil.parser import ParserError

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
EXCEL_FILE_NAME = "网站合集.xlsx"
TARGET_DATE_STR = '2025-01-01'

# ==============================================================================
# 2. CORE FUNCTIONS (V15 Final Upgrade)
# ==============================================================================
DATE_REGEX = re.compile(
    r'\[?(\d{4}[-年/\.]\s*\d{1,2}[-月/\.]\s*\d{1,2})\]?'
    r'|(\d{1,2}\s*[A-Za-z]{3,}\s*,?\s*\d{4})'
    r'|([A-Za-z]{3,}\s*\d{1,2},?\s*\d{4})'
    r'|\[?(\d{1,2}[-月/\.]\d{1,2})\]?'
)


def handle_yearless_date(date_str: str) -> str:
    """V15 变更: 增强对 YYYY/MM 或 YYYY-MM 格式的处理。"""
    try:
        date_str_normalized = date_str.replace('月', '-').replace('日', '').strip('[]/')
        # 如果日期只包含年月，补上 '01' 日
        if re.match(r'^\d{4}[-/]\d{1,2}$', date_str_normalized):
            date_str_normalized += '-01'

        parsed_date = parse_date(date_str_normalized).date()
        today = date.today()
        if parsed_date.year == today.year and (parsed_date - today).days > 60:
            return parsed_date.replace(year=today.year - 1).strftime('%Y-%m-%d')
        return parsed_date.strftime('%Y-%m-%d')
    except (ParserError, ValueError):
        today = date.today()
        full_date_str = f"{today.year}-{date_str_normalized}"
        try:
            parsed_date = parse_date(full_date_str).date()
            if (parsed_date - today).days > 60:
                return parsed_date.replace(year=today.year - 1).strftime('%Y-%m-%d')
            return parsed_date.strftime('%Y-%m-%d')
        except (ParserError, ValueError):
            return None


def parse_html_for_articles(html_content: str, base_url: str, target_date: datetime.date):
    """V15 终极解析函数，整合所有特例逻辑。"""
    soup = BeautifulSoup(html_content, 'lxml')
    found_articles = {}

    # V15 变更 1: "区域优先"策略，先寻找主要内容区域
    main_content_area = soup.find('div', class_=re.compile(r'PicList|content2|zpgw_box|list_box', re.I))
    search_scope = main_content_area if main_content_area else soup

    containers = search_scope.find_all(['li', 'tr', 'dd', 'article'])
    if not containers:
        containers = search_scope.find_all('div', class_=re.compile(r'item|post|list|news|row|col', re.I))

    for item in containers:
        link_tag = item.find('a', href=True)
        if not link_tag: continue

        # V15 变更 2: 引入“文本分割”逻辑，处理大杂烩标题
        raw_title_text = link_tag.get_text(strip=True)
        # 尝试根据关键词分割，提取纯净标题
        if '来源：' in raw_title_text:
            title = raw_title_text.split('来源：')[0].strip()
        elif '时间：' in raw_title_text:
            title = raw_title_text.split('时间：')[0].strip()
        else:
            # 如果没有关键词，使用之前的精准提取逻辑
            title_tag = link_tag.find(['h1', 'h2', 'h3', 'h4', 'div', 'p'],
                                      class_=re.compile(r'title|list|name|text', re.I))
            title = title_tag.get_text(strip=True) if title_tag else raw_title_text

        if len(title.split()) < 2 and len(title) < 8: continue

        date_str = None
        date_tag = item.find('time')
        if date_tag:
            date_str = date_tag.get_text(strip=True)
        else:
            time_div = item.find(class_=re.compile(r'time|date', re.I))
            if time_div:
                reassembled_date = ' '.join(time_div.stripped_strings).replace('/', '-')
                match = DATE_REGEX.search(reassembled_date)
                if match: date_str = match.group(0)

        if not date_str:
            item_text = item.get_text(separator=' ', strip=True)
            match = DATE_REGEX.search(item_text)
            if match: date_str = match.group(0)

        if date_str:
            final_date = None
            try:
                clean_date_str = date_str.strip('[]')
                if re.search(r'\d{4}', clean_date_str):
                    final_date = parse_date(clean_date_str).date()
                else:
                    processed_date_str = handle_yearless_date(clean_date_str)
                    if processed_date_str: final_date = datetime.strptime(processed_date_str, '%Y-%m-%d').date()
                if final_date and final_date >= target_date:
                    absolute_url = urljoin(base_url, link_tag['href'])
                    if absolute_url not in found_articles:
                        found_articles[absolute_url] = {'title': title, 'date': final_date.strftime('%Y-%m-%d'),
                                                        'url': absolute_url}
            except (ParserError, ValueError):
                continue

    # V15 变更 3: 强化“单页模式”
    if not found_articles and len(containers) < 3:
        main_title_tag = soup.find(['h1', 'h2'], class_=re.compile(r'title|headline', re.I)) or soup.find(['h1', 'h2'])
        if main_title_tag:
            title = main_title_tag.get_text(strip=True)
            # 寻找包含“来源”或“时间”的特定元素
            source_info = soup.find(lambda tag: ('来源' in tag.text or '时间' in tag.text) and len(tag.text) < 100)
            page_text = source_info.get_text(strip=True) if source_info else soup.get_text(separator=' ', strip=True)
            match = DATE_REGEX.search(page_text)
            if match:
                date_str = match.group(0)
                final_date = None
                try:
                    clean_date_str = date_str.strip('[]')
                    if re.search(r'\d{4}', clean_date_str):
                        final_date = parse_date(clean_date_str).date()
                    else:
                        processed_date_str = handle_yearless_date(clean_date_str)
                        if processed_date_str: final_date = datetime.strptime(processed_date_str, '%Y-%m-%d').date()
                    if final_date and final_date >= target_date:
                        found_articles[base_url] = {'title': title, 'date': final_date.strftime('%Y-%m-%d'),
                                                    'url': base_url}
                except (ParserError, ValueError):
                    pass

    return {'status': 'success', 'updates': list(found_articles.values())}


# --- 其他函数与V13版本完全相同 ---
def find_updates_dynamic_selenium(base_url: str, target_date: datetime.date):
    driver = None
    try:
        options = webdriver.ChromeOptions();
        options.add_argument('--headless');
        options.add_argument('--disable-gpu');
        options.add_argument('--log-level=3');
        options.add_argument('--ignore-certificate-errors');
        options.add_experimental_option("excludeSwitches", ["enable-automation"]);
        options.add_experimental_option('useAutomationExtension', False)
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument',
                               {'source': "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"})
        driver.get(base_url)
        WebDriverWait(driver, 20).until(EC.any_of(EC.presence_of_element_located((By.TAG_NAME, "li")),
                                                  EC.presence_of_element_located((By.TAG_NAME, "tr")),
                                                  EC.presence_of_element_located((By.TAG_NAME, "dd")),
                                                  EC.presence_of_element_located(
                                                      (By.CSS_SELECTOR, "div[class*='item']")),
                                                  EC.presence_of_element_located(
                                                      (By.CSS_SELECTOR, "div[class*='list']")),
                                                  EC.presence_of_element_located((By.TAG_NAME, "h1"))))
        time.sleep(2)
        html_content = driver.page_source
        return parse_html_for_articles(html_content, base_url, target_date)
    except TimeoutException:
        html_content = driver.page_source
        return parse_html_for_articles(html_content, base_url, target_date)
    except Exception as e:
        return {'status': 'error', 'reason': f"Selenium错误: {e}"}
    finally:
        if driver: driver.quit()


def find_updates_static(base_url: str, target_date: datetime.date):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7', 'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive', 'Upgrade-Insecure-Requests': '1', }
        response = requests.get(base_url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        return parse_html_for_articles(response.text, base_url, target_date)
    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'reason': f"网络错误: {e}"}


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


def generate_html_report(updated_sites, no_update_sites, error_sites, target_date_str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_filename = f"网页更新报告-{datetime.now().strftime('%Y%m%d')}.html"
    html_template = f"""
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>网页更新检查报告</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;margin:0 auto;max-width:1000px;padding:20px;color:#333}}h1,h2{{color:#1a73e8;border-bottom:2px solid #e0e0e0;padding-bottom:10px}}.summary{{background-color:#f8f9fa;border-left:5px solid #1a73e8;padding:15px;margin:20px 0}}.site-block{{margin-bottom:25px;padding:15px;border:1px solid #ddd;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.05)}}.site-title{{font-size:1.2em;font-weight:bold;color:#202124}}.site-url{{font-size:0.9em;color:#5f6368;word-break:break-all}}ul{{list-style-type:none;padding-left:0}}li.update-item{{margin-top:10px;padding:10px;background-color:#f1f8e9;border-radius:5px}}li.no-update-item,li.error-item{{margin-top:5px;padding:5px;background-color:#f3f3f3;border-radius:5px}}.date{{font-weight:bold;color:#1e8e3e}}.error-reason{{color:#d93025;font-style:italic}}a{{color:#1a73e8;text-decoration:none}}a:hover{{text-decoration:underline}}</style></head><body>
    <h1>网页更新检查报告</h1><div class="summary"><strong>报告生成时间:</strong> {now}<br><strong>监控起始日期:</strong> {target_date_str} 之后<br><strong>结果概要:</strong> <span style="color:#1e8e3e;">{len(updated_sites)}</span> 个网站有更新 | <span style="color:#5f6368;">{len(no_update_sites)}</span> 个无更新 | <span style="color:#d93025;">{len(error_sites)}</span> 个访问失败</div>
    <h2>✅ 有更新的网站</h2>{''.join([f'''<div class="site-block"><div class="site-title">{site['name']}</div><div class="site-url"><a href="{site['url']}" target="_blank">{site['url']}</a></div><ul>{''.join([f'<li class="update-item"><span class="date">[{update["date"]}]</span> <a href="{update["url"]}" target="_blank">{update["title"]}</a></li>' for update in site["updates"]])}</ul></div>''' for site in updated_sites]) if updated_sites else "<p>本次没有检测到任何网站有更新。</p>"}
    <h2>ℹ️ 无更新的网站</h2><ul>{''.join([f'<li class="no-update-item"><span class="site-title">{site["name"]}</span> - <a href="{site["url"]}" target="_blank">{site["url"]}</a></li>' for site in no_update_sites]) if no_update_sites else "<p>所有网站均有更新或访问失败。</p>"}</ul>
    <h2>❌ 无法访问的网站</h2><ul>{''.join([f'<li class="error-item"><span class="site-title">{site["name"]}</span> - {site["url"]}<br><span class="error-reason">原因: {site["reason"]}</span></li>' for site in error_sites]) if error_sites else "<p>所有网站均可正常访问。</p>"}</ul>
    </body></html>
    """
    try:
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(html_template)
        print(f"\n报告生成成功！已保存为: {report_filename}")
    except Exception as e:
        print(f"\n错误: 写入报告文件失败: {e}")


def main():
    print("--- 网页更新检查脚本 (V15 - 精准修复版) ---")
    sites_to_check = load_urls_from_excel(EXCEL_FILE_NAME)
    if not sites_to_check: return
    try:
        target_date = datetime.strptime(TARGET_DATE_STR, '%Y-%m-%d').date()
    except ValueError:
        print(f"错误: 日期格式不正确，请使用 'YYYY-MM-DD'。")
        return
    print(f"目标日期: >= {TARGET_DATE_STR}\n待检查网站: {len(sites_to_check)}\n")
    updated_sites, no_update_sites, error_sites = [], [], []
    for i, (name, url) in enumerate(sites_to_check):
        print(f"[{i + 1}/{len(sites_to_check)}] 检查: {name} (快速模式)...")
        result = find_updates_static(url, target_date)
        if result['status'] == 'error' or (result['status'] == 'success' and not result['updates']):
            if result['status'] == 'error':
                print(f"  -> 快速模式失败({result['reason']})，尝试动态模式...")
            else:
                print(f"  -> 快速模式未发现更新，尝试动态模式...")
            result = find_updates_dynamic_selenium(url, target_date)
        if result['status'] == 'success':
            if result['updates']:
                sorted_updates = sorted(result['updates'], key=lambda x: x['date'], reverse=True)
                updated_sites.append({'name': name, 'url': url, 'updates': sorted_updates})
            else:
                no_update_sites.append({'name': name, 'url': url})
        else:
            error_sites.append({'name': name, 'url': url, 'reason': result['reason']})
    generate_html_report(updated_sites, no_update_sites, error_sites, TARGET_DATE_STR)


if __name__ == "__main__":
    main()