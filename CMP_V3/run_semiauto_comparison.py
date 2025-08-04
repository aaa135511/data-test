import os
import re
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# ==============================================================================
# --- 1. 配置加载 (保持不变) ---
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
FODC_ANALYSIS_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_fodc_data_{TARGET_DATE_STR}.csv')
PLAN_COMPARISON_FILE = os.path.join(COMPARE_RESULT_DIR, f'plan_comparison_report_{TARGET_DATE_STR}.xlsx')
DYNAMIC_COMPARISON_FILE = os.path.join(COMPARE_RESULT_DIR, f'dynamic_comparison_report_{TARGET_DATE_STR}.xlsx')


# ==============================================================================
# --- 2. 辅助函数 (保持不变) ---
# ==============================================================================
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
    if isinstance(dt_obj, str):
        try:
            dt_obj = pd.to_datetime(dt_obj)
        except:
            return dt_obj
    return dt_obj.strftime('%m-%d %H:%M')


def parse_fpla_time(time_val):
    if pd.isna(time_val): return pd.NaT
    try:
        time_str = str(time_val).split('.')[0]
        if '-' in time_str and ':' in time_str: return pd.to_datetime(time_str)
        format_str = '%Y%m%d%H%M%S' if len(time_str) == 14 else '%Y%m%d%H%M'
        return pd.to_datetime(time_str, format=format_str, errors='coerce')
    except Exception:
        return pd.NaT


def auto_set_column_width(df, writer, sheet_name):
    worksheet = writer.sheets[sheet_name]
    for i, col in enumerate(df.columns):
        max_len = max(len(str(col)), df[col].astype(str).map(len).max()) + 2
        worksheet.set_column(i, i, max_len)


def safe_strip(val):
    return str(val).strip() if pd.notna(val) else ""


# ==============================================================================
# --- 3. 核心对比逻辑 ---
# ==============================================================================
def run_plan_comparison(aftn_df, fpla_df, fodc_df, target_date_obj):
    # 此函数逻辑保持不变
    print("--- 正在执行 [第一阶段]：最终计划状态快照对比 (引入FODC标杆) ---")
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
        latest_fpla = fpla_plans.iloc[0]
        fpl_time_match = re.search(r'-\w{4,10}(\d{4})\s', latest_fpl.get('RawMessage', ''))
        fpl_eobt_str = fpl_time_match.group(1) if fpl_time_match else np.nan
        dof_match = re.search(r'DOF/(\d{6})', latest_fpl.get('RawMessage', ''))
        base_date = datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date() if dof_match else target_date_obj
        aftn_sobt = convert_utc_str_to_bjt(fpl_eobt_str, base_date);
        aftn_reg = safe_strip(latest_fpl.get('RegNo'))
        fpla_sobt = parse_fpla_time(latest_fpla.get('SOBT'));
        fpla_reg = safe_strip(latest_fpla.get('RegNo'))
        reg_match = (aftn_reg == fpla_reg);
        sobt_match = (format_time(aftn_sobt) == format_time(fpla_sobt))
        result_row = {'FlightKey': flight_key, 'FPL_RegNo': aftn_reg, 'FPLA_RegNo': fpla_reg,
                      'FPL_SOBT_BJT': format_time(aftn_sobt), 'FPLA_SOBT': format_time(fpla_sobt), 'FODC_RegNo': 'N/A',
                      'FODC_SOBT': 'N/A', 'AFTN_vs_FODC': '无FODC数据', 'FPLA_vs_FODC': '无FODC数据',
                      'Final_Conclusion': '初步一致' if reg_match and sobt_match else '初步不一致'}
        if not reg_match or not sobt_match:
            fodc_records = fodc_df[fodc_df['FlightKey'] == flight_key].sort_values('ReceiveTime', ascending=False)
            if not fodc_records.empty:
                latest_fodc = fodc_records.iloc[0]
                fodc_sobt = parse_fpla_time(latest_fodc.get('SOBT'));
                fodc_reg = safe_strip(latest_fodc.get('RegNo'))
                result_row['FODC_RegNo'] = fodc_reg;
                result_row['FODC_SOBT'] = format_time(fodc_sobt)
                aftn_vs_fodc_reg = "一致" if aftn_reg == fodc_reg else "不一致"
                fpla_vs_fodc_reg = "一致" if fpla_reg == fodc_reg else "不一致"
                aftn_vs_fodc_sobt = "一致" if format_time(aftn_sobt) == format_time(fodc_sobt) else "不一致"
                fpla_vs_fodc_sobt = "一致" if format_time(fpla_sobt) == format_time(fodc_sobt) else "不一致"
                result_row['AFTN_vs_FODC'] = f"机号:{aftn_vs_fodc_reg}, 时刻:{aftn_vs_fodc_sobt}"
                result_row['FPLA_vs_FODC'] = f"机号:{fpla_vs_fodc_reg}, 时刻:{fpla_vs_fodc_sobt}"
                conclusions = []
                if aftn_vs_fodc_reg != "一致" or fpla_vs_fodc_reg != "一致":
                    if aftn_vs_fodc_reg == "一致" and fpla_vs_fodc_reg != "一致":
                        conclusions.append("机号:AFTN正确")
                    elif aftn_vs_fodc_reg != "一致" and fpla_vs_fodc_reg == "一致":
                        conclusions.append("机号:FPLA正确")
                    elif aftn_vs_fodc_reg != "一致" and fpla_vs_fodc_reg != "一致":
                        conclusions.append("机号:均为错误")
                if aftn_vs_fodc_sobt != "一致" or fpla_vs_fodc_sobt != "一致":
                    if aftn_vs_fodc_sobt == "一致" and fpla_vs_fodc_sobt != "一致":
                        conclusions.append("时刻:AFTN正确")
                    elif aftn_vs_fodc_sobt != "一致" and fpla_vs_fodc_sobt == "一致":
                        conclusions.append("时刻:FPLA正确")
                    elif aftn_vs_fodc_sobt != "一致" and fpla_vs_fodc_sobt != "一致":
                        conclusions.append("时刻:均为错误")
                result_row['Final_Conclusion'] = ", ".join(conclusions) if conclusions else "三方一致"
        plan_results.append(result_row)
    return pd.DataFrame(plan_results)


