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


# --- 配置文件管理器 (新增颜色配置) ---
class ConfigManager:
    def __init__(self):
        self.config_dir = os.path.join(os.path.expanduser("~"), ".auto_order_accepter")
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.defaults = {
            "monitor_x1": "100", "monitor_y1": "800",
            "monitor_x2": "600", "monitor_y2": "1000",
            "accept_btn_x": "300",
            # 搜索范围要大，覆盖有图和无图两种情况
            "search_y1": "700", "search_y2": "1000",
            # 【新增】接单按钮的RGB颜色
            "target_r": "255", "target_g": "100", "target_b": "50",
            "color_tolerance": "20",  # 颜色容差，防止渲染差异

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
        self.check_trial_period()
        self.title("自动接单助手 (智能色块定位版)")
        self.geometry("550x750")  # 加高一点
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

        # 【修改】接单按钮设置
        ttk.Label(settings_frame, text="接单按钮X坐标:").grid(row=2, column=0, sticky='w', padx=5, pady=2)
        self.entries['accept_btn_x'] = ttk.Entry(settings_frame, width=8)
        self.entries['accept_btn_x'].grid(row=2, column=1, padx=5)

        ttk.Label(settings_frame, text="搜索Y轴范围 (y1, y2):").grid(row=3, column=0, sticky='w', padx=5, pady=2)
        self.entries['search_y1'] = ttk.Entry(settings_frame, width=8)
        self.entries['search_y1'].grid(row=3, column=1, padx=5)
        self.entries['search_y2'] = ttk.Entry(settings_frame, width=8)
        self.entries['search_y2'].grid(row=3, column=2, padx=5)

        # 【新增】颜色设置
        color_frame = ttk.LabelFrame(main_frame, text="接单按钮颜色特征 (RGB)")
        color_frame.pack(fill=tk.X, pady=5)

        ttk.Label(color_frame, text="R(红):").pack(side=tk.LEFT, padx=5)
        self.entries['target_r'] = ttk.Entry(color_frame, width=5)
        self.entries['target_r'].pack(side=tk.LEFT)

        ttk.Label(color_frame, text="G(绿):").pack(side=tk.LEFT, padx=5)
        self.entries['target_g'] = ttk.Entry(color_frame, width=5)
        self.entries['target_g'].pack(side=tk.LEFT)

        ttk.Label(color_frame, text="B(蓝):").pack(side=tk.LEFT, padx=5)
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
        self.add_delay_entry(other_frame, "滚动页面后延时:", "delay_after_scroll", 3)
        self.add_delay_entry(other_frame, "点击接单后延时:", "delay_after_accept", 4)
        self.add_delay_entry(other_frame, "点击确认后延时:", "delay_after_confirm", 5)

        # 工具栏
        coords_frame = ttk.LabelFrame(main_frame, text="工具")
        coords_frame.pack(fill=tk.X, pady=10)
        self.coord_label = ttk.Label(coords_frame, text="鼠标: (x, y) RGB: -", font=("Helvetica", 10))
        self.coord_label.pack(side=tk.LEFT, padx=10)
        self.toggle_coords_btn = ttk.Button(coords_frame, text="开启取色/坐标", command=self.toggle_mouse_display)
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
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD)
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
                # 获取当前鼠标位置的颜色 (需要一点点性能，但只在调试时开启)
                pixel = pyautogui.screenshot(region=(x, y, 1, 1))
                r, g, b = pixel.getpixel((0, 0))
                self.coord_label.config(text=f"鼠标: ({x}, {y}) RGB: ({r}, {g}, {b})")
                time.sleep(0.1)
            except Exception:
                break

    def start_automation(self):
        self.is_running = True
        self.status_label.config(text="状态: 智能运行中...", foreground="green")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        try:
            self.current_config = {key: float(entry.get()) for key, entry in self.entries.items()}
        except ValueError:
            messagebox.showerror("错误", "所有输入必须是数字！")
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

        # --- 颜色搜索参数准备 ---
        accept_x = int(cfg['accept_btn_x'])
        search_y1 = int(cfg['search_y1'])
        search_y2 = int(cfg['search_y2'])

        target_color = np.array([cfg['target_b'], cfg['target_g'], cfg['target_r']])  # MSS 返回的是 BGR
        tolerance = int(cfg['color_tolerance'])

        # 定义搜索区域 (宽度设为10像素即可，减少计算量)
        search_monitor = {
            "left": accept_x - 5,
            "top": search_y1,
            "width": 10,
            "height": search_y2 - search_y1
        }

        confirm_x, confirm_y = int(cfg['confirm_btn_x']), int(cfg['confirm_btn_y'])
        close_x, close_y = int(cfg['close_btn_x']), int(cfg['close_btn_y'])

        print("--- 自动化流程已启动 (智能色块定位) ---")
        print(f"目标颜色 RGB: ({int(cfg['target_r'])}, {int(cfg['target_g'])}, {int(cfg['target_b'])})")

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

                        # 2. 滚动 (保持修复后的逻辑)
                        pyautogui.moveTo(center_x, center_y)
                        time.sleep(0.08)
                        pyautogui.scroll(-2000)
                        time.sleep(0.01)
                        pyautogui.scroll(-2000)
                        time.sleep(cfg['delay_after_scroll'])

                        # 3. 【核心修改】智能色块定位点击
                        # 截取按钮可能出现的垂直长条区域
                        search_img = np.array(sct.grab(search_monitor))
                        # 去掉alpha通道 (BGRA -> BGR)
                        search_img_bgr = search_img[:, :, :3]

                        # 计算颜色差异
                        diff = np.abs(search_img_bgr - target_color)
                        # 找到符合容差的像素点 (所有通道差异都小于容差)
                        mask = np.all(diff < tolerance, axis=2)

                        # 获取匹配点的坐标
                        y_indices, x_indices = np.where(mask)

                        if len(y_indices) > 0:
                            # 找到了！计算平均Y坐标
                            avg_y_offset = np.mean(y_indices)
                            real_click_y = search_y1 + avg_y_offset

                            # print(f"定位成功! Y坐标: {real_click_y:.1f}") # 调试用，生产环境可注释
                            pyautogui.click(accept_x, real_click_y)
                        else:
                            # 没找到颜色？可能是颜色设错了，或者按钮没加载出来
                            # 执行兜底策略：点击搜索区域的中间，或者原来的固定位置
                            print("未找到目标颜色，执行兜底点击...")
                            fallback_y = (search_y1 + search_y2) / 2
                            pyautogui.click(accept_x, fallback_y)

                        time.sleep(cfg['delay_after_accept'])

                        # 4. 确认
                        pyautogui.click(confirm_x, confirm_y)

                        t_end_action = time.time()

                        # 5. 后处理
                        time.sleep(cfg['delay_after_confirm'])
                        pyautogui.click(close_x, close_y)

                        print(f"\n[抢单报告] 耗时: {t_end_action - t0:.4f}s")
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