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


# --- 动态 Tesseract-OCR 路径配置 ---
def get_tesseract_path():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, 'tesseract', 'tesseract.exe')
    else:
        return r'C:\Program Files\Tesseract-OCR\tesseract.exe'


try:
    pytesseract.pytesseract.tesseract_cmd = get_tesseract_path()
except Exception as e:
    print(f"设置 Tesseract 路径时出错: {e}")


# --- 配置结束 ---


# --- 主应用界面 (容错版) ---
class VinSearchApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("车辆查找脚本")
        self.geometry("500x750")

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.monitoring_area = None
        self.search_thread = None
        self.is_searching = False

        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        # --- UI 组件 (布局无变化) ---
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

    # --- [核心修改] 优化的成功处理函数 ---
    def handle_found_vin(self, target_vin, recognized_num):
        self.is_searching = False
        if target_vin == recognized_num:
            # 精确匹配
            self.log(f"成功！已精确找到车架号: {target_vin}")
            pyautogui.alert(f"已找到车辆: {target_vin}", "任务完成")
        else:
            # 容错匹配
            self.log(f"成功！通过容错匹配找到目标 '{target_vin}' (识别为: '{recognized_num}')")
            pyautogui.alert(f"通过容错匹配找到车辆！\n\n目标: {target_vin}\n识别为: {recognized_num}", "任务完成")
        self.reset_ui_on_stop("查找成功，任务结束。")

    # --- 修改结束 ---

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
        cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        h, w, _ = cv_img.shape
        upscaled_img = cv2.resize(cv_img, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(upscaled_img, cv2.COLOR_BGR2GRAY)
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
            config = '--psm 4 -c tessedit_char_whitelist=0123456789'
            extracted_text = pytesseract.image_to_string(processed_img, lang='chi_sim+eng', config=config)

            # --- [核心修改] 实现容错匹配逻辑 ---
            # 1. 查找所有长度大于等于5的数字串
            found_numbers_raw = re.findall(r'\d{5,}', extracted_text)
            found_numbers = sorted(list(set(found_numbers_raw)))

            self.safe_ui_update(self.log, f"识别到: {found_numbers if found_numbers else '无'}")

            # 2. 循环检查每个识别出的数字，看是否与目标存在包含关系
            match_found = False
            for num in found_numbers:
                if target_vin in num or num in target_vin:
                    # 找到了！调度主线程处理成功后的所有事宜
                    self.safe_ui_update(self.handle_found_vin, target_vin, num)
                    match_found = True
                    break  # 退出内层循环

            if match_found:
                return  # 退出整个 search_loop 线程
            # --- 修改结束 ---

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