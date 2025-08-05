import os
import re
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# ==============================================================================
# --- 1. 配置加载 (已更新为新的文件结构) ---
# ==============================================================================
load_dotenv()
TARGET_DATE_STR = os.getenv("TARGET_DATE")
if not TARGET_DATE_STR:
    print("错误: 未在 .env 文件中找到 TARGET_DATE 设置。");
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREPROCESSED_DIR = os.path.join(BASE_DIR, 'preprocessed_files')
COMPARE_RESULT_DIR = os.path.join(BASE_DIR, 'compare_result')

# 指向新的预处理文件
AFTN_ANALYSIS_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_aftn_data_{TARGET_DATE_STR}.csv')
FPLA_PLAN_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_fpla_plan_data_{TARGET_DATE_STR}.csv')
FPLA_DYNAMIC_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_fpla_dynamic_data_{TARGET_DATE_STR}.csv')
FODC_PLAN_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_fodc_plan_data_{TARGET_DATE_STR}.csv')
FODC_DYNAMIC_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_fodc_dynamic_data_{TARGET_DATE_STR}.csv')

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
        format_str = '%Y%m%d%H%M%S' if len(time_str) >= 14 else '%Y%m%d%H%M'
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
# --- 3. 核心对比函数：计划对比 (已修改，使用新的plan文件，但保留原逻辑) ---
# ==============================================================================
def run_plan_comparison(aftn_df, fpla_plan_df, fodc_plan_df, target_date_obj):
    """【AFTN基准版】遍历所有AFTN FPL报文，与FPLA和FODC的计划数据进行对比。"""
    print("--- 正在执行 [第一阶段]：最终计划状态快照对比 (AFTN为基准) ---")
    plan_results = []

    # 核心修正：遍历所有 AFTN FPL 的 FlightKey
    aftn_fpl_keys = aftn_df[aftn_df['MessageType'] == 'FPL']['FlightKey'].unique()

    for flight_key in aftn_fpl_keys:
        aftn_fpls = aftn_df[(aftn_df['FlightKey'] == flight_key) & (aftn_df['MessageType'] == 'FPL')].sort_values(
            'ReceiveTime', ascending=False)
        if aftn_fpls.empty: continue
        latest_fpl = aftn_fpls.iloc[0]

        # 解析AFTN数据
        fpl_time_match = re.search(r'-\s*\w{4,10}\s*(\d{4})', latest_fpl.get('RawMessage', ''))
        fpl_eobt_str = fpl_time_match.group(1) if fpl_time_match else np.nan
        dof_match = re.search(r'DOF/(\d{6})', latest_fpl.get('RawMessage', ''))
        base_date = datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date() if dof_match else target_date_obj
        aftn_sobt = convert_utc_str_to_bjt(fpl_eobt_str, base_date)
        # 从原始报文的18项中提取REG
        aftn_reg_match = re.search(r'REG/(\S+)', latest_fpl.get('RawMessage', ''))
        aftn_reg = safe_strip(aftn_reg_match.group(1).strip(')')) if aftn_reg_match else safe_strip(
            latest_fpl.get('RegNo'))

        # 查找FPLA计划数据
        fpla_plans = fpla_plan_df[fpla_plan_df['FlightKey'] == flight_key]

        fpla_sobt, fpla_reg = (None, None)
        if not fpla_plans.empty:
            latest_fpla = fpla_plans.iloc[0]
            fpla_sobt = parse_fpla_time(latest_fpla.get('SOBT'))
            fpla_reg = safe_strip(latest_fpla.get('RegNo'))

        # 查找FODC计划数据
        fodc_records = fodc_plan_df[fodc_plan_df['FlightKey'] == flight_key]
        fodc_sobt, fodc_reg = (None, None)
        if not fodc_records.empty:
            latest_fodc = fodc_records.iloc[0]
            fodc_sobt = parse_fpla_time(latest_fodc.get('SOBT'))
            fodc_reg = safe_strip(latest_fodc.get('RegNo'))

        # 构建结果行
        result_row = {
            'FlightKey': flight_key,
            'FPL_RegNo': aftn_reg,
            'FPLA_RegNo': fpla_reg if fpla_reg is not None else '无FPLA数据',
            'FPL_SOBT_BJT': format_time(aftn_sobt),
            'FPLA_SOBT': format_time(fpla_sobt) if fpla_sobt is not None else '无FPLA数据',
            'FODC_RegNo': fodc_reg if fodc_reg is not None else '无FODC数据',
            'FODC_SOBT': format_time(fodc_sobt) if fodc_sobt is not None else '无FODC数据'
        }

        # 生成结论 (保留您的原始详细逻辑)
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
    return pd.DataFrame(plan_results)


