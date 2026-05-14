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
    "B22170002": "近1个月贷款笔数", "B22170003": "近3个月贷款笔数",
    "B22170004": "近6个月贷款笔数", "B22170005": "近12个月贷款笔数",
    "B22170006": "近24个月贷款笔数", "B22170007": "近1个月贷款总金额",
    "B22170008": "近3个月贷款总金额", "B22170009": "近6个月贷款总金额",
    "B22170010": "近12个月贷款总金额", "B22170011": "近24个月贷款总金额"
}


# --- 加密工具类 (全平台强兼容版) ---
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
        # 【关键修正】：增加 sort_keys=True
        # 确保字典在任何操作系统（Win7/Win10/Win11）下生成的字符串顺序完全一致
        json_string = json.dumps(data_dict, separators=(',', ':'), ensure_ascii=False, sort_keys=True).encode('utf-8')

        # 使用固定的字符集生成 AES Key
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
        self.root.title("API 高速自动化查询工具 (全系统兼容交付版)")
        self.root.geometry("680x600")
        self.session = requests.Session()
        # 强制设置 User-Agent，防止旧系统默认 UA 被服务器拦截
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

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
            messagebox.showwarning("警告", "请先选择路径！")
            return
        threading.Thread(target=self.run_automation, daemon=True).start()

    def save_to_csv_realtime(self, row_dict, csv_filename, headers_list):
        try:
            with open(csv_filename, mode='a', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=headers_list)
                writer.writerow(row_dict)
        except:
            pass

    def run_automation(self):
        self.log("开始初始化 API 客户端...")
        try:
            self.session.get("https://search.azbbzzc.com/login.html")
            login_res = self.session.post("https://search.azbbzzc.com/login",
                                          data={"username": self.username.get(), "password": self.password.get()})
            token = login_res.json().get("token")
            if not token:
                self.log("登录失败，未能获取到 Token。")
                return
            self.log("登录成功！准备开始批量查询...")

            req_headers = {"token": token, "Content-Type": "application/json"}
            df = pd.read_excel(self.excel_path.get(), dtype=str)

            headers_list = [
                "姓名", "身份证号", "电话号码", "核验结果", "黑名单核验",
                "近1个月贷款笔数", "近3个月贷款笔数", "近6个月贷款笔数", "近12个月贷款笔数", "近24个月贷款笔数",
                "近1个月贷款总金额", "近3个月贷款总金额", "近6个月贷款总金额", "近12个月贷款总金额", "近24个月贷款总金额"
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
                # 极致数据清洗
                name = str(row.get('姓名', '')).strip()
                id_card = re.sub(r'[^a-zA-Z0-9]', '', str(row.get('身份证', row.get('身份证号', '')))).upper()
                phone_raw = str(row.get('电话号码', '13888888888')).strip()
                if phone_raw.endswith('.0'): phone_raw = phone_raw[:-2]
                phone = phone_raw if phone_raw != 'nan' and phone_raw else '13888888888'

                self.log(f"--- 正在处理: {name} (身份证: {id_card[:6]}****{id_card[-4:]}) ---")

                row_data = {key: "-" for key in headers_list}
                row_data["姓名"] = name;
                row_data["身份证号"] = id_card;
                row_data["电话号码"] = phone
                row_data["核验结果"] = "";
                row_data["黑名单核验"] = ""

                try:
                    # 1. 查缓存
                    payload1 = CryptoUtil.encrypt_payload({"name": name, "idN": id_card, "phone": phone, "apitype": 4,
                                                           "nickname": "济南默默电子商务有限公司", "usr": 7})
                    self.session.post("https://search.azbbzzc.com/htOrderss/checkOne", json=payload1,
                                      headers=req_headers)

                    # 2. 生成计费订单
                    payload2 = CryptoUtil.encrypt_payload(
                        {"name": name, "idN": id_card, "phone": phone, "apitype": 10, "nickname": "测试手机租赁",
                         "usr": 67})
                    res2 = self.session.post("https://search.azbbzzc.com/htOrderss", json=payload2, headers=req_headers)

                    order_res_json = res2.json()
                    order_id = order_res_json.get("id") if res2.status_code == 200 else None

                    if order_id:
                        self.log(f"{name} 计费订单生成成功 (ID: {order_id})")

                        # 【全系统兼容修正】：必须提取服务器返回的打码身份证 idN
                        masked_id = order_res_json.get("idN")
                        if not masked_id: masked_id = id_card  # 防御性降级

                        # 3. 真实二要素核验 (URL 参数使用打码 ID)
                        auth_params = {"name": name, "id": masked_id, "type": 1, "order_id": str(order_id)}
                        res_auth = self.session.post("https://search.azbbzzc.com/auth_895w6q", params=auth_params,
                                                     headers=req_headers)
                        auth_json = res_auth.json()

                        if str(auth_json.get("code")) == "0":
                            self.log(f"{name} 真实核验结果：一致。正在查询逾期...")
                            row_data["核验结果"] = "一致"

                            res_overdue = self.session.post(
                                f"https://search.azbbzzc.com/htOrderss/checkOverdue/{order_id}", json={},
                                headers=req_headers)

                            mark_m12_count = 0
                            try:
                                mark_m12_count = res_overdue.json().get("data", {}).get("data", {}).get("markM12Count",
                                                                                                        0)
                            except:
                                pass

                            if mark_m12_count != 0:
                                row_data["黑名单核验"] = "命中"
                                self.log(f"{name} 逾期命中，跳过小雷达。")
                            else:
                                row_data["黑名单核验"] = "未命中"
                                self.log(f"{name} 逾期未命中，触发小雷达A版...")

                                # 4. 触发小雷达
                                self.session.post("https://search.azbbzzc.com/htOrderss/checkTwo",
                                                  json={"apiTpye": 15, "order_id": str(order_id)}, headers=req_headers)

                                # 5. 智能轮询 (使用打码 ID)
                                max_retries = 5
                                detail_params = {"name": name, "id": masked_id, "phone": phone, "type": 1,
                                                 "order_id": str(order_id)}

                                for attempt in range(max_retries):
                                    time.sleep(2)
                                    # POST 请求，参数在 URL 中，Body 为空字符串
                                    res_detail = self.session.post("https://search.azbbzzc.com/xyUnifyB",
                                                                   params=detail_params, data="", headers=req_headers)
                                    detail_json = res_detail.json()

                                    if str(detail_json.get("code")) == "0":
                                        details = detail_json.get("data", {}).get("result_detail")
                                        if details:
                                            for code, val in details.items():
                                                if code in FIELD_MAP: row_data[FIELD_MAP[code]] = val
                                            self.log(f"{name} 详情数据解析成功！")
                                            break
                                        else:
                                            self.log(f"{name} 报告生成中，等待重试 ({attempt + 1}/{max_retries})...")
                                    else:
                                        self.log(f"{name} 详情接口返回异常: {detail_json.get('msg')}")
                                        break
                        else:
                            self.log(f"{name} 核验不一致: {auth_json.get('msg')}")
                            row_data["核验结果"] = "不一致";
                            row_data["黑名单核验"] = "-"
                    else:
                        self.log(f"{name} 订单生成失败: {res2.text}")
                        row_data["核验结果"] = "订单生成失败"

                except Exception as inner_e:
                    self.log(f"{name} 查询异常: {str(inner_e)}")
                    row_data["核验结果"] = "查询异常"

                results.append(row_data)
                self.save_to_csv_realtime(row_data, backup_csv, headers_list)
                time.sleep(random.uniform(1.5, 2.5))

            output_df = pd.DataFrame(results)
            output_df.to_excel(final_excel, index=False)
            self.log("--- 任务完成！ ---")
            self.root.after(0, lambda: messagebox.showinfo("完成", f"任务已完成！\n路径:\n{final_excel}"))

        except Exception as e:
            self.log(f"严重错误: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = QueryApp(root)
    root.mainloop()