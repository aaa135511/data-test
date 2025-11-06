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


# 【新增】资源路径解析函数，解决打包后找不到文件的问题
def resource_path(relative_path):
    """ 获取资源的绝对路径，无论是从源码运行还是从打包后的exe运行 """
    try:
        # PyInstaller 创建一个临时文件夹，并将路径存储在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


# --- 配置文件管理器 (无变化) ---
class ConfigManager:
    def __init__(self):
        self.config_dir = os.path.join(os.path.expanduser("~"), ".auto_order_accepter")
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.defaults = {
            "monitor_x1": "100", "monitor_y1": "800",
            "monitor_x2": "600", "monitor_y2": "1000",
            "accept_area_x1": "200", "accept_area_y1": "600",
            "accept_area_x2": "800", "accept_area_y2": "1000",
            "confirm_btn_x": "500", "confirm_btn_y": "550",
            "close_btn_x": "900", "close_btn_y": "100",
            "delay_step1_2": "0.5",
            "delay_others": "0.1",
            "delay_after_confirm": "2.0",
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
        self.widget.insert(tk.END, str)
        self.widget.see(tk.END)

    def flush(self):
        pass


# --- 主应用 GUI (无变化) ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.check_trial_period()
        self.title("自动接单助手 (Windows版)")
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
        if current_time - first_run_time > 604800:
            messagebox.showerror("运行错误", "关键组件初始化失败，程序无法启动。 (Error: 0x80070005)")
            sys.exit()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        settings_frame = ttk.LabelFrame(main_frame, text="参数设置")
        settings_frame.pack(fill=tk.X, pady=5)
        self.add_coord_entry(settings_frame, "监控区左上角 (x1, y1):", "monitor_x1", "monitor_y1", 0)
        self.add_coord_entry(settings_frame, "监控区右下角 (x2, y2):", "monitor_x2", "monitor_y2", 1)
        self.add_coord_entry(settings_frame, "接单按钮搜索区 (x1, y1):", "accept_area_x1", "accept_area_y1", 2)
        self.add_coord_entry(settings_frame, "接单按钮搜索区 (x2, y2):", "accept_area_x2", "accept_area_y2", 3)
        self.add_coord_entry(settings_frame, "确认按钮坐标 (x, y):", "confirm_btn_x", "confirm_btn_y", 4)
        self.add_coord_entry(settings_frame, "关闭按钮坐标 (x, y):", "close_btn_x", "close_btn_y", 5)
        ttk.Separator(settings_frame, orient='horizontal').grid(row=6, columnspan=4, sticky='ew', pady=5)
        self.add_delay_entry(settings_frame, "步骤1->2延时(秒):", "delay_step1_2", 7)
        self.add_delay_entry(settings_frame, "其他步骤延时(秒):", "delay_others", 8)
        self.add_delay_entry(settings_frame, "确认后延时(秒):", "delay_after_confirm", 9)
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
        # 【修改】使用 resource_path 检查模板文件
        template_path = resource_path('accept_button_template.png')
        if not os.path.exists(template_path):
            messagebox.showerror("错误",
                                 f"找不到模板文件！\n路径: {template_path}\n请确保 'accept_button_template.png' 与程序在同一目录下。")
            return

        self.is_running = True
        self.status_label.config(text="状态: 运行中...", foreground="green")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        # 【修改】删除或注释掉下面这行
        # self.iconify()

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
        # 【修改】删除或注释掉下面这两行
        # self.deiconify()
        # self.attributes('-topmost', True)

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
        accept_search_region = (
            int(cfg['accept_area_x1']), int(cfg['accept_area_y1']),
            int(cfg['accept_area_x2']) - int(cfg['accept_area_x1']),
            int(cfg['accept_area_y2']) - int(cfg['accept_area_y1'])
        )

        # 【修改】使用 resource_path 加载模板图片
        template_path = resource_path('accept_button_template.png')
        template_image = cv2.imread(template_path, cv2.IMREAD_COLOR)
        template_h, template_w, _ = template_image.shape

        PIXEL_CHANGE_THRESHOLD = 100

        print("--- 自动化流程已启动 (终极优化版) ---")

        with mss.mss() as sct:
            previous_img_np = np.array(sct.grab(monitor_area))
            print("已获取初始状态，开始高频监控像素变化...")

            while self.is_running:
                try:
                    current_img_np = np.array(sct.grab(monitor_area))
                    diff_pixels = np.sum(previous_img_np != current_img_np)

                    if diff_pixels > PIXEL_CHANGE_THRESHOLD:
                        t0 = time.time()
                        print(f"\n检测到显著像素变化 ({diff_pixels} > {PIXEL_CHANGE_THRESHOLD})！判定为新订单...")
                        previous_img_np = current_img_np

                        pyautogui.click(monitor_area['left'] + monitor_area['width'] / 2,
                                        monitor_area['top'] + monitor_area['height'] / 2)
                        time.sleep(cfg['delay_step1_2'])

                        print("滚动页面...")
                        pyautogui.scroll(-2000)
                        time.sleep(cfg['delay_others'])

                        print("在指定区域内搜索'接单'按钮...")
                        search_area_shot = pyautogui.screenshot(region=accept_search_region)
                        search_area_cv = cv2.cvtColor(np.array(search_area_shot), cv2.COLOR_RGB2BGR)

                        search_h, search_w, _ = search_area_cv.shape
                        if search_h < template_h or search_w < template_w:
                            print(
                                f"[错误] '接单按钮搜索区' ({search_w}x{search_h}) 小于模板图片 ({template_w}x{template_h})！")
                            print("请在GUI中设置一个更大的搜索区域。正在关闭详情页...")
                            pyautogui.click(int(cfg['close_btn_x']), int(cfg['close_btn_y']))
                            time.sleep(3)
                            continue

                        result = cv2.matchTemplate(search_area_cv, template_image, cv2.TM_CCOEFF_NORMED)
                        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

                        if max_val >= 0.8:
                            button_center_x = accept_search_region[0] + max_loc[0] + template_w // 2
                            button_center_y = accept_search_region[1] + max_loc[1] + template_h // 2
                            print(
                                f"成功找到'接单'按钮，相似度: {max_val:.2f}，点击坐标: ({button_center_x}, {button_center_y})")
                            pyautogui.click(button_center_x, button_center_y)
                            time.sleep(cfg['delay_others'])
                            print(f"点击确认按钮...")
                            pyautogui.click(int(cfg['confirm_btn_x']), int(cfg['confirm_btn_y']))
                            print(f"等待加载 {cfg['delay_after_confirm']} 秒...")
                            time.sleep(cfg['delay_after_confirm'])
                            pyautogui.click(int(cfg['close_btn_x']), int(cfg['close_btn_y']))
                            t_end = time.time()
                            print("\n--- [计时报告] 新订单处理成功 ---")
                            print(f"总耗时 (从检测到变化开始): {t_end - t0:.4f} 秒")
                            print("------------------------------------")
                        else:
                            print(f"[信息] 未找到'接单'按钮 (最高相似度: {max_val:.2f})，可能已被他人接单。")
                            print("正在关闭详情页返回...")
                            pyautogui.click(int(cfg['close_btn_x']), int(cfg['close_btn_y']))

                        print("--- 一次处理流程完成，返回监控状态 ---\n")
                        time.sleep(3)
                        previous_img_np = np.array(sct.grab(monitor_area))

                except Exception as e:
                    print(f"自动化流程中发生严重错误: {e}\n")
                    time.sleep(2)

        print("--- 自动化流程已停止 ---")


if __name__ == "__main__":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    app = App()
    app.mainloop()