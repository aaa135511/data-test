import os
import re
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
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
FPLA_PLAN_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_fpla_plan_data_{TARGET_DATE_STR}.csv')
FPLA_DYNAMIC_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_fpla_dynamic_data_{TARGET_DATE_STR}.csv')
FODC_PLAN_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_fodc_plan_data_{TARGET_DATE_STR}.csv')
FODC_DYNAMIC_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_fodc_dynamic_data_{TARGET_DATE_STR}.csv')

OUTPUT_COMPARISON_FILE = os.path.join(COMPARE_RESULT_DIR, f'Comparison_Report_{TARGET_DATE_STR}.xlsx')


# ==============================================================================
# --- 2. 辅助函数 ---
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
        format_str = '%Y%m%d%H%M%S' if len(time_str) >= 14 else '%Y%m%d%H%M'
        return pd.to_datetime(time_str, format=format_str, errors='coerce')
    except Exception:
        return pd.NaT


def auto_set_column_width(df, writer, sheet_name):
    worksheet = writer.sheets[sheet_name]
    for i, col in enumerate(df.columns):
        max_len = max([len(str(s).encode('gbk')) for s in df[col].astype(str).tolist() + [col]]) + 2
        worksheet.set_column(i, i, max_len)


def safe_strip(val):
    return str(val).strip() if pd.notna(val) else ""


