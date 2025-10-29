import tkinter as tk
from tkinter import ttk, messagebox
import pyautogui
import pytesseract
from PIL import Image
import threading
import time
import json
import os


# --- 配置文件管理器 (跨平台，无需修改) ---
class ConfigManager:
    def __init__(self):
        self.config_dir = os.path.join(os.path.expanduser("~"), ".auto_order_accepter")
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.defaults = {
            "monitor_x1": "100", "monitor_y1": "800",
            "monitor_x2": "600", "monitor_y2": "1000",
            "accept_btn_x": "320", "accept_btn_y": "700",
            "confirm_btn_x": "500", "confirm_btn_y": "550",
            "close_btn_x": "900", "close_btn_y": "100",
            "delay_step1_2": "0.5",
            "delay_others": "0.1"
        }
        os.makedirs(self.config_dir, exist_ok=True)

    def load_config(self):
        if not os.path.exists(self.config_path):
            return self.defaults
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return self.defaults

    def save_config(self, data):
        try:
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=4)
            return True
        except IOError:
            return False


# --- 主应用 GUI ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("自动接单助手 (Windows版)")
        self.geometry("420x450")
        self.attributes('-topmost', True)

        self.config_manager = ConfigManager()
        self.entries = {}
        self.automation_thread = None
        self.is_running = False
        self.show_coords = False
        self.last_ocr_text = ""

        self.create_widgets()
        self.load_settings()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        settings_frame = ttk.LabelFrame(main_frame, text="参数设置")
        settings_frame.pack(fill=tk.X, pady=5)
        self.add_coord_entry(settings_frame, "监控区左上角 (x1, y1):", "monitor_x1", "monitor_y1", 0)
        self.add_coord_entry(settings_frame, "监控区右下角 (x2, y2):", "monitor_x2", "monitor_y2", 1)
        self.add_coord_entry(settings_frame, "接单按钮坐标 (x, y):", "accept_btn_x", "accept_btn_y", 2)
        self.add_coord_entry(settings_frame, "确认按钮坐标 (x, y):", "confirm_btn_x", "confirm_btn_y", 3)
        self.add_coord_entry(settings_frame, "关闭按钮坐标 (x, y):", "close_btn_x", "close_btn_y", 4)
        ttk.Separator(settings_frame, orient='horizontal').grid(row=5, columnspan=4, sticky='ew', pady=5)
        self.add_delay_entry(settings_frame, "步骤1->2延时(秒):", "delay_step1_2", 6)
        self.add_delay_entry(settings_frame, "其他步骤延时(秒):", "delay_others", 7)
        coords_frame = ttk.LabelFrame(main_frame, text="工具")
        coords_frame.pack(fill=tk.X, pady=10)
        self.coord_label = ttk.Label(coords_frame, text="鼠标坐标: (x, y)", font=("Helvetica", 12))
        self.coord_label.pack(side=tk.LEFT, padx=10)
        self.toggle_coords_btn = ttk.Button(coords_frame, text="开启坐标显示", command=self.toggle_mouse_display)
        self.toggle_coords_btn.pack(side=tk.RIGHT, padx=10)
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)
        self.save_btn = ttk.Button(control_frame, text="保存配置", command=self.save_settings)
        self.save_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.start_btn = ttk.Button(control_frame, text="开始运行", command=self.start_automation)
        self.start_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.stop_btn = ttk.Button(control_frame, text="停止运行", state=tk.DISABLED, command=self.stop_automation)
        self.stop_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.status_label = ttk.Label(main_frame, text="状态: 已停止", foreground="red")
        self.status_label.pack(pady=5)

    def add_coord_entry(self, parent, label_text, key_x, key_y, row):
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky='w', padx=5, pady=2)
        self.entries[key_x] = ttk.Entry(parent, width=8)
        self.entries[key_x].grid(row=row, column=1, padx=5)
        self.entries[key_y] = ttk.Entry(parent, width=8)
        self.entries[key_y].grid(row=row, column=2, padx=5)

    def add_delay_entry(self, parent, label_text, key, row):
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky='w', padx=5, pady=2)
        self.entries[key] = ttk.Entry(parent, width=8)
        self.entries[key].grid(row=row, column=1, padx=5)

    def load_settings(self):
        config = self.config_manager.load_config()
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, config.get(key, ""))

    def save_settings(self):
        data = {key: entry.get() for key, entry in self.entries.items()}
        if self.config_manager.save_config(data):
            messagebox.showinfo("成功", "配置已成功保存！")
        else:
            messagebox.showerror("错误", "无法保存配置。")

    def toggle_mouse_display(self):
        self.show_coords = not self.show_coords
        if self.show_coords:
            self.toggle_coords_btn.config(text="关闭坐标显示")
            self.coord_thread = threading.Thread(target=self._update_mouse_coords_loop, daemon=True)
            self.coord_thread.start()
        else:
            self.toggle_coords_btn.config(text="开启坐标显示")
            self.coord_label.config(text="鼠标坐标: (x, y)")

    def _update_mouse_coords_loop(self):
        while self.show_coords:
            try:
                x, y = pyautogui.position()
                self.coord_label.config(text=f"鼠标坐标: ({x}, {y})")
                time.sleep(0.1)
            except tk.TclError:
                break

    def start_automation(self):
        self.is_running = True
        self.status_label.config(text="状态: 运行中...", foreground="green")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.iconify()
        try:
            self.current_config = {key: float(entry.get()) for key, entry in self.entries.items()}
        except ValueError:
            messagebox.showerror("错误", "所有坐标和延时必须是数字！")
            self.stop_automation()
            return
        self.automation_thread = threading.Thread(target=self._automation_loop, daemon=True)
        self.automation_thread.start()

    def stop_automation(self):
        self.is_running = False
        self.status_label.config(text="状态: 已停止", foreground="red")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.deiconify()
        self.attributes('-topmost', True)

    def on_closing(self):
        if self.is_running:
            self.stop_automation()
        self.destroy()

    def _automation_loop(self):
        cfg = self.current_config
        monitor_region = (
            int(cfg['monitor_x1']), int(cfg['monitor_y1']),
            int(cfg['monitor_x2']) - int(cfg['monitor_x1']),
            int(cfg['monitor_y2']) - int(cfg['monitor_y1'])
        )
        if monitor_region[2] <= 0 or monitor_region[3] <= 0:
            self.after(0, lambda: messagebox.showerror("错误", "监控区域的右下角坐标必须大于左上角坐标！"))
            self.after(0, self.stop_automation)
            return

        print("--- 自动化流程已启动 ---")
        self.last_ocr_text = ""
        while self.is_running:
            try:
                screenshot = pyautogui.screenshot(region=monitor_region)
                text = pytesseract.image_to_string(screenshot, lang='chi_sim').strip()

                is_new_order = False
                if "故障派单通知" in text:
                    if self.last_ocr_text == "" or text != self.last_ocr_text:
                        is_new_order = True
                        print(f"发现新通知: '{text}'")
                    else:
                        print("内容与上次相同，判定为旧通知，跳过。")
                else:
                    print(f"未发现'故障派单通知'关键字。识别内容: '{text}'")

                if is_new_order:
                    self.last_ocr_text = text
                    print("[成功] 判定为新派单，执行接单流程...")

                    click_x = monitor_region[0] + monitor_region[2] / 2
                    click_y = monitor_region[1] + monitor_region[3] / 2
                    pyautogui.click(click_x, click_y)
                    time.sleep(cfg['delay_step1_2'])

                    print("进入详情页，执行单次快速滚动到底部...")
                    # 【滑动优化】执行一次大幅度的向下滚动
                    pyautogui.scroll(-2000)
                    time.sleep(cfg['delay_others'])

                    print(f"点击接单按钮: ({int(cfg['accept_btn_x'])}, {int(cfg['accept_btn_y'])})")
                    pyautogui.click(int(cfg['accept_btn_x']), int(cfg['accept_btn_y']))
                    time.sleep(cfg['delay_others'])

                    print(f"点击确认按钮: ({int(cfg['confirm_btn_x'])}, {int(cfg['confirm_btn_y'])})")
                    pyautogui.click(int(cfg['confirm_btn_x']), int(cfg['confirm_btn_y']))
                    time.sleep(cfg['delay_others'])

                    print(f"点击关闭按钮: ({int(cfg['close_btn_x'])}, {int(cfg['close_btn_y'])})")
                    pyautogui.click(int(cfg['close_btn_x']), int(cfg['close_btn_y']))

                    print("--- 一次接单流程完成，返回监控状态 ---")
                    time.sleep(3)

                time.sleep(0.5)

            except Exception as e:
                print(f"自动化流程中发生错误: {e}")
                time.sleep(2)

        print("--- 自动化流程已停止 ---")


if __name__ == "__main__":
    # --- Windows Tesseract 配置 ---
    # 【重要】请检查你的Tesseract安装路径是否与下面的一致。
    # 如果不一致，请修改为你的实际路径，然后取消下面这行代码的注释。
    # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

    app = App()
    app.mainloop()