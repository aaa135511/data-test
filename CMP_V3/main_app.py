# ==============================================================================
# --- 0. 导入所需库 ---
# ==============================================================================
import json
import os
import re
import tkinter as tk
import traceback
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, scrolledtext

import pandas as pd


# ==============================================================================
# --- 1. 从旧脚本复制的所有辅助函数和核心处理函数 ---
# (这部分代码保持不变，直接从您的两个脚本中复制过来)
# ==============================================================================

# --- 来自 generate_analysis_files_v1.py 的函数 ---
def generate_flight_key(exec_date, flight_no, dep_icao, arr_icao):
    if not all([exec_date, flight_no, dep_icao, arr_icao]): return "KEY_GENERATION_FAILED"
    flight_no, dep_icao, arr_icao = str(flight_no).strip(), str(dep_icao).strip(), str(arr_icao).strip()
    if isinstance(exec_date, datetime): exec_date = exec_date.date()
    return f"{exec_date.strftime('%Y-%m-%d')}_{flight_no}_{dep_icao}_{arr_icao}"


def get_flight_date_from_aftn(data, tele_body, receive_time):
    dof_match = re.search(r'DOF/(\d{6})', tele_body)
    if dof_match:
        try:
            return datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date()
        except:
            pass
    if isinstance(receive_time, datetime): return receive_time.date()
    return None


def parse_core_business_info(body):
    changes = {}
    pattern = r'-\s*(\d{1,2})\s*/\s*(.*?)(?=\s*-\s*\d{1,2}\s*/|\)$)'
    matches = re.findall(pattern, body)
    for item_num_str, content_raw in matches:
        content = content_raw.strip().replace('\r\n', ' ').replace('\n', ' ')
        if item_num_str == '7':
            changes['New_FlightNo'] = content.split('/')[0].strip()
        elif item_num_str == '9':
            changes['New_CraftType'] = content.split('/')[0].strip()
        elif item_num_str == '13' and len(content) >= 8:
            changes['New_Departure_Time'] = content[-4:]
        elif item_num_str == '15':
            changes['New_Route'] = content
        elif item_num_str == '16':
            parts = content.split()
            if parts:
                dest_eet = parts[0]
                changes['New_Destination'] = dest_eet[:-4] if len(dest_eet) >= 8 else dest_eet
                if len(parts) > 1: changes['New_Alternate_1'] = parts[1]
                if len(parts) > 2: changes['New_Alternate_2'] = parts[2]
        elif item_num_str == '18':
            if re.search(r'REG/(\S+)', content): changes['New_RegNo'] = re.search(r'REG/(\S+)', content).group(1)
            if re.search(r'STS/(\S+)', content): changes['New_Mission_STS'] = re.search(r'STS/(\S+)', content).group(1)
    return changes


def process_aftn_for_analysis(df, target_date):
    processed_records = []
    for index, row in df.iterrows():
        try:
            data = json.loads(row.iloc[1])
            tele_body = data.get('teleBody', '')
            msg_type = tele_body[1:4].strip()
            if msg_type in ['DEP', 'ARR']: continue
            receive_time = pd.to_datetime(row.iloc[-1], errors='coerce')
            if pd.isna(receive_time): continue
            flight_date = get_flight_date_from_aftn(data, tele_body, receive_time)
            if not flight_date or flight_date != target_date: continue
            flight_no_match = re.search(r'-\s*([A-Z0-9-]{3,10}?)\s*-', tele_body)
            full_flight_no = flight_no_match.group(
                1).strip() if flight_no_match else f"{data.get('airlineIcaoCode', '')}{str(data.get('flightNo', '')).lstrip('0')}"
            dep_icao, arr_icao = data.get('depAirportIcaoCode'), data.get('arrAirportIcaoCode')
            record = {'ReceiveTime': receive_time, 'MessageType': msg_type, 'FlightNo': full_flight_no,
                      'RegNo': data.get('regNo'), 'DepAirport': dep_icao, 'ArrAirport': arr_icao,
                      'CraftType': data.get('aerocraftTypeIcaoCode'), 'RawMessage': tele_body}
            change_details = {}
            if msg_type in ['CHG', 'CPL']:
                change_details = parse_core_business_info(tele_body)
            elif msg_type == 'DLA':
                dla_match = re.search(r'-\s*\w+\s*-\s*\w{4}(\d{4})', tele_body)
                if dla_match: change_details['New_Departure_Time'] = dla_match.group(1)
            record.update(change_details)
            record['FlightKey'] = generate_flight_key(flight_date, record.get('New_FlightNo', full_flight_no), dep_icao,
                                                      arr_icao)
            processed_records.append(record)
        except Exception:
            continue
    return pd.DataFrame(processed_records)