# ==============================================================================
# --- 3. 核心对比函数：计划对比 (逻辑不变) ---
# ==============================================================================
def run_plan_comparison(aftn_df, fpla_plan_df, fodc_plan_df, target_date_obj):
    print("--- 正在执行 [第一阶段]：最终计划状态快照对比 (AFTN为基准) ---")
    plan_results = []

    aftn_fpl_keys = aftn_df[aftn_df['MessageType'] == 'FPL']['FlightKey'].unique()

    for flight_key in aftn_fpl_keys:
        aftn_fpls = aftn_df[(aftn_df['FlightKey'] == flight_key) & (aftn_df['MessageType'] == 'FPL')].sort_values(
            'ReceiveTime', ascending=False)
        if aftn_fpls.empty: continue
        latest_fpl = aftn_fpls.iloc[0]

        fpl_time_match = re.search(r'-\s*\w{4,10}\s*(\d{4})', latest_fpl.get('RawMessage', ''))
        fpl_eobt_str = fpl_time_match.group(1) if fpl_time_match else np.nan
        dof_match = re.search(r'DOF/(\d{6})', latest_fpl.get('RawMessage', ''))
        base_date = datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date() if dof_match else target_date_obj
        aftn_sobt = convert_utc_str_to_bjt(fpl_eobt_str, base_date)
        aftn_reg_match = re.search(r'REG/(\S+)', latest_fpl.get('RawMessage', ''))
        aftn_reg = safe_strip(aftn_reg_match.group(1).strip(')')) if aftn_reg_match else safe_strip(
            latest_fpl.get('RegNo'))

        fpla_plans = fpla_plan_df[fpla_plan_df['FlightKey'] == flight_key].sort_values('ReceiveTime', ascending=False)
        fodc_records = fodc_plan_df[fodc_plan_df['FlightKey'] == flight_key].sort_values('ReceiveTime', ascending=False)

        fpla_sobt, fpla_reg = (None, None)
        if not fpla_plans.empty:
            latest_fpla = fpla_plans.iloc[0]
            fpla_sobt = parse_fpla_time(latest_fpla.get('SOBT'))
            fpla_reg = safe_strip(latest_fpla.get('RegNo'))

        fodc_sobt, fodc_reg = (None, None)
        if not fodc_records.empty:
            latest_fodc = fodc_records.iloc[0]
            fodc_sobt = parse_fpla_time(latest_fodc.get('SOBT'))
            fodc_reg = safe_strip(latest_fodc.get('RegNo'))

        result_row = {
            'FlightKey': flight_key, 'FPL_RegNo': aftn_reg,
            'FPLA_RegNo': fpla_reg if fpla_reg is not None else '无FPLA数据',
            'FPL_SOBT_BJT': format_time(aftn_sobt),
            'FPLA_SOBT': format_time(fpla_sobt) if fpla_sobt is not None else '无FPLA数据',
            'FODC_RegNo': fodc_reg if fodc_reg is not None else '无FODC数据',
            'FODC_SOBT': format_time(fodc_sobt) if fodc_sobt is not None else '无FODC数据'
        }

        if fpla_reg is None:
            result_row['AFTN_vs_FODC'] = 'N/A (无FPLA)'
            result_row['FPLA_vs_FODC'] = '无FPLA数据'
            result_row['Final_Conclusion'] = '无FPLA数据'
        elif fodc_reg is not None:
            aftn_vs_fodc_reg = "一致" if aftn_reg == fodc_reg else "不一致";
            fpla_vs_fodc_reg = "一致" if fpla_reg == fodc_reg else "不一致"
            aftn_vs_fodc_sobt = "一致" if format_time(aftn_sobt) == format_time(fodc_sobt) else "不一致";
            fpla_vs_fodc_sobt = "一致" if format_time(fpla_sobt) == format_time(fodc_sobt) else "不一致"
            result_row['AFTN_vs_FODC'] = f"机号:{aftn_vs_fodc_reg}, 时刻:{aftn_vs_fodc_sobt}";
            result_row['FPLA_vs_FODC'] = f"机号:{fpla_vs_fodc_reg}, 时刻:{fpla_vs_fodc_sobt}"
            conclusions = []
            if aftn_vs_fodc_reg != "一致" or fpla_vs_fodc_reg != "一致":
                if aftn_vs_fodc_reg == "一致":
                    conclusions.append("机号:AFTN正确")
                elif fpla_vs_fodc_reg == "一致":
                    conclusions.append("机号:FPLA正确")
                else:
                    conclusions.append("机号:三方不一致")
            if aftn_vs_fodc_sobt != "一致" or fpla_vs_fodc_sobt != "一致":
                if aftn_vs_fodc_sobt == "一致":
                    conclusions.append("时刻:AFTN正确")
                elif fpla_vs_fodc_sobt == "一致":
                    conclusions.append("时刻:FPLA正确")
                else:
                    conclusions.append("时刻:三方不一致")
            result_row['Final_Conclusion'] = ", ".join(conclusions) if conclusions else "三方一致"
        else:
            result_row['AFTN_vs_FODC'] = '无FODC数据';
            result_row['FPLA_vs_FODC'] = '无FODC数据'
            if aftn_reg == fpla_reg and format_time(aftn_sobt) == format_time(fpla_sobt):
                result_row['Final_Conclusion'] = '初步一致'
            else:
                diffs = []
                if aftn_reg != fpla_reg: diffs.append("机号不一致")
                if format_time(aftn_sobt) != format_time(fpla_sobt): diffs.append("时刻不一致")
                result_row['Final_Conclusion'] = ", ".join(diffs)

        plan_results.append(result_row)

    df = pd.DataFrame(plan_results)
    df.columns = [
        '航班标识(FlightKey)', 'AFTN-机号(FPL_RegNo)', 'FPLA-机号(FPLA_RegNo)',
        'AFTN-离港时间(FPL_SOBT_BJT)', 'FPLA-离港时间(FPLA_SOBT)',
        'FODC-机号(FODC_RegNo)', 'FODC-离港时间(FODC_SOBT)',
        'AFTN vs FODC 对比', 'FPLA vs FODC 对比', '最终结论(Final_Conclusion)'
    ]
    return df


