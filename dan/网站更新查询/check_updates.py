import requests
import re
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date
from dateutil.parser import ParserError

# 导入Selenium相关库
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException

# ==============================================================================
# 1. INPUT CONFIGURATION
# ==============================================================================
URLS = """
https://hr.masu.edu.cn/595/list.htm
http://www.gov.cn/zhengce/zuixin.htm
https://www.nature.com/nature/latest-news
"""
TARGET_DATE_STR = '2025-08-01'

# ==============================================================================
# 2. CORE FUNCTIONS
# ==============================================================================
DATE_REGEX = re.compile(
    r'(\d{4}[-年/\.]\s*\d{1,2}[-月/\.]\s*\d{1,2})'
    r'|(\d{1,2}\s*[A-Za-z]{3,}\s*,?\s*\d{4})'
    r'|([A-Za-z]{3,}\s*\d{1,2},?\s*\d{4})'
)


def parse_html_for_articles(html_content: str, base_url: str, target_date: datetime.date):
    """通用HTML解析函数，供两种抓取模式共用。"""
    soup = BeautifulSoup(html_content, 'lxml')
    found_articles = {}
    containers = soup.find_all(['li', 'tr'])
    if not containers:
        containers = soup.find_all('div', class_=re.compile(r'item|post|list|news', re.IGNORECASE))

    for item in containers:
        link_tag = item.find('a', href=True)
        item_text = item.get_text(separator=' ', strip=True)
        if not link_tag: continue
        title = link_tag.get_text(strip=True)
        if len(title) < 5: continue
        match = DATE_REGEX.search(item_text)
        if match:
            date_str = match.group(0)
            try:
                article_date = parse_date(date_str).date()
                if article_date >= target_date:
                    absolute_url = urljoin(base_url, link_tag['href'])
                    if absolute_url not in found_articles:
                        found_articles[absolute_url] = {
                            'title': title, 'date': article_date.strftime('%Y-%m-%d'), 'url': absolute_url
                        }
            except (ParserError, ValueError):
                continue
    return {'status': 'success', 'updates': list(found_articles.values())}


def find_updates_static(base_url: str, target_date: datetime.date):
    """模式一：使用requests进行快速静态抓取。"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        response = requests.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        return parse_html_for_articles(response.text, base_url, target_date)
    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'reason': f"网络错误 (快速模式): {e}"}


def find_updates_dynamic_selenium(base_url: str, target_date: datetime.date):
    """模式二：使用Selenium进行动态抓取。"""
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--log-level=3')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(base_url)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li, tr, div[class*='item'], div[class*='post']"))
        )

        html_content = driver.page_source
        return parse_html_for_articles(html_content, base_url, target_date)
    except TimeoutException:
        # 页面加载了，但没等到我们想要的关键元素，可能页面结构特殊或确实为空
        # 此时仍然可以尝试解析已加载的HTML
        html_content = driver.page_source
        return parse_html_for_articles(html_content, base_url, target_date)
    except Exception as e:
        return {'status': 'error', 'reason': f"Selenium错误 (动态模式): {e}"}
    finally:
        if driver:
            driver.quit()


# ==============================================================================
# 3. MAIN EXECUTION LOGIC
# ==============================================================================
def main():
    print("--- 网页更新检查脚本 (V5 - 智能混合模式) ---")

    urls_to_check = [url.strip() for url in URLS.strip().split('\n') if url.strip()]
    try:
        target_date = datetime.strptime(TARGET_DATE_STR, '%Y-%m-%d').date()
    except ValueError:
        print(f"错误: 日期格式不正确，请使用 'YYYY-MM-DD'。")
        return

    print(f"目标日期: >= {TARGET_DATE_STR}\n待检查的网站数量: {len(urls_to_check)}\n")

    updated_sites, no_update_sites, error_sites = [], [], []

    for i, url in enumerate(urls_to_check):
        print(f"[{i + 1}/{len(urls_to_check)}] 正在检查 (快速模式): {url} ...")

        # 第一步：总是先尝试快速的静态模式
        result = find_updates_static(url, target_date)

        # 第二步：如果静态模式成功但没找到结果，则启动动态模式作为备用方案
        if result['status'] == 'success' and not result['updates']:
            print(f"  -> 快速模式未发现更新，正在尝试动态模式 (较慢)...")
            result = find_updates_dynamic_selenium(url, target_date)

        # 第三步：处理最终结果
        if result['status'] == 'success':
            if result['updates']:
                sorted_updates = sorted(result['updates'], key=lambda x: x['date'], reverse=True)
                updated_sites.append({'url': url, 'updates': sorted_updates})
            else:
                no_update_sites.append(url)
        else:
            error_sites.append({'url': url, 'reason': result['reason']})

    # ... (打印报告的部分完全不变)
    print("\n\n--- 检查报告 ---")
    if updated_sites:
        print(f"\n✅ {len(updated_sites)} 个网站有更新：")
        for site in updated_sites:
            print(f"\n[+] 网站: {site['url']}")
            for update in site['updates']:
                print(f"  - [{update['date']}] {update['title']}")
                print(f"    链接: {update['url']}")
    else:
        print("\n✅ 所有可访问的网站均无指定日期后的更新。")
    if no_update_sites:
        print(f"\nℹ️ {len(no_update_sites)} 个网站可正常访问但无更新：")
        for url in no_update_sites: print(f"  - {url}")
    if error_sites:
        print(f"\n❌ {len(error_sites)} 个网站无法访问或发生错误：")
        for site in error_sites: print(f"  - 网站: {site['url']}\n    原因: {site['reason']}")
    print("\n--- 报告结束 ---")


if __name__ == "__main__":
    main()