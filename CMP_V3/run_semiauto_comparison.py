import pandas as pd
import numpy as np
import re
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# ==============================================================================
# --- 1. 配置加载 ---
# ==============================================================================
load_dotenv()
TARGET_DATE_STR = os.getenv("TARGET_DATE")
if not TARGET_DATE_STR:
    print("错误: 未在 .env 文件中找到 TARGET_DATE 设置。");
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREPROCESSED_DIR = os.path.join(BASE_DIR, 'preprocessed_files')
COMPARE_RESULT_DIR = os.path.join(BASE_DIR, 'compare_result')
AFTN_ANALYSIS_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_aftn_data_{TARGET_DATE_STR}.csv')
FPLA_ANALYSIS_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_fpla_data_{TARGET_DATE_STR}.csv')
PLAN_COMPARISON_FILE = os.path.join(COMPARE_RESULT_DIR, f'plan_comparison_report_{TARGET_DATE_STR}.xlsx')
DYNAMIC_COMPARISON_FILE = os.path.join(COMPARE_RESULT_DIR, f'dynamic_comparison_report_{TARGET_DATE_STR}.xlsx')


# ==============================================================================
# --- 2. 辅助函数 ---
# ==============================================================================
def convert_utc_str_to_bjt(time_str, date_obj):
    if pd.isna(time_str): return pd.NaT
    try:
        time_val_str = str(time_str).split('.')[0].zfill(4)
        utc_dt = datetime.combine(date_obj, datetime.strptime(time_val_str, "%H%M").time())
        return utc_dt + timedelta(hours=8)
    except:
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
    except:
        return pd.NaT


# ==============================================================================
# --- 3. 核心对比逻辑 ---
# ==============================================================================
def run_plan_comparison(aftn_df, fpla_df, target_date_obj):
    print("--- 正在执行 [第一阶段]：最终计划状态快照对比 ---")
    plan_results = []
    common_flight_keys = set(aftn_df['FlightKey'].unique()) & set(fpla_df['FlightKey'].unique())
    for flight_key in common_flight_keys:
        aftn_fpls = aftn_df[(aftn_df['FlightKey'] == flight_key) & (aftn_df['MessageType'] == 'FPL')].sort_values(
            'ReceiveTime', ascending=False)
        fpla_plans = fpla_df[
            (fpla_df['FlightKey'] == flight_key) & (fpla_df['FPLA_Status'].isin(['ADD', 'ALL', 'UPD']))].sort_values(
            'ReceiveTime', ascending=False)
        if aftn_fpls.empty or fpla_plans.empty: continue
        latest_fpl = aftn_fpls.iloc[0];
        latest_fpla_plan = fpla_plans.iloc[0]
        fpl_time_match = re.search(r'-\w{4,7}(\d{4})\s', latest_fpl.get('RawMessage', ''));
        fpl_eobt_str = fpl_time_match.group(1) if fpl_time_match else np.nan
        dof_match = re.search(r'DOF/(\d{6})', latest_fpl.get('RawMessage', ''));
        base_date = datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date() if dof_match else target_date_obj
        fpl_sobt_bjt = convert_utc_str_to_bjt(fpl_eobt_str, base_date)
        fpla_sobt = parse_fpla_time(latest_fpla_plan['SOBT'])
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
    """【V19最终版】第二阶段：AFTN动态 vs FPLA最新动态(或最新任何消息)"""
    print("--- 正在执行 [第二阶段]：动态变更事件溯源对比 ---")
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
            dof_match = re.search(r'DOF/(\d{6})', aftn_row.get('RawMessage', ''));
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
                if abs_diff <= 1:
                    conclusion = "时刻基本一致"
                else:
                    conclusion = f"时刻不一致 (相差 {abs_diff} 分钟)"
            dynamic_results.append(
                {'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time, 'AFTN_Event_Type': 'DLA (时刻变更)',
                 'AFTN_Change_Detail': f"New SOBT: {format_time(aftn_new_sobt)} BJT", 'FPLA_Evidence': fpla_evidence,
                 'Conclusion': conclusion})

        elif aftn_row['MessageType'] in ['CHG', 'CPL']:
            change_found = False
            # 1. 时刻变更 (编组13)
            if pd.notna(aftn_row.get('New_Departure_Time')):
                change_found = True;
                aftn_new_sobt = convert_utc_str_to_bjt(aftn_row.get('New_Departure_Time'), aftn_event_time.date())
                fpla_compare_sobt = parse_fpla_time(fpla_compare_state.get('SOBT'));
                time_diff = (aftn_new_sobt - fpla_compare_sobt).total_seconds() / 60.0 if pd.notna(
                    aftn_new_sobt) and pd.notna(fpla_compare_sobt) else np.nan
                conclusion = f"时刻不一致 (相差 {round(time_diff)} 分钟)" if pd.notna(time_diff) and abs(
                    time_diff) > 1 else "时刻基本一致"
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f'{aftn_row["MessageType"]} (时刻变更)',
                                        'AFTN_Change_Detail': f"New SOBT: {format_time(aftn_new_sobt)} BJT",
                                        'FPLA_Evidence': f"与FPLA最新动态({fpla_compare_state.get('FPLA_Status')})SOBT: {format_time(fpla_compare_sobt)}对比",
                                        'Conclusion': conclusion})
            # 2. 机号变更 (编组18 - REG)
            if pd.notna(aftn_row.get('New_RegNo')):
                change_found = True;
                conclusion = "机号不一致"
                if str(fpla_compare_state.get('RegNo')) == str(aftn_row.get('New_RegNo')): conclusion = "机号一致"
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f'{aftn_row["MessageType"]} (机号变更)',
                                        'AFTN_Change_Detail': f"New RegNo: {aftn_row.get('New_RegNo')}",
                                        'FPLA_Evidence': f"与FPLA最新动态({fpla_compare_state.get('FPLA_Status')})机号: {fpla_compare_state.get('RegNo')}对比",
                                        'Conclusion': conclusion})
            # 3. 航站变更 (编组16)
            if pd.notna(aftn_row.get('New_Destination')):
                change_found = True;
                alt1_val = aftn_row.get('New_Alternate_1');
                alt2_val = aftn_row.get('New_Alternate_2');
                alt1 = str(alt1_val) if pd.notna(alt1_val) else '';
                alt2 = str(alt2_val) if pd.notna(alt2_val) else '';
                alt_info = f"{alt1} {alt2}".strip()
                change_detail = f"New Dest: {aftn_row.get('New_Destination')}" + (
                    f", Alt: {alt_info}" if alt_info else "")
                conclusion = "航站信息不一致"
                if str(fpla_compare_state.get('ArrAirport')) == str(
                    aftn_row.get('New_Destination')): conclusion = "航站信息一致"
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f'{aftn_row["MessageType"]} (航站变更)',
                                        'AFTN_Change_Detail': change_detail,
                                        'FPLA_Evidence': f"与FPLA最新动态({fpla_compare_state.get('FPLA_Status')})航程: {fpla_compare_state.get('DepAirport')}->{fpla_compare_state.get('ArrAirport')}对比",
                                        'Conclusion': conclusion})
            # 4. 机型变更 (编组9)
            if pd.notna(aftn_row.get('New_CraftType')):
                change_found = True;
                conclusion = "机型不一致"
                if str(fpla_compare_state.get('CraftType')) == str(aftn_row.get('New_CraftType')): conclusion = "机型一致"
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f'{aftn_row["MessageType"]} (机型变更)',
                                        'AFTN_Change_Detail': f"New CraftType: {aftn_row.get('New_CraftType')}",
                                        'FPLA_Evidence': f"与FPLA最新动态({fpla_compare_state.get('FPLA_Status')})机型: {fpla_compare_state.get('CraftType')}对比",
                                        'Conclusion': conclusion})
            # 5. 航班号变更 (编组7)
            if pd.notna(aftn_row.get('New_FlightNo')):
                change_found = True;
                conclusion = "航班号不一致"
                if str(fpla_compare_state.get('FlightNo')) == str(aftn_row.get('New_FlightNo')): conclusion = "航班号一致"
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f'{aftn_row["MessageType"]} (航班号变更)',
                                        'AFTN_Change_Detail': f"New FlightNo: {aftn_row.get('New_FlightNo')}",
                                        'FPLA_Evidence': f"与FPLA最新动态({fpla_compare_state.get('FPLA_Status')})航班号: {fpla_compare_state.get('FlightNo')}对比",
                                        'Conclusion': conclusion})

            if not change_found:
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f'{aftn_row["MessageType"]} (其他变更)',
                                        'AFTN_Change_Detail': '未识别出核心字段变更', 'FPLA_Evidence': 'N/A',
                                        'Conclusion': 'N/A'})

    return pd.DataFrame(dynamic_results)