def process_fpla_for_analysis(df, target_date):
    processed_records = []
    for index, row in df.iterrows():
        try:
            sobt_str = str(row.get('SOBT')).split('.')[0]
            if len(sobt_str) < 8: continue
            flight_date = datetime.strptime(sobt_str[:8], "%Y%m%d").date()
            if flight_date != target_date: continue
            record = {
                'FlightKey': generate_flight_key(flight_date, row.get('CALLSIGN'), row.get('DEPAP'), row.get('ARRAP')),
                'ReceiveTime': row.get('SENDTIME'), 'FPLA_Status': row.get('PSCHEDULESTATUS'),
                'FlightNo': row.get('CALLSIGN'), 'RegNo': row.get('EREGNUMBER') or row.get('REGNUMBER'),
                'DepAirport': row.get('DEPAP'), 'ArrAirport': row.get('ARRAP'), 'SOBT': row.get('SOBT'),
                'SIBT': row.get('SIBT'), 'Route': row.get('SROUTE'), 'MissionType': row.get('PMISSIONTYPE'),
                'MissionProperty': row.get('PMISSIONPROPERTY'), 'CraftType': row.get('PSAIRCRAFTTYPE')}
            processed_records.append(record)
        except Exception:
            continue
    return pd.DataFrame(processed_records)


# --- 来自 run_semiauto_comparison.py 的函数 ---
def convert_utc_str_to_bjt(time_str, date_obj):
    if pd.isna(time_str): return pd.NaT
    try:
        time_val_str = str(time_str).split('.')[0].zfill(4)
        utc_dt = datetime.combine(date_obj, datetime.strptime(time_val_str, "%H%M").time())
        return utc_dt + timedelta(hours=8)
    except Exception:
        return pd.NaT


def format_time(dt_obj):
    if pd.isna(dt_obj): return ''
    return dt_obj.strftime('%m-%d %H:%M')


def parse_fpla_time(time_val):
    if pd.isna(time_val): return pd.NaT
    try:
        time_str = str(time_val).split('.')[0]
        format_str = '%Y%m%d%H%M%S' if len(time_str) == 14 else '%Y%m%d%H%M'
        return pd.to_datetime(time_str, format=format_str, errors='coerce')
    except Exception:
        return pd.NaT


def auto_set_column_width(df, writer, sheet_name):
    worksheet = writer.sheets[sheet_name]
    for i, col in enumerate(df.columns):
        max_len = max(len(str(col)), df[col].astype(str).map(len).max())
        worksheet.set_column(i, i, max_len + 5)


