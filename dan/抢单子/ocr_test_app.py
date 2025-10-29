import tkinter as tk
from tkinter import scrolledtext, messagebox
import pytesseract
import cv2
import numpy as np
import time
import threading
import pyautogui
from mss import mss


class OCRApp:
    def __init__(self, root):
        self.root = root
        self.root.title("智能OCR定位工具 v4.4")
        self.root.geometry("500x550")

        # --- 状态变量 (与之前版本相同) ---
        self.scan_area = None
        self.is_scanning = False
        self.scan_thread = None
        self.mouse_thread = None

        # --- UI 元素 (与之前版本相同) ---
        # ... (此处省略与v4.3完全相同的UI代码) ...
        keyword_frame = tk.Frame(root)
        keyword_frame.pack(pady=10, fill=tk.X, padx=10)
        tk.Label(keyword_frame, text="要识别的关键词:").pack(side=tk.LEFT)
        self.keyword_entry = tk.Entry(keyword_frame)
        self.keyword_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.keyword_entry.insert(0, "运维监控")

        coords_frame = tk.Frame(root, relief=tk.GROOVE, borderwidth=2)
        coords_frame.pack(pady=10, fill=tk.X, padx=10)

        self.mouse_pos_label = tk.Label(coords_frame, text="当前鼠标位置: (---, ---)", font=("Arial", 14, "bold"))
        self.mouse_pos_label.pack(pady=10)

        tl_frame = tk.Frame(coords_frame)
        tl_frame.pack(pady=5, fill=tk.X)
        tk.Label(tl_frame, text="左上角 X:").pack(side=tk.LEFT, padx=5)
        self.entry_x1 = tk.Entry(tl_frame, width=6)
        self.entry_x1.pack(side=tk.LEFT)
        tk.Label(tl_frame, text="Y:").pack(side=tk.LEFT, padx=5)
        self.entry_y1 = tk.Entry(tl_frame, width=6)
        self.entry_y1.pack(side=tk.LEFT)
        self.get_tl_button = tk.Button(tl_frame, text="<-- 获取当前位置", command=self.get_top_left)
        self.get_tl_button.pack(side=tk.LEFT, padx=10)

        br_frame = tk.Frame(coords_frame)
        br_frame.pack(pady=5, fill=tk.X)
        tk.Label(br_frame, text="右下角 X:").pack(side=tk.LEFT, padx=5)
        self.entry_x2 = tk.Entry(br_frame, width=6)
        self.entry_x2.pack(side=tk.LEFT)
        tk.Label(br_frame, text="Y:").pack(side=tk.LEFT, padx=5)
        self.entry_y2 = tk.Entry(br_frame, width=6)
        self.entry_y2.pack(side=tk.LEFT)
        self.get_br_button = tk.Button(br_frame, text="<-- 获取当前位置", command=self.get_bottom_right)
        self.get_br_button.pack(side=tk.LEFT, padx=10)

        for entry in [self.entry_x1, self.entry_y1, self.entry_x2, self.entry_y2]:
            entry.bind("<KeyRelease>", self.validate_area_from_entries)

        control_frame = tk.Frame(root)
        control_frame.pack(pady=20)
        self.start_button = tk.Button(control_frame, text="开始识别", command=self.start_scanning, state=tk.DISABLED,
                                      font=("Arial", 14))
        self.start_button.pack(side=tk.LEFT, padx=10)
        self.stop_button = tk.Button(control_frame, text="停止识别", command=self.stop_scanning, state=tk.DISABLED,
                                     font=("Arial", 14))
        self.stop_button.pack(side=tk.LEFT, padx=10)

        log_frame = tk.Frame(root)
        log_frame.pack(pady=10, fill=tk.BOTH, expand=True, padx=10)
        tk.Label(log_frame, text="识别日志:").pack(anchor=tk.W)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.status_label = tk.Label(root, text="状态: 请设置坐标", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.start_mouse_tracker()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def log(self, message, color="black"):
        # ... (与之前版本相同) ...
        self.log_text.config(state=tk.NORMAL)
        self.log_text.tag_configure(color, foreground=color)
        self.log_text.insert(tk.END, message + "\n", color)
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    # --- 核心识别逻辑 (v4.4 智能分析版) ---
    def scan_loop(self):
        keyword = self.keyword_entry.get()
        if not keyword:
            self.log("错误: 关键词不能为空！", "red")
            self.stop_scanning()
            return

        with mss() as sct:
            while self.is_scanning:
                self.status_label.config(text="状态: 正在识别...")
                sct_img = sct.grab(self.scan_area)
                img = np.array(sct_img)
                gray_img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

                # --- 智能预处理：自适应阈值 ---
                # 对于有不同背景色或光照的复杂大区域，这比全局阈值效果好得多
                processed_img = cv2.adaptiveThreshold(
                    gray_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY, 11, 2
                )

                # --- 使用最强大的全自动PSM模式 ---
                # --psm 3: 全自动页面分割（默认），最适合复杂布局
                custom_config = r'--oem 3 --psm 3'

                found = False
                try:
                    # 使用预处理后的图像进行识别
                    data = pytesseract.image_to_data(processed_img, lang='chi_sim', config=custom_config,
                                                     output_type=pytesseract.Output.DICT)

                    n_boxes = len(data['level'])
                    for i in range(n_boxes):
                        # 增加可信度阈值，过滤掉噪声
                        if int(data['conf'][i]) > 60 and keyword in data['text'][i]:
                            (x, y, w, h) = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
                            abs_x = self.scan_area['left'] + x
                            abs_y = self.scan_area['top'] + y

                            timestamp = time.strftime('%H:%M:%S')
                            log_msg = f"[{timestamp}] 找到! 文本: '{data['text'][i]}', 屏幕坐标: (x={abs_x}, y={abs_y}, w={w}, h={h})"
                            self.log(log_msg, "green")
                            found = True
                            break

                    if not found:
                        timestamp = time.strftime('%H:%M:%S')
                        self.log(f"[{timestamp}] 在区域内未找到关键词 '{keyword}'")

                except Exception as e:
                    self.log(f"识别错误: {e}", "red")
                    self.stop_scanning()

                time.sleep(1)

    # --- 以下是与v4.3完全相同的辅助函数 ---
    def get_top_left(self):
        pos = pyautogui.position()
        self.entry_x1.delete(0, tk.END);
        self.entry_x1.insert(0, str(pos.x))
        self.entry_y1.delete(0, tk.END);
        self.entry_y1.insert(0, str(pos.y))
        self.validate_area_from_entries()

    def get_bottom_right(self):
        pos = pyautogui.position()
        self.entry_x2.delete(0, tk.END);
        self.entry_x2.insert(0, str(pos.x))
        self.entry_y2.delete(0, tk.END);
        self.entry_y2.insert(0, str(pos.y))
        self.validate_area_from_entries()

    def validate_area_from_entries(self, event=None):
        try:
            x1, y1, x2, y2 = int(self.entry_x1.get()), int(self.entry_y1.get()), int(self.entry_x2.get()), int(
                self.entry_y2.get())
        except ValueError:
            self.start_button.config(state=tk.DISABLED);
            self.status_label.config(text="状态: 请输入有效的数字坐标", fg="red");
            self.scan_area = None;
            return
        left, top, width, height = min(x1, x2), min(y1, y2), abs(x1 - x2), abs(y1 - y2)
        if width > 0 and height > 0:
            self.scan_area = {"top": top, "left": left, "width": width, "height": height}
            self.status_label.config(text=f"区域已就绪: {self.scan_area}", fg="blue");
            self.start_button.config(state=tk.NORMAL)
        else:
            self.start_button.config(state=tk.DISABLED);
            self.status_label.config(text="状态: 区域的宽度和高度必须大于0", fg="red");
            self.scan_area = None

    def set_controls_state(self, state):
        for widget in [self.entry_x1, self.entry_y1, self.entry_x2, self.entry_y2, self.get_tl_button,
                       self.get_br_button]:
            widget.config(state=state)

    def start_scanning(self):
        self.is_scanning = True;
        self.start_button.config(state=tk.DISABLED);
        self.stop_button.config(state=tk.NORMAL)
        self.set_controls_state(tk.DISABLED);
        self.log_text.config(state=tk.NORMAL);
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED);
        self.scan_thread = threading.Thread(target=self.scan_loop, daemon=True);
        self.scan_thread.start()

    def stop_scanning(self):
        self.is_scanning = False;
        self.stop_button.config(state=tk.DISABLED);
        self.set_controls_state(tk.NORMAL)
        self.validate_area_from_entries();
        self.status_label.config(text="状态: 已停止")

    def start_mouse_tracker(self):
        self.mouse_thread = threading.Thread(target=self.track_mouse_position, daemon=True);
        self.mouse_thread.start()

    def track_mouse_position(self):
        while True:
            try:
                pos = pyautogui.position();
                self.mouse_pos_label.config(text=f"当前鼠标位置: ({pos.x}, {pos.y})");
                time.sleep(0.1)
            except tk.TclError:
                break

    def on_closing(self):
        self.is_scanning = False;
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = OCRApp(root)
    root.mainloop()