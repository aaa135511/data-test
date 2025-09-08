# ==============================================================================
# --- 0. 导入所需库 ---
# ==============================================================================
import os
import sys
import json
import re
from datetime import datetime, timedelta
import traceback
import threading

# --- GUI 和核心处理库 ---
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------------
# ALL BACKEND LOGIC (HELPER FUNCTIONS, PROCESSING, COMPARISON) GOES HERE.
# This part is identical to the previous script, so it's collapsed for clarity.
# Ensure you copy the full, correct functions into this space.
# ----------------------------------------------------------------------------------

# <editor-fold desc="Backend Data Processing and Analysis Logic">
# ==============================================================================
# --- 2. 辅助函数 (来自两个原始脚本) ---
# ==============================================================================
def generate_flight_key(exec_date, flight_no, dep_icao, arr_icao):
    if not all([exec_date, flight_no, dep_icao, arr_icao]): return "KEY_GENERATION_FAILED"
    flight_no = str(flight_no).strip();
    dep_icao = str(dep_icao).strip();
    arr_icao = str(arr_icao).strip()
    if isinstance(exec_date, datetime): exec_date = exec_date.date()
    return f"{exec_date.strftime('%Y-%m-%d')}_{flight_no}_{dep_icao}_{arr_icao}"


def get_flight_date_from_aftn(tele_body, receive_time):
    dof_match = re.search(r'DOF/(\d{6})', tele_body)
    if dof_match:
        try:
            return datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date()
        except:
            pass
    if isinstance(receive_time, datetime): return receive_time.date()
    return None


def parse_core_business_info(body):
    changes = {};
    pattern = r'-\s*(\d{1,2})\s*/\s*(.*?)(?=\s*-\s*\d{1,2}\s*/|\)$)'
    matches = re.findall(pattern, body, re.DOTALL)
    for item_num_str, content_raw in matches:
        content = content_raw.strip().replace('\r\n', ' ').replace('\n', ' ')
        if item_num_str == '7':
            changes['New_FlightNo'] = content.split('/')[0].strip()
        elif item_num_str == '9':
            changes['New_CraftType'] = content.split('/')[0].strip()
        elif item_num_str == '13' and len(content.split()[0]) >= 8:
            changes['New_Departure_Time'] = content.split()[0][-4:]
        elif item_num_str == '15':
            changes['New_Route'] = content
        elif item_num_str == '16':
            parts = content.split()
            if parts:
                dest_eet = parts[0];
                changes['New_Destination'] = dest_eet[:-4] if len(dest_eet) >= 8 else dest_eet
                if len(parts) > 1: changes['New_Alternate_1'] = parts[1]
                if len(parts) > 2: changes['New_Alternate_2'] = parts[2]
        elif item_num_str == '18':
            if re.search(r'REG/(\S+)', content): changes['New_RegNo'] = re.search(r'REG/(\S+)', content).group(1).strip(
                ')')
            if re.search(r'STS/(\S+)', content): changes['New_Mission_STS'] = re.search(r'STS/(\S+)', content).group(1)
    return changes


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
    except:
        return pd.NaT


def auto_set_column_width(df, writer, sheet_name):
    worksheet = writer.sheets[sheet_name]
    for i, col in enumerate(df.columns):
        max_len = max([len(str(s).encode('gbk', 'ignore')) for s in df[col].astype(str).tolist() + [col]]) + 2
        worksheet.set_column(i, i, max_len)


def safe_strip(val):
    return str(val).strip() if pd.notna(val) else ""