# ==============================================================================
# --- 4. 核心对比函数：动态对比 (已优化为 FPLA vs AFTN 和 FPLA vs FODC) ---
# ==============================================================================
def run_dynamic_comparison(aftn_df, fpla_dynamic_df, fodc_dynamic_df, target_date_obj):
    print("--- 正在执行 [第二阶段]：动态变更事件溯源对比 (AFTN为基准) ---")
    dynamic_results = []
    aftn_dynamics = aftn_df[aftn_df['MessageType'].isin(['DLA', 'CHG', 'CPL'])].sort_values('ReceiveTime')

    for index, aftn_row in aftn_dynamics.iterrows():
        flight_key = aftn_row.get('FlightKey')
        if pd.isna(flight_key): continue

        aftn_event_time = aftn_row['ReceiveTime']
        msg_type = aftn_row['MessageType']

        fpla_timeline = fpla_dynamic_df[fpla_dynamic_df['FlightKey'] == flight_key].sort_values('ReceiveTime',
                                                                                                ascending=False)
        fodc_timeline = fodc_dynamic_df[fodc_dynamic_df['FlightKey'] == flight_key].sort_values('ReceiveTime',
                                                                                                ascending=False)

        if fpla_timeline.empty:
            dynamic_results.append({
                'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                'AFTN_Event_Type': f"{msg_type} (无匹配)",
                'AFTN_Change_Detail': 'N/A',
                'FPLA_vs_AFTN_Status': '无FPLA数据',
                'FPLA_vs_FODC_Status': '无FPLA数据',
                'Evidence': '无FPLA数据'
            })
            continue

        latest_fodc = fodc_timeline.iloc[0] if not fodc_timeline.empty else None

        def find_match_in_history(aftn_value, timeline_df, col_name, is_time=False):
            if timeline_df is None or timeline_df.empty: return None, False
            for _, row in timeline_df.iterrows():
                platform_val = row.get(col_name)
                if is_time:
                    platform_val_formatted = format_time(parse_fpla_time(platform_val))
                    aftn_value_formatted = format_time(aftn_value)
                    if platform_val_formatted == aftn_value_formatted: return platform_val_formatted, True
                else:
                    platform_val_stripped = safe_strip(platform_val)
                    if platform_val_stripped == safe_strip(aftn_value): return platform_val_stripped, True
            last_value = timeline_df.iloc[0].get(col_name)
            return (format_time(parse_fpla_time(last_value)) if is_time else safe_strip(last_value)), False

        def compare_with_fodc(fpla_val, fodc_latest, fodc_col, is_time=False):
            if fodc_latest is None: return "无FODC标杆"
            fodc_val = fodc_latest.get(fodc_col)
            if pd.isna(fodc_val): return "无FODC数据"

            if is_time:
                fpla_formatted = format_time(parse_fpla_time(fpla_val))
                fodc_formatted = format_time(parse_fpla_time(fodc_val))
                return "一致" if fpla_formatted == fodc_formatted else "不一致"
            else:
                return "一致" if safe_strip(fpla_val) == safe_strip(fodc_val) else "不一致"

        if msg_type in ['DLA', 'CHG']:
            change_found = False
            if pd.notna(aftn_row.get('New_Departure_Time')):
                change_found = True
                aftn_val_dt = convert_utc_str_to_bjt(aftn_row.get('New_Departure_Time'), aftn_event_time.date())
                fpla_matched_val, fpla_aftn_match_bool = find_match_in_history(aftn_val_dt, fpla_timeline, 'APTSOBT',
                                                                               is_time=True)
                fpla_fodc_status = compare_with_fodc(fpla_matched_val, latest_fodc, 'FODC_ATOT', is_time=True)
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (时刻变更)",
                                        'AFTN_Change_Detail': f"新离港时刻: {format_time(aftn_val_dt)}",
                                        'FPLA_vs_AFTN_Status': "一致" if fpla_aftn_match_bool else "不一致",
                                        'FPLA_vs_FODC_Status': fpla_fodc_status,
                                        'Evidence': f"FPLA保障时刻: {fpla_matched_val}, FODC实际起飞: {format_time(parse_fpla_time(latest_fodc.get('FODC_ATOT')) if latest_fodc is not None else None)}"})

            if pd.notna(aftn_row.get('New_RegNo')):
                change_found = True
                aftn_val = safe_strip(aftn_row.get('New_RegNo'))
                fpla_matched_val, fpla_aftn_match_bool = find_match_in_history(aftn_val, fpla_timeline, 'RegNo')
                fpla_fodc_status = compare_with_fodc(fpla_matched_val, latest_fodc, 'RegNo')
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (机号变更)",
                                        'AFTN_Change_Detail': f"新机号: {aftn_val}",
                                        'FPLA_vs_AFTN_Status': "一致" if fpla_aftn_match_bool else "不一致",
                                        'FPLA_vs_FODC_Status': fpla_fodc_status,
                                        'Evidence': f"FPLA机号: {fpla_matched_val}, FODC机号: {safe_strip(latest_fodc.get('RegNo')) if latest_fodc is not None else None}"})

            if pd.notna(aftn_row.get('New_Destination')):
                change_found = True
                aftn_val = safe_strip(aftn_row.get('New_Destination'))
                fpla_matched_val, fpla_aftn_match_bool = find_match_in_history(aftn_val, fpla_timeline, 'APTARRAP')
                fpla_fodc_status = compare_with_fodc(fpla_matched_val, latest_fodc, 'ArrAirport')
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (航站变更)",
                                        'AFTN_Change_Detail': f"新目的地: {aftn_val}",
                                        'FPLA_vs_AFTN_Status': "一致" if fpla_aftn_match_bool else "不一致",
                                        'FPLA_vs_FODC_Status': fpla_fodc_status,
                                        'Evidence': f"FPLA保障目的地: {fpla_matched_val}, FODC目的地: {safe_strip(latest_fodc.get('ArrAirport')) if latest_fodc is not None else None}"})

            if pd.notna(aftn_row.get('New_CraftType')):
                change_found = True
                aftn_val = safe_strip(aftn_row.get('New_CraftType'))
                fpla_matched_val, fpla_aftn_match_bool = find_match_in_history(aftn_val, fpla_timeline, 'CraftType')
                fpla_fodc_status = compare_with_fodc(fpla_matched_val, latest_fodc, 'CraftType')
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (机型变更)",
                                        'AFTN_Change_Detail': f"新机型: {aftn_val}",
                                        'FPLA_vs_AFTN_Status': "一致" if fpla_aftn_match_bool else "不一致",
                                        'FPLA_vs_FODC_Status': fpla_fodc_status,
                                        'Evidence': f"FPLA机型: {fpla_matched_val}, FODC机型: {safe_strip(latest_fodc.get('CraftType')) if latest_fodc is not None else None}"})

            if pd.notna(aftn_row.get('New_FlightNo')):
                change_found = True
                aftn_val = safe_strip(aftn_row.get('New_FlightNo'))
                fpla_matched_val, fpla_aftn_match_bool = find_match_in_history(aftn_val, fpla_timeline, 'FlightNo')
                fpla_fodc_status = compare_with_fodc(fpla_matched_val, latest_fodc, 'FlightNo')
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (航班号变更)",
                                        'AFTN_Change_Detail': f"新航班号: {aftn_val}",
                                        'FPLA_vs_AFTN_Status': "一致" if fpla_aftn_match_bool else "不一致",
                                        'FPLA_vs_FODC_Status': fpla_fodc_status,
                                        'Evidence': f"FPLA航班号: {fpla_matched_val}, FODC航班号: {safe_strip(latest_fodc.get('FlightNo')) if latest_fodc is not None else None}"})

            if not change_found and msg_type == 'CHG':
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (其他变更)",
                                        'AFTN_Change_Detail': '未识别出核心字段变更', 'FPLA_vs_AFTN_Status': 'N/A',
                                        'FPLA_vs_FODC_Status': 'N/A', 'Evidence': 'N/A'})

        elif msg_type == 'CPL':
            cpl_fields_to_compare = {'航班号变更': ('New_FlightNo', 'FlightNo', 'FlightNo'),
                                     '机型变更': ('New_CraftType', 'CraftType', 'CraftType'),
                                     '机号变更': ('New_RegNo', 'RegNo', 'RegNo'),
                                     '航站变更': ('New_Destination', 'APTARRAP', 'ArrAirport')}
            for change_type, (aftn_col, fpla_col, fodc_col) in cpl_fields_to_compare.items():
                if pd.notna(aftn_row.get(aftn_col)):
                    aftn_val = safe_strip(aftn_row.get(aftn_col))
                    fpla_matched_val, fpla_aftn_match_bool = find_match_in_history(aftn_val, fpla_timeline, fpla_col)
                    fpla_fodc_status = compare_with_fodc(fpla_matched_val, latest_fodc, fodc_col)
                    dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                            'AFTN_Event_Type': f"CPL ({change_type})",
                                            'AFTN_Change_Detail': f"新数据: {aftn_val}",
                                            'FPLA_vs_AFTN_Status': "一致" if fpla_aftn_match_bool else "不一致",
                                            'FPLA_vs_FODC_Status': fpla_fodc_status,
                                            'Evidence': f"FPLA数据: {fpla_matched_val}, FODC数据: {safe_strip(latest_fodc.get(fodc_col)) if latest_fodc is not None else None}"})

    df = pd.DataFrame(dynamic_results)
    if not df.empty:
        df.columns = [
            '航班标识(FlightKey)', 'AFTN事件时间(AFTN_Event_Time)', 'AFTN事件类型(AFTN_Event_Type)',
            'AFTN变更明细(AFTN_Change_Detail)', 'FPLA vs AFTN 状态', 'FPLA vs FODC 状态', '数据源佐证(Evidence)'
        ]
    return df


