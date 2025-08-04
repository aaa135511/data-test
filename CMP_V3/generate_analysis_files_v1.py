import pandas as pd
import json
import re
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# ==============================================================================
# --- 1. 配置加载 (保持不变) ---
# ==============================================================================
load_dotenv()
TARGET_DATE_STR = os.getenv("TARGET_DATE")
AIRPORT_ICAO = os.getenv("AIRPORT")

if not TARGET_DATE_STR or not AIRPORT_ICAO:
    print("错误: 请确保 .env 文件中已设置 TARGET_DATE 和 AIRPORT。")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DATA_DIR = os.path.join(BASE_DIR, 'raw_data')
AFTN_CSV_FILE = os.path.join(RAW_DATA_DIR, 'sqlResult.csv')
PREPROCESSED_DIR = os.path.join(BASE_DIR, 'preprocessed_files')

try:
    target_date_obj_for_filename = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d")
    start_date_str = target_date_obj_for_filename.strftime('%Y%m%d')
    end_date_str = (target_date_obj_for_filename + timedelta(days=1)).strftime('%Y%m%d')

    FPLA_XLSX_FILE = os.path.join(RAW_DATA_DIR,
                                  f'FPLA-Details-{AIRPORT_ICAO}-{start_date_str}000000-{end_date_str}000000.xlsx')
    FODC_XLSX_FILE = os.path.join(RAW_DATA_DIR,
                                  f'FODC-Details-{AIRPORT_ICAO}-{start_date_str}000000-{end_date_str}000000.xlsx')
except ValueError:
    print(f"错误: 日期格式无效 ({TARGET_DATE_STR})。请使用 YYYY-MM-DD。")
    sys.exit(1)


# ==============================================================================
# --- 2. 辅助函数 (保持不变) ---
# ==============================================================================
def generate_flight_key(exec_date, flight_no, dep_icao, arr_icao):
    if not all([exec_date, flight_no, dep_icao, arr_icao]):
        return "KEY_GENERATION_FAILED"
    flight_no = str(flight_no).strip();
    dep_icao = str(dep_icao).strip();
    arr_icao = str(arr_icao).strip()
    if isinstance(exec_date, datetime):
        exec_date = exec_date.date()
    return f"{exec_date.strftime('%Y-%m-%d')}_{flight_no}_{dep_icao}_{arr_icao}"


def get_flight_date_from_aftn(data, tele_body, receive_time):
    dof_match = re.search(r'DOF/(\d{6})', tele_body)
    if dof_match:
        try:
            return datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date()
        except:
            pass
    if isinstance(receive_time, datetime):
        return receive_time.date()
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


