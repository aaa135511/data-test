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

BASE_DIR = os.path.dirname(os.path.abspath(__file__));
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
    return dt_obj.strftime('%H:%M')


def parse_fpla_time(time_val):
    if pd.isna(time_val): return pd.NaT
    try:
        time_str = str(int(float(time_val)))
        format_str = '%Y%m%d%H%M%S' if len(time_str) == 14 else '%Y%m%d%H%M'
        return pd.to_datetime(time_str, format=format_str, errors='coerce')
    except:
        return pd.NaT


# ==============================================================================
# --- 3. 核心对比逻辑 ---
# ==============================================================================
def run_plan_comparison(aftn_df, fpla_df, target_date_obj):
    print("--- 正在执行 [第一阶段]：最终计划状态快照对比 ---")
    plan_results = [];
    common_flight_keys = set(aftn_df['FlightKey'].unique()) & set(fpla_df['FlightKey'].unique())
    for flight_key in common_flight_keys:
        aftn_fpls = aftn_df[(aftn_df['FlightKey'] == flight_key) & (aftn_df['MessageType'] == 'FPL')].sort_values(
            'ReceiveTime', ascending=False)
        fpla_plans = fpla_df[
            (fpla_df['FlightKey'] == flight_key) & (fpla_df['FPLA_Status'].isin(['ADD', 'ALL']))].sort_values(
            'ReceiveTime', ascending=False)
        if aftn_fpls.empty or fpla_plans.empty: continue
        latest_fpl = aftn_fpls.iloc[0];
        latest_fpla_plan = fpla_plans.iloc[0]
        fpl_time_match = re.search(r'-\w{4,7}(\d{4})\s', latest_fpl.get('RawMessage', ''));
        fpl_eobt_str = fpl_time_match.group(1) if fpl_time_match else np.nan
        fpl_sobt_bjt = convert_utc_str_to_bjt(fpl_eobt_str, latest_fpl.get('ReceiveTime').date())
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
    print("--- 正在执行 [第二阶段]：动态变更事件溯源对比 ---")
    dynamic_results = []
    aftn_dynamics = aftn_df[aftn_df['MessageType'].isin(['DLA', 'CHG'])].sort_values('ReceiveTime')

    for index, aftn_row in aftn_dynamics.iterrows():
        flight_key = aftn_row.get('FlightKey')
        if pd.isna(flight_key): continue

        fpla_timeline = fpla_df[fpla_df['FlightKey'] == flight_key].sort_values('ReceiveTime')
        if fpla_timeline.empty: continue

        aftn_event_time = aftn_row['ReceiveTime']
        fpla_after_event = fpla_timeline[fpla_timeline['ReceiveTime'] > aftn_event_time]
        fpla_latest_state = fpla_timeline.iloc[-1]

        if aftn_row['MessageType'] == 'DLA':
            aftn_new_sobt = convert_utc_str_to_bjt(aftn_row.get('New_Departure_Time'), aftn_event_time.date())
            fpla_latest_sobt = parse_fpla_time(fpla_latest_state.get('SOBT'))
            time_diff = (aftn_new_sobt - fpla_latest_sobt).total_seconds() / 60.0 if pd.notna(
                aftn_new_sobt) and pd.notna(fpla_latest_sobt) else np.nan
            fpla_response_msgs = fpla_after_event[fpla_after_event['FPLA_Status'].isin(['DLA', 'SLOTCHG'])]
            fpla_response = f"收到 {len(fpla_response_msgs)} 条DLA/SLOTCHG" if not fpla_response_msgs.empty else "无直接对应的DLA/SLOTCHG"

            dynamic_results.append({
                'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time, 'AFTN_Event_Type': 'DLA (时刻变更)',
                'AFTN_Change_Detail': f"New SOBT: {format_time(aftn_new_sobt)} BJT",
                'FPLA_Response': fpla_response,
                'FPLA_Latest_SOBT': format_time(fpla_latest_sobt),
                'Time_Difference_Minutes': round(time_diff, 2) if pd.notna(time_diff) else ''
            })

        elif aftn_row['MessageType'] == 'CHG':
            if pd.notna(aftn_row.get('New_Destination')):
                alt1 = aftn_row.get('New_Alternate_1', '');
                alt2 = aftn_row.get('New_Alternate_2', '')
                alt_info = f"{alt1 if pd.notna(alt1) else ''} {alt2 if pd.notna(alt2) else ''}".strip()
                change_detail = f"New Dest: {aftn_row.get('New_Destination')}, Alt: {alt_info}"

                fpla_response_str = "FPLA未更新"
                fpla_exact_match = fpla_after_event[
                    (fpla_after_event['ArrAirport'] == aftn_row['New_Destination']) &
                    (fpla_after_event['FPLA_Status'].isin(['ALN', 'RTN', 'UPD']))
                    ]
                if not fpla_exact_match.empty:
                    match_row = fpla_exact_match.iloc[0]
                    fpla_response_str = f"在 {match_row['ReceiveTime'].strftime('%H:%M:%S')} 以 `{match_row['FPLA_Status']}` 状态更新"
                elif str(fpla_latest_state.get('ArrAirport')) == str(aftn_row.get('New_Destination')):
                    fpla_response_str = "FPLA最新状态已体现该变更"

                dynamic_results.append({
                    'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time, 'AFTN_Event_Type': 'CHG (航站变更)',
                    'AFTN_Change_Detail': change_detail,
                    'FPLA_Response': fpla_response_str
                })

    return pd.DataFrame(dynamic_results)


# ==============================================================================
# --- 4. 主程序入口 ---
# ==============================================================================
def main():
    if not TARGET_DATE_STR: print("错误: 未在 .env 文件中找到 TARGET_DATE 设置。"); sys.exit(1)
    try:
        target_date_obj = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d").date()
    except (ValueError, TypeError):
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
        final_cols = ['FlightKey', 'AFTN_Event_Time', 'AFTN_Event_Type', 'AFTN_Change_Detail', 'FPLA_Response',
                      'FPLA_Latest_SOBT', 'Time_Difference_Minutes']
        dynamic_report_df = dynamic_report_df.reindex(columns=final_cols)
        dynamic_report_df.to_excel(DYNAMIC_COMPARISON_FILE, index=False, engine='openpyxl')
        print(f"√ [第二阶段] 动态变更溯源报告已生成: {DYNAMIC_COMPARISON_FILE}")

    print(f"\n===== 日期 {TARGET_DATE_STR} 的对比分析任务已完成 =====")


if __name__ == "__main__":
    main()