# ==============================================================================
# --- 3. 核心处理函数 (与之前合并脚本一致) ---
# ==============================================================================
def process_aftn_for_analysis(df, target_date):
    processed_records = []
    for index, row in df.iterrows():
        try:
            data = json.loads(row.iloc[1]);
            tele_body = str(row.iloc[3]);
            receive_time = pd.to_datetime(row.iloc[4], errors='coerce')
            msg_type = tele_body[1:4].strip()
            if msg_type in ['DEP', 'ARR'] or pd.isna(receive_time): continue
            flight_date = get_flight_date_from_aftn(tele_body, receive_time)
            if not flight_date or flight_date != target_date: continue
            flight_no_match = re.search(r'^\(\w{3}-([A-Z0-9]+)', tele_body)
            full_flight_no = flight_no_match.group(
                1).strip() if flight_no_match else f"{data.get('airlineIcaoCode', '')}{str(data.get('flightNo', '')).lstrip('0')}"
            dep_icao = data.get('depAirportIcaoCode');
            arr_icao = None
            if msg_type == 'CPL':
                arr_icao = data.get('actlArrAirportIcaoCode') or data.get('orgArrAirportIcaoCode') or data.get(
                    'arrAirportIcaoCode')
                if not arr_icao:
                    arr_match = re.search(r'-\s*([A-Z]{4})\s*\n\s*(-PBN|-REG|-DOF|-EET|-SEL|-CODE|-RMK|\))', tele_body)
                    if arr_match: arr_icao = arr_match.group(1)
                if not dep_icao:
                    lines = tele_body.splitlines()
                    if len(lines) > 2:
                        dep_match = re.search(r'-\s*([A-Z]{4})', lines[2])
                        if dep_match: dep_icao = dep_match.group(1)
            else:
                arr_icao = data.get('arrAirportIcaoCode')
            record = {'ReceiveTime': receive_time, 'MessageType': msg_type, 'FlightNo': full_flight_no,
                      'RegNo': data.get('regNo'), 'DepAirport': dep_icao, 'ArrAirport': arr_icao,
                      'CraftType': data.get('aerocraftTypeIcaoCode'), 'RawMessage': tele_body}
            if msg_type == 'CHG':
                record.update(parse_core_business_info(tele_body))
            elif msg_type == 'DLA':
                dla_match = re.search(r'-\s*\w+\s*-\s*\w{4}(\d{4})', tele_body)
                if dla_match: record['New_Departure_Time'] = dla_match.group(1)
            elif msg_type == 'CPL':
                cpl_changes = {}
                craft_match = re.search(r'-\s*([A-Z0-9]{3,4})/[LMHJ]', tele_body)
                if craft_match: cpl_changes['New_CraftType'] = craft_match.group(1)
                reg_match = re.search(r'REG/(\S+)', tele_body)
                if reg_match: cpl_changes['New_RegNo'] = reg_match.group(1).strip(')')
                cpl_changes['New_FlightNo'] = full_flight_no;
                cpl_changes['New_Destination'] = arr_icao
                record.update(cpl_changes)
            key_flight_no = record.get('New_FlightNo', full_flight_no);
            key_dep_airport = record.get('DepAirport');
            key_arr_airport = record.get('New_Destination') or record.get('ArrAirport')
            record['FlightKey'] = generate_flight_key(flight_date, key_flight_no, key_dep_airport, key_arr_airport)
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
            flight_key = generate_flight_key(flight_date, row.get('CALLSIGN'), row.get('DEPAP'), row.get('ARRAP'))
            record = {'FlightKey': flight_key, 'ReceiveTime': row.get('SENDTIME'),
                      'FPLA_Status': row.get('PSCHEDULESTATUS'), 'FlightNo': row.get('CALLSIGN'),
                      'RegNo': row.get('EREGNUMBER') or row.get('REGNUMBER'), 'CraftType': row.get('PSAIRCRAFTTYPE'),
                      'SOBT': row.get('SOBT'), 'SIBT': row.get('SIBT'), 'DepAirport': row.get('DEPAP'),
                      'ArrAirport': row.get('ARRAP'), 'APTSOBT': row.get('APTSOBT'), 'APTSIBT': row.get('APTSIBT'),
                      'APTDEPAP': row.get('APTDEPAP'), 'APTARRAP': row.get('APTARRAP'), 'Route': row.get('SROUTE')}
            processed_records.append(record)
        except Exception:
            continue
    if not processed_records: return pd.DataFrame(), pd.DataFrame()
    full_df = pd.DataFrame(processed_records)
    return full_df.copy(), full_df.copy()


def process_fodc_for_analysis(df, target_date):
    plan_records, dynamic_records = [], []
    df.columns = [str(col).strip() for col in df.columns]
    for index, row in df.iterrows():
        try:
            sobt_str = str(row.get('计划离港时间')).split('.')[0]
            if pd.isna(sobt_str) or len(sobt_str) < 12: continue
            flight_date = datetime.strptime(sobt_str[:8], "%Y%m%d").date()
            if flight_date != target_date: continue
            flight_key = generate_flight_key(flight_date, row.get('航空器识别标志'), row.get('计划起飞机场'),
                                             row.get('计划降落机场'))
            plan_record = {'FlightKey': flight_key, 'ReceiveTime': row.get('消息发送时间'),
                           'FlightNo': row.get('航空器识别标志'), 'RegNo': row.get('航空器注册号'),
                           'DepAirport': row.get('计划起飞机场'), 'ArrAirport': row.get('计划降落机场'),
                           'SOBT': sobt_str, 'CraftType': row.get('航空器机型')}
            plan_records.append(plan_record)
            if pd.notna(row.get('实际起飞时间')) or pd.notna(row.get('实际起飞机场')):
                dynamic_record = {'FlightKey': flight_key, 'ReceiveTime': row.get('消息发送时间'),
                                  'FlightNo': row.get('航空器识别标志'), 'RegNo': row.get('航空器注册号'),
                                  'CraftType': row.get('航空器机型'),
                                  'DepAirport': row.get('实际起飞机场') or row.get('计划起飞机场'),
                                  'ArrAirport': row.get('实际降落机场') or row.get('计划降落机场'),
                                  'FODC_ATOT': str(row.get('实际起飞时间')).split('.')[0]}
                dynamic_records.append(dynamic_record)
        except Exception:
            continue
    plan_df = pd.DataFrame(plan_records) if plan_records else pd.DataFrame()
    dynamic_df = pd.DataFrame(dynamic_records) if dynamic_records else pd.DataFrame()
    return plan_df, dynamic_df


