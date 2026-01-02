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
        self.root.title("图纸版本标识识别工具 V2 (精简中文版)")
        self.root.geometry("850x650")

        # 默认配置
        self.default_base_url = "http://jeniya.cn"
        self.default_model = "gemini-3-flash-preview"  # 建议用这个，gemini-3-flash-preview 如果有效也可手动改
        self.default_token = "sk-KXrmyl8xw4jobewx8RaEM3c6uaMtjYGNErj2UxiKe6n5Ko3w"

        self.setup_ui()

    def setup_ui(self):
        # 参数配置区
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

        # 文件选择区
        file_frame = tk.Frame(self.root, padx=10, pady=10)
        file_frame.pack(fill="x")

        self.file_path_var = tk.StringVar(value="未选择文件")
        tk.Label(file_frame, textvariable=self.file_path_var, fg="#333", wraplength=600, justify="left").pack(
            side="left")
        tk.Button(file_frame, text="选择 PDF 图纸", command=self.select_file, width=15).pack(side="right")

        # 操作按钮
        self.run_btn = tk.Button(self.root, text="开始识别", command=self.start_thread, bg="#28a745", fg="white",
                                 height=2, font=("Arial", 10, "bold"))
        self.run_btn.pack(fill="x", padx=10, pady=10)

        # 日志输出控制台
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

        self.run_btn.config(state="disabled", text="正在识别并分析中...")
        thread = threading.Thread(target=self.process_request, args=(file_path,))
        thread.start()

    def process_request(self, file_path):
        token = self.token_entry.get().strip()
        model = self.model_entry.get().strip()
        base_url = self.url_entry.get().strip().rstrip('/')
        api_url = f"{base_url}/v1beta/models/{model}:generateContent"

        try:
            self.log("[任务] 正在读取图纸...")
            with open(file_path, "rb") as f:
                pdf_base64 = base64.b64encode(f.read()).decode('utf-8')

            # 修改后的 Prompt：极其严格地控制语言和格式
            prompt = """
                    任务：识别PDF图纸中带方框的版本标识（如 [C]）。

                    **严格规则（必须遵守）：**
                    1. 全程仅限使用【中文】。
                    2. 严禁输出任何分析过程、自我介绍、开场白（如 "Okay, so I..."）或结束语。
                    3. 严禁输出任何英文内容。
                    4. 仅输出最终的识别结果。

                    **参考示例（必须按此格式）：**
                    版本字母：A
                    位置 1：B2 区域
                    描述：位于标注123旁边
                    位置 2：C4 区域
                    描述：位于标题下方

                    **现在请开始识别并直接输出结果：**
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

            self.log(f"[任务] 正在分析图纸，请稍后...")
            response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=90)

            if response.status_code == 200:
                resp_json = response.json()
                try:
                    result_text = resp_json['candidates'][0]['content']['parts'][0]['text']
                    # 清理并显示结果
                    self.log("\n================ 识别结果 ================", clear=True)
                    self.log(result_text.strip())
                    self.log("==========================================")
                except:
                    self.log(f"[错误] API返回内容异常: {response.text}")
            else:
                self.log(f"[错误] 请求失败 (Status: {response.status_code}): {response.text}")

        except Exception as e:
            self.log(f"[异常] 发生错误: {str(e)}")

        finally:
            self.run_btn.config(state="normal", text="开始识别")


if __name__ == "__main__":
    root = tk.Tk()
    app = DrawingApp(root)
    root.mainloop()