# ==============================================================================
# --- 4. 核心对比函数：动态对比 (已修改，使用新的dynamic文件，但保留原逻辑) ---
# ==============================================================================
def run_dynamic_comparison(aftn_df, fpla_dynamic_df, fodc_dynamic_df, target_date_obj):
    """【AFTN基准版】遍历所有AFTN动态报文，与FPLA和FODC的动态数据进行对比。"""
    print("--- 正在执行 [第二阶段]：动态变更事件溯源对比 (AFTN为基准) ---")
    dynamic_results = []
    aftn_dynamics = aftn_df[aftn_df['MessageType'].isin(['DLA', 'CHG', 'CPL'])].sort_values('ReceiveTime')

    for index, aftn_row in aftn_dynamics.iterrows():
        flight_key = aftn_row.get('FlightKey')
        if pd.isna(flight_key): continue

        aftn_event_time = aftn_row['ReceiveTime']
        msg_type = aftn_row['MessageType']

        # 查找FPLA和FODC数据
        fpla_timeline = fpla_dynamic_df[fpla_dynamic_df['FlightKey'] == flight_key].sort_values('ReceiveTime')
        fodc_timeline = fodc_dynamic_df[fodc_dynamic_df['FlightKey'] == flight_key].sort_values('ReceiveTime',
                                                                                                ascending=False)

        fpla_compare_state = fpla_timeline.iloc[-1] if not fpla_timeline.empty else None
        latest_fodc = fodc_timeline.iloc[0] if not fodc_timeline.empty else None

        if fpla_compare_state is None:
            dynamic_results.append({
                'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                'AFTN_Event_Type': f"{msg_type} (无匹配)",
                'AFTN_Change_Detail': 'N/A',
                'FPLA_Evidence': '无FPLA数据',
                'Conclusion': '无FPLA数据'
            })
            continue

        # 保留您的原始详细对比逻辑
        if msg_type == 'DLA' or msg_type == 'CHG':
            change_found = False
            if pd.notna(aftn_row.get('New_Departure_Time')):
                change_found = True;
                # 使用保障计划时间（APT）进行对比
                aftn_val = convert_utc_str_to_bjt(aftn_row.get('New_Departure_Time'), aftn_event_time.date());
                fpla_val = parse_fpla_time(fpla_compare_state.get('APTSOBT'));
                fodc_val = parse_fpla_time(latest_fodc.get('FODC_ATOT')) if latest_fodc is not None and pd.notna(
                    latest_fodc.get('FODC_ATOT')) else None;
                conclusion = "无FODC(ATOT)标杆"
                if fodc_val is not None:
                    aftn_match = format_time(aftn_val) == format_time(fodc_val);
                    fpla_match = format_time(fpla_val) == format_time(fodc_val)
                    if aftn_match and fpla_match:
                        conclusion = "三方时刻一致"
                    elif aftn_match:
                        conclusion = "AFTN/FODC(ATOT)一致, FPLA不一致"
                    elif fpla_match:
                        conclusion = "FPLA/FODC(ATOT)一致, AFTN不一致"
                    else:
                        conclusion = f"三方不一致 (AFTN:{format_time(aftn_val)}, FPLA:{format_time(fpla_val)}, FODC:{format_time(fodc_val)})"
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (时刻变更)",
                                        'AFTN_Change_Detail': f"New SOBT: {format_time(aftn_val)}",
                                        'FPLA_Evidence': f"FPLA APTSOBT: {format_time(fpla_val)}, FODC ATOT: {format_time(fodc_val)}",
                                        'Conclusion': conclusion})
            if pd.notna(aftn_row.get('New_RegNo')):
                change_found = True;
                aftn_val = safe_strip(aftn_row.get('New_RegNo'));
                fpla_val = safe_strip(fpla_compare_state.get('RegNo'));
                fodc_val = safe_strip(latest_fodc.get('RegNo')) if latest_fodc is not None else None;
                conclusion = "无FODC标杆"
                if fodc_val is not None:
                    aftn_match = (aftn_val == fodc_val);
                    fpla_match = (fpla_val == fodc_val)
                    if aftn_match and fpla_match:
                        conclusion = "三方一致"
                    elif aftn_match:
                        conclusion = "AFTN/FODC一致, FPLA不一致"
                    elif fpla_match:
                        conclusion = "FPLA/FODC一致, AFTN不一致"
                    else:
                        conclusion = f"三方不一致 (AFTN:'{aftn_val}', FPLA:'{fpla_val}', FODC:'{fodc_val}')"
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (机号变更)",
                                        'AFTN_Change_Detail': f"New RegNo: {aftn_val}",
                                        'FPLA_Evidence': f"FPLA: {fpla_val}, FODC: {fodc_val}",
                                        'Conclusion': conclusion})
            if pd.notna(aftn_row.get('New_Destination')):
                change_found = True;
                # 使用保障计划机场进行对比
                aftn_val = safe_strip(aftn_row.get('New_Destination'));
                fpla_val = safe_strip(fpla_compare_state.get('APTARRAP'));
                fodc_val = safe_strip(latest_fodc.get('ArrAirport')) if latest_fodc is not None else None;
                conclusion = "无FODC标杆"
                if fodc_val is not None:
                    aftn_match = (aftn_val == fodc_val);
                    fpla_match = (fpla_val == fodc_val)
                    if aftn_match and fpla_match:
                        conclusion = "三方一致"
                    elif aftn_match:
                        conclusion = "AFTN/FODC一致, FPLA不一致"
                    elif fpla_match:
                        conclusion = "FPLA/FODC一致, AFTN不一致"
                    else:
                        conclusion = f"三方不一致 (AFTN:'{aftn_val}', FPLA:'{fpla_val}', FODC:'{fodc_val}')"
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (航站变更)",
                                        'AFTN_Change_Detail': f"New Dest: {aftn_val}",
                                        'FPLA_Evidence': f"FPLA APTARRAP: {fpla_val}, FODC: {fodc_val}",
                                        'Conclusion': conclusion})
            # 其他字段对比... (保持不变)
            if pd.notna(aftn_row.get('New_CraftType')):
                change_found = True;
                aftn_val = safe_strip(aftn_row.get('New_CraftType'));
                fpla_val = safe_strip(fpla_compare_state.get('CraftType'));
                fodc_val = safe_strip(latest_fodc.get('CraftType')) if latest_fodc is not None else None;
                conclusion = "无FODC标杆"
                if fodc_val is not None:
                    aftn_match = (aftn_val == fodc_val);
                    fpla_match = (fpla_val == fodc_val)
                    if aftn_match and fpla_match:
                        conclusion = "三方一致"
                    elif aftn_match:
                        conclusion = "AFTN/FODC一致, FPLA不一致"
                    elif fpla_match:
                        conclusion = "FPLA/FODC一致, AFTN不一致"
                    else:
                        conclusion = f"三方不一致 (AFTN:'{aftn_val}', FPLA:'{fpla_val}', FODC:'{fodc_val}')"
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (机型变更)",
                                        'AFTN_Change_Detail': f"New CraftType: {aftn_val}",
                                        'FPLA_Evidence': f"FPLA: {fpla_val}, FODC: {fodc_val}",
                                        'Conclusion': conclusion})
            if pd.notna(aftn_row.get('New_FlightNo')):
                change_found = True;
                aftn_val = safe_strip(aftn_row.get('New_FlightNo'));
                fpla_val = safe_strip(fpla_compare_state.get('FlightNo'));
                fodc_val = safe_strip(latest_fodc.get('FlightNo')) if latest_fodc is not None else None;
                conclusion = "无FODC标杆"
                if fodc_val is not None:
                    aftn_match = (aftn_val == fodc_val);
                    fpla_match = (fpla_val == fodc_val)
                    if aftn_match and fpla_match:
                        conclusion = "三方一致"
                    elif aftn_match:
                        conclusion = "AFTN/FODC一致, FPLA不一致"
                    elif fpla_match:
                        conclusion = "FPLA/FODC一致, AFTN不一致"
                    else:
                        conclusion = f"三方不一致 (AFTN:'{aftn_val}', FPLA:'{fpla_val}', FODC:'{fodc_val}')"
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (航班号变更)",
                                        'AFTN_Change_Detail': f"New FlightNo: {aftn_val}",
                                        'FPLA_Evidence': f"FPLA: {fpla_val}, FODC: {fodc_val}",
                                        'Conclusion': conclusion})

            if not change_found and msg_type == 'CHG':
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (其他变更)",
                                        'AFTN_Change_Detail': '未识别出核心字段变更', 'FPLA_Evidence': 'N/A',
                                        'Conclusion': '不影响地面保障，忽略对比'})

        elif msg_type == 'CPL':
            cpl_fields_to_compare = {'航班号变更': ('New_FlightNo', 'FlightNo', 'FlightNo'),
                                     '机型变更': ('New_CraftType', 'CraftType', 'CraftType'),
                                     '机号变更': ('New_RegNo', 'RegNo', 'RegNo'),
                                     '航站变更': ('New_Destination', 'APTARRAP', 'ArrAirport')}  # CPL航站变更对比FPLA动态航站
            for change_type, (aftn_col, fpla_col, fodc_col) in cpl_fields_to_compare.items():
                if pd.notna(aftn_row.get(aftn_col)):
                    aftn_val = safe_strip(aftn_row.get(aftn_col));
                    fpla_val = safe_strip(fpla_compare_state.get(fpla_col));
                    fodc_val = safe_strip(latest_fodc.get(fodc_col)) if latest_fodc is not None else None;
                    conclusion = "无FODC标杆"
                    if fodc_val is not None:
                        aftn_match = (aftn_val == fodc_val);
                        fpla_match = (fpla_val == fodc_val)
                        if aftn_match and fpla_match:
                            conclusion = "三方一致"
                        elif aftn_match:
                            conclusion = "AFTN/FODC一致, FPLA不一致"
                        elif fpla_match:
                            conclusion = "FPLA/FODC一致, AFTN不一致"
                        else:
                            conclusion = f"三方不一致 (AFTN:'{aftn_val}', FPLA:'{fpla_val}', FODC:'{fodc_val}')"
                    dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                            'AFTN_Event_Type': f"CPL ({change_type})",
                                            'AFTN_Change_Detail': f"New Value: {aftn_val}",
                                            'FPLA_Evidence': f"FPLA: {fpla_val}, FODC: {fodc_val}",
                                            'Conclusion': conclusion})
    return pd.DataFrame(dynamic_results)


