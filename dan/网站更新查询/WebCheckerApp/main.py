# main.py
# 这是一个包含了所有逻辑和GUI的完整文件，可以直接用于PyInstaller打包

import pandas as pd
import os
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
    'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:'
    'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:'
    'ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:'
    'DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384'
)


class Tls12Adapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = requests.packages.urllib3.PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=create_urllib3_context(ciphers=CIPHERS)
        )


DATE_REGEX = re.compile(
    r'\[?(\d{4}[-年/\.]\s*\d{1,2}[-月/\.]\s*\d{1,2})\]?'
    r'|(\d{1,2}\s*[A-Za-z]{3,}\s*,?\s*\d{4})'
    r'|([A-Za-z]{3,}\s*\d{1,2},?\s*\d{4})'
    r'|\[?(\d{1,2}[-月/\.]\d{1,2})\]?'
)


# ==============================================================================
# 2. CORE PARSING AND SCRAPING FUNCTIONS
# ==============================================================================

def handle_yearless_date(date_str: str) -> str:
    try:
        date_str_normalized = date_str.replace('月', '-').replace('日', '').strip('[]/')
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
    soup = BeautifulSoup(html_content, 'lxml')
    found_articles = {}
    main_content_area = soup.find('div', class_=re.compile(r'PicList|content2|zpgw_box|list_box', re.I))
    search_scope = main_content_area if main_content_area else soup
    containers = search_scope.find_all(['li', 'tr', 'dd', 'article'])
    if not containers:
        containers = search_scope.find_all('div', class_=re.compile(r'item|post|list|news|row|col', re.I))
    for item in containers:
        link_tag = item.find('a', href=True)
        if not link_tag: continue
        raw_title_text = link_tag.get_text(strip=True)
        if '来源：' in raw_title_text:
            title = raw_title_text.split('来源：')[0].strip()
        elif '时间：' in raw_title_text:
            title = raw_title_text.split('时间：')[0].strip()
        else:
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
    if not found_articles and len(containers) < 3:
        main_title_tag = soup.find(['h1', 'h2'], class_=re.compile(r'title|headline', re.I)) or soup.find(['h1', 'h2'])
        if main_title_tag:
            title = main_title_tag.get_text(strip=True)
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


# --- 升级后的 find_updates_dynamic_selenium (V17) ---
# 这个版本增加了 iframe 处理、页面滚动、更强的反检测和更详细的错误报告
def find_updates_dynamic_selenium(base_url: str, target_date: datetime.date):
    driver = None
    try:
        options = uc.ChromeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--log-level=3')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--disable-blink-features=AutomationControlled')

        # 增加一些额外的反检测参数
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument(
            'user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36')

        driver = uc.Chrome(options=options)
        driver.set_page_load_timeout(30)  # 设置页面加载超时

        driver.get(base_url)

        # 等待页面基础元素加载
        WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(random.uniform(2, 4))  # 模仿人类阅读延迟

        # 增加页面滚动，这对于触发动态加载（懒加载）的网站至关重要
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(random.uniform(1, 2))
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(1, 2))
        except Exception:
            pass  # 如果页面不允许滚动，就跳过

        html_content = driver.page_source

        # 尝试处理 iframe
        # 如果初始页面内容很少，且解析不到文章，就检查是否存在 iframe
        initial_parse_result = parse_html_for_articles(html_content, base_url, target_date)
        if not initial_parse_result['updates'] and len(html_content) < 20000:  # 20KB, 小于这个大小的页面很可疑
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            if iframes:
                print("  -> 检测到 iframe，正在切换...")
                try:
                    driver.switch_to.frame(iframes[0])
                    time.sleep(2)  # 等待 iframe 加载
                    html_content = driver.page_source  # 获取 iframe 的源码
                    driver.switch_to.default_content()  # 切回主页面
                except Exception as e:
                    print(f"  -> iframe 切换失败: {e}")
                    pass  # 如果切换失败，继续使用原始 html

        return parse_html_for_articles(html_content, base_url, target_date)

    except TimeoutException:
        # 超时后，我们依然尽力去获取源码并解析
        html_content = driver.page_source
        if len(html_content) < 500:
            return {'status': 'error', 'reason': "Selenium错误: 页面加载超时且内容为空"}
        return parse_html_for_articles(html_content, base_url, target_date)

    # 增强的错误捕获，提供更详细的错误信息
    except Exception as e:
        # 使用 type(e).__name__ 获取异常类型，str(e) 获取详细信息
        error_message = f"{type(e).__name__}: {str(e)}".strip()
        return {'status': 'error', 'reason': f"Selenium错误: {error_message}"}

    finally:
        if driver:
            driver.quit()