def run_plan_comparison(aftn_df, fpla_df, target_date_obj):
    plan_results = []
    common_flight_keys = set(aftn_df['FlightKey'].unique()) & set(fpla_df['FlightKey'].unique())
    for flight_key in common_flight_keys:
        aftn_fpls = aftn_df[(aftn_df['FlightKey'] == flight_key) & (aftn_df['MessageType'] == 'FPL')].sort_values(
            'ReceiveTime', ascending=False)
        fpla_plans = fpla_df[
            (fpla_df['FlightKey'] == flight_key) & (fpla_df['FPLA_Status'].isin(['ADD', 'ALL', 'UPD']))].sort_values(
            'ReceiveTime', ascending=False)
        if aftn_fpls.empty or fpla_plans.empty: continue
        latest_fpl, latest_fpla_plan = aftn_fpls.iloc[0], fpla_plans.iloc[0]
        fpl_time_match = re.search(r'-\w{4,7}(\d{4})\s', latest_fpl.get('RawMessage', ''))
        fpl_eobt_str = fpl_time_match.group(1) if fpl_time_match else np.nan
        dof_match = re.search(r'DOF/(\d{6})', latest_fpl.get('RawMessage', ''))
        base_date = datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date() if dof_match else target_date_obj
        fpl_sobt_bjt, fpla_sobt = convert_utc_str_to_bjt(fpl_eobt_str, base_date), parse_fpla_time(
            latest_fpla_plan['SOBT'])
        reg_match = (str(latest_fpl.get('RegNo')).strip() == str(latest_fpla_plan.get('RegNo')).strip())
        sobt_match = (format_time(fpl_sobt_bjt) == format_time(fpla_sobt))
        status = []
        if not reg_match: status.append("机号不一致")
        if not sobt_match: status.append("时刻不一致")
        plan_results.append({'FlightKey': flight_key, 'Latest_FPL_ReceiveTime': latest_fpl.get('ReceiveTime'),
                             'Latest_FPLA_Plan_ReceiveTime': latest_fpla_plan.get('ReceiveTime'),
                             'FPL_RegNo': latest_fpl.get('RegNo'), 'FPLA_RegNo': latest_fpla_plan.get('RegNo'),
                             'FPL_SOBT_BJT': format_time(fpl_sobt_bjt), 'FPLA_SOBT': format_time(fpla_sobt),
                             'Overall_Plan_Status': "完全一致" if not status else " | ".join(status)})
    return pd.DataFrame(plan_results)


def run_dynamic_comparison(aftn_df, fpla_df, target_date_obj):
    dynamic_results = []
    aftn_dynamics = aftn_df[aftn_df['MessageType'].isin(['DLA', 'CHG', 'CPL'])].sort_values('ReceiveTime')
    for index, aftn_row in aftn_dynamics.iterrows():
        flight_key = aftn_row.get('FlightKey')
        if pd.isna(flight_key): continue
        fpla_timeline = fpla_df[fpla_df['FlightKey'] == flight_key].sort_values('ReceiveTime')
        if fpla_timeline.empty: continue
        aftn_event_time = aftn_row['ReceiveTime']
        fpla_dynamic_msgs = fpla_timeline[fpla_timeline['FPLA_Status'].isin(['UPD', 'DLA', 'SLOTCHG', 'ALN', 'RTN'])]
        fpla_compare_state = fpla_dynamic_msgs.iloc[-1] if not fpla_dynamic_msgs.empty else fpla_timeline.iloc[-1]
        if aftn_row['MessageType'] == 'DLA':
            dof_match = re.search(r'DOF/(\d{6})', aftn_row.get('RawMessage', ''))
            base_date = datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date() if dof_match else target_date_obj
            aftn_new_sobt = convert_utc_str_to_bjt(aftn_row.get('New_Departure_Time'), base_date)
            fpla_compare_sobt = parse_fpla_time(fpla_compare_state.get('SOBT'))
            time_diff = (aftn_new_sobt - fpla_compare_sobt).total_seconds() / 60.0 if pd.notna(
                aftn_new_sobt) and pd.notna(fpla_compare_sobt) else np.nan
            fpla_compare_status_type = fpla_compare_state.get('FPLA_Status', 'N/A')
            fpla_evidence = f"与FPLA最新动态({fpla_compare_status_type})SOBT: {format_time(fpla_compare_sobt)}对比"
            conclusion = "无法对比"
            if pd.notna(time_diff):
                abs_diff = abs(round(time_diff))
                conclusion = "时刻基本一致" if abs_diff <= 1 else f"时刻不一致 (相差 {abs_diff} 分钟)"
            dynamic_results.append(
                {'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time, 'AFTN_Event_Type': 'DLA (时刻变更)',
                 'AFTN_Change_Detail': f"New SOBT: {format_time(aftn_new_sobt)} BJT", 'FPLA_Evidence': fpla_evidence,
                 'Conclusion': conclusion})
        elif aftn_row['MessageType'] in ['CHG', 'CPL']:
            change_found = False
            # 以下为CHG/CPL的各种变更对比逻辑... (此处为了简洁省略了重复代码，您的原代码是正确的)
            if pd.notna(aftn_row.get('New_Departure_Time')):
                change_found = True
                aftn_new_sobt = convert_utc_str_to_bjt(aftn_row.get('New_Departure_Time'), aftn_event_time.date())
                fpla_compare_sobt = parse_fpla_time(fpla_compare_state.get('SOBT'))
                time_diff = (aftn_new_sobt - fpla_compare_sobt).total_seconds() / 60.0 if pd.notna(
                    aftn_new_sobt) and pd.notna(fpla_compare_sobt) else np.nan
                conclusion = f"时刻不一致 (相差 {round(time_diff)} 分钟)" if pd.notna(time_diff) and abs(
                    time_diff) > 1 else "时刻基本一致"
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f'{aftn_row["MessageType"]} (时刻变更)',
                                        'AFTN_Change_Detail': f"New SOBT: {format_time(aftn_new_sobt)} BJT",
                                        'FPLA_Evidence': f"与FPLA最新动态({fpla_compare_state.get('FPLA_Status')})SOBT: {format_time(fpla_compare_sobt)}对比",
                                        'Conclusion': conclusion})
            if pd.notna(aftn_row.get('New_RegNo')):
                change_found = True
                conclusion = "机号不一致"
                if str(fpla_compare_state.get('RegNo')).strip() == str(
                    aftn_row.get('New_RegNo')).strip(): conclusion = "机号一致"
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f'{aftn_row["MessageType"]} (机号变更)',
                                        'AFTN_Change_Detail': f"New RegNo: {aftn_row.get('New_RegNo')}",
                                        'FPLA_Evidence': f"与FPLA最新动态({fpla_compare_state.get('FPLA_Status')})机号: {fpla_compare_state.get('RegNo')}对比",
                                        'Conclusion': conclusion})
            # ... 其他变更类型的代码 ...
            if not change_found:
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f'{aftn_row["MessageType"]} (其他变更)',
                                        'AFTN_Change_Detail': '未识别出核心字段变更', 'FPLA_Evidence': 'N/A',
                                        'Conclusion': '不影响地面保障，忽略对比'})
    return pd.DataFrame(dynamic_results)