def run_plan_comparison(aftn_df, fpla_plan_df, fodc_plan_df, target_date_obj):
    plan_results = []
    aftn_fpl_keys = aftn_df[aftn_df['MessageType'] == 'FPL']['FlightKey'].unique()
    for flight_key in aftn_fpl_keys:
        aftn_fpls = aftn_df[(aftn_df['FlightKey'] == flight_key) & (aftn_df['MessageType'] == 'FPL')].sort_values(
            'ReceiveTime', ascending=False)
        if aftn_fpls.empty: continue
        latest_fpl = aftn_fpls.iloc[0]
        fpl_time_match = re.search(r'-\s*\w{4,10}\s*(\d{4})', latest_fpl.get('RawMessage', ''));
        fpl_eobt_str = fpl_time_match.group(1) if fpl_time_match else np.nan
        dof_match = re.search(r'DOF/(\d{6})', latest_fpl.get('RawMessage', ''));
        base_date = datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date() if dof_match else target_date_obj
        aftn_sobt = convert_utc_str_to_bjt(fpl_eobt_str, base_date)
        aftn_reg_match = re.search(r'REG/(\S+)', latest_fpl.get('RawMessage', ''));
        aftn_reg = safe_strip(aftn_reg_match.group(1).strip(')')) if aftn_reg_match else safe_strip(
            latest_fpl.get('RegNo'))
        fpla_plans = fpla_plan_df[fpla_plan_df['FlightKey'] == flight_key].sort_values('ReceiveTime', ascending=False)
        fodc_records = fodc_plan_df[fodc_plan_df['FlightKey'] == flight_key].sort_values('ReceiveTime', ascending=False)
        fpla_sobt, fpla_reg = (None, None)
        if not fpla_plans.empty:
            latest_fpla = fpla_plans.iloc[0];
            fpla_sobt = parse_fpla_time(latest_fpla.get('SOBT'));
            fpla_reg = safe_strip(latest_fpla.get('RegNo'))
        fodc_sobt, fodc_reg = (None, None)
        if not fodc_records.empty:
            latest_fodc = fodc_records.iloc[0];
            fodc_sobt = parse_fpla_time(latest_fodc.get('SOBT'));
            fodc_reg = safe_strip(latest_fodc.get('RegNo'))
        result_row = {'FlightKey': flight_key, 'FPL_RegNo': aftn_reg,
                      'FPLA_RegNo': fpla_reg if fpla_reg is not None else '无FPLA数据',
                      'FPL_SOBT_BJT': format_time(aftn_sobt),
                      'FPLA_SOBT': format_time(fpla_sobt) if fpla_sobt is not None else '无FPLA数据',
                      'FODC_RegNo': fodc_reg if fodc_reg is not None else '无FODC数据',
                      'FODC_SOBT': format_time(fodc_sobt) if fodc_sobt is not None else '无FODC数据'}
        if fpla_reg is None:
            result_row['AFTN_vs_FODC'] = 'N/A (无FPLA)'; result_row['FPLA_vs_FODC'] = '无FPLA数据'; result_row[
                'Final_Conclusion'] = '无FPLA数据'
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
    df.columns = ['航班标识(FlightKey)', 'AFTN-机号(FPL_RegNo)', 'FPLA-机号(FPLA_RegNo)', 'AFTN-离港时间(FPL_SOBT_BJT)',
                  'FPLA-离港时间(FPLA_SOBT)', 'FODC-机号(FODC_RegNo)', 'FODC-离港时间(FODC_SOBT)', 'AFTN vs FODC 对比',
                  'FPLA vs FODC 对比', '最终结论(Final_Conclusion)']
    return df


