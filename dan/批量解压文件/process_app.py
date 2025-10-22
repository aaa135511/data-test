import os
import zipfile
import pandas as pd
import threading
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

# 定义要查找和重命名的图片文件类型
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']


class BatchProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("批量解压重命名工具 (V9 - 匹配命名)")
        self.root.geometry("600x500")

        self.target_folder = ""
        self.excel_path = ""

        # --- UI 界面元素 ---
        self.folder_label = tk.Label(root, text="尚未选择处理文件夹", wraplength=500)
        self.folder_label.pack(pady=(10, 5))
        self.folder_button = tk.Button(root, text="1. 选择包含ZIP的文件夹", command=self.select_folder)
        self.folder_button.pack(pady=5)

        self.excel_label = tk.Label(root, text="尚未选择Excel命名规则文件", wraplength=500)
        self.excel_label.pack(pady=5)
        self.excel_button = tk.Button(root, text="2. 选择Excel文件", command=self.select_excel)
        self.excel_button.pack(pady=5)

        self.process_button = tk.Button(root, text="3. 开始处理", command=self.start_processing_thread, bg="#D7BDE2",
                                        font=("Helvetica", 12, "bold"))
        self.process_button.pack(pady=20)

        self.log_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, state='disabled', height=15)
        self.log_area.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

    def select_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.target_folder = folder_selected
            self.folder_label.config(text=f"已选文件夹: {self.target_folder}")

    def select_excel(self):
        file_selected = filedialog.askopenfilename(
            title="选择Excel命名规则文件",
            filetypes=(("Excel Files", "*.xlsx"), ("All files", "*.*"))
        )
        if file_selected:
            self.excel_path = file_selected
            self.excel_label.config(text=f"已选Excel: {self.excel_path}")

    def log(self, message):
        self.root.after(0, self._log_update, message)

    def _log_update(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def start_processing_thread(self):
        if not self.target_folder or not self.excel_path:
            messagebox.showerror("错误", "请先选择要处理的文件夹和Excel命名规则文件！")
            return

        self.process_button.config(state='disabled', text="正在处理...")
        thread = threading.Thread(target=self.process_files)
        thread.start()

    def process_files(self):
        try:
            self.log("--- 开始处理 (V9 - 匹配命名模式) ---")

            # 1. 加载规则
            df = pd.read_excel(self.excel_path)
            if '设置' not in df.columns or '大健' not in df.columns:
                raise ValueError("Excel文件中必须包含名为 '设置' 和 '大健' 的两列。")
            rules = df[['设置', '大健']].values.tolist()
            self.log(f"成功加载 {len(rules)} 条命名规则。")

            zip_files = sorted([f for f in os.listdir(self.target_folder) if f.lower().endswith('.zip')])
            self.log(f"发现 {len(zip_files)} 个ZIP压缩包。")
            if not zip_files: raise ValueError("文件夹中未找到任何 .zip 压缩包。")

            # 2. 遍历所有ZIP文件
            for zip_filename in zip_files:
                self.log(f"\n--- 正在处理压缩包: {zip_filename} ---")

                # 3. !! 核心逻辑: 为当前ZIP文件查找匹配的规则 !!
                matched_rule = None
                unzipped_root_name = os.path.splitext(zip_filename)[0]
                for rule in rules:
                    # rule[0] is '设置', rule[1] is '大健'
                    dajian_value = str(rule[1])
                    if dajian_value in unzipped_root_name:
                        matched_rule = rule
                        self.log(f"  -> 匹配成功！文件夹名 '{unzipped_root_name}' 包含规则 '{dajian_value}'。")
                        break  # 找到后即停止搜索

                if not matched_rule:
                    self.log(f"  -> !! 警告: 未在Excel中找到与 '{unzipped_root_name}' 匹配的规则，跳过此压缩包。")
                    continue

                # 4. 解压
                unzipped_root_path = os.path.join(self.target_folder, unzipped_root_name)
                if os.path.exists(unzipped_root_path):
                    shutil.rmtree(unzipped_root_path)
                with zipfile.ZipFile(os.path.join(self.target_folder, zip_filename), 'r') as zip_ref:
                    zip_ref.extractall(unzipped_root_path)
                self.log(f"  -> 解压完成。")

                # 5. !! 核心逻辑: 在解压后的文件夹内查找包含'image'的子文件夹 !!
                image_folder_path = None
                for item in os.listdir(unzipped_root_path):
                    item_path = os.path.join(unzipped_root_path, item)
                    if os.path.isdir(item_path) and 'image' in item.lower():
                        image_folder_path = item_path
                        self.log(f"  -> 找到目标图片文件夹: '{item}'")
                        break  # 找到第一个就用

                if not image_folder_path:
                    self.log(f"  -> !! 警告: 在 '{unzipped_root_name}' 内未找到含'image'的子文件夹，不执行重命名。")
                else:
                    # 6. 执行图片重命名
                    image_prefix = str(matched_rule[0])  # '设置'
                    image_counter = 1
                    self.log(f"  -> 将使用前缀 '{image_prefix}' 进行重命名...")

                    for dirpath, _, filenames in os.walk(image_folder_path):
                        for filename in sorted(filenames):
                            if any(filename.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
                                file_ext = os.path.splitext(filename)[1]
                                new_name = f"{image_prefix}_{image_counter}{file_ext}"
                                os.rename(os.path.join(dirpath, filename), os.path.join(dirpath, new_name))
                                image_counter += 1

                    if image_counter > 1:
                        self.log(f"    -> 重命名完成，共处理 {image_counter - 1} 张图片。")
                    else:
                        self.log(f"    -> 在 '{os.path.basename(image_folder_path)}' 中未找到图片。")

                # 7. 删除原始ZIP
                os.remove(os.path.join(self.target_folder, zip_filename))
                self.log(f"  -> 已删除压缩包。")

            self.log("\n--- 所有压缩包处理完成！---")
            self.root.after(0, lambda: messagebox.showinfo("成功", "所有文件已成功处理！"))

        except Exception as e:
            error_message = f"发生严重错误: {e}"
            self.log(error_message)
            self.root.after(0, lambda: messagebox.showerror("处理失败", f"发生错误:\n{e}"))
        finally:
            self.root.after(0, lambda: self.process_button.config(state='normal', text="3. 开始处理"))


if __name__ == "__main__":
    root = tk.Tk()
    app = BatchProcessorApp(root)
    root.mainloop()