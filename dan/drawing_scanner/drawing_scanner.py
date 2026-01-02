import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import pathlib
import os
from google import genai
from google.genai import types


class DrawingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("图纸版本标识识别工具 (Gemini AI)")
        self.root.geometry("800x600")

        # 默认配置
        self.default_model = "gemini-3-flash-preview"  # 建议使用当前稳定版，或按需改为 gemini-3-flash-preview
        self.default_api_key = "sk-RSTbBpugL4LbOMjGzjl7VPVKD9d392gjFslgNJB62tYqnGAz"

        self.setup_ui()

    def setup_ui(self):
        # 参数配置区
        config_frame = tk.LabelFrame(self.root, text="配置信息", padx=10, pady=10)
        config_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(config_frame, text="API Key:").grid(row=0, column=0, sticky="w")
        self.api_key_entry = tk.Entry(config_frame, width=50)
        self.api_key_entry.insert(0, self.default_api_key)
        self.api_key_entry.grid(row=0, column=1, padx=5, pady=2)

        tk.Label(config_frame, text="模型名称:").grid(row=1, column=0, sticky="w")
        self.model_entry = tk.Entry(config_frame, width=50)
        self.model_entry.insert(0, self.default_model)
        self.model_entry.grid(row=1, column=1, padx=5, pady=2)

        # 文件选择区
        file_frame = tk.Frame(self.root, padx=10, pady=10)
        file_frame.pack(fill="x")

        self.file_path_var = tk.StringVar(value="未选择文件")
        tk.Label(file_frame, textvariable=self.file_path_var, fg="blue", wraplength=500).pack(side="left")

        tk.Button(file_frame, text="选择 PDF 图纸", command=self.select_file).pack(side="right")

        # 操作按钮
        self.run_btn = tk.Button(self.root, text="开始识别", command=self.start_thread, bg="#4CAF50", fg="white",
                                 height=2)
        self.run_btn.pack(fill="x", padx=10, pady=5)

        # 日志输出控制台
        tk.Label(self.root, text="运行日志及识别结果:").pack(anchor="w", padx=10)
        self.log_area = scrolledtext.ScrolledText(self.root, state='disabled', wrap=tk.WORD, bg="black",
                                                  fg="lightgreen")
        self.log_area.pack(expand=True, fill="both", padx=10, pady=10)

    def log(self, message):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')
        self.root.update_idletasks()

    def select_file(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self.file_path_var.set(path)
            self.log(f"[系统] 已选择文件: {path}")

    def start_thread(self):
        file_path = self.file_path_var.get()
        if file_path == "未选择文件":
            messagebox.showwarning("错误", "请先选择 PDF 文件")
            return

        # 禁用按钮防止重复点击
        self.run_btn.config(state="disabled")
        thread = threading.Thread(target=self.process_drawing, args=(file_path,))
        thread.start()

    def process_drawing(self, file_path):
        api_key = self.api_key_entry.get().strip()
        model_name = self.model_entry.get().strip()

        try:
            self.log(f"[任务] 正在连接 Gemini API ({model_name})...")
            client = genai.Client(api_key=api_key)

            pdf_path = pathlib.Path(file_path)

            # 精细化的 Prompt
            prompt = """
            任务：识别PDF图纸中的版本更新标识。
            特征：版本标识通常是带有方框的大写字母（如 [A], [B], [C]）。
            坐标参考：图纸四周有坐标刻度，纵轴为字母（A, B, C, D...），横轴为数字（1, 2, 3, 4...）。

            请输出：
            1. 识别到的版本字母（当前最新的版本）。
            2. 每一处标识所在的坐标区域（如 A3, C6）。
            3. 该位置的简短描述（它靠近什么零件或标注）。

            输出格式要求（严格遵守）：
            版本字母：[字母]
            位置 1：[区域坐标] 区域
            描述：[描述内容]
            位置 2：[区域坐标] 区域
            描述：[描述内容]
            ...
            """

            self.log("[任务] 正在上传并分析图纸，请稍候...")

            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(
                        data=pdf_path.read_bytes(),
                        mime_type='application/pdf',
                    ),
                    prompt
                ]
            )

            result_text = response.text
            self.log("\n--- 识别结果 ---")
            self.log(result_text)
            self.log("----------------\n")

            # 弹窗提醒
            messagebox.showinfo("识别完成", "图纸分析任务已成功结束！")

        except Exception as e:
            self.log(f"[错误] 发生异常: {str(e)}")
            messagebox.showerror("运行错误", f"识别失败: {str(e)}")

        finally:
            self.run_btn.config(state="normal")


if __name__ == "__main__":
    root = tk.Tk()
    app = DrawingApp(root)
    root.mainloop()