import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import time
import re
from PIL import ImageGrab, Image
import pytesseract
import pyautogui
import cv2
import numpy as np
import customtkinter as ctk
import sys
import os


# --- [重要] 动态 Tesseract-OCR 路径配置 ---
# 此函数用于在打包后正确找到 Tesseract 的路径
def get_tesseract_path():
    # 检查脚本是否作为打包后的可执行文件运行
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # 如果是打包文件，Tesseract被我们放在了'tesseract'子文件夹中
        # sys._MEIPASS 指向 PyInstaller 创建的临时文件夹
        return os.path.join(sys._MEIPASS, 'tesseract', 'tesseract.exe')
    else:
        # 如果是作为.py脚本运行，则使用本地安装的Tesseract
        # 请确保此路径对您的开发环境是正确的
        return r'C:\Program Files\Tesseract-OCR\tesseract.exe'


# 在程序启动时设置 Tesseract 命令路径
try:
    pytesseract.pytesseract.tesseract_cmd = get_tesseract_path()
except Exception as e:
    print(f"设置 Tesseract 路径时出错: {e}")
    # 您可以在这里添加一个弹窗，如果找不到Tesseract就提示用户


# --- 配置结束 ---


# --- 主应用界面 (Windows 捆绑版) ---
class VinSearchApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("车辆查找脚本 (Windows 捆绑版)")
        self.geometry("500x750")

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.monitoring_area = None
        self.search_thread = None
        self.is_searching = False

        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        # --- UI 组件 ---
        self.vin_label = ctk.CTkLabel(self.main_frame, text="输入目标车架号后六位:")
        self.vin_label.pack(pady=(0, 5))
        self.vin_entry = ctk.CTkEntry(self.main_frame, width=200)
        self.vin_entry.pack(pady=(0, 20))

        coords_display_frame = ctk.CTkFrame(self.main_frame)
        coords_display_frame.pack(pady=10, fill="x")
        ctk.CTkLabel(coords_display_frame, text="实时鼠标坐标 (用于下方设置):", font=ctk.CTkFont(weight="bold")).pack()
        self.mouse_coords_label = ctk.CTkLabel(coords_display_frame, text="X: 0, Y: 0", font=ctk.CTkFont(size=18))
        self.mouse_coords_label.pack(pady=5)

        self.coords_label = ctk.CTkLabel(self.main_frame, text="设置监控区域坐标:", font=ctk.CTkFont(weight="bold"))
        self.coords_label.pack(pady=(10, 5))

        coords_frame = ctk.CTkFrame(self.main_frame)
        coords_frame.pack(pady=5, padx=10)
        coords_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.x1_entry = ctk.CTkEntry(coords_frame, width=70);
        self.y1_entry = ctk.CTkEntry(coords_frame, width=70)
        self.x2_entry = ctk.CTkEntry(coords_frame, width=70);
        self.y2_entry = ctk.CTkEntry(coords_frame, width=70)

        ctk.CTkLabel(coords_frame, text="左上角 X1:").grid(row=0, column=0, padx=5, pady=5);
        self.x1_entry.grid(row=0, column=1, padx=5, pady=5)
        ctk.CTkLabel(coords_frame, text="左上角 Y1:").grid(row=0, column=2, padx=5, pady=5);
        self.y1_entry.grid(row=0, column=3, padx=5, pady=5)
        ctk.CTkLabel(coords_frame, text="右下角 X2:").grid(row=1, column=0, padx=5, pady=5);
        self.x2_entry.grid(row=1, column=1, padx=5, pady=5)
        ctk.CTkLabel(coords_frame, text="右下角 Y2:").grid(row=1, column=2, padx=5, pady=5);
        self.y2_entry.grid(row=1, column=3, padx=5, pady=5)

        scroll_frame = ctk.CTkFrame(self.main_frame)
        scroll_frame.pack(pady=10)
        ctk.CTkLabel(scroll_frame, text="单次滚动幅度:").pack(padx=10)
        self.scroll_amount_entry = ctk.CTkEntry(scroll_frame, width=120)
        self.scroll_amount_entry.pack(pady=5)

        self.start_button = ctk.CTkButton(self.main_frame, text="开始查找", command=self.toggle_search)
        self.start_button.pack(pady=20)

        self.log_text = scrolledtext.ScrolledText(self.main_frame, height=10, bg="#2B2B2B", fg="white", relief="flat",
                                                  font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)

        self.vin_entry.insert(0, "896140");
        self.x1_entry.insert(0, "730");
        self.y1_entry.insert(0, "600")
        self.x2_entry.insert(0, "1132");
        self.y2_entry.insert(0, "967");
        self.scroll_amount_entry.insert(0, "9")

        self.update_mouse_coords_display()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ... (其余所有函数保持不变) ...

    def update_mouse_coords_display(self):
        try:
            x, y = pyautogui.position()
            self.mouse_coords_label.configure(text=f"X: {x}, Y: {y}")
            self.after(100, self.update_mouse_coords_display)
        except tk.TclError:
            pass

    def log(self, message):
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)

    def safe_ui_update(self, func, *args):
        self.after(0, func, *args)

    def reset_ui_on_stop(self, final_message="查找任务结束。"):
        self.is_searching = False
        self.start_button.configure(text="开始查找")
        self.log(final_message)

    def handle_found_vin(self, found_vin):
        self.is_searching = False
        self.log(f"成功！已找到车架号: {found_vin}")
        pyautogui.alert(f"已找到车辆: {found_vin}", "任务完成")
        self.reset_ui_on_stop("查找成功，任务结束。")

    def toggle_search(self):
        if self.is_searching:
            self.is_searching = False
            self.start_button.configure(text="正在停止...")
            self.log("已发送停止信号，请等待当前循环结束。")
        else:
            try:
                self.monitoring_area = (
                int(self.x1_entry.get()), int(self.y1_entry.get()), int(self.x2_entry.get()), int(self.y2_entry.get()))
                if not (self.monitoring_area[2] > self.monitoring_area[0] and self.monitoring_area[3] >
                        self.monitoring_area[1]):
                    messagebox.showerror("坐标错误", "右下角坐标值必须大于左上角。");
                    return
                self.log(f"监控区域已设置为: {self.monitoring_area}")
            except ValueError:
                messagebox.showerror("输入错误", "坐标值必须是纯数字。");
                return
            self.is_searching = True
            self.start_button.configure(text="停止查找")
            self.search_thread = threading.Thread(target=self.search_loop, daemon=True)
            self.search_thread.start()

    def preprocess_image_for_ocr(self, img):
        gray = cv2.cvtColor(np.array(img), cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return Image.fromarray(thresh)

    def search_loop(self):
        target_vin = self.vin_entry.get().strip()
        if not target_vin.isdigit() or len(target_vin) != 6:
            self.safe_ui_update(self.reset_ui_on_stop, "错误: 请输入有效的6位数字车架号。")
            return
        try:
            scroll_amount = int(self.scroll_amount_entry.get())
        except ValueError:
            self.safe_ui_update(self.reset_ui_on_stop, "错误: 滚动幅度必须是数字。")
            return

        self.safe_ui_update(self.log, f"开始查找，目标: {target_vin}, 滚动幅度: {scroll_amount}")

        scroll_attempts, max_scrolls, last_image = 0, 200, None

        while self.is_searching and scroll_attempts < max_scrolls:
            screenshot = ImageGrab.grab(bbox=self.monitoring_area)
            if last_image is not None and np.sum(np.array(screenshot) != np.array(last_image)) == 0:
                self.safe_ui_update(self.log, "检测到屏幕内容不再变化，已到达列表底部。")
                break
            last_image = screenshot

            processed_img = self.preprocess_image_for_ocr(screenshot)
            extracted_text = pytesseract.image_to_string(processed_img, lang='chi_sim+eng',
                                                         config='--psm 6 -c tessedit_char_whitelist=0123456789')
            found_numbers = re.findall(r'\d{6}', extracted_text)
            self.safe_ui_update(self.log, f"识别到: {found_numbers if found_numbers else '无'}")

            if target_vin in found_numbers:
                self.safe_ui_update(self.handle_found_vin, target_vin)
                return

            self.safe_ui_update(self.log, "向下滚动...")
            pyautogui.moveTo(self.monitoring_area[0] + (self.monitoring_area[2] - self.monitoring_area[0]) / 2,
                             self.monitoring_area[1] + (self.monitoring_area[3] - self.monitoring_area[1]) / 2)
            pyautogui.scroll(-scroll_amount)
            scroll_attempts += 1
            time.sleep(0.5)

        if self.is_searching: self.safe_ui_update(self.log, "已达到最大滚动次数，自动停止。")
        self.safe_ui_update(self.reset_ui_on_stop)

    def on_closing(self):
        self.is_searching = False
        if self.search_thread and self.search_thread.is_alive(): self.search_thread.join(timeout=1)
        self.destroy()


if __name__ == "__main__":
    app = VinSearchApp()
    app.mainloop()