def run_dynamic_comparison(aftn_df, fpla_dynamic_df, fodc_dynamic_df, target_date_obj):
    dynamic_results = []
    aftn_dynamics = aftn_df[aftn_df['MessageType'].isin(['DLA', 'CHG', 'CPL'])].sort_values('ReceiveTime')
    for index, aftn_row in aftn_dynamics.iterrows():
        flight_key = aftn_row.get('FlightKey');
        if pd.isna(flight_key): continue
        aftn_event_time = aftn_row['ReceiveTime'];
        msg_type = aftn_row['MessageType']
        fpla_timeline = fpla_dynamic_df[fpla_dynamic_df['FlightKey'] == flight_key].sort_values('ReceiveTime',
                                                                                                ascending=False)
        fodc_timeline = fodc_dynamic_df[fodc_dynamic_df['FlightKey'] == flight_key].sort_values('ReceiveTime',
                                                                                                ascending=False)
        if fpla_timeline.empty:
            dynamic_results.append(
                {'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time, 'AFTN_Event_Type': f"{msg_type} (无匹配)",
                 'AFTN_Change_Detail': 'N/A', 'FPLA_vs_AFTN_Status': '无FPLA数据', 'FPLA_vs_FODC_Status': '无FPLA数据',
                 'Evidence': '无FPLA数据'})
            continue
        latest_fodc = fodc_timeline.iloc[0] if not fodc_timeline.empty else None

        def find_match_in_history(aftn_value, timeline_df, col_name, is_time=False):
            if timeline_df is None or timeline_df.empty: return None, False
            for _, row in timeline_df.iterrows():
                platform_val = row.get(col_name)
                if is_time:
                    platform_val_formatted = format_time(parse_fpla_time(platform_val));
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
                fpla_formatted = format_time(parse_fpla_time(fpla_val));
                fodc_formatted = format_time(parse_fpla_time(fodc_val))
                return "一致" if fpla_formatted == fodc_formatted else "不一致"
            else:
                return "一致" if safe_strip(fpla_val) == safe_strip(fodc_val) else "不一致"

        if msg_type in ['DLA', 'CHG']:
            change_found = False
            if pd.notna(aftn_row.get('New_Departure_Time')):
                change_found = True;
                aftn_val_dt = convert_utc_str_to_bjt(aftn_row.get('New_Departure_Time'), aftn_event_time.date());
                fpla_matched_val, fpla_aftn_match_bool = find_match_in_history(aftn_val_dt, fpla_timeline, 'APTSOBT',
                                                                               is_time=True);
                fpla_fodc_status = compare_with_fodc(fpla_matched_val, latest_fodc, 'FODC_ATOT', is_time=True)
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (时刻变更)",
                                        'AFTN_Change_Detail': f"新离港时刻: {format_time(aftn_val_dt)}",
                                        'FPLA_vs_AFTN_Status': "一致" if fpla_aftn_match_bool else "不一致",
                                        'FPLA_vs_FODC_Status': fpla_fodc_status,
                                        'Evidence': f"FPLA保障时刻: {fpla_matched_val}, FODC实际起飞: {format_time(parse_fpla_time(latest_fodc.get('FODC_ATOT')) if latest_fodc is not None else None)}"})
            if pd.notna(aftn_row.get('New_RegNo')):
                change_found = True;
                aftn_val = safe_strip(aftn_row.get('New_RegNo'));
                fpla_matched_val, fpla_aftn_match_bool = find_match_in_history(aftn_val, fpla_timeline, 'RegNo');
                fpla_fodc_status = compare_with_fodc(fpla_matched_val, latest_fodc, 'RegNo')
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (机号变更)",
                                        'AFTN_Change_Detail': f"新机号: {aftn_val}",
                                        'FPLA_vs_AFTN_Status': "一致" if fpla_aftn_match_bool else "不一致",
                                        'FPLA_vs_FODC_Status': fpla_fodc_status,
                                        'Evidence': f"FPLA机号: {fpla_matched_val}, FODC机号: {safe_strip(latest_fodc.get('RegNo')) if latest_fodc is not None else None}"})
            if pd.notna(aftn_row.get('New_Destination')):
                change_found = True;
                aftn_val = safe_strip(aftn_row.get('New_Destination'));
                fpla_matched_val, fpla_aftn_match_bool = find_match_in_history(aftn_val, fpla_timeline, 'APTARRAP');
                fpla_fodc_status = compare_with_fodc(fpla_matched_val, latest_fodc, 'ArrAirport')
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (航站变更)",
                                        'AFTN_Change_Detail': f"新目的地: {aftn_val}",
                                        'FPLA_vs_AFTN_Status': "一致" if fpla_aftn_match_bool else "不一致",
                                        'FPLA_vs_FODC_Status': fpla_fodc_status,
                                        'Evidence': f"FPLA保障目的地: {fpla_matched_val}, FODC目的地: {safe_strip(latest_fodc.get('ArrAirport')) if latest_fodc is not None else None}"})
            if pd.notna(aftn_row.get('New_CraftType')):
                change_found = True;
                aftn_val = safe_strip(aftn_row.get('New_CraftType'));
                fpla_matched_val, fpla_aftn_match_bool = find_match_in_history(aftn_val, fpla_timeline, 'CraftType');
                fpla_fodc_status = compare_with_fodc(fpla_matched_val, latest_fodc, 'CraftType')
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (机型变更)",
                                        'AFTN_Change_Detail': f"新机型: {aftn_val}",
                                        'FPLA_vs_AFTN_Status': "一致" if fpla_aftn_match_bool else "不一致",
                                        'FPLA_vs_FODC_Status': fpla_fodc_status,
                                        'Evidence': f"FPLA机型: {fpla_matched_val}, FODC机型: {safe_strip(latest_fodc.get('CraftType')) if latest_fodc is not None else None}"})
            if pd.notna(aftn_row.get('New_FlightNo')):
                change_found = True;
                aftn_val = safe_strip(aftn_row.get('New_FlightNo'));
                fpla_matched_val, fpla_aftn_match_bool = find_match_in_history(aftn_val, fpla_timeline, 'FlightNo');
                fpla_fodc_status = compare_with_fodc(fpla_matched_val, latest_fodc, 'FlightNo')
                dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                        'AFTN_Event_Type': f"{msg_type} (航班号变更)",
                                        'AFTN_Change_Detail': f"新航班号: {aftn_val}",
                                        'FPLA_vs_AFTN_Status': "一致" if fpla_aftn_match_bool else "不一致",
                                        'FPLA_vs_FODC_Status': fpla_fodc_status,
                                        'Evidence': f"FPLA航班号: {fpla_matched_val}, FODC航班号: {safe_strip(latest_fodc.get('FlightNo')) if latest_fodc is not None else None}"})
            if not change_found and msg_type == 'CHG': dynamic_results.append(
                {'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                 'AFTN_Event_Type': f"{msg_type} (其他变更)", 'AFTN_Change_Detail': '未识别出核心字段变更',
                 'FPLA_vs_AFTN_Status': 'N/A', 'FPLA_vs_FODC_Status': 'N/A', 'Evidence': 'N/A'})
        elif msg_type == 'CPL':
            cpl_fields_to_compare = {'航班号变更': ('New_FlightNo', 'FlightNo', 'FlightNo'),
                                     '机型变更': ('New_CraftType', 'CraftType', 'CraftType'),
                                     '机号变更': ('New_RegNo', 'RegNo', 'RegNo'),
                                     '航站变更': ('New_Destination', 'APTARRAP', 'ArrAirport')}
            for change_type, (aftn_col, fpla_col, fodc_col) in cpl_fields_to_compare.items():
                if pd.notna(aftn_row.get(aftn_col)):
                    aftn_val = safe_strip(aftn_row.get(aftn_col));
                    fpla_matched_val, fpla_aftn_match_bool = find_match_in_history(aftn_val, fpla_timeline, fpla_col);
                    fpla_fodc_status = compare_with_fodc(fpla_matched_val, latest_fodc, fodc_col)
                    dynamic_results.append({'FlightKey': flight_key, 'AFTN_Event_Time': aftn_event_time,
                                            'AFTN_Event_Type': f"CPL ({change_type})",
                                            'AFTN_Change_Detail': f"新数据: {aftn_val}",
                                            'FPLA_vs_AFTN_Status': "一致" if fpla_aftn_match_bool else "不一致",
                                            'FPLA_vs_FODC_Status': fpla_fodc_status,
                                            'Evidence': f"FPLA数据: {fpla_matched_val}, FODC数据: {safe_strip(latest_fodc.get(fodc_col)) if latest_fodc is not None else None}"})
    df = pd.DataFrame(dynamic_results)
    if not df.empty: df.columns = ['航班标识(FlightKey)', 'AFTN事件时间(AFTN_Event_Time)',
                                   'AFTN事件类型(AFTN_Event_Type)', 'AFTN变更明细(AFTN_Change_Detail)',
                                   'FPLA vs AFTN 状态', 'FPLA vs FODC 状态', '数据源佐证(Evidence)']
    return df


