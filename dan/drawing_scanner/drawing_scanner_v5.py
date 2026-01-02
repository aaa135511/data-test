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
        self.root.title("智能图纸识别系统（AIRSIO）- V9.1 强力调试版")
        self.root.geometry("1100x800")

        self.style = ttk.Style()
        self.style.theme_use('clam')

        # 默认配置
        self.default_base_url = "http://jeniya.cn"
        self.default_model = "gemini-3-flash-preview-thinking"
        self.default_token = "sk-KXrmyl8xw4jobewx8RaEM3c6uaMtjYGNErj2UxiKe6n5Ko3w"

        self.setup_ui()

    def setup_ui(self):
        # 1. 配置区
        config_frame = tk.LabelFrame(self.root, text="系统参数配置", padx=12, pady=10, font=("微软雅黑", 10, "bold"))
        config_frame.pack(fill="x", padx=15, pady=10)

        tk.Label(config_frame, text="API Token:", font=("微软雅黑", 9)).grid(row=0, column=0, sticky="w")
        self.token_entry = tk.Entry(config_frame, width=50)
        self.token_entry.insert(0, self.default_token)
        self.token_entry.grid(row=0, column=1, padx=8, pady=5, sticky="w")

        tk.Label(config_frame, text="推理模型:", font=("微软雅黑", 9)).grid(row=1, column=0, sticky="w")
        self.model_entry = tk.Entry(config_frame, width=35)
        self.model_entry.insert(0, self.default_model)
        self.model_entry.grid(row=1, column=1, padx=8, pady=5, sticky="w")
        tk.Label(config_frame, text="(控制台输出Raw JSON)", fg="#d63384", font=("微软雅黑", 8)).grid(row=1, column=2,
                                                                                                     sticky="w")

        tk.Label(config_frame, text="Base URL:", font=("微软雅黑", 9)).grid(row=2, column=0, sticky="w")
        self.url_entry = tk.Entry(config_frame, width=50)
        self.url_entry.insert(0, self.default_base_url)
        self.url_entry.grid(row=2, column=1, padx=8, pady=5, sticky="w")

        # 2. 文件区
        file_frame = tk.Frame(self.root, padx=5, pady=5)
        file_frame.pack(fill="x", padx=10)
        self.file_path_var = tk.StringVar(value="等待导入图纸...")
        tk.Label(file_frame, textvariable=self.file_path_var, bg="#f8f9fa", relief="solid", bd=1, width=60,
                 anchor="w").pack(side="left", padx=(0, 10))
        tk.Button(file_frame, text="📂 导入 PDF", command=self.select_file, bg="#007bff", fg="white").pack(side="right")

        # 3. 运行按钮
        self.run_btn = tk.Button(self.root, text="执行双步识别 (含Debug信息)", command=self.start_thread,
                                 bg="#6610f2", fg="white", height=2, font=("微软雅黑", 12, "bold"), state="disabled")
        self.run_btn.pack(fill="x", padx=15, pady=15)

        # 4. 日志
        self.log_area = scrolledtext.ScrolledText(self.root, state='disabled', bg="#1e1e1e", fg="#00ff00",
                                                  font=("Consolas", 11))
        self.log_area.pack(expand=True, fill="both", padx=15, pady=5)

        # 5. 状态
        self.status_var = tk.StringVar(value="系统就绪")
        tk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, bg="#e9ecef").pack(
            side=tk.BOTTOM, fill=tk.X)

    def log(self, message, clear=False):
        self.log_area.configure(state='normal')
        if clear: self.log_area.delete(1.0, tk.END)
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')
        self.root.update_idletasks()

    def select_file(self):
        path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if path:
            self.file_path_var.set(path)
            self.run_btn.config(state="normal")
            self.log(f"已加载: {os.path.basename(path)}", clear=True)

    def start_thread(self):
        thread = threading.Thread(target=self.execute_pipeline)
        thread.daemon = True
        thread.start()

    def call_gemini_api(self, prompt, pdf_base64, task_name):
        token = self.token_entry.get().strip()
        model = self.model_entry.get().strip()
        base_url = self.url_entry.get().strip().rstrip('/')

        api_url = base_url if "generateContent" in base_url else f"{base_url}/v1beta/models/{model}:generateContent"

        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": "application/pdf", "data": pdf_base64}},
                    {"text": prompt}
                ]
            }],
            "generationConfig": {
                "temperature": 0.3,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 8192,
                "thinkingConfig": {"includeThoughts": True}
            },
            # 显式放宽安全设置，防止误杀
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        }

        headers = {'Content-Type': 'application/json'}
        if "googleapis" not in base_url: headers['Authorization'] = f'Bearer {token}'
        params = {"key": token} if "googleapis" in base_url else {}

        self.log(f"[{task_name}] 发送请求...")

        try:
            response = requests.post(api_url, headers=headers, params=params, data=json.dumps(payload), timeout=240)

            if response.status_code == 200:
                resp_json = response.json()

                # --- V9.1 DEBUG: 强制打印完整 JSON 到控制台 ---
                print(f"\n>>>>>>>>>>>>>> DEBUG RAW JSON ({task_name}) >>>>>>>>>>>>>>")
                print(json.dumps(resp_json, indent=2, ensure_ascii=False))
                print("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<\n")

                final_text = ""
                thought_text = ""

                if 'candidates' in resp_json and len(resp_json['candidates']) > 0:
                    parts = resp_json['candidates'][0].get('content', {}).get('parts', [])

                    for part in parts:
                        is_thought = part.get('thought', False)
                        text_content = part.get('text', '')

                        if is_thought:
                            thought_text += text_content  # 备份思考内容
                        else:
                            final_text += text_content

                    final_text = final_text.strip()

                    # --- V9.1 兜底逻辑 ---
                    # 如果过滤后的正式回答为空，说明模型可能把答案写在 Thinking 里了，或者出了故障
                    if not final_text:
                        print(f"[{task_name}] 警告: 正式回答为空，尝试提取思维链内容作为兜底...")
                        # 尝试从 thought_text 中提取有效信息（如果它包含了答案）
                        if thought_text:
                            # 简单的启发式提取：看是否有 "【" 开头的内容
                            if "【" in thought_text:
                                final_text = thought_text[thought_text.find("【"):]
                            else:
                                final_text = "(模型仅返回了思考过程，未生成正式结果，以下为原始思考):\n" + thought_text[
                                                                                                         :500] + "..."
                        else:
                            final_text = "API 返回了空内容 (Empty Content)"

                    return final_text
                else:
                    self.log(f"[{task_name}] Warning: Candidates list is empty.")
                    return None
            else:
                self.log(f"[{task_name}] Error: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            self.log(f"[{task_name}] Exception: {str(e)}")
            return None

    def execute_pipeline(self):
        file_path = self.file_path_var.get()
        self.run_btn.config(state="disabled")

        try:
            with open(file_path, "rb") as f:
                pdf_base64 = base64.b64encode(f.read()).decode('utf-8')

            self.log("=" * 20 + " 开始 V9.1 强力调试识别 " + "=" * 20, clear=True)

            # Task 1: 标题栏
            self.status_var.set("Task 1: 识别标题栏版次...")
            prompt_task1 = """
            **任务**: 识别图纸右下角标题栏的【最新版次】。

            **坐标系统定义 (Coordinate System)**:
            *   **X轴 (水平)**: 看图纸上下边缘的数字标尺 (1, 2, 3...8)。
            *   **Y轴 (垂直)**: 看图纸左右边缘的字母标尺 (A, B, C, D...)。
            *   **定位方法**: 找到目标后，分别向水平边缘和垂直边缘引虚拟线，读取对应的 字母+数字。

            **输出格式**:
            【标题栏版次识别】
            版本号: [字母]
            坐标: [字母][数字] (例如 D8)
            """
            result_1 = self.call_gemini_api(prompt_task1, pdf_base64, "Task 1 (Rev)")
            if not result_1: result_1 = "Task 1 失败 (请查看控制台 JSON)"

            # Task 2: 绘图区
            self.status_var.set("Task 2: 扫描全图并计算坐标...")
            prompt_task2 = """
            **任务**: 识别绘图区域内**所有**的【改版标记】并计算精确坐标。

            **坐标计算指令 (必须严格执行)**:
            对于每一个发现的标记，请执行“十字交叉定位法”：
            1.  **水平投影**: 向上或向下看图纸边缘，读取最近的**数字** (1-8)。
            2.  **垂直投影**: 向左或向右看图纸边缘，读取最近的**字母** (A-F)。
            3.  **组合**: 将字母和数字组合成坐标，例如 **A4**, **C3**, **B6**。
            *注意：不要输出 "Grid 4" 这种模糊描述，必须是 "字母+数字" 的格式。*

            **识别逻辑**:
            1. 寻找带有大写字母的方框。
            2. 排除基准符号 (有三角底座的)。
            3. 保留改版标记 (悬浮或连线)。

            **输出格式**:
            【改版标记识别】
            总数量: [数字]

            【详细列表】
            1. 标记: [字母] | 坐标: [字母+数字, 如 A4] | 类型: [悬浮/连线] | 描述: [位置描述]
            2. 标记: [字母] | 坐标: [字母+数字, 如 B6] | 类型: [悬浮/连线] | 描述: [位置描述]
            """
            result_2 = self.call_gemini_api(prompt_task2, pdf_base64, "Task 2 (Tags)")
            if not result_2: result_2 = "Task 2 失败 (请查看控制台 JSON)"

            # 合并
            self.log("\n" + "=" * 20 + " 最终结果 " + "=" * 20)

            def clean_marker(text, marker):
                if marker in text: return text[text.find(marker):]
                return text

            final_output = clean_marker(result_1, "【标题栏版次识别】") + "\n\n" + \
                           "-" * 40 + "\n\n" + \
                           clean_marker(result_2, "【改版标记识别】")

            self.log(final_output)
            self.status_var.set("识别完成。")

        except Exception as e:
            self.log(f"Error: {str(e)}")
        finally:
            self.run_btn.config(state="normal")


if __name__ == "__main__":
    root = tk.Tk()
    app = DrawingApp(root)
    root.mainloop()