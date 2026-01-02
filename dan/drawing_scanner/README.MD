这是一个非常实用的需求。为了实现跨平台（Windows 和 macOS）并支持 `PyInstaller` 打包，我建议使用 Python 自带的 `tkinter` 库来构建 GUI。它轻量、无需额外安装依赖，且在两个系统上运行都很稳定。

以下是完整的 Python 代码实现。

### 1. 准备工作
你需要安装必要的库：
```bash
pip install -U google-genai
```

### 2. Python 完整代码 (`drawing_scanner.py`)

```python
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
        self.default_model = "gemini-2.0-flash" # 建议使用当前稳定版，或按需改为 gemini-3-flash-preview
        self.default_api_key = "AIzaSyC9dD-RM6ST4tZzbUWjRezeeDjBNexFwAU"

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
        self.run_btn = tk.Button(self.root, text="开始识别", command=self.start_thread, bg="#4CAF50", fg="white", height=2)
        self.run_btn.pack(fill="x", padx=10, pady=5)

        # 日志输出控制台
        tk.Label(self.root, text="运行日志及识别结果:").pack(anchor="w", padx=10)
        self.log_area = scrolledtext.ScrolledText(self.root, state='disabled', wrap=tk.WORD, bg="black", fg="lightgreen")
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
```

### 3. 代码关键点说明

1.  **多线程处理 (`threading`)**: AI 的识别过程通常需要 10-20 秒，如果不使用多线程，GUI 界面会卡死（显示为“未响应”）。这里将 API 调用放在了后台线程。
2.  **Prompt 设计**: 明确告诉模型如何查看坐标（纵轴字母，横轴数字）以及寻找“带方框的字母”，并强制要求它按你给出的格式输出。
3.  **日志系统**: 通过 `scrolledtext` 模拟了一个控制台，实时向用户反馈“正在连接”、“正在分析”等状态。
4.  **跨平台**: `tkinter` 是 Python 标准库，在 Windows、macOS 上行为一致。在 macOS 上打包时，它会自动适配系统菜单。

### 4. 如何使用 PyInstaller 打包

你可以根据你的系统（Windows 或 Mac）运行以下命令来生成可执行文件：

#### 安装 PyInstaller
```bash
pip install pyinstaller
```

#### 执行打包命令
在终端/命令行进入脚本所在目录：

```bash
# Windows (生成一个 .exe 文件)
pyinstaller --noconsole --onefile drawing_scanner.py

# macOS (生成一个 .app 文件)
pyinstaller --noconsole --onefile --windowed drawing_scanner.py
```

*   `--noconsole`: 运行时不显示黑色的命令行窗口。
*   `--onefile`: 将所有依赖打包进一个文件。
*   `--windowed`: (macOS专用) 确保生成的是图形界面的 .app。

### 5. 注意事项
*   **模型名称**: 代码中默认填写的模型是 `gemini-2.0-flash`。如果 Google 发布了 `gemini-3-flash-preview` 且该名称生效，你可以在 GUI 界面直接修改。
*   **API 额度**: PDF 处理消耗的 Token 较多，请确保你的 API Key 有足够的配额。
*   **图纸清晰度**: 如果图纸非常复杂，建议使用 `gemini-2.0-pro-exp` 等性能更强的模型以获得更高的坐标准确度。