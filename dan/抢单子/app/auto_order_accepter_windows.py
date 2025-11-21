import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import pyautogui
import pytesseract
from PIL import Image
import threading
import time
import json
import os
import cv2
import numpy as np
import sys
import mss

# --- 全局极速设置 ---
# 保持极速设置，但我们在关键部位手动控制微秒级延迟
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True


# --- 路径函数 (无变化) ---
def get_application_path(relative_path):
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(application_path, relative_path)


# --- 配置文件管理器 (无变化) ---
class ConfigManager:
    def __init__(self):
        self.config_dir = os.path.join(os.path.expanduser("~"), ".auto_order_accepter")
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.defaults = {
            "monitor_x1": "100", "monitor_y1": "800",
            "monitor_x2": "600", "monitor_y2": "1000",
            "accept_btn_x": "300",
            "accept_btn_y1": "860", "accept_btn_y2": "920",
            "confirm_btn_x": "500", "confirm_btn_y": "550",
            "close_btn_x": "900", "close_btn_y": "100",
            "delay_after_click_notify": "0.3",
            "delay_after_scroll": "0.05",
            "delay_after_accept": "0.05",
            "delay_after_confirm": "1.5",
            "first_run_timestamp": 0
        }
        os.makedirs(self.config_dir, exist_ok=True)

    def load_config(self):
        if not os.path.exists(self.config_path):
            return self.defaults
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                for key, value in self.defaults.items():
                    if key not in config:
                        config[key] = value
                return config
        except (json.JSONDecodeError, IOError):
            return self.defaults

    def save_config(self, data):
        try:
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=4)
            return True
        except IOError:
            return False


# --- 日志重定向类 (无变化) ---
class TextRedirector(object):
    def __init__(self, widget):
        self.widget = widget

    def write(self, str):
        try:
            self.widget.insert(tk.END, str)
            self.widget.see(tk.END)
        except:
            pass

    def flush(self):
        pass