def find_updates_static(base_url: str, target_date: datetime.date):
    session = requests.Session()
    session.mount('https://', Tls12Adapter())
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        response = session.get(base_url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        return parse_html_for_articles(response.text, base_url, target_date)
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
    html_template = f"""
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>网页更新检查报告</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;margin:0 auto;max-width:1000px;padding:20px;color:#333}}h1,h2{{color:#1a73e8;border-bottom:2px solid #e0e0e0;padding-bottom:10px}}.summary{{background-color:#f8f9fa;border-left:5px solid #1a73e8;padding:15px;margin:20px 0}}.site-block{{margin-bottom:25px;padding:15px;border:1px solid #ddd;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.05)}}.site-title{{font-size:1.2em;font-weight:bold;color:#202124}}.site-url{{font-size:0.9em;color:#5f6368;word-break:break-all}}ul{{list-style-type:none;padding-left:0}}li.update-item{{margin-top:10px;padding:10px;background-color:#f1f8e9;border-radius:5px}}li.no-update-item,li.error-item{{margin-top:5px;padding:5px;background-color:#f3f3f3;border-radius:5px}}.date{{font-weight:bold;color:#1e8e3e}}.error-reason{{color:#d93025;font-style:italic}}a{{color:#1a73e8;text-decoration:none}}a:hover{{text-decoration:underline}}</style></head><body>
    <h1>网页更新检查报告</h1><div class="summary"><strong>报告生成时间:</strong> {now}<br><strong>监控起始日期:</strong> {target_date_str} 之后<br><strong>结果概要:</strong> <span style="color:#1e8e3e;">{len(updated_sites)}</span> 个网站有更新 | <span style="color:#5f6368;">{len(no_update_sites)}</span> 个无更新 | <span style="color:#d93025;">{len(error_sites)}</span> 个访问失败</div>
    <h2>✅ 有更新的网站</h2>{''.join([f'''<div class="site-block"><div class="site-title">{site['name']}</div><div class="site-url"><a href="{site['url']}" target="_blank">{site['url']}</a></div><ul>{''.join([f'<li class="update-item"><span class="date">[{update["date"]}]</span> <a href="{update["url"]}" target="_blank">{update["title"]}</a></li>' for update in site["updates"]])}</ul></div>''' for site in updated_sites]) if updated_sites else "<p>本次没有检测到任何网站有更新。</p>"}
    <h2>ℹ️ 无更新（或因强反爬机制需手动查看）的网站</h2><ul>{''.join([f'<li class="no-update-item"><span class="site-title">{site["name"]}</span> - <a href="{site["url"]}" target="_blank">{site["url"]}</a></li>' for site in no_update_sites]) if no_update_sites else "<p>所有网站均有更新或访问失败。</p>"}</ul>
    <h2>❌ 无法访问的网站</h2><ul>{''.join([f'<li class="error-item"><span class="site-title">{site["name"]}</span> - {site["url"]}<br><span class="error-reason">原因: {site["reason"]}</span></li>' for site in error_sites]) if error_sites else "<p>所有网站均可正常访问。</p>"}</ul>
    </body></html>
    """
    try:
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(html_template)
        return {'success': True, 'path': report_filename}
    except Exception as e:
        return {'success': False, 'error': f"写入报告文件失败: {e}"}


# ==============================================================================
# 3. CORE EXECUTION FUNCTION (Called by GUI)
# ==============================================================================
def run_checker(excel_path, target_date_str, output_dir, status_callback):
    status_callback("开始检查...")
    sites_to_check = load_urls_from_excel(excel_path)
    if isinstance(sites_to_check, dict) and 'error' in sites_to_check:
        return {'error': sites_to_check['error']}

    try:
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    except ValueError:
        return {'error': "日期格式不正确，请使用 'YYYY-MM-DD'。"}

    status_callback(f"目标日期: >= {target_date_str}\n待检查网站: {len(sites_to_check)}")
    updated_sites, no_update_sites, error_sites = [], [], []

    total_sites = len(sites_to_check)
    for i, (name, url) in enumerate(sites_to_check):
        status_callback(f"[{i + 1}/{total_sites}] 检查: {name} (快速模式)...")
        result = find_updates_static(url, target_date)

        if result['status'] == 'error' or (result['status'] == 'success' and not result['updates']):
            reason = result.get('reason', '未发现更新')
            status_callback(f"  -> 快速模式失败({reason})，尝试动态模式...")
            result = find_updates_dynamic_selenium(url, target_date)

        if result['status'] == 'success':
            if result['updates']:
                sorted_updates = sorted(result['updates'], key=lambda x: x['date'], reverse=True)
                updated_sites.append({'name': name, 'url': url, 'updates': sorted_updates})
                status_callback(f"  -> ✅ 发现 {len(sorted_updates)} 条更新！")
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
        self.root.title("网页更新检查器 V17")
        self.root.geometry("600x450")

        self.excel_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.target_date = tk.StringVar(value=date.today().strftime('%Y-%m-%d'))

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

        self.run_button = tk.Button(main_frame, text="开始检查", bg="#4CAF50", fg="black",
                                    font=("Helvetica", 12, "bold"), command=self.start_checking)
        self.run_button.grid(row=6, column=0, columnspan=2, pady=(20, 10), sticky="ew")

        tk.Label(main_frame, text="运行日志:").grid(row=7, column=0, sticky="w", pady=(10, 5))
        self.log_area = scrolledtext.ScrolledText(main_frame, height=10, state='disabled')
        self.log_area.grid(row=8, column=0, columnspan=2, sticky="nsew")

        main_frame.grid_columnconfigure(0, weight=1)

    def select_excel(self):
        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")])
        if path:
            self.excel_path.set(path)

    def select_output_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.output_dir.set(path)

    def log(self, message):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.configure(state='disabled')
        self.log_area.see(tk.END)
        self.root.update_idletasks()

    def start_checking(self):
        excel = self.excel_path.get()
        target_d = self.target_date.get()
        output = self.output_dir.get()

        if not all([excel, target_d, output]):
            messagebox.showerror("错误", "所有选项均为必填项！")
            return

        self.run_button.config(text="正在运行...", state="disabled")
        self.log_area.configure(state='normal')
        self.log_area.delete(1.0, tk.END)
        self.log_area.configure(state='disabled')

        thread = threading.Thread(target=self.run_checker_thread, args=(excel, target_d, output))
        thread.start()

    def run_checker_thread(self, excel, target_d, output):
        result = run_checker(excel, target_d, output, self.log)
        self.root.after(0, self.on_checking_complete, result)

    def on_checking_complete(self, result):
        if 'error' in result:
            messagebox.showerror("执行出错", result['error'])
        elif 'success' in result:
            messagebox.showinfo("完成", f"报告已成功生成！\n路径: {result['path']}")
            if os.path.exists(result['path']):
                os.system(f'open "{os.path.dirname(result["path"])}"')

        self.run_button.config(text="开始检查", state="normal")


# ==============================================================================
# 5. APPLICATION ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()