def run_dynamic_comparison(aftn_df, fpla_df, fodc_df, target_date_obj):
    """【最终完整版】第二阶段对比：对所有核心字段变更进行三方裁决。"""
    print("--- 正在执行 [第二阶段]：动态变更事件溯源对比 (FODC ATOT为基准) ---")
    dynamic_results = []
    aftn_dynamics = aftn_df[aftn_df['MessageType'].isin(['DLA', 'CHG', 'CPL'])].sort_values('ReceiveTime')

    for index, aftn_row in aftn_dynamics.iterrows():
        flight_key = aftn_row.get('FlightKey')
        if pd.isna(flight_key): continue

        fpla_timeline = fpla_df[fpla_df['FlightKey'] == flight_key].sort_values('ReceiveTime')
        fodc_timeline = fodc_df[fodc_df['FlightKey'] == flight_key].sort_values('ReceiveTime', ascending=False)

        if fpla_timeline.empty: continue

        aftn_event_time = aftn_row['ReceiveTime']
        fpla_compare_state = fpla_timeline.iloc[-1]
        latest_fodc = fodc_timeline.iloc[0] if not fodc_timeline.empty else None

        change_found = False

        # 1. 时刻变更 (DLA 或 CHG/CPL-编组13)
        if pd.notna(aftn_row.get('New_Departure_Time')):
            change_found = True
            aftn_val = convert_utc_str_to_bjt(aftn_row.get('New_Departure_Time'), aftn_event_time.date())
            fpla_val = parse_fpla_time(fpla_compare_state.get('APTSOBT'))
            fodc_benchmark_time = parse_fpla_time(latest_fodc.get('FODC_ATOT')) if latest_fodc is not None and pd.notna(
                latest_fodc.get('FODC_ATOT')) else None

            aftn_match = format_time(aftn_val) == format_time(fodc_benchmark_time) if pd.notna(
                fodc_benchmark_time) else None
            fpla_match = format_time(fpla_val) == format_time(fodc_benchmark_time) if pd.notna(
                fodc_benchmark_time) else None

            conclusion = "无FODC实际起飞时间(ATOT)作为标杆"
            if aftn_match is not None:
                if aftn_match and fpla_match:
                    conclusion = "三方时刻一致"
                elif aftn_match and not fpla_match:
                    conclusion = "AFTN与FODC(ATOT)一致, FPLA不一致"
                elif not aftn_match and fpla_match:
                    conclusion = "FPLA与FODC(ATOT)一致, AFTN不一致"
                else:
                    conclusion = "AFTN/FPLA均与FODC(ATOT)不一致"

            dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                    'AFTN_Event_Type': f"{aftn_row['MessageType']} (时刻变更)",
                                    'AFTN_Change_Detail': f"New SOBT: {format_time(aftn_val)}",
                                    'FPLA_Evidence': f"FPLA APTSOBT: {format_time(fpla_val)}, FODC ATOT基准: {format_time(fodc_benchmark_time)}",
                                    'Conclusion': conclusion})

        # 2. 机号变更 (CHG/CPL-编组18)
        if pd.notna(aftn_row.get('New_RegNo')):
            change_found = True
            aftn_val = safe_strip(aftn_row.get('New_RegNo'))
            fpla_val = safe_strip(fpla_compare_state.get('RegNo'))
            fodc_val = safe_strip(latest_fodc.get('RegNo')) if latest_fodc is not None else None

            aftn_match = (aftn_val == fodc_val) if fodc_val is not None else None
            fpla_match = (fpla_val == fodc_val) if fodc_val is not None else None

            conclusion = "无FODC标杆";
            if aftn_match is not None:
                if aftn_match and fpla_match:
                    conclusion = "三方一致"
                elif aftn_match and not fpla_match:
                    conclusion = "AFTN/FODC一致, FPLA不一致"
                elif not aftn_match and fpla_match:
                    conclusion = "FPLA/FODC一致, AFTN不一致"
                else:
                    conclusion = "AFTN/FPLA均与FODC不一致"
            dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                    'AFTN_Event_Type': f"{aftn_row['MessageType']} (机号变更)",
                                    'AFTN_Change_Detail': f"New RegNo: {aftn_val}",
                                    'FPLA_Evidence': f"FPLA机号: {fpla_val}, FODC机号: {fodc_val}",
                                    'Conclusion': conclusion})

        # 3. 航站变更 (CHG/CPL-编组16)
        if pd.notna(aftn_row.get('New_Destination')):
            change_found = True
            aftn_val = safe_strip(aftn_row.get('New_Destination'))
            fpla_val = safe_strip(fpla_compare_state.get('ArrAirport'))
            fodc_val = safe_strip(latest_fodc.get('ArrAirport')) if latest_fodc is not None else None

            aftn_match = (aftn_val == fodc_val) if fodc_val is not None else None
            fpla_match = (fpla_val == fodc_val) if fodc_val is not None else None

            conclusion = "无FODC标杆"
            if aftn_match is not None:
                if aftn_match and fpla_match:
                    conclusion = "三方一致"
                elif aftn_match and not fpla_match:
                    conclusion = "AFTN/FODC一致, FPLA不一致"
                elif not aftn_match and fpla_match:
                    conclusion = "FPLA/FODC一致, AFTN不一致"
                else:
                    conclusion = "AFTN/FPLA均与FODC不一致"

            dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                    'AFTN_Event_Type': f"{aftn_row['MessageType']} (航站变更)",
                                    'AFTN_Change_Detail': f"New Dest: {aftn_val}",
                                    'FPLA_Evidence': f"FPLA目的站: {fpla_val}, FODC目的站: {fodc_val}",
                                    'Conclusion': conclusion})

        # 4. 机型变更 (CHG/CPL-编组9)
        if pd.notna(aftn_row.get('New_CraftType')):
            change_found = True
            aftn_val = safe_strip(aftn_row.get('New_CraftType'))
            fpla_val = safe_strip(fpla_compare_state.get('CraftType'))
            fodc_val = safe_strip(latest_fodc.get('CraftType')) if latest_fodc is not None else None

            aftn_match = (aftn_val == fodc_val) if fodc_val is not None else None
            fpla_match = (fpla_val == fodc_val) if fodc_val is not None else None

            conclusion = "无FODC标杆"
            if aftn_match is not None:
                if aftn_match and fpla_match:
                    conclusion = "三方一致"
                elif aftn_match and not fpla_match:
                    conclusion = "AFTN/FODC一致, FPLA不一致"
                elif not aftn_match and fpla_match:
                    conclusion = "FPLA/FODC一致, AFTN不一致"
                else:
                    conclusion = "AFTN/FPLA均与FODC不一致"

            dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                    'AFTN_Event_Type': f"{aftn_row['MessageType']} (机型变更)",
                                    'AFTN_Change_Detail': f"New CraftType: {aftn_val}",
                                    'FPLA_Evidence': f"FPLA机型: {fpla_val}, FODC机型: {fodc_val}",
                                    'Conclusion': conclusion})

        # 5. 航班号变更 (CHG/CPL-编组7)
        if pd.notna(aftn_row.get('New_FlightNo')):
            change_found = True
            aftn_val = safe_strip(aftn_row.get('New_FlightNo'))
            fpla_val = safe_strip(fpla_compare_state.get('FlightNo'))
            fodc_val = safe_strip(latest_fodc.get('FlightNo')) if latest_fodc is not None else None

            aftn_match = (aftn_val == fodc_val) if fodc_val is not None else None
            fpla_match = (fpla_val == fodc_val) if fodc_val is not None else None

            conclusion = "无FODC标杆"
            if aftn_match is not None:
                if aftn_match and fpla_match:
                    conclusion = "三方一致"
                elif aftn_match and not fpla_match:
                    conclusion = "AFTN/FODC一致, FPLA不一致"
                elif not aftn_match and fpla_match:
                    conclusion = "FPLA/FODC一致, AFTN不一致"
                else:
                    conclusion = "AFTN/FPLA均与FODC不一致"

            dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                    'AFTN_Event_Type': f"{aftn_row['MessageType']} (航班号变更)",
                                    'AFTN_Change_Detail': f"New FlightNo: {aftn_val}",
                                    'FPLA_Evidence': f"FPLA航班号: {fpla_val}, FODC航班号: {fodc_val}",
                                    'Conclusion': conclusion})

        if not change_found and aftn_row['MessageType'] in ['CHG', 'CPL']:
            dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                    'AFTN_Event_Type': f"{aftn_row['MessageType']} (其他变更)",
                                    'AFTN_Change_Detail': '未识别出核心字段变更', 'FPLA_Evidence': 'N/A',
                                    'Conclusion': '不影响地面保障，忽略对比'})

    return pd.DataFrame(dynamic_results)