# --- 主应用 GUI (无变化) ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.check_trial_period()
        self.title("自动接单助手 (极速修正版)")
        self.geometry("550x680")
        self.attributes('-topmost', True)
        self.entries = {}
        self.automation_thread = None
        self.is_running = False
        self.show_coords = False
        self.create_widgets()
        self.load_settings()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def check_trial_period(self):
        config = self.config_manager.load_config()
        first_run_time = config.get("first_run_timestamp", 0)
        if first_run_time == 0:
            config["first_run_timestamp"] = time.time()
            self.config_manager.save_config(config)
            return
        current_time = time.time()
        if current_time - first_run_time > 60480000:
            messagebox.showerror("运行错误", "关键组件初始化失败。")
            sys.exit()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        settings_frame = ttk.LabelFrame(main_frame, text="参数设置")
        settings_frame.pack(fill=tk.X, pady=5)

        self.add_coord_entry(settings_frame, "监控区左上角 (x1, y1):", "monitor_x1", "monitor_y1", 0)
        self.add_coord_entry(settings_frame, "监控区右下角 (x2, y2):", "monitor_x2", "monitor_y2", 1)

        ttk.Label(settings_frame, text="接单按钮X坐标:").grid(row=2, column=0, sticky='w', padx=5, pady=2)
        self.entries['accept_btn_x'] = ttk.Entry(settings_frame, width=8)
        self.entries['accept_btn_x'].grid(row=2, column=1, padx=5)

        ttk.Label(settings_frame, text="接单按钮Y轴范围 (y1, y2):").grid(row=3, column=0, sticky='w', padx=5, pady=2)
        self.entries['accept_btn_y1'] = ttk.Entry(settings_frame, width=8)
        self.entries['accept_btn_y1'].grid(row=3, column=1, padx=5)
        self.entries['accept_btn_y2'] = ttk.Entry(settings_frame, width=8)
        self.entries['accept_btn_y2'].grid(row=3, column=2, padx=5)

        self.add_coord_entry(settings_frame, "确认按钮坐标 (x, y):", "confirm_btn_x", "confirm_btn_y", 4)
        self.add_coord_entry(settings_frame, "关闭按钮坐标 (x, y):", "close_btn_x", "close_btn_y", 5)
        ttk.Separator(settings_frame, orient='horizontal').grid(row=6, columnspan=4, sticky='ew', pady=5)
        self.add_delay_entry(settings_frame, "点击通知后延时(秒):", "delay_after_click_notify", 7)
        self.add_delay_entry(settings_frame, "滚动页面后延时(秒):", "delay_after_scroll", 8)
        self.add_delay_entry(settings_frame, "点击接单后延时(秒):", "delay_after_accept", 9)
        self.add_delay_entry(settings_frame, "点击确认后延时(秒):", "delay_after_confirm", 10)

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
        self.status_label.pack(pady=2)
        log_frame = ttk.LabelFrame(main_frame, text="运行日志")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        sys.stdout = TextRedirector(self.log_text)
        sys.stderr = TextRedirector(self.log_text)

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
        current_config = self.config_manager.load_config()
        data['first_run_timestamp'] = current_config.get('first_run_timestamp', 0)
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
        self.status_label.config(text="状态: 极速运行中...", foreground="green")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
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

    def on_closing(self):
        if self.is_running:
            self.stop_automation()
        self.destroy()

    def _automation_loop(self):
        cfg = self.current_config
        monitor_area = {
            "left": int(cfg['monitor_x1']), "top": int(cfg['monitor_y1']),
            "width": int(cfg['monitor_x2']) - int(cfg['monitor_x1']),
            "height": int(cfg['monitor_y2']) - int(cfg['monitor_y1'])
        }
        PIXEL_CHANGE_THRESHOLD = 100

        screen_width, screen_height = pyautogui.size()
        center_x, center_y = screen_width / 2, screen_height / 2

        notify_click_x = monitor_area['left'] + monitor_area['width'] / 2
        notify_click_y = monitor_area['top'] + monitor_area['height'] / 2

        accept_x = int(cfg['accept_btn_x'])
        y1 = int(cfg['accept_btn_y1'])
        y2 = int(cfg['accept_btn_y2'])
        click_points = [
            (accept_x, y1),
            (accept_x, (y1 + y2) // 2),
            (accept_x, y2)
        ]

        confirm_x, confirm_y = int(cfg['confirm_btn_x']), int(cfg['confirm_btn_y'])
        close_x, close_y = int(cfg['close_btn_x']), int(cfg['close_btn_y'])

        print("--- 自动化流程已启动 (滚动修复版) ---")

        with mss.mss() as sct:
            previous_img_np = np.array(sct.grab(monitor_area))
            print("监控中...")

            last_loop_time = time.time()

            while self.is_running:
                try:
                    current_img_np = np.array(sct.grab(monitor_area))
                    diff_pixels = np.sum(previous_img_np != current_img_np)

                    if diff_pixels > PIXEL_CHANGE_THRESHOLD:
                        t0 = time.time()
                        previous_img_np = current_img_np

                        # 1. 点击通知
                        pyautogui.click(notify_click_x, notify_click_y)

                        # 等待页面加载 (根据网速调整)
                        time.sleep(cfg['delay_after_click_notify'])

                        # 2. 【修复】滚动逻辑
                        # 瞬间移动到屏幕中心
                        pyautogui.moveTo(center_x, center_y)

                        # 【关键修复】: 必须给浏览器一点时间识别鼠标已经到了页面中间
                        # 0.08秒是经验值，既比原来的0.2秒快，又能保证系统识别到焦点
                        time.sleep(0.08)

                        # 【优化】爆发式滚动
                        # 分两次大滚动，中间加极微小的间隔，防止系统吞掉指令
                        # -2000 的值比之前的 -1000 更大，滚得更远
                        pyautogui.scroll(-2000)
                        time.sleep(0.01)  # 10毫秒间隔，几乎不耗时但能保证稳定性
                        pyautogui.scroll(-2000)

                        # 滚动后等待
                        time.sleep(cfg['delay_after_scroll'])

                        # 3. 区域连击
                        for point in click_points:
                            pyautogui.click(point[0], point[1])

                        time.sleep(cfg['delay_after_accept'])

                        # 4. 确认
                        pyautogui.click(confirm_x, confirm_y)

                        t_end_action = time.time()

                        # 5. 后处理
                        time.sleep(cfg['delay_after_confirm'])
                        pyautogui.click(close_x, close_y)

                        total_action_time = t_end_action - t0
                        print(f"\n[抢单报告] 动作总耗时: {total_action_time:.4f} 秒")
                        print("------------------------------------")

                        time.sleep(2)
                        previous_img_np = np.array(sct.grab(monitor_area))
                        print("--- 返回监控 ---")

                    last_loop_time = time.time()

                except Exception as e:
                    print(f"错误: {e}")
                    time.sleep(1)

        print("--- 流程停止 ---")


if __name__ == "__main__":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    app = App()
    app.mainloop()