import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import pyautogui
import threading
import time
import json
import os
import numpy as np
import sys
import mss
import mss.tools  # 引入工具用于保存调试图片
from datetime import datetime, timedelta

# --- 全局极速设置 ---
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True


# --- 路径函数 ---
def get_application_path(relative_path):
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(application_path, relative_path)


# --- 配置文件管理器 ---
class ConfigManager:
    def __init__(self):
        self.config_dir = os.path.join(os.path.expanduser("~"), ".auto_order_accepter")
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.defaults = {
            "monitor_x1": "100", "monitor_y1": "800",
            "monitor_x2": "600", "monitor_y2": "1000",
            "accept_btn_x": "220",  # 用户当前的设置
            "search_y1": "700", "search_y2": "1015",
            "target_r": "46", "target_g": "150", "target_b": "213",
            "color_tolerance": "30",  # 稍微调大一点容差
            "confirm_btn_x": "500", "confirm_btn_y": "550",
            "close_btn_x": "900", "close_btn_y": "100",
            "delay_after_click_notify": "0.3",
            "delay_after_accept": "0.05",
            "delay_after_confirm": "1.5",
            "license_key": ""
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


# --- 日志重定向类 ---
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


# --- 主应用 GUI ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()

        self.title("自动接单助手 (调试增强版)")
        self.geometry("580x780")  # 稍微加宽一点显示日志
        self.attributes('-topmost', True)
        self.entries = {}
        self.automation_thread = None
        self.is_running = False
        self.show_coords = False

        self.SECRET_CODE = "VIP888"
        self.TRIAL_END_DATE = datetime(2025, 12, 5, 0, 0, 0)

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

        ttk.Label(settings_frame, text="接单按钮X坐标:").grid(row=2, column=0, sticky='w', padx=5, pady=2)
        self.entries['accept_btn_x'] = ttk.Entry(settings_frame, width=8)
        self.entries['accept_btn_x'].grid(row=2, column=1, padx=5)

        ttk.Label(settings_frame, text="搜索Y轴范围 (y1, y2):").grid(row=3, column=0, sticky='w', padx=5, pady=2)
        self.entries['search_y1'] = ttk.Entry(settings_frame, width=8)
        self.entries['search_y1'].grid(row=3, column=1, padx=5)
        self.entries['search_y2'] = ttk.Entry(settings_frame, width=8)
        self.entries['search_y2'].grid(row=3, column=2, padx=5)

        # 颜色设置
        color_frame = ttk.LabelFrame(main_frame, text="接单按钮颜色特征 (RGB)")
        color_frame.pack(fill=tk.X, pady=5)

        ttk.Label(color_frame, text="R:").pack(side=tk.LEFT, padx=2)
        self.entries['target_r'] = ttk.Entry(color_frame, width=5)
        self.entries['target_r'].pack(side=tk.LEFT)

        ttk.Label(color_frame, text="G:").pack(side=tk.LEFT, padx=2)
        self.entries['target_g'] = ttk.Entry(color_frame, width=5)
        self.entries['target_g'].pack(side=tk.LEFT)

        ttk.Label(color_frame, text="B:").pack(side=tk.LEFT, padx=2)
        self.entries['target_b'] = ttk.Entry(color_frame, width=5)
        self.entries['target_b'].pack(side=tk.LEFT)

        ttk.Label(color_frame, text="容差:").pack(side=tk.LEFT, padx=5)
        self.entries['color_tolerance'] = ttk.Entry(color_frame, width=5)
        self.entries['color_tolerance'].pack(side=tk.LEFT)

        # 其他设置
        other_frame = ttk.LabelFrame(main_frame, text="其他坐标与延时")
        other_frame.pack(fill=tk.X, pady=5)

        self.add_coord_entry(other_frame, "确认按钮 (x, y):", "confirm_btn_x", "confirm_btn_y", 0)
        self.add_coord_entry(other_frame, "关闭按钮 (x, y):", "close_btn_x", "close_btn_y", 1)

        self.add_delay_entry(other_frame, "点击通知后延时:", "delay_after_click_notify", 2)
        self.add_delay_entry(other_frame, "点击接单后延时:", "delay_after_accept", 3)
        self.add_delay_entry(other_frame, "点击确认后延时:", "delay_after_confirm", 4)

        # 工具栏
        coords_frame = ttk.LabelFrame(main_frame, text="工具")
        coords_frame.pack(fill=tk.X, pady=10)
        self.coord_label = ttk.Label(coords_frame, text="鼠标: (x, y) RGB: -", font=("Helvetica", 10))
        self.coord_label.pack(side=tk.LEFT, padx=10)
        self.toggle_coords_btn = ttk.Button(coords_frame, text="开启取色/坐标", command=self.toggle_mouse_display)
        self.toggle_coords_btn.pack(side=tk.RIGHT, padx=10)

        # 控制栏
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)
        self.save_btn = ttk.Button(control_frame, text="保存配置", command=self.save_settings)
        self.save_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.start_btn = ttk.Button(control_frame, text="开始运行", command=self.start_automation)
        self.start_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.stop_btn = ttk.Button(control_frame, text="停止运行", state=tk.DISABLED, command=self.stop_automation)
        self.stop_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        self.entries['license_key'] = ttk.Entry(control_frame, width=8, show="*")
        self.entries['license_key'].pack(side=tk.RIGHT, padx=5)

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
        if self.config_manager.save_config(data):
            messagebox.showinfo("成功", "配置已成功保存！")
        else:
            messagebox.showerror("错误", "无法保存配置。")

    def toggle_mouse_display(self):
        self.show_coords = not self.show_coords
        if self.show_coords:
            self.toggle_coords_btn.config(text="关闭取色")
            self.coord_thread = threading.Thread(target=self._update_mouse_coords_loop, daemon=True)
            self.coord_thread.start()
        else:
            self.toggle_coords_btn.config(text="开启取色/坐标")
            self.coord_label.config(text="鼠标: (x, y) RGB: -")

    def _update_mouse_coords_loop(self):
        while self.show_coords:
            try:
                x, y = pyautogui.position()
                pixel = pyautogui.screenshot(region=(x, y, 1, 1))
                r, g, b = pixel.getpixel((0, 0))
                self.coord_label.config(text=f"鼠标: ({x}, {y}) RGB: ({r}, {g}, {b})")
                time.sleep(0.1)
            except Exception:
                break

    def check_license_and_trial(self):
        user_code = self.entries['license_key'].get()
        if user_code == self.SECRET_CODE:
            return True
        current_time = datetime.now()
        if current_time < self.TRIAL_END_DATE:
            return True
        return False

    def start_automation(self):
        if not self.check_license_and_trial():
            messagebox.showerror("运行错误", "关键组件初始化失败。 (Error: 0x80070005)")
            sys.exit()

        self.is_running = True
        self.status_label.config(text="状态: 运行中...", foreground="green")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        try:
            self.current_config = {}
            for key, entry in self.entries.items():
                if key == 'license_key': continue
                self.current_config[key] = float(entry.get())
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

        notify_click_x = monitor_area['left'] + monitor_area['width'] / 2
        notify_click_y = monitor_area['top'] + monitor_area['height'] / 2

        accept_x = int(cfg['accept_btn_x'])
        search_y1 = int(cfg['search_y1'])
        search_y2 = int(cfg['search_y2'])

        target_color = np.array([cfg['target_b'], cfg['target_g'], cfg['target_r']])  # BGR
        tolerance = int(cfg['color_tolerance'])

        # 【优化】将搜索宽度增加到 20，防止X轴微小偏差导致切到文字
        search_monitor = {
            "left": accept_x - 10,
            "top": search_y1,
            "width": 20,
            "height": search_y2 - search_y1
        }

        confirm_x, confirm_y = int(cfg['confirm_btn_x']), int(cfg['confirm_btn_y'])
        close_x, close_y = int(cfg['close_btn_x']), int(cfg['close_btn_y'])

        print("--- 自动化流程已启动 ---")

        with mss.mss() as sct:
            previous_img_np = np.array(sct.grab(monitor_area))
            print("监控中...")

            while self.is_running:
                try:
                    current_img_np = np.array(sct.grab(monitor_area))
                    diff_pixels = np.sum(previous_img_np != current_img_np)

                    if diff_pixels > PIXEL_CHANGE_THRESHOLD:
                        t0 = time.time()
                        previous_img_np = current_img_np

                        # 1. 点击通知
                        pyautogui.click(notify_click_x, notify_click_y)
                        time.sleep(cfg['delay_after_click_notify'])

                        # 2. 高位锁定搜索
                        search_img = sct.grab(search_monitor)  # 获取MSS对象
                        search_img_np = np.array(search_img)  # 转Numpy
                        search_img_bgr = search_img_np[:, :, :3]  # 提取BGR

                        diff = np.abs(search_img_bgr - target_color)
                        mask = np.all(diff < tolerance, axis=2)

                        y_indices, x_indices = np.where(mask)

                        if len(y_indices) > 0:
                            min_y_offset = np.min(y_indices)
                            real_click_y = search_y1 + min_y_offset + 10
                            print(f"锁定成功! 坐标: ({accept_x}, {real_click_y})")
                            pyautogui.click(accept_x, real_click_y)
                        else:
                            # 【调试核心】详细分析为什么没找到
                            print("未找到目标颜色!")

                            # 计算整个区域内最接近的颜色
                            # 对每个像素求RGB三个通道的平均差异
                            mean_diff_per_pixel = np.mean(diff, axis=2)
                            min_diff_val = np.min(mean_diff_per_pixel)

                            # 找到最接近的那个像素的坐标
                            min_loc = np.unravel_index(np.argmin(mean_diff_per_pixel), mean_diff_per_pixel.shape)
                            closest_pixel_bgr = search_img_bgr[min_loc[0], min_loc[1]]
                            closest_pixel_rgb = closest_pixel_bgr[::-1]  # 转回RGB方便阅读

                            print(f" > 区域内最小色差: {min_diff_val:.1f} (阈值: {tolerance})")
                            print(f" > 最接近的颜色 RGB: {closest_pixel_rgb}")
                            print(f" > 建议: 检查X轴是否对准，或将容差设为 {int(min_diff_val) + 5}")

                            # 保存调试图片
                            debug_filename = "debug_error_strip.png"
                            mss.tools.to_png(search_img.rgb, search_img.size, output=debug_filename)
                            print(f" > 已保存调试图片: {debug_filename} (请查看是否截到了按钮)")

                            # 兜底点击
                            fallback_y = search_y1 + (search_y2 - search_y1) * 0.3
                            pyautogui.click(accept_x, fallback_y)

                        time.sleep(cfg['delay_after_accept'])

                        # 3. 确认
                        pyautogui.click(confirm_x, confirm_y)

                        t_end_action = time.time()

                        # 4. 后处理
                        time.sleep(cfg['delay_after_confirm'])
                        pyautogui.click(close_x, close_y)

                        print(f"[抢单报告] 耗时: {t_end_action - t0:.4f}s")
                        print("------------------------------------")

                        time.sleep(2)
                        previous_img_np = np.array(sct.grab(monitor_area))
                        print("--- 返回监控 ---")

                except Exception as e:
                    print(f"错误: {e}")
                    time.sleep(1)

        print("--- 流程停止 ---")


if __name__ == "__main__":
    app = App()
    app.mainloop()