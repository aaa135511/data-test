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
            "accept_btn_x": "300", "accept_btn_y": "900",
            "confirm_btn_x": "500", "confirm_btn_y": "550",
            "close_btn_x": "900", "close_btn_y": "100",
            "delay_after_click_notify": "0.5",
            "delay_after_scroll": "0.1",
            "delay_after_accept": "0.1",
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
        self.title("自动接单助手 (极速版)")
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
        self.add_coord_entry(settings_frame, "接单按钮坐标 (x, y):", "accept_btn_x", "accept_btn_y", 2)
        self.add_coord_entry(settings_frame, "确认按钮坐标 (x, y):", "confirm_btn_x", "confirm_btn_y", 3)
        self.add_coord_entry(settings_frame, "关闭按钮坐标 (x, y):", "close_btn_x", "close_btn_y", 4)
        ttk.Separator(settings_frame, orient='horizontal').grid(row=5, columnspan=4, sticky='ew', pady=5)
        self.add_delay_entry(settings_frame, "点击通知后延时(秒):", "delay_after_click_notify", 6)
        self.add_delay_entry(settings_frame, "滚动页面后延时(秒):", "delay_after_scroll", 7)
        self.add_delay_entry(settings_frame, "点击接单后延时(秒):", "delay_after_accept", 8)
        self.add_delay_entry(settings_frame, "点击确认后延时(秒):", "delay_after_confirm", 9)
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
        self.status_label.config(text="状态: 运行中...", foreground="green")
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

        print("--- 自动化流程已启动 (极速固定坐标版) ---")

        with mss.mss() as sct:
            previous_img_np = np.array(sct.grab(monitor_area))
            print("已获取初始状态，开始高频监控像素变化...")

            # 【新增】用于记录上一次循环的时间点
            last_loop_time = time.time()

            while self.is_running:
                try:
                    current_img_np = np.array(sct.grab(monitor_area))
                    diff_pixels = np.sum(previous_img_np != current_img_np)

                    if diff_pixels > PIXEL_CHANGE_THRESHOLD:
                        timestamps = {'t0_detected': time.time()}
                        print(f"\n检测到像素变化 ({diff_pixels} > {PIXEL_CHANGE_THRESHOLD})！执行抢单...")
                        previous_img_np = current_img_np

                        pyautogui.click(monitor_area['left'] + monitor_area['width'] / 2,
                                        monitor_area['top'] + monitor_area['height'] / 2)
                        timestamps['t1_clicked_notify'] = time.time()
                        time.sleep(cfg['delay_after_click_notify'])
                        timestamps['t2_after_delay1'] = time.time()

                        pyautogui.scroll(-2000)
                        timestamps['t3_scrolled'] = time.time()
                        time.sleep(cfg['delay_after_scroll'])
                        timestamps['t4_after_delay2'] = time.time()

                        pyautogui.click(int(cfg['accept_btn_x']), int(cfg['accept_btn_y']))
                        timestamps['t5_clicked_accept'] = time.time()
                        time.sleep(cfg['delay_after_accept'])
                        timestamps['t6_after_delay3'] = time.time()

                        pyautogui.click(int(cfg['confirm_btn_x']), int(cfg['confirm_btn_y']))
                        timestamps['t7_clicked_confirm'] = time.time()
                        time.sleep(cfg['delay_after_confirm'])
                        timestamps['t8_after_delay4'] = time.time()

                        pyautogui.click(int(cfg['close_btn_x']), int(cfg['close_btn_y']))
                        timestamps['t9_clicked_close'] = time.time()

                        # 【修改】更新计时报告
                        print("\n--- [计时报告] 抢单流程完毕 ---")
                        print(f" > 像素识别耗时:      {timestamps['t0_detected'] - last_loop_time:.4f} 秒")
                        print(
                            f" > 点击通知耗时:      {timestamps['t1_clicked_notify'] - timestamps['t0_detected']:.4f} 秒")
                        print(
                            f" > [等待] 加载详情页: {timestamps['t2_after_delay1'] - timestamps['t1_clicked_notify']:.4f} 秒 (设置值: {cfg['delay_after_click_notify']})")
                        print(
                            f" > 滚动页面耗时:      {timestamps['t3_scrolled'] - timestamps['t2_after_delay1']:.4f} 秒")
                        print(
                            f" > [等待] 滚动后延时: {timestamps['t4_after_delay2'] - timestamps['t3_scrolled']:.4f} 秒 (设置值: {cfg['delay_after_scroll']})")
                        print(
                            f" > 点击接单耗时:      {timestamps['t5_clicked_accept'] - timestamps['t4_after_delay2']:.4f} 秒")
                        print(
                            f" > [等待] 接单后延时: {timestamps['t6_after_delay3'] - timestamps['t5_clicked_accept']:.4f} 秒 (设置值: {cfg['delay_after_accept']})")
                        print(
                            f" > 点击确认耗时:      {timestamps['t7_clicked_confirm'] - timestamps['t6_after_delay3']:.4f} 秒")
                        print(
                            f" > [等待] 确认后加载: {timestamps['t8_after_delay4'] - timestamps['t7_clicked_confirm']:.4f} 秒 (设置值: {cfg['delay_after_confirm']})")
                        print(
                            f" > 点击关闭耗时:      {timestamps['t9_clicked_close'] - timestamps['t8_after_delay4']:.4f} 秒")
                        print("------------------------------------")
                        print(
                            f" >> 总耗时 (从上轮检测结束到本轮关闭): {timestamps['t9_clicked_close'] - last_loop_time:.4f} 秒 <<")

                        print("\n--- 返回监控状态 ---\n")
                        time.sleep(3)
                        previous_img_np = np.array(sct.grab(monitor_area))

                    # 【修改】在每次循环结束后，更新时间戳
                    last_loop_time = time.time()

                except Exception as e:
                    print(f"自动化流程中发生严重错误: {e}\n")
                    time.sleep(2)

        print("--- 自动化流程已停止 ---")


if __name__ == "__main__":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    app = App()
    app.mainloop()