# main.py
# 这是一个包含了所有逻辑和GUI的完整文件，可以直接用于PyInstaller打包
# 版本 V21: 本地驱动版 - 自动检测并使用与App/Exe同级的chromedriver

import pandas as pd
import os
import sys  # 导入sys模块以检测操作系统和可执行文件路径
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
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import multiprocessing

# ... [从 Tls12Adapter 到 generate_html_report 的所有代码保持不变] ...
# ==============================================================================
# 1. INITIAL CONFIGURATION & NETWORKING SETUP
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
# 2. CORE PARSING AND SCRAPING FUNCTIONS
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
        return {'error': f"错误: Excel文件未找到 '{file_path}'。"}
    except Exception as e:
        return {'error': f"错误: 读取Excel失败: {e}"}


def generate_html_report(updated_sites, no_update_sites, error_sites, target_date_str, output_dir):
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
        return {'success': True, 'path': report_filename}
    except Exception as e:
        return {'success': False, 'error': f"写入报告文件失败: {e}"}


# ==============================================================================
# 3. CORE EXECUTION FUNCTION (MODIFIED FOR LOCAL DRIVER)
# ==============================================================================
def run_checker(excel_path, target_date_str, output_dir, status_callback, key_keywords_str, exclude_keywords_str):
    key_list = [k.strip() for k in key_keywords_str.split(',') if k.strip()]
    exclude_list = [k.strip() for k in exclude_keywords_str.split(',') if k.strip()]
    status_callback("开始检查...")
    status_callback(f"关键词: {key_list if key_list else '无'}")
    status_callback(f"排除词: {exclude_list if exclude_list else '无'}")
    sites_to_check = load_urls_from_excel(excel_path)
    if isinstance(sites_to_check, dict) and 'error' in sites_to_check: return {'error': sites_to_check['error']}
    try:
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    except ValueError:
        return {'error': "日期格式不正确，请使用 'YYYY-MM-DD'。"}

    status_callback(f"目标日期: >= {target_date_str}\n待检查网站: {len(sites_to_check)}")
    updated_sites, no_update_sites, error_sites = [], [], []

    dynamic_driver = None
    try:
        total_sites = len(sites_to_check)
        for i, (name, url) in enumerate(sites_to_check):
            status_callback(f"[{i + 1}/{total_sites}] 检查: {name} (快速模式)...")
            result = find_updates_static(url, target_date, key_list, exclude_list)
            is_static_empty = (
                    result['status'] == 'success' and not result['key_updates'] and not result['other_updates'])
            if result['status'] == 'error' or is_static_empty:
                reason = result.get('reason', '未发现更新')
                status_callback(f"  -> 快速模式失败({reason})，尝试动态模式...")

                if dynamic_driver is None:
                    status_callback("  -> 准备初始化动态浏览器实例 (只需一次)...")

                    # --- 核心修改：自动检测并构建本地驱动路径 ---
                    driver_path = None
                    # sys.executable 是指向打包后App/Exe的可靠路径
                    # 'frozen' 属性是 PyInstaller 添加的，用于判断是否是打包环境
                    if getattr(sys, 'frozen', False):
                        base_path = os.path.dirname(sys.executable)
                    else:
                        base_path = os.path.dirname(os.path.abspath(__file__))

                    if sys.platform.startswith('win'):
                        potential_path = os.path.join(base_path, 'chromedriver.exe')
                        if os.path.exists(potential_path): driver_path = potential_path
                    else:  # macOS or Linux
                        potential_path = os.path.join(base_path, 'chromedriver')
                        if os.path.exists(potential_path): driver_path = potential_path

                    options = uc.ChromeOptions()
                    options.add_argument('--headless=new')
                    # ... other options ...

                    try:
                        status_callback("  -> 正在调用 uc.Chrome()...")
                        if driver_path:
                            status_callback(f"  -> 发现并使用本地驱动: {driver_path}")
                            dynamic_driver = uc.Chrome(options=options, driver_executable_path=driver_path)
                        else:
                            status_callback("  -> 未发现本地驱动，尝试自动下载...")
                            dynamic_driver = uc.Chrome(options=options)

                        status_callback("  -> 动态浏览器实例已创建。")
                        dynamic_driver.set_page_load_timeout(30)
                    except Exception as e:
                        error_msg = f"初始化浏览器时发生致命错误: {e}"
                        status_callback(f"  -> [错误] {error_msg}")
                        # 使用messagebox从线程中安全地弹出错误
                        root.after(0, messagebox.showerror, "初始化失败", error_msg)
                        break

                if not dynamic_driver:
                    status_callback("  -> 浏览器初始化失败，跳过后续所有动态检查。")
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
                    status_callback(f"  -> ✅ 发现 {len(sorted_key)} 条重点更新, {len(sorted_other)} 条其他更新！")
                else:
                    no_update_sites.append({'name': name, 'url': url})
                    status_callback("  -> ℹ️ 未发现有效更新。")
            else:
                error_sites.append({'name': name, 'url': url, 'reason': result['reason']})
                status_callback(f"  -> ❌ 访问失败: {result['reason']}")

            if i < total_sites - 1:
                sleep_time = random.uniform(2, 5)
                status_callback(f"--- (延时 {sleep_time:.1f} 秒) ---\n")
                time.sleep(sleep_time)
    finally:
        if dynamic_driver:
            status_callback("正在关闭动态浏览器实例...")
            dynamic_driver.quit()
            status_callback("浏览器已关闭。")

    status_callback("正在生成HTML报告...")
    report_result = generate_html_report(updated_sites, no_update_sites, error_sites, target_date_str, output_dir)
    if report_result['success']:
        status_callback(f"报告生成成功！已保存至: {report_result['path']}")
        return {'success': True, 'path': report_result['path']}
    else:
        status_callback(f"错误: {report_result['error']}")
        return {'error': report_result['error']}