# ==============================================================================
# --- 5. 核心函数：准确率统计 (已重构为直接从报告计数) ---
# ==============================================================================
def calculate_accuracy(plan_report_df, dynamic_report_df):
    # --- 计划-FPLA vs AFTN ---
    plan_aftn_data = []
    total_plans = len(plan_report_df)
    fpla_found = plan_report_df['FPLA-机号(FPLA_RegNo)'] != '无FPLA数据'
    matched_fpla_df = plan_report_df[fpla_found]

    plan_aftn_data.append({'分类': '匹配度', '统计项': '总计划航班数 (AFTN FPL)', '数量/比例': total_plans,
                           '备注': '以当天AFTN FPL报文为基准'})
    plan_aftn_data.append({'分类': '匹配度', '统计项': 'FPLA 匹配航班数', '数量/比例': fpla_found.sum(),
                           '备注': '在FPLA数据中能找到对应航班的数量'})
    plan_aftn_data.append({'分类': '匹配度', '统计项': 'FPLA 匹配率',
                           '数量/比例': f"{(fpla_found.sum() / total_plans * 100):.2f}%" if total_plans > 0 else "0.00%",
                           '备注': 'FPLA匹配数 / 总计划航班数'})

    if not matched_fpla_df.empty:
        reg_accurate = (matched_fpla_df['AFTN-机号(FPL_RegNo)'] == matched_fpla_df['FPLA-机号(FPLA_RegNo)']).sum()
        sobt_accurate = (
                matched_fpla_df['AFTN-离港时间(FPL_SOBT_BJT)'] == matched_fpla_df['FPLA-离港时间(FPLA_SOBT)']).sum()
        combined_accurate = ((matched_fpla_df['AFTN-机号(FPL_RegNo)'] == matched_fpla_df['FPLA-机号(FPLA_RegNo)']) & (
                matched_fpla_df['AFTN-离港时间(FPL_SOBT_BJT)'] == matched_fpla_df['FPLA-离港时间(FPLA_SOBT)'])).sum()

        plan_aftn_data.append(
            {'分类': '准确度', '统计项': '(对比基数：FPLA匹配的航班)', '数量/比例': len(matched_fpla_df), '备注': ''})
        plan_aftn_data.append({'分类': '准确度', '统计项': '机号一致数', '数量/比例': reg_accurate, '备注': ''})
        plan_aftn_data.append({'分类': '准确度', '统计项': '时刻一致数', '数量/比例': sobt_accurate, '备注': ''})
        plan_aftn_data.append({'分类': '准确度', '统计项': '综合一致数', '数量/比例': combined_accurate,
                               '备注': '机号和时刻均一致的数量'})
        plan_aftn_data.append({'分类': '准确度', '统计项': '综合准确率',
                               '数量/比例': f"{(combined_accurate / len(matched_fpla_df) * 100):.2f}%",
                               '备注': '综合一致数 / FPLA匹配航班数'})
    plan_aftn_stats_df = pd.DataFrame(plan_aftn_data)

    # --- 计划-FPLA vs FODC ---
    plan_fodc_data = []
    matched_both_df = plan_report_df[(plan_report_df['FPLA-机号(FPLA_RegNo)'] != '无FPLA数据') & (
            plan_report_df['FODC-机号(FODC_RegNo)'] != '无FODC数据')]

    plan_fodc_data.append(
        {'分类': '匹配度', '统计项': 'FPLA与FODC均存在的计划航班数', '数量/比例': len(matched_both_df),
         '备注': '作为对比基准'})
    if not matched_both_df.empty:
        reg_accurate = (matched_both_df['FPLA-机号(FPLA_RegNo)'] == matched_both_df['FODC-机号(FODC_RegNo)']).sum()
        sobt_accurate = (
                matched_both_df['FPLA-离港时间(FPLA_SOBT)'] == matched_both_df['FODC-离港时间(FODC_SOBT)']).sum()
        combined_accurate = ((matched_both_df['FPLA-机号(FPLA_RegNo)'] == matched_both_df['FODC-机号(FODC_RegNo)']) & (
                matched_both_df['FPLA-离港时间(FPLA_SOBT)'] == matched_both_df['FODC-离港时间(FODC_SOBT)'])).sum()

        plan_fodc_data.append({'分类': '准确度', '统计项': '机号一致数', '数量/比例': reg_accurate, '备注': ''})
        plan_fodc_data.append({'分类': '准确度', '统计项': '时刻一致数', '数量/比例': sobt_accurate, '备注': ''})
        plan_fodc_data.append({'分类': '准确度', '统计项': '综合一致数', '数量/比例': combined_accurate,
                               '备注': '机号和时刻均一致的数量'})
        plan_fodc_data.append({'分类': '准确度', '统计项': '综合准确率',
                               '数量/比例': f"{(combined_accurate / len(matched_both_df) * 100):.2f}%",
                               '备注': '综合一致数 / FPLA与FODC均匹配数'})
    plan_fodc_stats_df = pd.DataFrame(plan_fodc_data)

    # --- 动态-FPLA vs AFTN ---
    dyn_aftn_stats = {}
    total_events = len(dynamic_report_df)
    matched_df = dynamic_report_df[dynamic_report_df['FPLA vs AFTN 状态'] != '无FPLA数据']
    accurate_total = (matched_df['FPLA vs AFTN 状态'] == '一致').sum()

    dyn_aftn_stats['总计'] = {'total': total_events, 'matched': len(matched_df), 'accurate': accurate_total}

    for event in ['时刻变更', '机号变更', '航站变更', '机型变更', '航班号变更']:
        event_df = dynamic_report_df[dynamic_report_df['AFTN事件类型(AFTN_Event_Type)'].str.contains(event, na=False)]
        if not event_df.empty:
            matched_event_df = event_df[event_df['FPLA vs AFTN 状态'] != '无FPLA数据']
            accurate_event = (matched_event_df['FPLA vs AFTN 状态'] == '一致').sum()
            dyn_aftn_stats[event] = {'total': len(event_df), 'matched': len(matched_event_df),
                                     'accurate': accurate_event}

    dyn_aftn_data = []
    for event, data in dyn_aftn_stats.items():
        if data.get('total', 0) > 0:  # 只显示有事件发生的类型
            dyn_aftn_data.append({'事件类型': event, '统计项': 'AFTN事件数', '数值': data['total']})
            dyn_aftn_data.append({'事件类型': event, '统计项': 'FPLA匹配数', '数值': data['matched']})
            if event == '总计':
                dyn_aftn_data.append({'事件类型': event, '统计项': 'FPLA匹配率',
                                      '数值': f"{(data['matched'] / data['total'] * 100):.2f}%" if data[
                                                                                                       'total'] > 0 else "0.00%"})
                dyn_aftn_data.append({'事件类型': event, '统计项': '综合准确事件数', '数值': data['accurate']})
            if data['matched'] > 0:
                dyn_aftn_data.append({'事件类型': event, '统计项': '准确率',
                                      '数值': f"{(data['accurate'] / data['matched'] * 100):.2f}% ({data['accurate']}/{data['matched']})"})
    dyn_aftn_stats_df = pd.DataFrame(dyn_aftn_data)

    # --- 动态-FPLA vs FODC ---
    dyn_fodc_stats = {}
    fodc_present_df = dynamic_report_df[dynamic_report_df['FPLA vs FODC 状态'] != '无FODC标杆']
    accurate_fodc_df = fodc_present_df[fodc_present_df['FPLA vs FODC 状态'] == '一致']

    dyn_fodc_stats['总计'] = {'base': len(fodc_present_df), 'accurate': len(accurate_fodc_df)}

    for event in ['时刻变更', '机号变更', '航站变更', '机型变更', '航班号变更']:
        event_df = fodc_present_df[fodc_present_df['AFTN事件类型(AFTN_Event_Type)'].str.contains(event, na=False)]
        if not event_df.empty:
            accurate_event_df = event_df[event_df['FPLA vs FODC 状态'] == '一致']
            dyn_fodc_stats[event] = {'base': len(event_df), 'accurate': len(accurate_event_df)}

    dyn_fodc_data = []
    for event, data in dyn_fodc_stats.items():
        if data.get('base', 0) > 0:  # 只显示有标杆的事件类型
            dyn_fodc_data.append({'事件类型': event, '统计项': 'FODC存在标杆数', '数值': data['base']})
            if event == '总计':
                dyn_fodc_data.append({'事件类型': event, '统计项': '综合准确事件数', '数值': data['accurate']})
            if data['base'] > 0:
                dyn_fodc_data.append({'事件类型': event, '统计项': '准确率',
                                      '数值': f"{(data['accurate'] / data['base'] * 100):.2f}% ({data['accurate']}/{data['base']})"})
    dyn_fodc_stats_df = pd.DataFrame(dyn_fodc_data)

    return plan_aftn_stats_df, plan_fodc_stats_df, dyn_aftn_stats_df, dyn_fodc_stats_df


