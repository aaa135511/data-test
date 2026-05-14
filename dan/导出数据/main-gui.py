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



if __name__ == "__main__":
    root = tk.Tk()
    app = QueryApp(root)
    root.mainloop()