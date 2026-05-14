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
import traceback
from urllib.parse import quote
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad

# 字段精准映射
FIELD_MAP = {
    "B22170002": "近1个月贷款笔数", "B22170003": "近3个月贷款笔数",
    "B22170004": "近6个月贷款笔数", "B22170005": "近12个月贷款笔数",
    "B22170006": "近24个月贷款笔数", "B22170007": "近1个月贷款总金额",
    "B22170008": "近3个月贷款总金额", "B22170009": "近6个月贷款总金额",
    "B22170010": "近12个月贷款总金额", "B22170011": "近24个月贷款总金额"
}


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
        json_string = json.dumps(data_dict, separators=(',', ':'), ensure_ascii=False, sort_keys=True).encode('utf-8')
        aes_key_str = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))
        aes_key = aes_key_str.encode('utf-8')
        cipher = AES.new(aes_key, AES.MODE_ECB)
        encrypted_data = base64.b64encode(cipher.encrypt(pad(json_string, AES.block_size))).decode('utf-8')
        rsa_key = RSA.import_key(CryptoUtil.PUBLIC_KEY)
        cipher_rsa = PKCS1_v1_5.new(rsa_key)
        encrypted_aes_key = base64.b64encode(cipher_rsa.encrypt(aes_key)).decode('utf-8')
        return {"encryptedKey": encrypted_aes_key, "encryptedData": encrypted_data}


class QueryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("API 高速自动化查询工具 (原始日志诊断版)")
        self.root.geometry("750x650")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest"
        })
        self.excel_path = tk.StringVar();
        self.export_path = tk.StringVar()
        self.username = tk.StringVar(value="qq888");
        self.password = tk.StringVar(value="qq888")
        self.setup_ui()

    def setup_ui(self):
        frame_login = tk.LabelFrame(self.root, text="登录设置", padx=10, pady=10);
        frame_login.pack(fill="x", padx=10, pady=5)
        tk.Label(frame_login, text="账号:").grid(row=0, column=0);
        tk.Entry(frame_login, textvariable=self.username, width=20).grid(row=0, column=1)
        tk.Label(frame_login, text="密码:").grid(row=0, column=2);
        tk.Entry(frame_login, textvariable=self.password, show="*", width=20).grid(row=0, column=3)
        frame_file = tk.LabelFrame(self.root, text="文件与路径", padx=10, pady=10);
        frame_file.pack(fill="x", padx=10, pady=5)
        tk.Entry(frame_file, textvariable=self.excel_path, width=55, state="readonly").grid(row=0, column=1)
        tk.Button(frame_file, text="导入Excel", command=self.select_file).grid(row=0, column=2)
        tk.Entry(frame_file, textvariable=self.export_path, width=55, state="readonly").grid(row=1, column=1)
        tk.Button(frame_file, text="选择目录", command=self.select_export_dir).grid(row=1, column=2)
        tk.Button(self.root, text="开始执行任务", bg="green", fg="white", font=("Arial", 12, "bold"),
                  command=self.start_task_thread).pack(pady=10)
        frame_log = tk.LabelFrame(self.root, text="运行详细日志", padx=10, pady=10);
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(frame_log, wrap=tk.WORD);
        self.log_text.pack(fill="both", expand=True)

    def log(self, message):
        self.root.after(0, lambda: self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n"))
        self.root.after(0, lambda: self.log_text.see(tk.END))

    def select_file(self):
        p = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xls")]);
        if p: self.excel_path.set(p)

    def select_export_dir(self):
        p = filedialog.askdirectory();
        if p: self.export_path.set(p)

    def start_task_thread(self):
        if not self.excel_path.get() or not self.export_path.get(): return
        threading.Thread(target=self.run_automation, daemon=True).start()

    def safe_parse_json(self, response, label=""):
        """安全解析JSON，失败时打印原始报错内容"""
        try:
            return response.json()
        except Exception:
            self.log(f"!!! {label} 接口返回非JSON格式数据 !!!")
            self.log(f"状态码: {response.status_code}")
            self.log(f"服务器原始返回内容: {response.text}")
            return None

    def run_automation(self):
        self.log("开始查询流程...")
        try:
            self.session.get("https://search.azbbzzc.com/login.html")
            login_res = self.session.post("https://search.azbbzzc.com/login",
                                          data={"username": self.username.get(), "password": self.password.get()})
            login_data = self.safe_parse_json(login_res, "登录")
            if not login_data: return

            token = login_data.get("token")
            if not token: return self.log("登录失败：未获取到 token")

            req_headers = {"token": token, "Content-Type": "application/json"}
            df = pd.read_excel(self.excel_path.get(), dtype=str)
            headers_list = ["姓名", "身份证号", "电话号码", "核验结果", "黑名单核验", "近1个月贷款笔数",
                            "近3个月贷款笔数", "近6个月贷款笔数", "近12个月贷款笔数", "近24个月贷款笔数",
                            "近1个月贷款总金额", "近3个月贷款总金额", "近6个月贷款总金额", "近12个月贷款总金额",
                            "近24个月贷款总金额"]

            timestamp = int(time.time());
            final_excel = os.path.join(self.export_path.get(), f"查询导出_{timestamp}.xlsx")
            results = []

            for index, row in df.iterrows():
                name = str(row.get('姓名', '')).strip()
                id_card = re.sub(r'\s+', '', str(row.get('身份证', row.get('身份证号', '')))).upper()
                phone = str(row.get('电话号码', '13888888888')).strip()
                if phone == 'nan' or not phone: phone = '13888888888'

                self.log(f"--- 正在处理: {name} ---")
                row_data = {key: "-" for key in headers_list}
                row_data.update(
                    {"姓名": name, "身份证号": id_card, "电话号码": phone, "核验结果": "", "黑名单核验": ""})

                try:
                    # 1. 缓存与下单
                    payload1 = CryptoUtil.encrypt_payload(
                        {"name": name, "idN": id_card, "phone": phone, "apitype": 4, "nickname": "测试", "usr": 7})
                    self.session.post("https://search.azbbzzc.com/htOrderss/checkOne", json=payload1,
                                      headers=req_headers)

                    payload2 = CryptoUtil.encrypt_payload(
                        {"name": name, "idN": id_card, "phone": phone, "apitype": 10, "nickname": "测试", "usr": 67})
                    res2_raw = self.session.post("https://search.azbbzzc.com/htOrderss", json=payload2,
                                                 headers=req_headers)
                    res2 = self.safe_parse_json(res2_raw, f"{name} 下单接口")

                    if not res2 or not isinstance(res2, dict):
                        self.log(f"{name} 流程中断：下单接口返回数据异常");
                        results.append(row_data);
                        continue

                    order_id = res2.get("id");
                    masked_id = res2.get("idN")

                    if order_id and masked_id:
                        safe_name = quote(name);
                        safe_id = quote(masked_id)
                        referer_url = f"https://search.azbbzzc.com/pages/user/updateUser.html?name={safe_name}&id={safe_id}&apitype=10&order_id={order_id}"
                        current_headers = req_headers.copy()
                        current_headers["Referer"] = referer_url

                        # 2. 真实核验
                        auth_url = f"https://search.azbbzzc.com/auth_895w6q?name={safe_name}&id={safe_id}&type=1&order_id={order_id}"
                        res_auth_raw = self.session.post(auth_url, headers=current_headers)
                        res_auth = self.safe_parse_json(res_auth_raw, f"{name} 核验接口")

                        if res_auth and str(res_auth.get("code")) == "0":
                            row_data["核验结果"] = "一致";
                            self.log(f"{name} 核验一致")

                            # 3. 逾期拦截
                            res_over_raw = self.session.post(
                                f"https://search.azbbzzc.com/htOrderss/checkOverdue/{order_id}", json={},
                                headers=current_headers)
                            res_over = self.safe_parse_json(res_over_raw, f"{name} 逾期接口")

                            m12 = 0
                            if res_over and isinstance(res_over, dict):
                                m12 = res_over.get("data", {}).get("data", {}).get("markM12Count", 0)

                            if m12 != 0:
                                row_data["黑名单核验"] = "命中";
                                self.log(f"{name} 黑名单拦截 (markM12Count={m12})")
                            else:
                                row_data["黑名单核验"] = "未命中"
                                self.session.post("https://search.azbbzzc.com/htOrderss/checkTwo",
                                                  json={"apiTpye": 15, "order_id": str(order_id)},
                                                  headers=current_headers)

                                # 4. 轮询详情
                                for i in range(5):
                                    time.sleep(2.5)
                                    detail_url = f"https://search.azbbzzc.com/xyUnifyB?name={safe_name}&id={safe_id}&phone={phone}&type=1&order_id={order_id}"
                                    res_det_raw = self.session.post(detail_url, headers=current_headers)
                                    res_det = self.safe_parse_json(res_det_raw, f"{name} 详情接口重试{i + 1}")

                                    if res_det and isinstance(res_det, dict):
                                        details = res_det.get("data", {}).get("result_detail")
                                        if details:
                                            for c, v in details.items():
                                                if c in FIELD_MAP: row_data[FIELD_MAP[c]] = v
                                            self.log(f"{name} 详情获取成功");
                                            break
                                        else:
                                            self.log(f"{name} 报告生成中，等待重试...");
                                    else:
                                        break
                        else:
                            msg = res_auth.get('msg') if res_auth else "接口返回内容无法解析"
                            row_data["核验结果"] = "不一致";
                            self.log(f"{name} 不一致: {msg}")
                    else:
                        self.log(f"{name} 订单生成失败 (缺少ID或打码ID)")
                except Exception as e:
                    self.log(f"处理 {name} 时发生程序异常: {str(e)}")
                    self.log(f"异常堆栈详情:\n{traceback.format_exc()}")

                results.append(row_data);
                time.sleep(1.5)

            pd.DataFrame(results).to_excel(final_excel, index=False)
            self.log("任务全部完成");
            messagebox.showinfo("完成", f"已导出至: {final_excel}")
        except Exception as e:
            self.log(f"全局严重错误: {e}")
            self.log(traceback.format_exc())


if __name__ == "__main__":
    root = tk.Tk();
    app = QueryApp(root);
    root.mainloop()