# ==============================================================================
# --- 5. 主程序入口 (已修改为加载新文件) ---
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
        # 加载所有五个预处理文件
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

    # 执行计划对比
    plan_report_df = run_plan_comparison(aftn_df, fpla_plan_df, fodc_plan_df, target_date_obj)
    if not plan_report_df.empty:
        with pd.ExcelWriter(PLAN_COMPARISON_FILE, engine='xlsxwriter') as writer:
            plan_report_df.to_excel(writer, sheet_name='PlanComparison', index=False)
            auto_set_column_width(plan_report_df, writer, 'PlanComparison')
        print(f"\n√ [第一阶段] 最终计划对比报告已生成: {PLAN_COMPARISON_FILE}")

    # 执行动态对比
    dynamic_report_df = run_dynamic_comparison(aftn_df, fpla_dynamic_df, fodc_dynamic_df, target_date_obj)
    if not dynamic_report_df.empty:
        final_cols = ['FlightKey', 'AFTN_Event_Time', 'AFTN_Event_Type', 'AFTN_Change_Detail', 'FPLA_Evidence',
                      'Conclusion']
        dynamic_report_df = dynamic_report_df.reindex(columns=final_cols).fillna('')
        with pd.ExcelWriter(DYNAMIC_COMPARISON_FILE, engine='xlsxwriter') as writer:
            dynamic_report_df.to_excel(writer, sheet_name='DynamicComparison', index=False)
            auto_set_column_width(dynamic_report_df, writer, 'DynamicComparison')
        print(f"√ [第二阶段] 动态变更溯源报告已生成: {DYNAMIC_COMPARISON_FILE}")
    else:
        print("\n[第二阶段] 未生成动态变更溯源报告，因为没有AFTN动态消息或相应FPLA数据。")

    print(f"\n===== 日期 {TARGET_DATE_STR} 的对比分析任务已完成 =====")


if __name__ == "__main__":
    main()