# ==============================================================================
# --- 3. 核心处理函数 (process_aftn_for_analysis 已最终修正) ---
# ==============================================================================
def process_aftn_for_analysis(df, target_date):
    """【最终修正版】对 CPL 报文采用“完全替换”策略。"""
    processed_records = []
    for index, row in df.iterrows():
        try:
            data = json.loads(row.iloc[1])
            tele_body = row.iloc[3]
            receive_time = pd.to_datetime(row.iloc[4], errors='coerce')

            msg_type = tele_body[1:4].strip()
            if msg_type in ['DEP', 'ARR']: continue
            if pd.isna(receive_time): continue

            flight_date = get_flight_date_from_aftn(data, tele_body, receive_time)
            if not flight_date or flight_date != target_date: continue

            # flight_no_match = re.search(r'-\s*([A-Z0-9-]{3,10}?)\s*-', tele_body)
            # full_flight_no = flight_no_match.group(
            #     1).strip() if flight_no_match else f"{data.get('airlineIcaoCode', '')}{str(data.get('flightNo', '')).lstrip('0')}"

            json_flight_no = f"{data.get('airlineIcaoCode', '')}{str(data.get('flightNo', '')).lstrip('0')}"

            if json_flight_no and data.get('airlineIcaoCode') and data.get('flightNo'):
                full_flight_no = json_flight_no
            else:
                # 仅在Json信息不全时，才回退到正则提取
                flight_no_match = re.search(r'-\s*([A-Z0-9-]{3,10}?)\s*-', tele_body)
                full_flight_no = flight_no_match.group(1).strip() if flight_no_match else json_flight_no

            dep_icao = data.get('depAirportIcaoCode')
            arr_icao = data.get('arrAirportIcaoCode')

            # --- 最终修正逻辑 ---
            if msg_type == 'CPL':
                # 从报文体中解析基础信息，以备Json中缺失
                body_dep_match = re.search(r'-\s*([A-Z]{4})[A-Z\s]*/\d{4}', tele_body) or re.search(
                    r'-\s*([A-Z]{4})\d{4}', tele_body)
                if not dep_icao and body_dep_match:
                    dep_icao = body_dep_match.group(1)

                body_arr_match = re.search(r'-([A-Z]{4})\s*-PBN', tele_body)  # 目的地机场通常在航路之后、其他信息之前
                if not arr_icao and body_arr_match:
                    arr_icao = body_arr_match.group(1)

            record = {'ReceiveTime': receive_time, 'MessageType': msg_type, 'FlightNo': full_flight_no,
                      'RegNo': data.get('regNo'), 'DepAirport': dep_icao, 'ArrAirport': arr_icao,
                      'CraftType': data.get('aerocraftTypeIcaoCode'), 'RawMessage': tele_body}

            # --- 策略调整 ---
            if msg_type == 'CHG':
                change_details = parse_core_business_info(tele_body)
                record.update(change_details)
            elif msg_type == 'DLA':
                dla_match = re.search(r'-\s*\w+\s*-\s*\w{4}(\d{4})', tele_body)
                if dla_match: record['New_Departure_Time'] = dla_match.group(1)
            elif msg_type == 'CPL':
                # 对于CPL，将基础信息视为“新”信息，用于全面对比
                cpl_changes = {}
                # 从报文中提取机型
                craft_match = re.search(r'-\s*([A-Z0-9]{2,4})/[LMHJ]', tele_body)
                if craft_match: cpl_changes['New_CraftType'] = craft_match.group(1)
                # 从报文中提取机号
                reg_match = re.search(r'REG/(\S+)', tele_body)
                if reg_match: cpl_changes['New_RegNo'] = reg_match.group(1).strip(')')
                # 将航班号、起降站也视为变更项
                cpl_changes['New_FlightNo'] = full_flight_no
                cpl_changes['New_Destination'] = arr_icao
                record.update(cpl_changes)

            key_flight_no = record.get('New_FlightNo', full_flight_no)
            key_dep_airport = record.get('DepAirport')
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
            record = {
                'FlightKey': generate_flight_key(flight_date, row.get('CALLSIGN'), row.get('DEPAP'), row.get('ARRAP')),
                'ReceiveTime': row.get('SENDTIME'), 'FPLA_Status': row.get('PSCHEDULESTATUS'),
                'FlightNo': row.get('CALLSIGN'), 'RegNo': row.get('EREGNUMBER') or row.get('REGNUMBER'),
                'DepAirport': row.get('DEPAP'), 'ArrAirport': row.get('ARRAP'), 'SOBT': row.get('SOBT'),
                'SIBT': row.get('SIBT'), 'APTSOBT': row.get('APTSOBT'), 'APTSIBT': row.get('APTSIBT'),
                'Route': row.get('SROUTE'), 'MissionType': row.get('PMISSIONTYPE'),
                'MissionProperty': row.get('PMISSIONPROPERTY'), 'CraftType': row.get('PSAIRCRAFTTYPE')}
            processed_records.append(record)
        except Exception:
            continue
    return pd.DataFrame(processed_records)


def process_fodc_for_analysis(df, target_date):
    processed_records = []
    df.columns = [str(col).strip() for col in df.columns]
    for index, row in df.iterrows():
        try:
            sobt_str = str(row.get('计划离港时间')).split('.')[0]
            if pd.isna(sobt_str) or len(sobt_str) < 12: continue
            flight_date = datetime.strptime(sobt_str[:8], "%Y%m%d").date()
            if flight_date != target_date: continue
            flight_key = generate_flight_key(flight_date, row.get('航空器识别标志'), row.get('计划起飞机场'),
                                             row.get('计划降落机场'))
            record = {'FlightKey': flight_key, 'ReceiveTime': row.get('消息发送时间'),
                      'FlightNo': row.get('航空器识别标志'), 'RegNo': row.get('航空器注册号'),
                      'DepAirport': row.get('计划起飞机场'), 'ArrAirport': row.get('计划降落机场'), 'SOBT': sobt_str,
                      'CraftType': row.get('航空器机型'), 'FODC_ATOT': str(row.get('实际起飞时间')).split('.')[0]}
            processed_records.append(record)
        except Exception:
            continue
    return pd.DataFrame(processed_records)


