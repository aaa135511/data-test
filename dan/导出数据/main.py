import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import pandas as pd
import time
import csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class QueryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("自动化查询导出工具 - search.azbbzzc.com")
        self.root.geometry("650x550")

        self.excel_path = tk.StringVar()
        self.username = tk.StringVar(value="qq888")
        self.password = tk.StringVar(value="qq888")

        self.setup_ui()

    def setup_ui(self):
        # 账号密码设置区
        frame_login = tk.LabelFrame(self.root, text="登录设置", padx=10, pady=10)
        frame_login.pack(fill="x", padx=10, pady=5)

        tk.Label(frame_login, text="账号:").grid(row=0, column=0, padx=5, pady=5)
        tk.Entry(frame_login, textvariable=self.username, width=20).grid(row=0, column=1, padx=5, pady=5)

        tk.Label(frame_login, text="密码:").grid(row=0, column=2, padx=5, pady=5)
        tk.Entry(frame_login, textvariable=self.password, show="*", width=20).grid(row=0, column=3, padx=5, pady=5)

        # 文件选择区
        frame_file = tk.LabelFrame(self.root, text="数据源设置", padx=10, pady=10)
        frame_file.pack(fill="x", padx=10, pady=5)

        tk.Entry(frame_file, textvariable=self.excel_path, width=55, state="readonly").grid(row=0, column=0, padx=5,
                                                                                            pady=5)
        tk.Button(frame_file, text="导入Excel文件", command=self.select_file).grid(row=0, column=1, padx=5, pady=5)

        # 按钮区
        frame_action = tk.Frame(self.root)
        frame_action.pack(fill="x", padx=10, pady=5)
        tk.Button(frame_action, text="开始执行任务", bg="green", fg="white", font=("Arial", 12, "bold"),
                  command=self.start_task_thread).pack(pady=5)

        # 日志区
        frame_log = tk.LabelFrame(self.root, text="运行日志", padx=10, pady=10)
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(frame_log, wrap=tk.WORD)
        self.log_text.pack(fill="both", expand=True)

    def log(self, message):
        """线程安全的日志输出"""

        def update_log():
            current_time = time.strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{current_time}] {message}\n")
            self.log_text.see(tk.END)

        self.root.after(0, update_log)

    def show_info(self, title, message):
        """线程安全的成功弹窗"""
        self.root.after(0, lambda: messagebox.showinfo(title, message))

    def show_error(self, title, message):
        """线程安全的错误弹窗"""
        self.root.after(0, lambda: messagebox.showerror(title, message))

    def select_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
        if filepath:
            self.excel_path.set(filepath)
            self.log(f"已选择文件: {filepath}")

    def start_task_thread(self):
        if not self.excel_path.get():
            messagebox.showwarning("警告", "请先导入Excel文件！")
            return
        thread = threading.Thread(target=self.run_automation)
        thread.daemon = True
        thread.start()

    def set_checkbox(self, driver, label_text, check=True):
        try:
            xpath = f"//label[contains(., '{label_text}')]"
            label = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath)))
            class_str = label.get_attribute("class")
            is_checked = "is-checked" in class_str

            if (check and not is_checked) or (not check and is_checked):
                driver.execute_script("arguments[0].click();", label)
                time.sleep(0.5)
        except Exception as e:
            self.log(f"操作复选框 {label_text} 失败: {str(e)}")

    def get_detail_value(self, driver, title_text):
        try:
            xpath = f"//div[contains(text(), '{title_text}')]/following-sibling::div[1]"
            elem = driver.find_element(By.XPATH, xpath)
            return elem.text.strip()
        except NoSuchElementException:
            return ""

    def submit_and_handle_popups(self, driver):
        try:
            submit_btn = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//button/span[contains(text(), '请求报告')]/parent::button"))
            )
            driver.execute_script("arguments[0].click();", submit_btn)
            time.sleep(1.5)

            try:
                agree_btn = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.XPATH,
                                                    "//div[contains(@class, 'el-message-box__btns')]//button[contains(@class, 'el-button--primary')]"))
                )
                driver.execute_script("arguments[0].click();", agree_btn)
                time.sleep(1.5)
            except TimeoutException:
                pass

            try:
                new_data_btn = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.XPATH, "//span[contains(text(), '获取新数据')]/parent::button"))
                )
                driver.execute_script("arguments[0].click();", new_data_btn)
                time.sleep(1.5)
            except TimeoutException:
                pass

        except Exception as e:
            self.log(f"点击请求报告或处理弹窗时出现异常: {str(e)}")

    def save_to_csv_realtime(self, row_dict, csv_filename, headers):
        """静默的数据实时备份"""
        try:
            with open(csv_filename, mode='a', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writerow(row_dict)
        except Exception:
            pass

    def run_automation(self):
        self.log("开始初始化Chrome WebDriver...")
        driver = None
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--start-maximized')

            prefs = {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False
            }
            options.add_experimental_option("prefs", prefs)
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            wait = WebDriverWait(driver, 15)

            self.log("正在打开登录页面...")
            driver.get("http://search.azbbzzc.com/login.html")

            wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(self.username.get())
            driver.find_element(By.ID, "password").send_keys(self.password.get())
            driver.find_element(By.XPATH, "//button[@onclick='login(this)']").click()
            self.log("已点击登录，等待系统加载...")
            time.sleep(3)

            try:
                js_close_popups = """
                let layBtn = document.querySelector('.layui-layer-btn0');
                if(layBtn) layBtn.click();
                let elBtns = document.querySelectorAll('.el-message-box__btns button.el-button--primary');
                elBtns.forEach(btn => { if(btn.innerText.includes('确定')) btn.click(); });
                """
                driver.execute_script(js_close_popups)
            except Exception:
                pass
            time.sleep(1)

            self.log("进入客户管理...")
            menu_client = wait.until(EC.presence_of_element_located((By.XPATH, "//cite[text()='客户管理']")))
            driver.execute_script("arguments[0].click();", menu_client)
            time.sleep(1)

            self.log("进入数据查询...")
            menu_search = wait.until(EC.presence_of_element_located((By.XPATH, "//cite[text()='数据查询']")))
            driver.execute_script("arguments[0].click();", menu_search)
            time.sleep(3)

            try:
                iframe = wait.until(EC.presence_of_element_located((By.XPATH,
                                                                    "//iframe[contains(@src, 'changePassword.html') or contains(@src, 'data_search')] | //div[contains(@class, 'layui-show')]//iframe")))
                driver.switch_to.frame(iframe)
            except Exception:
                pass

            df = pd.read_excel(self.excel_path.get())
            self.log(f"成功读取Excel，共 {len(df)} 条数据，开始查询。")

            headers = [
                "姓名", "身份证", "核验结果", "当前逾期机构数", "当前履约机构数",
                "异常还款机构数", "睡眠机构数", "最大履约金额", "最近履约时间",
                "最近逾期时间", "履约笔数", "最长逾期天数", "探查结果", "最大逾期金额"
            ]

            timestamp = int(time.time())
            backup_csv = f"查询结果_实时备份_{timestamp}.csv"
            final_excel = f"查询结果导出_{timestamp}.xlsx"

            with open(backup_csv, mode='w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()

            results = []

            for index, row in df.iterrows():
                name = str(row['姓名']).strip()
                id_card = str(row['身份证']).strip()

                self.log(f"--- 正在处理: {name} ---")

                row_result = {key: "" for key in headers}
                row_result["姓名"] = name
                row_result["身份证"] = id_card

                # --- 步骤 A: 查 二要素 ---
                name_input = wait.until(
                    EC.presence_of_element_located((By.XPATH, "//label[@for='name']/following-sibling::div//input")))
                id_input = driver.find_element(By.XPATH, "//label[@for='idN']/following-sibling::div//input")

                driver.execute_script("arguments[0].value = '';", name_input)
                driver.execute_script("arguments[0].value = '';", id_input)
                name_input.send_keys(name)
                id_input.send_keys(id_card)

                self.set_checkbox(driver, "二要素认证", check=True)
                self.set_checkbox(driver, "超针C", check=False)

                self.submit_and_handle_popups(driver)

                try:
                    result_div = wait.until(
                        EC.presence_of_element_located((By.XPATH, "//div[contains(text(), '二要素核验结果')]")))
                    if "不一致" in result_div.text:
                        self.log(f"{name} 核验结果: 不一致")
                        row_result["核验结果"] = "不一致"

                        results.append(row_result)
                        self.save_to_csv_realtime(row_result, backup_csv, headers)

                        btn_back = driver.find_element(By.XPATH, "//button[@onclick='returnBack()']")
                        driver.execute_script("arguments[0].click();", btn_back)
                        time.sleep(1.5)
                        continue
                    else:
                        self.log(f"{name} 核验结果: 一致，抓取详情...")
                        row_result["核验结果"] = "一致"

                        btn_back = driver.find_element(By.XPATH, "//button[@onclick='returnBack()']")
                        driver.execute_script("arguments[0].click();", btn_back)
                        time.sleep(2)
                except Exception as e:
                    self.log(f"{name} 获取二要素失败，跳过。")
                    results.append(row_result)
                    self.save_to_csv_realtime(row_result, backup_csv, headers)

                    driver.execute_script("location.reload();")
                    time.sleep(3)
                    continue

                # --- 步骤 B: 查 超针C ---
                name_input = wait.until(
                    EC.presence_of_element_located((By.XPATH, "//label[@for='name']/following-sibling::div//input")))
                id_input = driver.find_element(By.XPATH, "//label[@for='idN']/following-sibling::div//input")

                driver.execute_script("arguments[0].value = '';", name_input)
                driver.execute_script("arguments[0].value = '';", id_input)
                name_input.send_keys(name)
                id_input.send_keys(id_card)

                self.set_checkbox(driver, "二要素认证", check=False)
                self.set_checkbox(driver, "超针C", check=True)

                self.submit_and_handle_popups(driver)

                wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(text(), '详细信息')]")))
                time.sleep(1)

                row_result["当前逾期机构数"] = self.get_detail_value(driver, "当前逾期机构数")
                row_result["当前履约机构数"] = self.get_detail_value(driver, "当前履约机构数")
                row_result["异常还款机构数"] = self.get_detail_value(driver, "异常还款机构数")
                row_result["睡眠机构数"] = self.get_detail_value(driver, "睡眠机构数")
                row_result["最大履约金额"] = self.get_detail_value(driver, "最大履约金额")
                row_result["最近履约时间"] = self.get_detail_value(driver, "最近履约时间")
                row_result["最近逾期时间"] = self.get_detail_value(driver, "最近逾期时间")
                row_result["履约笔数"] = self.get_detail_value(driver, "履约笔数")
                row_result["最长逾期天数"] = self.get_detail_value(driver, "最长逾期天数")
                row_result["最大逾期金额"] = self.get_detail_value(driver, "最大逾期金额")

                try:
                    detect_xpath = "//div[contains(text(), '探查结果')]/following-sibling::div//span[not(contains(@class, 'hidden'))]"
                    detect_elem = driver.find_element(By.XPATH, detect_xpath)
                    row_result["探查结果"] = detect_elem.text.strip()
                except NoSuchElementException:
                    row_result["探查结果"] = ""

                self.log(f"{name} 详情抓取完毕")

                results.append(row_result)
                self.save_to_csv_realtime(row_result, backup_csv, headers)

                btn_back = driver.find_element(By.XPATH, "//button[@onclick='returnBack()']")
                driver.execute_script("arguments[0].click();", btn_back)
                time.sleep(2)

            # --- 4. 正常结束 ---
            output_df = pd.DataFrame(results)
            output_df.to_excel(final_excel, index=False)
            self.log(f"--- 任务全部完成！ ---")
            self.log(f"最终结果保存在: {final_excel}")

            # 使用线程安全的方法弹出提示
            self.show_info("完成", f"全部查询顺利完成！\n数据已保存为:\n{final_excel}")

        except Exception as e:
            self.log(f"执行中断: {str(e)}")
            self.show_error("提示", f"程序未能执行到底，遇到错误:\n{str(e)}\n\n已有数据保存在同目录下的.csv文件中。")
        finally:
            if driver:
                driver.quit()
                self.log("浏览器已关闭。")


if __name__ == "__main__":
    root = tk.Tk()
    app = QueryApp(root)
    root.mainloop()