import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk
import threading
import os
import base64
import json
import requests
import re


class DrawingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("智能图纸识别系统（AIRSIO）- 深度推理版")
        self.root.geometry("900x720")

        # 设置样式
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # ==========================================================
        # 默认配置 (用户指定)
        # ==========================================================
        self.default_base_url = "http://jeniya.cn"
        self.default_model = "gemini-3-flash-preview-thinking"  # 若此模型不可用，建议尝试 gemini-2.0-flash-thinking-exp
        self.default_token = "sk-KXrmyl8xw4jobewx8RaEM3c6uaMtjYGNErj2UxiKe6n5Ko3w"

        self.setup_ui()

    def setup_ui(self):
        # 1. 顶部配置区域
        config_frame = tk.LabelFrame(self.root, text="系统参数配置", padx=12, pady=10, font=("微软雅黑", 10, "bold"))
        config_frame.pack(fill="x", padx=15, pady=10)

        # Token
        tk.Label(config_frame, text="API Token:", font=("微软雅黑", 9)).grid(row=0, column=0, sticky="w")
        self.token_entry = tk.Entry(config_frame, width=50)
        self.token_entry.insert(0, self.default_token)
        self.token_entry.grid(row=0, column=1, padx=8, pady=5, sticky="w")

        # Model
        tk.Label(config_frame, text="推理模型:", font=("微软雅黑", 9)).grid(row=1, column=0, sticky="w")
        self.model_entry = tk.Entry(config_frame, width=35)
        self.model_entry.insert(0, self.default_model)
        self.model_entry.grid(row=1, column=1, padx=8, pady=5, sticky="w")
        tk.Label(config_frame, text="(已启用 Thinking 模式)", fg="#28a745", font=("微软雅黑", 8)).grid(row=1, column=2,
                                                                                                       sticky="w")

        # Base URL
        tk.Label(config_frame, text="Base URL:", font=("微软雅黑", 9)).grid(row=2, column=0, sticky="w")
        self.url_entry = tk.Entry(config_frame, width=50)
        self.url_entry.insert(0, self.default_base_url)
        self.url_entry.grid(row=2, column=1, padx=8, pady=5, sticky="w")

        # 2. 文件选择区域
        file_frame = tk.Frame(self.root, padx=5, pady=5)
        file_frame.pack(fill="x", padx=10)

        self.file_path_var = tk.StringVar(value="等待导入图纸...")

        # 路径显示框
        lbl_path = tk.Label(file_frame, textvariable=self.file_path_var,
                            bg="#f8f9fa", fg="#333", relief="solid", bd=1,
                            wraplength=600, justify="left", height=2, anchor="w", padx=10)
        lbl_path.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # 按钮
        btn_select = tk.Button(file_frame, text="📂 导入 PDF 图纸", command=self.select_file,
                               bg="#007bff", fg="white", font=("微软雅黑", 10), padx=15, relief="flat")
        btn_select.pack(side="right")

        # 3. 运行按钮
        self.run_btn = tk.Button(self.root, text="开始深度识别", command=self.start_thread,
                                 bg="#28a745", fg="white", height=2,
                                 font=("微软雅黑", 12, "bold"), state="disabled", relief="flat")
        self.run_btn.pack(fill="x", padx=15, pady=(5, 15))

        # 4. 日志区域
        log_header = tk.Frame(self.root)
        log_header.pack(fill="x", padx=15)
        tk.Label(log_header, text="识别报告:", font=("微软雅黑", 10, "bold")).pack(side="left")

        self.log_area = scrolledtext.ScrolledText(self.root, state='disabled', wrap=tk.WORD,
                                                  bg="#1e1e1e", fg="#00ff00",
                                                  font=("Consolas", 11), padx=10, pady=10)
        self.log_area.pack(expand=True, fill="both", padx=15, pady=(0, 5))

        # 5. 状态栏
        self.status_var = tk.StringVar(value="系统就绪")
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W, padx=10,
                              bg="#e9ecef")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def log(self, message, clear=False):
        self.log_area.configure(state='normal')
        if clear:
            self.log_area.delete(1.0, tk.END)
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')
        self.root.update_idletasks()

    def select_file(self):
        path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if path:
            self.file_path_var.set(path)
            self.run_btn.config(state="normal")
            self.log(f"已加载文件: {os.path.basename(path)}", clear=True)
            self.status_var.set("文件已就绪")

    def start_thread(self):
        file_path = self.file_path_var.get()
        if not os.path.exists(file_path):
            messagebox.showwarning("提示", "文件路径无效")
            return

        self.run_btn.config(state="disabled", text="AI 正在深度思考中...", bg="#6c757d")
        self.status_var.set("正在上传数据并进行推理分析...")

        thread = threading.Thread(target=self.process_request, args=(file_path,))
        thread.daemon = True
        thread.start()

    def process_request(self, file_path):
        token = self.token_entry.get().strip()
        model = self.model_entry.get().strip()
        base_url = self.url_entry.get().strip().rstrip('/')

        # 兼容 URL 格式
        if "generateContent" not in base_url:
            api_url = f"{base_url}/v1beta/models/{model}:generateContent"
        else:
            api_url = base_url

        try:
            self.log("[1/3] 读取并预处理图纸...")
            with open(file_path, "rb") as f:
                pdf_base64 = base64.b64encode(f.read()).decode('utf-8')

            # =======================================================
            # 核心 Prompt：结合 Thinking 能力与情景判断
            # =======================================================
            prompt = """
            **Role**: Senior Mechanical Inspector with high-level reasoning capabilities.
            **Objective**: Identify ALL "Revision Tags" (Modification Symbols) in the drawing area.

            **Thinking Process Requirements (Do this internally)**:
            1.  **Context Check**: First, determine the Global Revision letter from the Revision Table (e.g., is it Rev B?).
            2.  **Visual Scan**: Find all boxes/circles containing that letter (e.g., [B]).
            3.  **Complex Reasoning (Datum vs. Revision)**:
                *   *Scenario A (Datum)*: A box [B] connected to a surface line by a stem/triangle base. -> IGNORE.
                *   *Scenario B (Revision)*: A box [B] connected to a **Dimension Line** or **Extension Line**, AND the Global Revision matches B. -> **ACCEPT**. (This indicates the dimension value was changed).
                *   *Scenario C (Revision)*: A floating box [B] next to a dimension. -> **ACCEPT**.

            **Output Rules**:
            1.  Perform the reasoning in your thought block.
            2.  **Output Language**: Simplified Chinese (简体中文).
            3.  **Output Format**: Strictly follow the structure below. DO NOT output English thoughts in the final block.

            **Final Output Marker**: Start your final response with "【识别汇总】".

            **Format Template**:
            【识别汇总】
            检测到的版本号：[Letter]
            有效标识总数：[Number]

            【详细列表】
            1. 版本: [Letter] | 区域: [Grid, e.g., A4] | 类型: [悬浮/连线] | 描述: [位置描述, 如: 12.5尺寸旁]
            2. 版本: [Letter] | 区域: [Grid] | 类型: [悬浮/连线] | 描述: [...]
            (List all items found, including those connected to dimensions in Scenario B)
            """

            payload = {
                "contents": [{
                    "role": "user",
                    "parts": [
                        {"inline_data": {"mime_type": "application/pdf", "data": pdf_base64}},
                        {"text": prompt}
                    ]
                }],
                # =================================================
                # Thinking 模式参数配置 (High Level)
                # =================================================
                "generationConfig": {
                    "temperature": 0.7,  # 稍高的温度以支持推理辩证
                    "topK": 40,
                    "topP": 0.95,
                    "maxOutputTokens": 8192,  # 给予足够的思考长度
                    # 尝试启用 Thinking Config (适配 REST API)
                    "thinkingConfig": {"includeThoughts": True}
                }
            }

            headers = {
                'Content-Type': 'application/json'
            }
            # 处理鉴权
            if "googleapis" not in base_url:
                headers['Authorization'] = f'Bearer {token}'

            params = {}
            if "googleapis" in base_url:
                params["key"] = token

            self.log(f"[2/3] 发送深度推理请求 ({model})...")

            # 增加超时时间，因为 Thinking 模型生成速度较慢
            response = requests.post(api_url, headers=headers, params=params, data=json.dumps(payload), timeout=240)

            self.log("[3/3] 正在清洗思维链数据...")

            if response.status_code == 200:
                resp_json = response.json()

                try:
                    raw_text = ""

                    # 1. 拼接所有返回片段
                    if 'candidates' in resp_json and len(resp_json['candidates']) > 0:
                        candidate = resp_json['candidates'][0]
                        content_parts = candidate.get('content', {}).get('parts', [])

                        for part in content_parts:
                            if 'text' in part:
                                raw_text += part['text']

                        # ==========================================================
                        # 核心清洗逻辑：截取 "【识别汇总】" 之后的内容
                        # ==========================================================
                        marker = "【识别汇总】"

                        if marker in raw_text:
                            # 找到标记，丢弃前面的思考过程
                            clean_text = raw_text[raw_text.find(marker):]
                        else:
                            # 备用方案：如果没找到标记，尝试正则去除 xml 思考标签
                            clean_text = re.sub(r'<thought>.*?</thought>', '', raw_text, flags=re.DOTALL).strip()
                            # 如果还是空，说明模型可能直接输出了
                            if not clean_text: clean_text = raw_text

                        self.log("\n" + "=" * 20 + " 智能识别结果 " + "=" * 20, clear=True)
                        self.log(clean_text.strip())
                        self.log("=" * 50)

                        # 简单的数量统计检查
                        count_match = re.search(r'有效标识总数[：:]\s*(\d+)', clean_text)
                        if count_match:
                            self.status_var.set(f"识别完成，共发现 {count_match.group(1)} 个标识")
                        else:
                            self.status_var.set("识别完成")

                    else:
                        self.log("[警告] API 返回内容为空。可能是安全设置拦截。")
                        self.log(f"Debug: {json.dumps(resp_json)}")

                except Exception as e:
                    self.log(f"[解析错误] {str(e)}")
            else:
                self.log(f"[API 错误] 状态码: {response.status_code}")
                self.log(f"详情: {response.text}")

        except Exception as e:
            self.log(f"[系统异常] {str(e)}")
            messagebox.showerror("错误", f"发生未捕获异常:\n{str(e)}")

        finally:
            self.reset_ui()

    def reset_ui(self):
        self.run_btn.config(state="normal", text="开始深度识别", bg="#28a745")
        if "识别完成" not in self.status_var.get():
            self.status_var.set("就绪")


if __name__ == "__main__":
    root = tk.Tk()
    app = DrawingApp(root)
    root.mainloop()