# ==============================================================================
# --- 5. 主程序入口 ---
# ==============================================================================
def main():
    if not TARGET_DATE_STR: print("错误: 未在 .env 文件中找到 TARGET_DATE 设置。"); sys.exit(1)
    try:
        target_date_obj = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d").date()
    except:
        print(f"错误: .env 日期格式无效 ({TARGET_DATE_STR})。"); return
    print(f"\n===== 开始为日期 {TARGET_DATE_STR} 生成对比报告 =====")
    os.makedirs(COMPARE_RESULT_DIR, exist_ok=True)
    try:
        aftn_df = pd.read_csv(AFTN_ANALYSIS_FILE, low_memory=False);
        fpla_df = pd.read_csv(FPLA_ANALYSIS_FILE, low_memory=False)
    except FileNotFoundError:
        print(f"错误: 找不到预处理文件。请先运行 `generate_analysis_files.py`。");
        return
    for df in [aftn_df, fpla_df]: df['ReceiveTime'] = pd.to_datetime(df['ReceiveTime'], errors='coerce')
    plan_report_df = run_plan_comparison(aftn_df, fpla_df, target_date_obj)
    if not plan_report_df.empty:
        plan_report_df.to_excel(PLAN_COMPARISON_FILE, index=False, engine='openpyxl')
        print(f"\n√ [第一阶段] 最终计划对比报告已生成: {PLAN_COMPARISON_FILE}")
    dynamic_report_df = run_dynamic_comparison(aftn_df, fpla_df, target_date_obj)
    if not dynamic_report_df.empty:
        final_cols = ['FlightKey', 'AFTN_Event_Time', 'AFTN_Event_Type', 'AFTN_Change_Detail', 'FPLA_Evidence',
                      'Conclusion']
        dynamic_report_df = dynamic_report_df.reindex(columns=final_cols);
        dynamic_report_df.to_excel(DYNAMIC_COMPARISON_FILE, index=False, engine='openpyxl')
        print(f"√ [第二阶段] 动态变更溯源报告已生成: {DYNAMIC_COMPARISON_FILE}")
    print(f"\n===== 日期 {TARGET_DATE_STR} 的对比分析任务已完成 =====")


if __name__ == "__main__":
    TARGET_DATE_OBJ = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d").date()
    main()