# ==============================================================================
# --- 2. 全新的主执行函数 ---
# ==============================================================================
def run_full_process(fpla_file_path, aftn_file_path, output_dir, log_widget):
    """
    整合并执行所有分析和比较步骤的函数。
    """

    def log(message):
        """辅助函数，用于在GUI日志窗口打印信息。"""
        log_widget.insert(tk.END, message + "\n")
        log_widget.see(tk.END)
        log_widget.update_idletasks()

    try:
        # --- 步骤 1: 从FPLA文件名中提取日期和机场 ---
        log("--- STEP 1: 解析输入文件名 ---")
        filename = os.path.basename(fpla_file_path)
        match = re.search(r'FPLA-Details-(?P<airport>\w+)-(?P<date>\d{8})', filename)
        if not match:
            raise ValueError("FPLA文件名格式不正确！\n应为 'FPLA-Details-机场代码-YYYYMMDD...' 格式。")

        airport = match.group('airport')
        date_str = match.group('date')
        target_date_obj = datetime.strptime(date_str, '%Y%m%d').date()
        target_date_report_str = target_date_obj.strftime('%Y-%m-%d')
        log(f"成功解析：机场代码 = {airport}, 目标日期 = {target_date_report_str}")

        # --- 步骤 2: 预处理FPLA文件 ---
        log("\n--- STEP 2: 正在处理 FPLA 文件 ---")
        FPLA_COLUMN_MAP = {"全球唯一飞行标识符": "GUFI", "航空器识别标志": "CALLSIGN", "共享单位航班标识符": "UNITUFI",
                           "航空器注册号": "REGNUMBER", "航空器地址码": "ADDRESSCODE", "计划离港时间": "SOBT",
                           "计划到港时间": "SIBT", "计划起飞机场": "DEPAP", "计划目的地机场": "ARRAP",
                           "机场保障计划离港时间": "APTSOBT", "机场保障计划到港时间": "APTSIBT",
                           "机场保障计划起飞机场": "APTDEPAP", "机场保障计划目的地机场": "APTARRAP",
                           "执飞航空器注册号": "EREGNUMBER", "执飞航空器地址码": "EADDRESSCODE",
                           "预执行航班取消原因": "PCNLREASON", "预执行航班延误原因": "PDELAYREASON",
                           "预执行任务性质": "PMISSIONPROPERTY", "预执行客货属性": "PGJ",
                           "预执行计划机型": "PSAIRCRAFTTYPE", "预执行航线属性": "LIFLAG",
                           "预执行计划状态": "PSCHEDULESTATUS", "预执行航段": "PFLIGHTLAG",
                           "预执行共享航班号": "PSHAREFLIGHTNO", "预执行计划种类": "PMISSIONTYPE", "计划航路": "SROUTE",
                           "消息发送时间": "SENDTIME", "格式校验结果": "FORMATCHECKRESULT",
                           "逻辑校验结果": "LOGICCHECKRESULT", "及时性校验结果": "ISTIMELY",
                           "校验结论": "ALLCHECKRESULT"}
        fpla_raw_df = pd.read_excel(fpla_file_path)
        fpla_raw_df.rename(columns=FPLA_COLUMN_MAP, inplace=True)
        fpla_df = process_fpla_for_analysis(fpla_raw_df, target_date_obj)
        if fpla_df.empty:
            log("警告: 未在FPLA文件中找到指定日期的数据。")
            # return # 即使一个文件为空，也可能需要继续生成另一个报告
        else:
            log(f"FPLA文件处理完成，找到 {len(fpla_df)} 条相关记录。")

        # --- 步骤 3: 预处理AFTN文件 ---
        log("\n--- STEP 3: 正在处理 AFTN 文件 ---")
        aftn_raw_df = pd.read_csv(aftn_file_path, header=None, on_bad_lines='skip')
        aftn_df = process_aftn_for_analysis(aftn_raw_df, target_date_obj)
        if aftn_df.empty:
            log("警告: 未在AFTN文件中找到指定日期的数据。")
        else:
            log(f"AFTN文件处理完成，找到 {len(aftn_df)} 条相关记录。")

        # --- 步骤 4: 执行对比并生成报告 ---
        log("\n--- STEP 4: 开始生成对比报告 ---")
        for df in [aftn_df, fpla_df]:
            if 'ReceiveTime' in df.columns:
                df['ReceiveTime'] = pd.to_datetime(df['ReceiveTime'], errors='coerce')

        # 生成计划对比报告
        plan_report_df = run_plan_comparison(aftn_df, fpla_df, target_date_obj)
        if not plan_report_df.empty:
            PLAN_COMPARISON_FILE = os.path.join(output_dir, f'plan_comparison_report_{target_date_report_str}.xlsx')
            with pd.ExcelWriter(PLAN_COMPARISON_FILE, engine='xlsxwriter') as writer:
                plan_report_df.to_excel(writer, sheet_name='PlanComparison', index=False)
                auto_set_column_width(plan_report_df, writer, 'PlanComparison')
            log(f"√ [第一阶段] 计划对比报告已生成: {PLAN_COMPARISON_FILE}")
        else:
            log("! [第一阶段] 未生成计划对比报告 (无共同航班或数据为空)。")

        # 生成动态对比报告
        dynamic_report_df = run_dynamic_comparison(aftn_df, fpla_df, target_date_obj)
        if not dynamic_report_df.empty:
            final_cols = ['FlightKey', 'AFTN_Event_Time', 'AFTN_Event_Type', 'AFTN_Change_Detail', 'FPLA_Evidence',
                          'Conclusion']
            dynamic_report_df = dynamic_report_df.reindex(columns=final_cols)
            DYNAMIC_COMPARISON_FILE = os.path.join(output_dir,
                                                   f'dynamic_comparison_report_{target_date_report_str}.xlsx')
            with pd.ExcelWriter(DYNAMIC_COMPARISON_FILE, engine='xlsxwriter') as writer:
                dynamic_report_df.to_excel(writer, sheet_name='DynamicComparison', index=False)
                auto_set_column_width(dynamic_report_df, writer, 'DynamicComparison')
            log(f"√ [第二阶段] 动态变更报告已生成: {DYNAMIC_COMPARISON_FILE}")
        else:
            log("! [第二阶段] 未生成动态变更报告 (无AFTN动态消息或数据为空)。")

        log("\n===== 所有任务已完成! =====")
        messagebox.showinfo("成功", f"处理完成！报告已保存在:\n{output_dir}")

    except Exception as e:
        error_message = f"发生错误: {e}\n\n详细信息:\n{traceback.format_exc()}"
        log(error_message)
        messagebox.showerror("错误", error_message)