# ==============================================================================
# --- 6. 主程序入口 ---
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
        fpla_plan_df = pd.read_csv(FPLA_PLAN_FILE, low_memory=False)
        fpla_dynamic_df = pd.read_csv(FPLA_DYNAMIC_FILE, low_memory=False)
        fodc_plan_df = pd.read_csv(FODC_PLAN_FILE, low_memory=False)
        fodc_dynamic_df = pd.read_csv(FODC_DYNAMIC_FILE, low_memory=False)
    except FileNotFoundError as e:
        print(f"错误: 找不到预处理文件: {e}。请确保已成功运行 `generate_analysis_files_v1.py`。");
        return

    for df in [aftn_df, fpla_plan_df, fpla_dynamic_df, fodc_plan_df, fodc_dynamic_df]:
        if 'ReceiveTime' in df.columns:
            df['ReceiveTime'] = pd.to_datetime(df['ReceiveTime'], errors='coerce')

    plan_report_df = run_plan_comparison(aftn_df, fpla_plan_df, fodc_plan_df, target_date_obj)
    dynamic_report_df = run_dynamic_comparison(aftn_df, fpla_dynamic_df, fodc_dynamic_df, target_date_obj)

    plan_aftn_stats, plan_fodc_stats, dyn_aftn_stats, dyn_fodc_stats = calculate_accuracy(
        plan_report_df, dynamic_report_df
    )

    with pd.ExcelWriter(OUTPUT_COMPARISON_FILE, engine='xlsxwriter') as writer:
        if not plan_report_df.empty:
            plan_report_df.to_excel(writer, sheet_name='计划对比详情', index=False)
            auto_set_column_width(plan_report_df, writer, '计划对比详情')
            print(f"\n√ [Sheet 1] 计划对比详情已生成")

        if not dynamic_report_df.empty:
            dynamic_report_df.to_excel(writer, sheet_name='动态对比详情', index=False)
            auto_set_column_width(dynamic_report_df, writer, '动态对比详情')
            print(f"√ [Sheet 2] 动态对比详情已生成")

        if not plan_aftn_stats.empty:
            plan_aftn_stats.to_excel(writer, sheet_name='计划-FPLA vs AFTN', index=False)
            auto_set_column_width(plan_aftn_stats, writer, '计划-FPLA vs AFTN')
            print(f"√ [Sheet 3] 计划准确率(vs AFTN)统计已生成")

        if not plan_fodc_stats.empty:
            plan_fodc_stats.to_excel(writer, sheet_name='计划-FPLA vs FODC', index=False)
            auto_set_column_width(plan_fodc_stats, writer, '计划-FPLA vs FODC')
            print(f"√ [Sheet 4] 计划准确率(vs FODC)统计已生成")

        if not dyn_aftn_stats.empty:
            dyn_aftn_stats.to_excel(writer, sheet_name='动态-FPLA vs AFTN', index=False)
            auto_set_column_width(dyn_aftn_stats, writer, '动态-FPLA vs AFTN')
            print(f"√ [Sheet 5] 动态准确率(vs AFTN)统计已生成")

        if not dyn_fodc_stats.empty:
            dyn_fodc_stats.to_excel(writer, sheet_name='动态-FPLA vs FODC', index=False)
            auto_set_column_width(dyn_fodc_stats, writer, '动态-FPLA vs FODC')
            print(f"√ [Sheet 6] 动态准确率(vs FODC)统计已生成")

    print(f"\n===== 日期 {TARGET_DATE_STR} 的对比分析报告已生成: {OUTPUT_COMPARISON_FILE} =====")


if __name__ == "__main__":
    main()