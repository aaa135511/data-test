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
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad

# 字段映射表 (JSON编码 -> Excel表头)
FIELD_MAP = {
    "B22170019": "当前逾期机构数",
    "B22170018": "当前履约机构数",
    "B22170020": "异常还款机构数",
    "B22170021": "睡眠机构数",
    "B22170044": "最大履约金额",
    "B22170054": "最近履约时间",
    "B22170042": "最近逾期时间",
    "B22170048": "履约笔数",
    "B22170050": "最长逾期天数",
    "B22170008": "最大逾期金额"
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
        json_string = json.dumps(data_dict, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        aes_key = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32)).encode()
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
        self.root.title("API 高速自动化查询工具 (含逾期拦截)")
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

            # --- 更新表头：增加黑名单核验 ---
            headers_list = [
                "姓名", "身份证", "核验结果", "黑名单核验", "当前逾期机构数", "当前履约机构数",
                "异常还款机构数", "睡眠机构数", "最大履约金额", "最近履约时间",
                "最近逾期时间", "履约笔数", "最长逾期天数", "最大逾期金额"
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
                name = str(row['姓名']).strip()
                id_card = str(row['身份证']).strip()
                if id_card.endswith('.0'): id_card = id_card[:-2]

                self.log(f"--- 正在处理: {name} (身份证: {id_card[:6]}****{id_card[-4:]}) ---")

                # 初始化默认值
                row_data = {key: "" for key in headers_list}
                row_data["姓名"] = name
                row_data["身份证"] = id_card
                row_data["黑名单核验"] = "-"  # 默认值为 -

                try:
                    # 1. 查询缓存
                    payload1 = CryptoUtil.encrypt_payload(
                        {"name": name, "idN": id_card, "phone": "13888888888", "apitype": 4,
                         "nickname": "济南默默电子商务有限公司", "usr": 7})
                    self.session.post("https://search.azbbzzc.com/htOrderss/checkOne", json=payload1,
                                      headers=req_headers)

                    # 2. 生成订单
                    payload2 = CryptoUtil.encrypt_payload(
                        {"name": name, "idN": id_card, "phone": "13888888888", "apitype": "10",
                         "nickname": "测试手机租赁", "usr": 67})
                    res2 = self.session.post("https://search.azbbzzc.com/htOrderss", json=payload2, headers=req_headers)

                    order_id = None
                    try:
                        order_id = res2.json().get("id")
                    except Exception:
                        pass

                    if order_id:
                        self.log(f"{name} 计费订单生成成功 (ID: {order_id})")

                        # 3. 核心步骤：真实二要素核验
                        auth_params = {"name": name, "id": id_card, "type": 1, "order_id": str(order_id)}
                        res_auth = self.session.post("https://search.azbbzzc.com/auth_895w6q", params=auth_params,
                                                     headers=req_headers)
                        auth_json = res_auth.json()

                        # 判断真实核验结果
                        if str(auth_json.get("code")) == "0":
                            self.log(f"{name} 真实核验结果：一致。正在查询逾期...")
                            row_data["核验结果"] = "一致"

                            # ----------------------------------------
                            # 4. 新增步骤：查询逾期并拦截
                            # ----------------------------------------
                            overdue_url = f"https://search.azbbzzc.com/htOrderss/checkOverdue/{order_id}"
                            res_overdue = self.session.post(overdue_url, json={}, headers=req_headers)
                            overdue_json = res_overdue.json()

                            # 防御式解析 JSON，提取 markM12Count
                            mark_m12_count = 0
                            try:
                                outer_data = overdue_json.get("data") or {}
                                inner_data = outer_data.get("data") or {}
                                mark_m12_count = inner_data.get("markM12Count", 0)
                            except Exception:
                                pass

                            if mark_m12_count != 0:
                                # 命中拦截，不再查询小雷达
                                row_data["黑名单核验"] = "命中"
                                self.log(f"{name} 逾期命中 (markM12Count: {mark_m12_count})，跳过小雷达详情查询。")
                            else:
                                # 未命中，继续查询小雷达
                                row_data["黑名单核验"] = "未命中"
                                self.log(f"{name} 逾期未命中，正在触发小雷达A版...")

                                # 5. 触发小雷达
                                payload_check2 = {"apiTpye": 15, "order_id": str(order_id)}
                                self.session.post("https://search.azbbzzc.com/htOrderss/checkTwo", json=payload_check2,
                                                  headers=req_headers)
                                time.sleep(1)  # 等待报告生成

                                # 6. 拉取详情数据
                                detail_params = {"name": name, "id": id_card, "phone": "13888888888", "type": 1,
                                                 "order_id": str(order_id)}
                                res_detail = self.session.post("https://search.azbbzzc.com/xyUnifyB",
                                                               params=detail_params, headers=req_headers)
                                detail_json = res_detail.json()

                                if str(detail_json.get("code")) == "0":
                                    data_dict = detail_json.get("data") or {}
                                    details = data_dict.get("result_detail") or {}

                                    # 将拉取到的数据填入 Excel 列中
                                    for code, val in details.items():
                                        if code in FIELD_MAP:
                                            row_data[FIELD_MAP[code]] = val
                                    self.log(f"{name} 详情数据拉取并解析成功！")
                                else:
                                    self.log(f"{name} 获取详情失败: {detail_json.get('msg')}")

                        else:
                            # auth 接口返回不一致
                            self.log(f"{name} 真实核验结果：不一致 ({auth_json.get('msg')})")
                            row_data["核验结果"] = "不一致"
                            row_data["黑名单核验"] = "-"
                    else:
                        self.log(f"{name} 订单生成失败。HTTP状态: {res2.status_code}, 服务器返回: {res2.text}")
                        row_data["核验结果"] = "订单生成失败"
                        row_data["黑名单核验"] = "-"

                except Exception as inner_e:
                    self.log(f"{name} 查询异常: {str(inner_e)}")
                    row_data["核验结果"] = "查询异常"

                # 实时保存到备份CSV
                results.append(row_data)
                self.save_to_csv_realtime(row_data, backup_csv, headers_list)

                # --- 防刷频安全间隔机制 ---
                sleep_time = random.uniform(1.5, 2.5)
                time.sleep(sleep_time)

            # --- 全部查完，导出最终 Excel ---
            output_df = pd.DataFrame(results)
            output_df.to_excel(final_excel, index=False)
            self.log("--- 任务全部完成！ ---")
            self.log(f"最终结果已保存在: {final_excel}")

            self.root.after(0, lambda: messagebox.showinfo("完成", f"全部查询顺利完成！\n数据已保存为:\n{final_excel}"))

        except Exception as e:
            self.log(f"执行中断，严重错误: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("错误", f"程序未能执行到底:\n{str(e)}"))


if __name__ == "__main__":
    root = tk.Tk()
    app = QueryApp(root)
    root.mainloop()