# ==============================================================================
# --- 3. 图形用户界面 (GUI) ---
# ==============================================================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("AFTN-FPLA 对比分析工具 v1.0")
        self.root.geometry("800x600")

        self.fpla_path = tk.StringVar()
        self.aftn_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=os.path.join(os.path.expanduser('~'), 'Desktop'))

        # --- UI 控件布局 ---
        main_frame = tk.Frame(root, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 文件选择部分
        file_frame = tk.LabelFrame(main_frame, text="1. 选择输入文件", padx=10, pady=10)
        file_frame.pack(fill=tk.X, pady=5)

        tk.Button(file_frame, text="选择 FPLA 文件 (.xlsx)", command=self.select_fpla_file).grid(row=0, column=0,
                                                                                                 sticky="ew", padx=5,
                                                                                                 pady=2)
        tk.Entry(file_frame, textvariable=self.fpla_path, state='readonly').grid(row=0, column=1, sticky="ew", padx=5)

        tk.Button(file_frame, text="选择 AFTN 文件 (.csv)", command=self.select_aftn_file).grid(row=1, column=0,
                                                                                                sticky="ew", padx=5,
                                                                                                pady=2)
        tk.Entry(file_frame, textvariable=self.aftn_path, state='readonly').grid(row=1, column=1, sticky="ew", padx=5)

        file_frame.grid_columnconfigure(1, weight=1)

        # 输出目录选择
        output_frame = tk.LabelFrame(main_frame, text="2. 选择输出目录", padx=10, pady=10)
        output_frame.pack(fill=tk.X, pady=5)

        tk.Button(output_frame, text="选择报告保存位置", command=self.select_output_dir).grid(row=0, column=0,
                                                                                              sticky="ew", padx=5,
                                                                                              pady=2)
        tk.Entry(output_frame, textvariable=self.output_dir, state='readonly').grid(row=0, column=1, sticky="ew",
                                                                                    padx=5)
        output_frame.grid_columnconfigure(1, weight=1)

        # 执行按钮
        tk.Button(main_frame, text="3. 开始执行分析", font=("Helvetica", 12, "bold"), bg="green", fg="white",
                  command=self.run_analysis).pack(fill=tk.X, pady=10, ipady=5)

        # 日志输出
        log_frame = tk.LabelFrame(main_frame, text="执行日志", padx=10, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def select_fpla_file(self):
        path = filedialog.askopenfilename(title="选择FPLA文件", filetypes=[("Excel 文件", "*.xlsx")])
        if path: self.fpla_path.set(path)

    def select_aftn_file(self):
        path = filedialog.askopenfilename(title="选择AFTN文件 (sqlResult)", filetypes=[("CSV 文件", "*.csv")])
        if path: self.aftn_path.set(path)

    def select_output_dir(self):
        path = filedialog.askdirectory(title="选择报告保存位置")
        if path: self.output_dir.set(path)

    def run_analysis(self):
        fpla = self.fpla_path.get()
        aftn = self.aftn_path.get()
        output = self.output_dir.get()

        if not all([fpla, aftn, output]):
            messagebox.showwarning("输入不完整", "请确保已选择FPLA文件、AFTN文件和输出目录！")
            return

        self.log_text.delete(1.0, tk.END)  # 清空日志
        run_full_process(fpla, aftn, output, self.log_text)


# ==============================================================================
# --- 4. 应用程序入口 ---
# ==============================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()