# ==============================================================================
# --- 4. 主程序入口 (保持不变) ---
# ==============================================================================
def main():
    try:
        target_date_obj = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        print(f"错误: 日期格式无效 ({TARGET_DATE_STR})。")
        return

    print(f"\n===== 开始为日期 {TARGET_DATE_STR} 生成分析文件 =====")
    os.makedirs(PREPROCESSED_DIR, exist_ok=True)

    try:
        print(f"--- 正在读取原始AFTN文件: {AFTN_CSV_FILE} ---")
        aftn_raw_df = pd.read_csv(AFTN_CSV_FILE, header=0, on_bad_lines='skip')
        aftn_df = process_aftn_for_analysis(aftn_raw_df, target_date_obj)
        if not aftn_df.empty:
            AFTN_ANALYSIS_COLS = ['FlightKey', 'ReceiveTime', 'MessageType', 'FlightNo', 'New_FlightNo', 'CraftType',
                                  'New_CraftType', 'RegNo', 'New_RegNo', 'DepAirport', 'ArrAirport', 'New_Destination',
                                  'New_Alternate_1', 'New_Alternate_2', 'New_Departure_Time', 'New_Route',
                                  'New_Mission_STS', 'RawMessage']
            aftn_final = aftn_df.reindex(columns=AFTN_ANALYSIS_COLS)
            aftn_final.to_csv(os.path.join(PREPROCESSED_DIR, f'analysis_aftn_data_{TARGET_DATE_STR}.csv'), index=False,
                              encoding='utf-8-sig')
            print(f"√ AFTN分析文件已生成")
        else:
            print(f"警告: 在文件 {AFTN_CSV_FILE} 中未找到日期为 {TARGET_DATE_STR} 的有效AFTN数据。")
    except FileNotFoundError:
        print(f"错误: 原始AFTN文件 '{AFTN_CSV_FILE}' 未找到。")
    except Exception as e:
        print(f"处理AFTN文件时发生未知错误: {e}")

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
                       "逻辑校验结果": "LOGICCHECKRESULT", "及时性校验结果": "ISTIMELY", "校验结论": "ALLCHECKRESULT"}
    try:
        print(f"--- 正在读取原始FPLA文件: {FPLA_XLSX_FILE} ---")
        fpla_raw_df = pd.read_excel(FPLA_XLSX_FILE)
        fpla_raw_df.rename(columns=FPLA_COLUMN_MAP, inplace=True)
        fpla_df = process_fpla_for_analysis(fpla_raw_df, target_date_obj)
        if not fpla_df.empty:
            fpla_df.to_csv(os.path.join(PREPROCESSED_DIR, f'analysis_fpla_data_{TARGET_DATE_STR}.csv'), index=False,
                           encoding='utf-8-sig')
            print(f"√ FPLA分析文件已生成")
        else:
            print(f"警告: 在文件 {FPLA_XLSX_FILE} 中未找到指定日期的数据。")
    except FileNotFoundError:
        print(f"错误: 原始FPLA文件 '{FPLA_XLSX_FILE}' 未找到。")
    except Exception as e:
        print(f"处理FPLA文件时发生错误: {e}")
    try:
        print(f"--- 正在读取原始FODC文件: {FODC_XLSX_FILE} ---")
        fodc_raw_df = pd.read_excel(FODC_XLSX_FILE, engine='openpyxl')
        fodc_df = process_fodc_for_analysis(fodc_raw_df, target_date_obj)
        if not fodc_df.empty:
            output_path = os.path.join(PREPROCESSED_DIR, f'analysis_fodc_data_{TARGET_DATE_STR}.csv')
            fodc_df.to_csv(output_path, index=False, encoding='utf-8-sig')
            print(f"√ FODC分析文件已生成: {output_path}")
        else:
            print("警告: 未找到指定日期的FODC数据。")
    except FileNotFoundError:
        print(f"错误: 原始FODC文件 '{FODC_XLSX_FILE}' 未找到。")
    except Exception as e:
        print(f"处理FODC文件时发生错误: {e}")

    print(f"\n===== 日期 {TARGET_DATE_STR} 的预处理任务已完成 =====")


if __name__ == "__main__":
    main()