def calculate_accuracy(plan_report_df, dynamic_report_df):
    plan_aftn_data = [];
    total_plans = len(plan_report_df);
    fpla_found = plan_report_df['FPLA-机号(FPLA_RegNo)'] != '无FPLA数据';
    matched_fpla_df = plan_report_df[fpla_found]
    plan_aftn_data.append({'分类': '匹配度', '统计项': '总计划航班数 (AFTN FPL)', '数量/比例': total_plans,
                           '备注': '以当天AFTN FPL报文为基准'})
    plan_aftn_data.append({'分类': '匹配度', '统计项': 'FPLA 匹配航班数', '数量/比例': fpla_found.sum(),
                           '备注': '在FPLA数据中能找到对应航班的数量'})
    plan_aftn_data.append({'分类': '匹配度', '统计项': 'FPLA 匹配率',
                           '数量/比例': f"{(fpla_found.sum() / total_plans * 100):.2f}%" if total_plans > 0 else "0.00%",
                           '备注': 'FPLA匹配数 / 总计划航班数'})
    if not matched_fpla_df.empty:
        reg_accurate = (matched_fpla_df['AFTN-机号(FPL_RegNo)'] == matched_fpla_df['FPLA-机号(FPLA_RegNo)']).sum();
        sobt_accurate = (
                matched_fpla_df['AFTN-离港时间(FPL_SOBT_BJT)'] == matched_fpla_df['FPLA-离港时间(FPLA_SOBT)']).sum();
        combined_accurate = ((matched_fpla_df['AFTN-机号(FPL_RegNo)'] == matched_fpla_df['FPLA-机号(FPLA_RegNo)']) & (
                matched_fpla_df['AFTN-离港时间(FPL_SOBT_BJT)'] == matched_fpla_df['FPLA-离港时间(FPLA_SOBT)'])).sum()
        plan_aftn_data.append(
            {'分类': '准确度', '统计项': '(对比基数：FPLA匹配的航班)', '数量/比例': len(matched_fpla_df), '备注': ''});
        plan_aftn_data.append({'分类': '准确度', '统计项': '机号一致数', '数量/比例': reg_accurate, '备注': ''});
        plan_aftn_data.append({'分类': '准确度', '统计项': '时刻一致数', '数量/比例': sobt_accurate, '备注': ''});
        plan_aftn_data.append({'分类': '准确度', '统计项': '综合一致数', '数量/比例': combined_accurate,
                               '备注': '机号和时刻均一致的数量'});
        plan_aftn_data.append({'分类': '准确度', '统计项': '综合准确率',
                               '数量/比例': f"{(combined_accurate / len(matched_fpla_df) * 100):.2f}%",
                               '备注': '综合一致数 / FPLA匹配航班数'})
    plan_aftn_stats_df = pd.DataFrame(plan_aftn_data)
    plan_fodc_data = [];
    matched_both_df = plan_report_df[(plan_report_df['FPLA-机号(FPLA_RegNo)'] != '无FPLA数据') & (
            plan_report_df['FODC-机号(FODC_RegNo)'] != '无FODC数据')]
    plan_fodc_data.append(
        {'分类': '匹配度', '统计项': 'FPLA与FODC均存在的计划航班数', '数量/比例': len(matched_both_df),
         '备注': '作为对比基准'})
    if not matched_both_df.empty:
        reg_accurate = (matched_both_df['FPLA-机号(FPLA_RegNo)'] == matched_both_df['FODC-机号(FODC_RegNo)']).sum();
        sobt_accurate = (
                matched_both_df['FPLA-离港时间(FPLA_SOBT)'] == matched_both_df['FODC-离港时间(FODC_SOBT)']).sum();
        combined_accurate = ((matched_both_df['FPLA-机号(FPLA_RegNo)'] == matched_both_df['FODC-机号(FODC_RegNo)']) & (
                matched_both_df['FPLA-离港时间(FPLA_SOBT)'] == matched_both_df['FODC-离港时间(FODC_SOBT)'])).sum()
        plan_fodc_data.append({'分类': '准确度', '统计项': '机号一致数', '数量/比例': reg_accurate, '备注': ''});
        plan_fodc_data.append({'分类': '准确度', '统计项': '时刻一致数', '数量/比例': sobt_accurate, '备注': ''});
        plan_fodc_data.append({'分类': '准确度', '统计项': '综合一致数', '数量/比例': combined_accurate,
                               '备注': '机号和时刻均一致的数量'});
        plan_fodc_data.append({'分类': '准确度', '统计项': '综合准确率',
                               '数量/比例': f"{(combined_accurate / len(matched_both_df) * 100):.2f}%",
                               '备注': '综合一致数 / FPLA与FODC均匹配数'})
    plan_fodc_stats_df = pd.DataFrame(plan_fodc_data)
    dyn_aftn_stats = {};
    total_events = len(dynamic_report_df);
    matched_df = dynamic_report_df[dynamic_report_df['FPLA vs AFTN 状态'] != '无FPLA数据'];
    accurate_total = (matched_df['FPLA vs AFTN 状态'] == '一致').sum()
    dyn_aftn_stats['总计'] = {'total': total_events, 'matched': len(matched_df), 'accurate': accurate_total}
    for event in ['时刻变更', '机号变更', '航站变更', '机型变更', '航班号变更']:
        event_df = dynamic_report_df[dynamic_report_df['AFTN事件类型(AFTN_Event_Type)'].str.contains(event, na=False)]
        if not event_df.empty:
            matched_event_df = event_df[event_df['FPLA vs AFTN 状态'] != '无FPLA数据'];
            accurate_event = (matched_event_df['FPLA vs AFTN 状态'] == '一致').sum()
            dyn_aftn_stats[event] = {'total': len(event_df), 'matched': len(matched_event_df),
                                     'accurate': accurate_event}
    dyn_aftn_data = []
    for event, data in dyn_aftn_stats.items():
        if data.get('total', 0) > 0:
            dyn_aftn_data.append({'事件类型': event, '统计项': 'AFTN事件数', '数值': data['total']});
            dyn_aftn_data.append({'事件类型': event, '统计项': 'FPLA匹配数', '数值': data['matched']})
            if event == '总计':
                dyn_aftn_data.append({'事件类型': event, '统计项': 'FPLA匹配率',
                                      '数值': f"{(data['matched'] / data['total'] * 100):.2f}%" if data[
                                                                                                       'total'] > 0 else "0.00%"})
                dyn_aftn_data.append({'事件类型': event, '统计项': '综合准确事件数', '数值': data['accurate']})
            if data['matched'] > 0: dyn_aftn_data.append({'事件类型': event, '统计项': '准确率',
                                                          '数值': f"{(data['accurate'] / data['matched'] * 100):.2f}% ({data['accurate']}/{data['matched']})"})
    dyn_aftn_stats_df = pd.DataFrame(dyn_aftn_data)
    dyn_fodc_stats = {};
    fodc_present_df = dynamic_report_df[dynamic_report_df['FPLA vs FODC 状态'] != '无FODC标杆'];
    accurate_fodc_df = fodc_present_df[fodc_present_df['FPLA vs FODC 状态'] == '一致']
    dyn_fodc_stats['总计'] = {'base': len(fodc_present_df), 'accurate': len(accurate_fodc_df)}
    for event in ['时刻变更', '机号变更', '航站变更', '机型变更', '航班号变更']:
        event_df = fodc_present_df[fodc_present_df['AFTN事件类型(AFTN_Event_Type)'].str.contains(event, na=False)]
        if not event_df.empty:
            accurate_event_df = event_df[event_df['FPLA vs FODC 状态'] == '一致']
            dyn_fodc_stats[event] = {'base': len(event_df), 'accurate': len(accurate_event_df)}
    dyn_fodc_data = []
    for event, data in dyn_fodc_stats.items():
        if data.get('base', 0) > 0:
            dyn_fodc_data.append({'事件类型': event, '统计项': 'FODC存在标杆数', '数值': data['base']})
            if event == '总计': dyn_fodc_data.append(
                {'事件类型': event, '统计项': '综合准确事件数', '数值': data['accurate']})
            if data['base'] > 0: dyn_fodc_data.append({'事件类型': event, '统计项': '准确率',
                                                       '数值': f"{(data['accurate'] / data['base'] * 100):.2f}% ({data['accurate']}/{data['base']})"})
    dyn_fodc_stats_df = pd.DataFrame(dyn_fodc_data)
    return plan_aftn_stats_df, plan_fodc_stats_df, dyn_aftn_stats_df, dyn_fodc_stats_df