# ==============================================================================
# 4. GRAPHICAL USER INTERFACE (GUI) using Tkinter
# ==============================================================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("网页更新检查器 V21 - 本地驱动版")
        self.root.geometry("600x550")
        self.excel_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.target_date = tk.StringVar(value=date.today().strftime('%Y-%m-%d'))
        self.key_keywords = tk.StringVar(value="招聘, 人才引进")
        self.exclude_keywords = tk.StringVar(value="博士, 拟聘用, 高层次, 公示")
        main_frame = tk.Frame(root, padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(main_frame, text="1. 选择网站列表 Excel 文件:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        excel_entry = tk.Entry(main_frame, textvariable=self.excel_path, width=50)
        excel_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        excel_btn = tk.Button(main_frame, text="浏览...", command=self.select_excel)
        excel_btn.grid(row=1, column=1, sticky="ew")
        tk.Label(main_frame, text="2. 设定监控起始日期 (格式 YYYY-MM-DD):").grid(row=2, column=0, sticky="w",
                                                                                 pady=(10, 5))
        date_entry = tk.Entry(main_frame, textvariable=self.target_date, width=20)
        date_entry.grid(row=3, column=0, columnspan=2, sticky="w")
        tk.Label(main_frame, text="3. 选择报告输出目录:").grid(row=4, column=0, sticky="w", pady=(10, 5))
        output_entry = tk.Entry(main_frame, textvariable=self.output_dir, width=50)
        output_entry.grid(row=5, column=0, sticky="ew", padx=(0, 10))
        output_btn = tk.Button(main_frame, text="选择...", command=self.select_output_dir)
        output_btn.grid(row=5, column=1, sticky="ew")
        tk.Label(main_frame, text="4. 包含关键词 (用英文逗号 , 分隔):").grid(row=6, column=0, sticky="w", pady=(10, 5))
        key_entry = tk.Entry(main_frame, textvariable=self.key_keywords)
        key_entry.grid(row=7, column=0, columnspan=2, sticky="ew")
        tk.Label(main_frame, text="5. 排除关键词 (用英文逗号 , 分隔):").grid(row=8, column=0, sticky="w", pady=(10, 5))
        exclude_entry = tk.Entry(main_frame, textvariable=self.exclude_keywords)
        exclude_entry.grid(row=9, column=0, columnspan=2, sticky="ew")
        self.run_button = tk.Button(main_frame, text="开始检查", bg="#4CAF50", fg="black",
                                    font=("Helvetica", 12, "bold"), command=self.start_checking)
        self.run_button.grid(row=10, column=0, columnspan=2, pady=(20, 10), sticky="ew")
        tk.Label(main_frame, text="运行日志:").grid(row=11, column=0, sticky="w", pady=(10, 5))
        self.log_area = scrolledtext.ScrolledText(main_frame, height=10, state='disabled')
        self.log_area.grid(row=12, column=0, columnspan=2, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(12, weight=1)

    def select_excel(self):
        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")])
        if path: self.excel_path.set(path)

    def select_output_dir(self):
        path = filedialog.askdirectory()
        if path: self.output_dir.set(path)

    def log(self, message):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.configure(state='disabled')
        self.log_area.see(tk.END)
        self.root.update_idletasks()

    def start_checking(self):
        excel, target_d, output = self.excel_path.get(), self.target_date.get(), self.output_dir.get()
        key_kws = self.key_keywords.get()
        exclude_kws = self.exclude_keywords.get()
        if not all([excel, target_d, output]):
            messagebox.showerror("错误", "前三个选项均为必填项！")
            return
        self.run_button.config(text="正在运行...", state="disabled")
        self.log_area.configure(state='normal')
        self.log_area.delete(1.0, tk.END)
        self.log_area.configure(state='disabled')
        thread = threading.Thread(target=run_checker, args=(excel, target_d, output, self.log, key_kws, exclude_kws))
        thread.start()
        self.monitor_thread(thread)

    def monitor_thread(self, thread):
        if thread.is_alive():
            self.root.after(100, lambda: self.monitor_thread(thread))
        else:
            # 线程结束后，我们假设run_checker处理了所有结果，这里只恢复按钮
            # 也可以通过队列等方式从线程获取最终结果
            self.run_button.config(text="开始检查", state="normal")
            # 报告生成和弹窗逻辑已移至run_checker的finally块之后
            # 这里不再需要on_checking_complete方法


# ==============================================================================
# 5. APPLICATION ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    multiprocessing.freeze_support()
    root = tk.Tk()
    app = App(root)


    # 将对run_checker的调用移出App类，以便在线程中安全地显示messagebox
    def run_checker_thread(excel, target_d, output, log_func, key_kws, exclude_kws):
        result = run_checker(excel, target_d, output, log_func, key_kws, exclude_kws)

        # 在主线程中处理最终结果
        def final_actions():
            if 'error' in result:
                messagebox.showerror("执行出错", result['error'])
            elif 'success' in result:
                messagebox.showinfo("完成", f"报告已成功生成！\n路径: {result['path']}")
                if os.path.exists(result['path']):
                    try:
                        if os.name == 'nt':
                            os.startfile(os.path.dirname(result['path']))
                        elif sys.platform == 'darwin':
                            os.system(f'open "{os.path.dirname(result["path"])}"')
                    except Exception as e:
                        log_func(f"无法自动打开文件夹: {e}")
            app.run_button.config(text="开始检查", state="normal")

        root.after(0, final_actions)


    # 重新绑定按钮的命令
    def start_checking_wrapper():
        excel = app.excel_path.get()
        target_d = app.target_date.get()
        output = app.output_dir.get()
        key_kws = app.key_keywords.get()
        exclude_kws = app.exclude_keywords.get()
        if not all([excel, target_d, output]):
            messagebox.showerror("错误", "前三个选项均为必填项！")
            return
        app.run_button.config(text="正在运行...", state="disabled")
        app.log_area.configure(state='normal')
        app.log_area.delete(1.0, tk.END)
        app.log_area.configure(state='disabled')

        thread = threading.Thread(target=run_checker_thread,
                                  args=(excel, target_d, output, app.log, key_kws, exclude_kws))
        thread.start()


    app.run_button.config(command=start_checking_wrapper)
    root.mainloop()