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

# ==========================================
# 字段精准映射表
# ==========================================
FIELD_MAP = {
    "B22170035": "近1个月失败扣款笔数",
    "B22170045": "近1个月履约贷款次数",
    "B22170040": "近1个月履约贷款总金额",
    # M0/M1在近1和近3个月接口本身无数据，代码将自动填入 "-"
    "B22170036": "近3个月失败扣款笔数",
    "B22170046": "近3个月履约贷款次数",
    "B22170041": "近3个月履约贷款总金额",
    "B22170052": "贷款已结清订单数 （ 不限于24个月结清笔数 ）",
    "B22170054": "最近一次贷款放款时间",
    "B22170015": "近 12 个月贷款金额在 1w 以上的笔数",
    "B22170053": "信用贷款时长",
    "B22170034": "正常还款订单数占贷款总订单数比例",
    "B22170050": "最近一次履约距今天数"
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
        # 强制原生 UTF-8 编码加密
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
        self.root.title("API 高速自动化查询工具 (防断网优化版)")
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

    # ==========================================
    # 【核心新增】：断网安全挂起请求函数
    # ==========================================
    def safe_request(self, method, url, **kwargs):
        """带有无限重试机制的网络请求，专门应对断网和网络波动"""
        kwargs.setdefault('timeout', 15)  # 设置合理的超时时间，防止死锁
        while True:
            try:
                if method.upper() == 'GET':
                    return self.session.get(url, **kwargs)
                elif method.upper() == 'POST':
                    return self.session.post(url, **kwargs)
            except requests.exceptions.RequestException as e:
                # 捕获所有网络层面的异常（断网、超时、DNS解析失败等）
                self.log(f"⚠️ [网络异常] 失去连接，程序已自动挂起等待网络恢复... (5秒后重试)")
                time.sleep(5)

    def run_automation(self):
        self.log("开始初始化 API 客户端...")
        try:
            # 1. 执行登录 (使用 safe_request 保护)
            self.safe_request("GET", "https://search.azbbzzc.com/login.html")
            login_res = self.safe_request("POST", "https://search.azbbzzc.com/login",
                                          data={"username": self.username.get(), "password": self.password.get()})
            token = login_res.json().get("token")
            if not token:
                self.log("登录失败，未能获取到 Token。请检查账号密码。")
                return

            req_headers = {
                "token": token,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            # 2. 动态获取客户的专属 usr 和 nickname
            current_usr_id = None
            current_nickname = "未知客户"

            try:
                ts = int(time.time() * 1000)
                info_res = self.safe_request("GET", f"https://search.azbbzzc.com/users/current?_={ts}",
                                             headers=req_headers)
                if info_res.status_code == 200:
                    info_json = info_res.json()
                    current_usr_id = info_json.get("id")
                    current_nickname = info_json.get("nickname") or info_json.get("username")
            except Exception as e:
                self.log(f"获取账号信息异常: {str(e)}")

            if not current_usr_id:
                self.log("❌ 严重错误：无法自动获取到该账号的绑定信息！")
                return

            self.log(f"✅ 账号动态绑定成功！[账户名: {current_nickname}, 内部ID: {current_usr_id}]")

            df = pd.read_excel(self.excel_path.get(), dtype=str)

            # 客户要求的新表头
            headers_list = [
                "姓名", "身份证号", "电话号码", "核验结果", "黑名单核验",
                "近1个月失败扣款笔数", "近1个月履约贷款次数", "近1个月履约贷款总金额",
                "近1个月M0+逾期贷款笔数", "近1个月M1+逾期贷款笔数",
                "近3个月失败扣款笔数", "近3个月履约贷款次数", "近3个月履约贷款总金额",
                "近3个月M0+逾期贷款笔数", "近3个月M1+逾期贷款笔数",
                "贷款已结清订单数 （ 不限于24个月结清笔数 ）", "最近一次贷款放款时间",
                "近 12 个月贷款金额在 1w 以上的笔数", "信用贷款时长",
                "正常还款订单数占贷款总订单数比例", "最近一次履约距今天数"
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
                id_card = re.sub(r'[^a-zA-Z0-9]', '', str(row.get('身份证', row.get('身份证号', '')))).upper()
                phone = str(row.get('电话号码', '13888888888')).strip()
                if phone == 'nan' or not phone: phone = '13888888888'
                if phone.endswith('.0'): phone = phone[:-2]

                self.log(f"--- 正在处理: {name} (身份证: {id_card[:6]}****{id_card[-4:]}) ---")

                # 初始化默认值 "-"
                row_data = {key: "-" for key in headers_list}
                row_data["姓名"] = name
                row_data["身份证号"] = id_card
                row_data["电话号码"] = phone
                row_data["核验结果"] = ""
                row_data["黑名单核验"] = ""

                try:
                    payload1 = CryptoUtil.encrypt_payload(
                        {"name": name, "idN": id_card, "phone": phone, "apitype": 4, "nickname": current_nickname,
                         "usr": current_usr_id})
                    self.safe_request("POST", "https://search.azbbzzc.com/htOrderss/checkOne", json=payload1,
                                      headers=req_headers)

                    payload2 = CryptoUtil.encrypt_payload(
                        {"name": name, "idN": id_card, "phone": phone, "apitype": "10", "nickname": current_nickname,
                         "usr": current_usr_id})
                    res2 = self.safe_request("POST", "https://search.azbbzzc.com/htOrderss", json=payload2,
                                             headers=req_headers)

                    order_id = res2.json().get("id") if res2.status_code == 200 else None

                    if order_id:
                        self.log(f"{name} 计费订单生成成功 (ID: {order_id})")

                        auth_params = {"name": name, "id": id_card, "type": 1, "order_id": str(order_id)}
                        res_auth = self.safe_request("POST", "https://search.azbbzzc.com/auth_895w6q",
                                                     params=auth_params, headers=req_headers)
                        auth_json = res_auth.json()

                        if str(auth_json.get("code")) == "0":
                            self.log(f"{name} 真实核验结果：一致。正在查询逾期...")
                            row_data["核验结果"] = "一致"

                            overdue_url = f"https://search.azbbzzc.com/htOrderss/checkOverdue/{order_id}"
                            res_overdue = self.safe_request("POST", overdue_url, json={}, headers=req_headers)

                            mark_m12_count = 0
                            try:
                                mark_m12_count = res_overdue.json().get("data", {}).get("data", {}).get("markM12Count",
                                                                                                        0)
                            except Exception:
                                pass

                            if mark_m12_count != 0:
                                row_data["黑名单核验"] = "命中"
                                self.log(f"{name} 逾期命中，跳过小雷达查询。")
                            else:
                                row_data["黑名单核验"] = "未命中"
                                self.log(f"{name} 逾期未命中，触发小雷达A版...")

                                payload_check2 = {"apiTpye": 15, "order_id": str(order_id)}
                                self.safe_request("POST", "https://search.azbbzzc.com/htOrderss/checkTwo",
                                                  json=payload_check2, headers=req_headers)

                                # 【极速单次拉取】：去掉了 5 次重试，只等待 2 秒拉取一次
                                time.sleep(2)
                                detail_params = {"name": name, "id": id_card, "phone": phone, "type": 1,
                                                 "order_id": str(order_id)}
                                res_detail = self.safe_request("POST", "https://search.azbbzzc.com/xyUnifyB",
                                                               params=detail_params, headers=req_headers)
                                detail_json = res_detail.json()

                                if str(detail_json.get("code")) == "0":
                                    details = detail_json.get("data", {}).get("result_detail")
                                    if details:  # 包含有效数据
                                        for code, val in details.items():
                                            if code in FIELD_MAP:
                                                row_data[FIELD_MAP[code]] = val
                                        self.log(f"{name} 详情数据拉取并解析成功！")
                                    else:
                                        # 数据确认为空，不重试，直接判定无数据
                                        self.log(f"{name} 查询无数据（该用户无相关雷达记录）。")
                                else:
                                    self.log(f"{name} 获取详情失败: {detail_json.get('msg')}")
                        else:
                            self.log(f"{name} 核验不一致: {auth_json.get('msg')}")
                            row_data["核验结果"] = "不一致"
                            row_data["黑名单核验"] = "-"
                    else:
                        self.log(f"{name} 订单生成失败: {res2.text}")
                        row_data["核验结果"] = "订单生成失败"
                        row_data["黑名单核验"] = "-"

                except Exception as inner_e:
                    # 这边的 exception 仅处理 JSON 解析失败、字典不存在等代码级报错
                    # 断网类异常已在 safe_request 中无限拦截，不会抛到这里导致跳过
                    self.log(f"{name} 数据处理异常: {str(inner_e)}")
                    row_data["核验结果"] = "查询异常"

                # 保存到结果集，并追加写入 CSV 备份
                results.append(row_data)
                self.save_to_csv_realtime(row_data, backup_csv, headers_list)

                # 防刷频安全间隔
                time.sleep(random.uniform(1.5, 2.5))

            # --- 导出最终结果 ---
            output_df = pd.DataFrame(results)
            output_df.to_excel(final_excel, index=False)
            self.log("--- 任务全部完成！ ---")
            self.root.after(0, lambda: messagebox.showinfo("完成", f"全部查询顺利完成！\n数据已保存为:\n{final_excel}"))

        except Exception as e:
            self.log(f"执行中断，严重错误: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("错误", f"程序未能执行到底:\n{str(e)}"))


if __name__ == "__main__":
    root = tk.Tk()
    app = QueryApp(root)
    root.mainloop()