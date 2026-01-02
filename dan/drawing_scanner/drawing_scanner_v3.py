import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import pathlib
import os
import base64
import json
import requests


class DrawingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("图纸版本标识识别工具 V3 (专业过滤版)")
        self.root.geometry("850x650")

        # 默认配置
        self.default_base_url = "http://jeniya.cn"
        self.default_model = "gemini-3-flash-preview"
        self.default_token = "sk-KXrmyl8xw4jobewx8RaEM3c6uaMtjYGNErj2UxiKe6n5Ko3w"

        self.setup_ui()

    def setup_ui(self):
        config_frame = tk.LabelFrame(self.root, text="API 配置", padx=10, pady=10)
        config_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(config_frame, text="Authorization Token:").grid(row=0, column=0, sticky="w")
        self.token_entry = tk.Entry(config_frame, width=60)
        self.token_entry.insert(0, self.default_token)
        self.token_entry.grid(row=0, column=1, padx=5, pady=2)

        tk.Label(config_frame, text="模型名称:").grid(row=1, column=0, sticky="w")
        self.model_entry = tk.Entry(config_frame, width=60)
        self.model_entry.insert(0, self.default_model)
        self.model_entry.grid(row=1, column=1, padx=5, pady=2)

        tk.Label(config_frame, text="中转 Base URL:").grid(row=2, column=0, sticky="w")
        self.url_entry = tk.Entry(config_frame, width=60)
        self.url_entry.insert(0, self.default_base_url)
        self.url_entry.grid(row=2, column=1, padx=5, pady=2)

        file_frame = tk.Frame(self.root, padx=10, pady=10)
        file_frame.pack(fill="x")

        self.file_path_var = tk.StringVar(value="未选择文件")
        tk.Label(file_frame, textvariable=self.file_path_var, fg="#333", wraplength=600, justify="left").pack(
            side="left")
        tk.Button(file_frame, text="选择 PDF 图纸", command=self.select_file, width=15).pack(side="right")

        self.run_btn = tk.Button(self.root, text="开始识别", command=self.start_thread, bg="#28a745", fg="white",
                                 height=2, font=("Arial", 10, "bold"))
        self.run_btn.pack(fill="x", padx=10, pady=10)

        tk.Label(self.root, text="识别结果输出:").pack(anchor="w", padx=10)
        self.log_area = scrolledtext.ScrolledText(self.root, state='disabled', wrap=tk.WORD, bg="#1e1e1e", fg="#d4d4d4",
                                                  font=("Consolas", 11))
        self.log_area.pack(expand=True, fill="both", padx=10, pady=10)

    def log(self, message, clear=False):
        self.log_area.configure(state='normal')
        if clear:
            self.log_area.delete(1.0, tk.END)
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')
        self.root.update_idletasks()

    def select_file(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self.file_path_var.set(path)
            self.log(f"[系统] 已选择: {os.path.basename(path)}", clear=True)

    def start_thread(self):
        file_path = self.file_path_var.get()
        if file_path == "未选择文件":
            messagebox.showwarning("提示", "请先选择 PDF 文件")
            return

        self.run_btn.config(state="disabled", text="正在高精度分析中...")
        thread = threading.Thread(target=self.process_request, args=(file_path,))
        thread.start()

    def process_request(self, file_path):
        token = self.token_entry.get().strip()
        model = self.model_entry.get().strip()
        base_url = self.url_entry.get().strip().rstrip('/')
        api_url = f"{base_url}/v1beta/models/{model}:generateContent"

        try:
            self.log("[任务] 正在读取并准备上传...")
            with open(file_path, "rb") as f:
                pdf_base64 = base64.b64encode(f.read()).decode('utf-8')

            # 核心改进：极其严苛的规则，明确区分“表头”和“修改标识”
            prompt = """
            任务：识别PDF图纸中的独立版本更新标识（Revision Tag）。

            **严格判定准则：**
            1. 必须是【纯粹的、独立的方框包含一个大写字母】（如 [B]）。
            2. **【重要过滤规则】**：严禁识别表格（如标题栏、修改记录表）内部的表头文字。
               - 例如：表格顶部的 "REV. B"、"B REV." 或 "NUMB" 属于表格结构，【不属于】版本修改标识，必须忽略。
            3. 只寻找悬浮在图纸绘图区域、尺寸线旁、视图标题旁的独立方框标识。
            4. 必须使用【中文】回答。禁止任何分析过程或英文废话。

            **输出格式：**
            版本字母：[主版本字母]
            位置 1：[区域坐标，如A4] 区域
            描述：[标识所在位置，例如：位于尺寸 4.35 下方]
            ...
            """

            payload = {
                "contents": [{
                    "role": "user",
                    "parts": [
                        {"inline_data": {"mime_type": "application/pdf", "data": pdf_base64}},
                        {"text": prompt}
                    ]
                }]
            }

            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

            self.log(f"[任务] 正在进行视觉分析...")
            response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=90)

            if response.status_code == 200:
                resp_json = response.json()
                try:
                    result_text = resp_json['candidates'][0]['content']['parts'][0]['text']
                    self.log("\n================ 识别结果 ================", clear=True)
                    self.log(result_text.strip())
                    self.log("==========================================")
                except:
                    self.log(f"[错误] 解析异常: {response.text}")
            else:
                self.log(f"[错误] 状态码: {response.status_code}")

        except Exception as e:
            self.log(f"[异常] {str(e)}")

        finally:
            self.run_btn.config(state="normal", text="开始识别")


if __name__ == "__main__":
    root = tk.Tk()
    app = DrawingApp(root)
    root.mainloop()