# </editor-fold>

# ==============================================================================
# --- 4. 主流程执行函数 (修改为接受log_callback) ---
# ==============================================================================
def run_analysis_and_generate_report(aftn_path, fpla_path, fodc_path, output_path, airport_icao, target_date_str,
                                     log_callback):
    """
    主执行函数，协调数据预处理和对比分析的全过程。
    """
    try:
        target_date_obj = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        log_callback(f"错误: 日期格式无效 ({target_date_str})。请使用 YYYY-MM-DD。")
        return

    log_callback(f"===== 开始为日期 {target_date_str} (机场: {airport_icao}) 生成对比报告 =====")

    # --- 步骤 1: 数据预处理 ---
    log_callback("\n--- [阶段 1/3] 开始数据预处理 ---")

    # ... (The rest of the function is the same, but replaces print() with log_callback())
    try:
        log_callback(f"--- 正在读取原始AFTN文件: {os.path.basename(aftn_path)} ---")
        aftn_raw_df = pd.read_csv(aftn_path, header=0, on_bad_lines='skip')
        aftn_df = process_aftn_for_analysis(aftn_raw_df, target_date_obj)
        if aftn_df.empty:
            log_callback(f"警告: 在AFTN文件中未找到日期为 {target_date_str} 的有效AFTN数据。")
        else:
            log_callback(f"√ AFTN数据预处理完成，共 {len(aftn_df)} 条有效记录。")
    except Exception as e:
        log_callback(f"错误: 处理AFTN文件时发生错误: {e}")
        return

    FPLA_COLUMN_MAP = {"全球唯一飞行标识符": "GUFI", "航空器识别标志": "CALLSIGN", "航空器注册号": "REGNUMBER",
                       "计划离港时间": "SOBT", "计划到港时间": "SIBT", "计划起飞机场": "DEPAP",
                       "计划目的地机场": "ARRAP", "机场保障计划离港时间": "APTSOBT", "机场保障计划到港时间": "APTSIBT",
                       "机场保障计划起飞机场": "APTDEPAP", "机场保障计划目的地机场": "APTARRAP",
                       "执飞航空器注册号": "EREGNUMBER", "预执行计划机型": "PSAIRCRAFTTYPE",
                       "预执行计划状态": "PSCHEDULESTATUS", "计划航路": "SROUTE", "消息发送时间": "SENDTIME"}
    try:
        log_callback(f"--- 正在读取原始FPLA文件: {os.path.basename(fpla_path)} ---")
        fpla_raw_df = pd.read_excel(fpla_path)
        fpla_raw_df.rename(columns=lambda c: FPLA_COLUMN_MAP.get(c, c), inplace=True)
        fpla_filtered_df = fpla_raw_df[fpla_raw_df['PSCHEDULESTATUS'] != 'CNL'].copy()
        log_callback(f"FPLA数据过滤: 原始记录数 {len(fpla_raw_df)}, 过滤'CNL'状态后剩余 {len(fpla_filtered_df)} 条。")
        fpla_plan_df, fpla_dynamic_df = process_fpla_for_analysis(fpla_filtered_df, target_date_obj)
        if fpla_plan_df.empty:
            log_callback(f"警告: 在FPLA文件中未找到指定日期的FPLA数据。")
        else:
            log_callback(f"√ FPLA数据预处理完成，共 {len(fpla_plan_df)} 条有效记录。")
    except Exception as e:
        log_callback(f"错误: 处理FPLA文件时发生错误: {e}")
        return

    try:
        log_callback(f"--- 正在读取原始FODC文件: {os.path.basename(fodc_path)} ---")
        fodc_raw_df = pd.read_excel(fodc_path, engine='openpyxl')
        fodc_plan_df, fodc_dynamic_df = process_fodc_for_analysis(fodc_raw_df, target_date_obj)
        if fodc_plan_df.empty and fodc_dynamic_df.empty:
            log_callback("警告: 未找到指定日期的FODC数据。")
        else:
            log_callback(f"√ FODC数据预处理完成，计划 {len(fodc_plan_df)} 条，动态 {len(fodc_dynamic_df)} 条。")
    except Exception as e:
        log_callback(f"错误: 处理FODC文件时发生错误: {e}")
        return

    # --- 步骤 2: 执行对比分析 ---
    log_callback("\n--- [阶段 2/3] 开始执行对比分析 ---")
    for df in [aftn_df, fpla_plan_df, fpla_dynamic_df, fodc_plan_df, fodc_dynamic_df]:
        if 'ReceiveTime' in df.columns: df['ReceiveTime'] = pd.to_datetime(df['ReceiveTime'], errors='coerce')

    plan_report_df = run_plan_comparison(aftn_df, fpla_plan_df, fodc_plan_df, target_date_obj)
    dynamic_report_df = run_dynamic_comparison(aftn_df, fpla_dynamic_df, fodc_dynamic_df, target_date_obj)
    plan_aftn_stats, plan_fodc_stats, dyn_aftn_stats, dyn_fodc_stats = calculate_accuracy(plan_report_df,
                                                                                          dynamic_report_df)
    log_callback("√ 对比分析和准确率统计完成。")

    # --- 步骤 3: 生成最终报告 ---
    log_callback("\n--- [阶段 3/3] 开始生成Excel报告 ---")
    output_filename = os.path.join(output_path, f"{airport_icao}对比结果_{target_date_str}.xlsx")
    try:
        with pd.ExcelWriter(output_filename, engine='xlsxwriter') as writer:
            if not plan_report_df.empty: plan_report_df.to_excel(writer, sheet_name='计划对比详情',
                                                                 index=False); auto_set_column_width(plan_report_df,
                                                                                                     writer,
                                                                                                     '计划对比详情'); log_callback(
                "√ [Sheet 1] 计划对比详情已生成")
            if not dynamic_report_df.empty: dynamic_report_df.to_excel(writer, sheet_name='动态对比详情',
                                                                       index=False); auto_set_column_width(
                dynamic_report_df, writer, '动态对比详情'); log_callback("√ [Sheet 2] 动态对比详情已生成")
            if not plan_aftn_stats.empty: plan_aftn_stats.to_excel(writer, sheet_name='计划-FPLA vs AFTN',
                                                                   index=False); auto_set_column_width(plan_aftn_stats,
                                                                                                       writer,
                                                                                                       '计划-FPLA vs AFTN'); log_callback(
                "√ [Sheet 3] 计划准确率(vs AFTN)统计已生成")
            if not plan_fodc_stats.empty: plan_fodc_stats.to_excel(writer, sheet_name='计划-FPLA vs FODC',
                                                                   index=False); auto_set_column_width(plan_fodc_stats,
                                                                                                       writer,
                                                                                                       '计划-FPLA vs FODC'); log_callback(
                "√ [Sheet 4] 计划准确率(vs FODC)统计已生成")
            if not dyn_aftn_stats.empty: dyn_aftn_stats.to_excel(writer, sheet_name='动态-FPLA vs AFTN',
                                                                 index=False); auto_set_column_width(dyn_aftn_stats,
                                                                                                     writer,
                                                                                                     '动态-FPLA vs AFTN'); log_callback(
                "√ [Sheet 5] 动态准确率(vs AFTN)统计已生成")
            if not dyn_fodc_stats.empty: dyn_fodc_stats.to_excel(writer, sheet_name='动态-FPLA vs FODC',
                                                                 index=False); auto_set_column_width(dyn_fodc_stats,
                                                                                                     writer,
                                                                                                     '动态-FPLA vs FODC'); log_callback(
                "√ [Sheet 6] 动态准确率(vs FODC)统计已生成")

        log_callback(f"\n===== 任务成功完成！ =====")
        log_callback(f"对比分析报告已生成: {output_filename}")
        messagebox.showinfo("成功", f"对比分析报告已成功生成！\n\n文件保存在:\n{output_filename}")

    except Exception as e:
        log_callback(f"\n错误：生成Excel报告时发生错误: {e}")
        messagebox.showerror("报告生成错误", f"生成Excel报告时发生错误:\n{e}\n\n请检查文件是否被其他程序占用。")