# ==============================================================================
# --- 5. 主程序入口 ---
# ==============================================================================
def main():
    if not TARGET_DATE_STR: print("错误: .env中未设置TARGET_DATE"); sys.exit(1)
    try:
        target_date_obj = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d").date()
    except ValueError:
        print(f"错误: 日期格式无效 ({TARGET_DATE_STR})");
        return

    print(f"\n===== 开始为日期 {TARGET_DATE_STR} 生成对比报告 =====")
    os.makedirs(COMPARE_RESULT_DIR, exist_ok=True)

    try:
        aftn_df = pd.read_csv(AFTN_ANALYSIS_FILE, low_memory=False)
        fpla_df = pd.read_csv(FPLA_ANALYSIS_FILE, low_memory=False)
        fodc_df = pd.read_csv(FODC_ANALYSIS_FILE, low_memory=False)
    except FileNotFoundError as e:
        print(f"错误: 找不到预处理文件: {e}。请确保已成功运行 `generate_analysis_files.py`。");
        return

    for df in [aftn_df, fpla_df, fodc_df]:
        if 'ReceiveTime' in df.columns:
            df['ReceiveTime'] = pd.to_datetime(df['ReceiveTime'], errors='coerce')

    plan_report_df = run_plan_comparison(aftn_df, fpla_df, fodc_df, target_date_obj)
    if not plan_report_df.empty:
        with pd.ExcelWriter(PLAN_COMPARISON_FILE, engine='xlsxwriter') as writer:
            plan_report_df.to_excel(writer, sheet_name='PlanComparison', index=False)
            auto_set_column_width(plan_report_df, writer, 'PlanComparison')
        print(f"\n√ [第一阶段] 最终计划对比报告已生成: {PLAN_COMPARISON_FILE}")

    dynamic_report_df = run_dynamic_comparison(aftn_df, fpla_df, fodc_df, target_date_obj)
    if not dynamic_report_df.empty:
        final_cols = ['FlightKey', 'AFTN_Event_Time', 'AFTN_Event_Type', 'AFTN_Change_Detail', 'FPLA_Evidence',
                      'Conclusion']
        dynamic_report_df = dynamic_report_df.reindex(columns=final_cols).fillna('')
        with pd.ExcelWriter(DYNAMIC_COMPARISON_FILE, engine='xlsxwriter') as writer:
            dynamic_report_df.to_excel(writer, sheet_name='DynamicComparison', index=False)
            auto_set_column_width(dynamic_report_df, writer, 'DynamicComparison')
        print(f"√ [第二阶段] 动态变更溯源报告已生成: {DYNAMIC_COMPARISON_FILE}")

    print(f"\n===== 日期 {TARGET_DATE_STR} 的对比分析任务已完成 =====")


if __name__ == "__main__":
    main()