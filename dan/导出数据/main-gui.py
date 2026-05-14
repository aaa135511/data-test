import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import pandas as pd
import requests
import json
import base64
import string
import random
import time
import os
import csv
import re
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad

# 字段精准映射表 (JSON编码 -> 客户要求的新表头)
FIELD_MAP = {
    "B22170002": "近1个月贷款笔数",
    "B22170003": "近3个月贷款笔数",
    "B22170004": "近6个月贷款笔数",
    "B22170005": "近12个月贷款笔数",
    "B22170006": "近24个月贷款笔数",
    "B22170007": "近1个月贷款总金额",
    "B22170008": "近3个月贷款总金额",
    "B22170009": "近6个月贷款总金额",
    "B22170010": "近12个月贷款总金额",
    "B22170011": "近24个月贷款总金额"
}


# --- 加密工具类 ---
class CryptoUtil:
    PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqt2A/9Yt3sPrdDE6LZCJ
lIP1AEhy1HJi2zEbK1RIw4QT6gitue8t1I4hOU17n5G35ENmtfN2rYWhmdRfX/Mm
uMqiFzHikoSGhPXVTUjsXkrXoSw7p3pqCoaN/b1hetj8MC0hK0rj8TvVkgLsplpp
iS1MzH7pkr+fTRIjyITL2l3BgcUBH6CQvdfmOKdkQGZy3T5UvUjdT2FWkf+nMdw5
ydTPv8G64OAeWONF0gkyq/QlwpMK50Y0XceRgHJIXtUaBYwB2o5n/l5/EY9IlX6u
149d6cv52AU0xxFM3vsAuDI/1YDOl5zJZD8LmKg0//ShWm3sFCkzwrBW0/veijja
tQIDAQAB
-----END PUBLIC KEY-----"""

    @staticmethod
    def encrypt_payload(data_dict):
        # 【核心修复】：恢复最标准的 UTF-8 编码，不要转换 ASCII。
        # 这样上游征信机构接收到的就是原汁原味的中文，绝对不会再报“约束有误/加密方式有误”
        json_string = json.dumps(data_dict, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        aes_key_str = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))
        aes_key = aes_key_str.encode('utf-8')

        cipher = AES.new(aes_key, AES.MODE_ECB)
        encrypted_data = base64.b64encode(cipher.encrypt(pad(json_string, AES.block_size))).decode('utf-8')

        rsa_key = RSA.import_key(CryptoUtil.PUBLIC_KEY)
        cipher_rsa = PKCS1_v1_5.new(rsa_key)
        encrypted_aes_key = base64.b64encode(cipher_rsa.encrypt(aes_key)).decode('utf-8')

        return {"encryptedKey": encrypted_aes_key, "encryptedData": encrypted_data}


# --- 主程序类 ---
class QueryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("API 高速自动化查询工具 (无错纯净版)")
        self.root.geometry("680x600")
        self.session = requests.Session()

        self.excel_path = tk.StringVar()
        self.export_path = tk.StringVar()
        self.username = tk.StringVar(value="test")
        self.password = tk.StringVar(value="bb111")

        self.setup_ui()

    def setup_ui(self):
        frame_login = tk.LabelFrame(self.root, text="登录设置", padx=10, pady=10)
        frame_login.pack(fill="x", padx=10, pady=5)
        tk.Label(frame_login, text="账号:").grid(row=0, column=0, padx=5)
        tk.Entry(frame_login, textvariable=self.username, width=20).grid(row=0, column=1, padx=5)
        tk.Label(frame_login, text="密码:").grid(row=0, column=2, padx=5)
        tk.Entry(frame_login, textvariable=self.password, show="*", width=20).grid(row=0, column=3, padx=5)

        frame_file = tk.LabelFrame(self.root, text="文件与路径配置", padx=10, pady=10)
        frame_file.pack(fill="x", padx=10, pady=5)

        tk.Label(frame_file, text="数据源:").grid(row=0, column=0, sticky="e")
        tk.Entry(frame_file, textvariable=self.excel_path, width=45, state="readonly").grid(row=0, column=1, padx=5,
                                                                                            pady=5)
        tk.Button(frame_file, text="导入Excel", command=self.select_file).grid(row=0, column=2, padx=5, pady=5)

        tk.Label(frame_file, text="导出到:").grid(row=1, column=0, sticky="e")
        tk.Entry(frame_file, textvariable=self.export_path, width=45, state="readonly").grid(row=1, column=1, padx=5,
                                                                                             pady=5)
        tk.Button(frame_file, text="选择目录", command=self.select_export_dir).grid(row=1, column=2, padx=5, pady=5)

        tk.Button(self.root, text="开始执行任务", bg="green", fg="white", font=("Arial", 12, "bold"),
                  command=self.start_task_thread).pack(pady=10)

        frame_log = tk.LabelFrame(self.root, text="运行日志", padx=10, pady=10)
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(frame_log, wrap=tk.WORD)
        self.log_text.pack(fill="both", expand=True)

    def log(self, message):
        self.root.after(0, lambda: self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n"))
        self.root.after(0, lambda: self.log_text.see(tk.END))

    def select_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
        if filepath: self.excel_path.set(filepath)

    def select_export_dir(self):
        dirpath = filedialog.askdirectory()
        if dirpath: self.export_path.set(dirpath)

    def start_task_thread(self):
        if not self.excel_path.get() or not self.export_path.get():
            messagebox.showwarning("警告", "请先导入数据源文件并选择导出目录！")
            return
        threading.Thread(target=self.run_automation, daemon=True).start()

    def save_to_csv_realtime(self, row_dict, csv_filename, headers_list):
        try:
            with open(csv_filename, mode='a', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=headers_list)
                writer.writerow(row_dict)
        except Exception:
            pass


def run_automation(self):
    self.log("开始初始化 API 客户端...")
    try:
        # ========== Win10 TLS 修复开始 ==========
        import ssl
        import warnings
        warnings.filterwarnings('ignore')

        # 创建强制 TLS 1.2+ 的 Session
        self.session = requests.Session()

        # 方法1：自定义 SSL 上下文（最有效）
        try:
            # 创建 SSL 上下文，强制最低 TLS 1.2
            ssl_context = ssl.create_default_context()
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3
            # 设置更兼容的加密套件
            ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')  # 降低安全级别要求
        except AttributeError:
            # Python 3.6 以下回退
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)

        # 挂载自定义 SSL 适配器
        from requests.adapters import HTTPAdapter
        from urllib3.poolmanager import PoolManager

        class TLSAdapter(HTTPAdapter):
            def __init__(self, ssl_context=None, **kwargs):
                self.ssl_context = ssl_context
                super().__init__(**kwargs)

            def init_poolmanager(self, *args, **kwargs):
                if self.ssl_context:
                    kwargs['ssl_context'] = self.ssl_context
                return super().init_poolmanager(*args, **kwargs)

        adapter = TLSAdapter(ssl_context)
        self.session.mount('https://', adapter)

        # 方法2：关闭 SSL 验证（仅作为备用方案）
        self.session.verify = False

        # 添加完整的请求头，模拟真实浏览器
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        })

        # ========== 登录流程 ==========
        self.log("正在登录...")
        self.session.get("https://search.azbbzzc.com/login.html", timeout=30)
        login_res = self.session.post(
            "https://search.azbbzzc.com/login",
            data={"username": self.username.get(), "password": self.password.get()},
            timeout=30
        )

        try:
            token = login_res.json().get("token")
            if not token:
                self.log(f"登录失败: {login_res.text}")
                return
            self.log("登录成功！")
        except Exception as e:
            self.log(f"登录响应解析失败: {e}")
            return

        # 请求头中带上 token
        self.session.headers.update({"token": token})

        # 读取 Excel
        df = pd.read_excel(self.excel_path.get(), dtype=str)

        headers_list = [
            "姓名", "身份证号", "电话号码", "核验结果", "黑名单核验",
            "近1个月贷款笔数", "近3个月贷款笔数", "近6个月贷款笔数",
            "近12个月贷款笔数", "近24个月贷款笔数",
            "近1个月贷款总金额", "近3个月贷款总金额", "近6个月贷款总金额",
            "近12个月贷款总金额", "近24个月贷款总金额"
        ]

        timestamp = int(time.time())
        export_dir = self.export_path.get()
        backup_csv = os.path.join(export_dir, f"查询结果_实时备份_{timestamp}.csv")
        final_excel = os.path.join(export_dir, f"查询结果导出_{timestamp}.xlsx")

        with open(backup_csv, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=headers_list)
            writer.writeheader()

        results = []

        for index, row in df.iterrows():
            name = str(row.get('姓名', '')).strip()
            id_card_raw = str(row.get('身份证', row.get('身份证号', '')))
            id_card = re.sub(r'[^0-9Xx]', '', id_card_raw).upper()
            phone = str(row.get('电话号码', '13888888888')).strip()

            if phone == 'nan' or not phone or phone == '':
                phone = '13888888888'
            if phone.endswith('.0'):
                phone = phone[:-2]

            self.log(f"--- 处理: {name} ({id_card[:6]}****{id_card[-4:]}) ---")

            row_data = {key: "-" for key in headers_list}
            row_data["姓名"] = name
            row_data["身份证号"] = id_card
            row_data["电话号码"] = phone

            try:
                # 1. 占位查询
                payload1 = CryptoUtil.encrypt_payload({
                    "name": name, "idN": id_card, "phone": phone,
                    "apitype": 4, "nickname": "济南默默电子商务有限公司", "usr": 7
                })
                self.session.post("https://search.azbbzzc.com/htOrderss/checkOne",
                                  json=payload1, timeout=30)

                # 2. 生成订单
                payload2 = CryptoUtil.encrypt_payload({
                    "name": name, "idN": id_card, "phone": phone,
                    "apitype": "10", "nickname": "测试手机租赁", "usr": 67
                })
                res2 = self.session.post("https://search.azbbzzc.com/htOrderss",
                                         json=payload2, timeout=30)

                order_id = None
                try:
                    order_id = res2.json().get("id")
                except:
                    pass

                if order_id:
                    self.log(f"订单生成成功 ID:{order_id}")

                    # 3. 二要素核验
                    auth_params = {"name": name, "id": id_card, "type": 1, "order_id": str(order_id)}
                    res_auth = self.session.post("https://search.azbbzzc.com/auth_895w6q",
                                                 params=auth_params, timeout=30)
                    auth_json = res_auth.json()

                    if str(auth_json.get("code")) == "0":
                        row_data["核验结果"] = "一致"
                        self.log("核验一致，检查逾期...")

                        # 4. 检查逾期
                        overdue_url = f"https://search.azbbzzc.com/htOrderss/checkOverdue/{order_id}"
                        res_overdue = self.session.post(overdue_url, json={}, timeout=30)

                        mark_m12_count = 0
                        try:
                            mark_m12_count = res_overdue.json().get("data", {}).get("data", {}).get("markM12Count", 0)
                        except:
                            pass

                        if mark_m12_count != 0:
                            row_data["黑名单核验"] = "命中"
                            self.log("命中逾期，跳过查询")
                        else:
                            row_data["黑名单核验"] = "未命中"
                            self.log("未命中逾期，查询小雷达...")

                            # 5. 触发小雷达
                            payload_check2 = {"apiTpye": 15, "order_id": str(order_id)}
                            self.session.post("https://search.azbbzzc.com/htOrderss/checkTwo",
                                              json=payload_check2, timeout=30)

                            # 6. 轮询获取详情（关键修复：增加等待时间和重试次数）
                            max_retries = 8  # 增加到8次
                            detail_params = {
                                "name": name, "id": id_card, "phone": phone,
                                "type": 1, "order_id": str(order_id)
                            }

                            detail_success = False
                            for attempt in range(max_retries):
                                # 第一次等待3秒，后续每次递减
                                wait_time = max(1, 4 - attempt // 2)
                                time.sleep(wait_time)

                                try:
                                    res_detail = self.session.post(
                                        "https://search.azbbzzc.com/xyUnifyB",
                                        params=detail_params,
                                        timeout=30,
                                        headers={"token": token}  # 显式带上 token
                                    )
                                    detail_json = res_detail.json()

                                    if str(detail_json.get("code")) == "0":
                                        details = detail_json.get("data", {}).get("result_detail")
                                        if details and isinstance(details, dict):
                                            for code, val in details.items():
                                                if code in FIELD_MAP:
                                                    row_data[FIELD_MAP[code]] = val
                                            self.log(f"详情获取成功！")
                                            detail_success = True
                                            break
                                        else:
                                            self.log(f"报告生成中 ({attempt + 1}/{max_retries})...")
                                    else:
                                        error_msg = detail_json.get("msg", "未知错误")
                                        if "加密" in error_msg or "约束" in error_msg:
                                            self.log(f"API返回错误: {error_msg}，重试中...")
                                        else:
                                            self.log(f"获取失败: {error_msg}")
                                except Exception as req_e:
                                    self.log(f"请求异常: {str(req_e)[:50]}，重试...")

                            if not detail_success:
                                self.log("详情获取超时，跳过")
                    else:
                        row_data["核验结果"] = f"不一致: {auth_json.get('msg', '')}"
                        self.log(f"核验不一致")
                else:
                    row_data["核验结果"] = "订单生成失败"
                    self.log(f"订单失败: {res2.text[:100]}")

            except Exception as inner_e:
                self.log(f"异常: {str(inner_e)[:100]}")
                row_data["核验结果"] = "查询异常"

            results.append(row_data)
            self.save_to_csv_realtime(row_data, backup_csv, headers_list)
            time.sleep(1.5)  # 控制请求频率

        # 导出结果
        pd.DataFrame(results).to_excel(final_excel, index=False)
        self.log(f"完成！导出到: {final_excel}")
        self.root.after(0, lambda: messagebox.showinfo("完成", f"查询完成！\n{final_excel}"))

    except Exception as e:
        self.log(f"严重错误: {str(e)}")
        self.root.after(0, lambda: messagebox.showerror("错误", str(e)))

if __name__ == "__main__":
    root = tk.Tk()
    app = QueryApp(root)
    root.mainloop()