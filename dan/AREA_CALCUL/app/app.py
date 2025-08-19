# 文件名: app.py

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import os
# 导入我们的核心处理逻辑
from processing_logic import run_processing


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("订单面积自动统计工具 V5.0")
        self.root.geometry("500x350")

        self.input_path = ""
        self.output_path = ""

        # --- 界面布局 ---
        self.main_frame = tk.Frame(root, padx=20, pady=20)
        self.main_frame.pack(fill="both", expand=True)

        # 输入文件选择
        self.input_label = tk.Label(self.main_frame, text="请选择要处理的Excel文件:", anchor="w")
        self.input_label.pack(fill="x")

        self.input_path_label = tk.Label(self.main_frame, text="未选择文件", relief="sunken", bg="white", anchor="w",
                                         padx=5)
        self.input_path_label.pack(fill="x", pady=(0, 10))

        self.input_btn = tk.Button(self.main_frame, text="浏览...", command=self.select_input_file)
        self.input_btn.pack(anchor="e")

        # 输出文件选择
        self.output_label = tk.Label(self.main_frame, text="\n请选择结果要保存的位置:", anchor="w")
        self.output_label.pack(fill="x")

        self.output_path_label = tk.Label(self.main_frame, text="未选择位置", relief="sunken", bg="white", anchor="w",
                                          padx=5)
        self.output_path_label.pack(fill="x", pady=(0, 10))

        self.output_btn = tk.Button(self.main_frame, text="选择保存位置...", command=self.select_output_file)
        self.output_btn.pack(anchor="e")

        # 运行按钮和状态栏
        self.run_btn = tk.Button(self.main_frame, text="开始处理", font=("Helvetica", 12, "bold"),
                                 command=self.start_processing_thread, height=2)
        self.run_btn.pack(fill="x", pady=20)

        self.status_label = tk.Label(self.main_frame, text="准备就绪", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    def select_input_file(self):
        path = filedialog.askopenfilename(
            title="选择Excel文件",
            filetypes=(("Excel 文件", "*.xlsx *.xls"), ("所有文件", "*.*"))
        )
        if path:
            self.input_path = path
            self.input_path_label.config(text=os.path.basename(path))
            self.status_label.config(text="已选择输入文件")

    def select_output_file(self):
        # 自动生成默认文件名
        default_name = "订单统计结果.xlsx"
        if self.input_path:
            base, _ = os.path.splitext(os.path.basename(self.input_path))
            default_name = f"{base}_统计结果.xlsx"

        path = filedialog.asksaveasfilename(
            title="选择保存位置",
            initialfile=default_name,
            defaultextension=".xlsx",
            filetypes=(("Excel 文件", "*.xlsx"),)
        )
        if path:
            self.output_path = path
            self.output_path_label.config(text=os.path.basename(path))
            self.status_label.config(text="已选择输出位置")

    def start_processing_thread(self):
        if not self.input_path or not self.output_path:
            messagebox.showwarning("提示", "请先选择输入文件和输出位置！")
            return

        # 使用线程来运行，防止界面卡死
        thread = threading.Thread(target=self.process_data)
        thread.start()

    def process_data(self):
        self.run_btn.config(state="disabled", text="正在处理中...")
        self.status_label.config(text="正在处理，请稍候...")

        success, message = run_processing(self.input_path, self.output_path)

        if success:
            messagebox.showinfo("成功", message)
            self.status_label.config(text="处理完成！")
        else:
            messagebox.showerror("错误", message)
            self.status_label.config(text="处理失败！")

        self.run_btn.config(state="normal", text="开始处理")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()