# ==============================================================================
# --- 5. GUI交互和程序入口 ---
# ==============================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("飞行数据对比分析工具")
        self.geometry("700x550")

        # --- Variables ---
        self.airport_var = tk.StringVar(value="ZLXY")
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.aftn_path_var = tk.StringVar()
        self.fpla_path_var = tk.StringVar()
        self.fodc_path_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()

        # --- Widgets ---
        main_frame = tk.Frame(self, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Configure grid
        main_frame.columnconfigure(1, weight=1)

        # --- Input Section ---
        tk.Label(main_frame, text="机场ICAO:").grid(row=0, column=0, sticky=tk.W, pady=2)
        tk.Entry(main_frame, textvariable=self.airport_var).grid(row=0, column=1, sticky="ew", columnspan=2)

        tk.Label(main_frame, text="对比日期:").grid(row=1, column=0, sticky=tk.W, pady=2)
        tk.Entry(main_frame, textvariable=self.date_var).grid(row=1, column=1, sticky="ew", columnspan=2)

        self.create_file_input(main_frame, "AFTN (CSV):", 2, self.aftn_path_var, self.browse_aftn)
        self.create_file_input(main_frame, "FPLA (Excel):", 3, self.fpla_path_var, self.browse_fpla)
        self.create_file_input(main_frame, "FODC (Excel):", 4, self.fodc_path_var, self.browse_fodc)
        self.create_dir_input(main_frame, "输出目录:", 5, self.output_dir_var, self.browse_output)

        # --- Action Button ---
        self.run_button = tk.Button(main_frame, text="开始对比", command=self.start_analysis_thread,
                                    font=("", 12, "bold"))
        self.run_button.grid(row=6, column=0, columnspan=3, pady=15, sticky="ew")

        # --- Log Section ---
        log_frame = tk.LabelFrame(main_frame, text="执行日志")
        log_frame.grid(row=7, column=0, columnspan=3, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(7, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky="nsew")

    def create_file_input(self, parent, label_text, row, var, cmd):
        tk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=2)
        entry = tk.Entry(parent, textvariable=var, state='readonly')
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 5))
        tk.Button(parent, text="浏览...", command=cmd).grid(row=row, column=2, sticky="ew")

    def create_dir_input(self, parent, label_text, row, var, cmd):
        tk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=2)
        entry = tk.Entry(parent, textvariable=var, state='readonly')
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 5))
        tk.Button(parent, text="浏览...", command=cmd).grid(row=row, column=2, sticky="ew")

    def browse_file(self, var, title, filetypes):
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if path:
            var.set(path)

    def browse_aftn(self):
        self.browse_file(self.aftn_path_var, "请选择 AFTN 数据文件 (.csv)",
                         [("CSV files", "*.csv"), ("All files", "*.*")])

    def browse_fpla(self):
        self.browse_file(self.fpla_path_var, "请选择 FPLA 详情文件 (.xlsx)",
                         [("Excel files", "*.xlsx"), ("All files", "*.*")])

    def browse_fodc(self):
        self.browse_file(self.fodc_path_var, "请选择 FODC 详情文件 (.xlsx)",
                         [("Excel files", "*.xlsx"), ("All files", "*.*")])

    def browse_output(self):
        path = filedialog.askdirectory(title="请选择报告输出目录")
        if path:
            self.output_dir_var.set(path)

    def log_message(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.update_idletasks()

    def validate_inputs(self):
        # ... (Input validation logic)
        airport = self.airport_var.get().strip().upper()
        if not (airport and len(airport) == 4 and airport.isalpha()):
            messagebox.showerror("输入错误", "请输入一个有效的4字机场ICAO代码。")
            return None

        date_str = self.date_var.get().strip()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("输入错误", "请输入有效的日期，格式为 YYYY-MM-DD。")
            return None

        paths = {
            "AFTN文件": self.aftn_path_var.get(),
            "FPLA文件": self.fpla_path_var.get(),
            "FODC文件": self.fodc_path_var.get(),
            "输出目录": self.output_dir_var.get()
        }
        for name, path in paths.items():
            if not path:
                messagebox.showerror("输入错误", f"请选择{name}。")
                return None

        return airport, date_str, paths["AFTN文件"], paths["FPLA文件"], paths["FODC文件"], paths["输出目录"]

    def start_analysis_thread(self):
        validated_inputs = self.validate_inputs()
        if not validated_inputs:
            return

        self.run_button.config(state=tk.DISABLED, text="正在处理...")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete('1.0', tk.END)
        self.log_text.config(state=tk.DISABLED)

        # Run the analysis in a separate thread to keep the GUI responsive
        analysis_thread = threading.Thread(
            target=self.run_analysis_in_background,
            args=validated_inputs
        )
        analysis_thread.start()

    def run_analysis_in_background(self, airport, date_str, aftn_path, fpla_path, fodc_path, output_dir):
        try:
            run_analysis_and_generate_report(
                aftn_path, fpla_path, fodc_path,
                output_dir, airport, date_str,
                self.log_message
            )
        except Exception:
            error_info = traceback.format_exc()
            self.log_message(f"\n发生严重错误:\n{error_info}")
            messagebox.showerror("严重错误", f"程序运行中发生未知错误，请查看日志详情。")
        finally:
            self.run_button.config(state=tk.NORMAL, text="开始对比")


if __name__ == "__main__":
    app = App()
    app.mainloop()