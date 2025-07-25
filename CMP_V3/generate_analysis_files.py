import pandas as pd
import json
import re
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# ==============================================================================
# --- 1. 配置加载 ---
# ==============================================================================
load_dotenv()
TARGET_DATE_STR = os.getenv("TARGET_DATE")
if not TARGET_DATE_STR:
    print("错误: 未在 .env 文件中找到 TARGET_DATE 设置。")
    print("请在项目根目录创建 .env 文件，并添加一行: TARGET_DATE=\"YYYY-MM-DD\"")
    sys.exit(1)

# 文件路径与常量定义
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DATA_DIR = os.path.join(BASE_DIR, 'raw_data')
AFTN_CSV_FILE = os.path.join(RAW_DATA_DIR, 'sqlResult.csv')
FPLA_XLSX_FILE = os.path.join(RAW_DATA_DIR, 'data_core_gxpt_aloi_fpla_message.xlsx')
PREPROCESSED_DIR = os.path.join(BASE_DIR, 'preprocessed_files')


# ==============================================================================
# --- 2. 辅助函数 ---
# ==============================================================================
def generate_flight_key(exec_date, flight_no, dep_icao, arr_icao):
    """根据核心航班信息生成唯一的、可用于关联的键。"""
    if not all([exec_date, flight_no, dep_icao, arr_icao]):
        return "KEY_GENERATION_FAILED"
    flight_no = str(flight_no).strip()
    dep_icao = str(dep_icao).strip()
    arr_icao = str(arr_icao).strip()
    if isinstance(exec_date, datetime):
        exec_date = exec_date.date()
    return f"{exec_date.strftime('%Y-%m-%d')}_{flight_no}_{dep_icao}_{arr_icao}"


def get_flight_date_from_aftn(data, tele_body, receive_time):
    """从AFTN消息中稳健地提取航班执行日期。"""
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
    """【最终版】解析CHG/CPL所有核心编组"""
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
# --- 3. 核心处理函数 ---
# ==============================================================================
def process_aftn_for_analysis(df, target_date):
    """预处理AFTN数据"""
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

            dep_icao = data.get('depAirportIcaoCode');
            arr_icao = data.get('arrAirportIcaoCode')

            record = {
                'ReceiveTime': receive_time, 'MessageType': msg_type, 'FlightNo': full_flight_no,
                'RegNo': data.get('regNo'), 'DepAirport': dep_icao, 'ArrAirport': arr_icao,
                'CraftType': data.get('aerocraftTypeIcaoCode'), 'RawMessage': tele_body
            }

            change_details = {}
            if msg_type in ['CHG', 'CPL']:
                change_details = parse_core_business_info(tele_body)
            elif msg_type == 'DLA':
                dla_match = re.search(r'-\s*\w+\s*-\s*\w{4}(\d{4})', tele_body)
                if dla_match:
                    change_details['New_Departure_Time'] = dla_match.group(1)

            record.update(change_details)
            record['FlightKey'] = generate_flight_key(flight_date, record.get('New_FlightNo', full_flight_no), dep_icao,
                                                      arr_icao)
            processed_records.append(record)
        except Exception:
            continue
    return pd.DataFrame(processed_records)


def process_fpla_for_analysis(df, target_date):
    """预处理FPLA数据"""
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
                'DepAirport': row.get('DEPAP'), 'ArrAirport': row.get('ARRAP'),
                'SOBT': row.get('SOBT'), 'SIBT': row.get('SIBT'), 'Route': row.get('SROUTE'),
                'MissionType': row.get('PMISSIONTYPE'), 'MissionProperty': row.get('PMISSIONPROPERTY'),
                'CraftType': row.get('PSAIRCRAFTTYPE')
            }
            processed_records.append(record)
        except Exception:
            continue
    return pd.DataFrame(processed_records)


# ==============================================================================
# --- 4. 主程序入口 ---
# ==============================================================================
def main():
    try:
        target_date_obj = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        print(f"错误: .env 文件中的日期格式无效 ({TARGET_DATE_STR})。请使用 YYYY-MM-DD 格式。")
        return

    print(f"\n===== 开始为日期 {TARGET_DATE_STR} 生成分析文件 =====")
    os.makedirs(PREPROCESSED_DIR, exist_ok=True)

    AFTN_ANALYSIS_COLS = ['FlightKey', 'ReceiveTime', 'MessageType', 'FlightNo', 'New_FlightNo', 'CraftType',
                          'New_CraftType', 'RegNo', 'New_RegNo', 'DepAirport', 'ArrAirport', 'New_Destination',
                          'New_Alternate_1', 'New_Alternate_2', 'New_Departure_Time', 'New_Route', 'New_Mission_STS',
                          'RawMessage']
    FPLA_ANALYSIS_COLS = ['FlightKey', 'ReceiveTime', 'FPLA_Status', 'FlightNo', 'CraftType', 'RegNo', 'DepAirport',
                          'ArrAirport', 'SOBT', 'SIBT', 'Route', 'MissionType', 'MissionProperty']

    try:
        print(f"--- 正在读取原始AFTN文件: {AFTN_CSV_FILE} ---")
        aftn_raw_df = pd.read_csv(AFTN_CSV_FILE, header=None, on_bad_lines='skip')
        aftn_df = process_aftn_for_analysis(aftn_raw_df, target_date_obj)
        if not aftn_df.empty:
            output_path = os.path.join(PREPROCESSED_DIR, f'analysis_aftn_data_{TARGET_DATE_STR}.csv')
            aftn_final = aftn_df.reindex(columns=AFTN_ANALYSIS_COLS)
            aftn_final.to_csv(output_path, index=False, encoding='utf-8-sig')
            print(f"√ AFTN分析文件已生成: {output_path}")
        else:
            print("警告: 未找到指定日期的AFTN数据。")
    except FileNotFoundError:
        print(f"错误: 原始AFTN文件 '{AFTN_CSV_FILE}' 未找到。")

    try:
        print(f"--- 正在读取原始FPLA文件: {FPLA_XLSX_FILE} ---")
        fpla_raw_df = pd.read_excel(FPLA_XLSX_FILE)
        fpla_raw_df.columns = [str(col).strip().upper() for col in fpla_raw_df.columns]
        fpla_df = process_fpla_for_analysis(fpla_raw_df, target_date_obj)
        if not fpla_df.empty:
            output_path = os.path.join(PREPROCESSED_DIR, f'analysis_fpla_data_{TARGET_DATE_STR}.csv')
            fpla_final = fpla_df.reindex(columns=FPLA_ANALYSIS_COLS)
            fpla_final.to_csv(output_path, index=False, encoding='utf-8-sig')
            print(f"√ FPLA分析文件已生成: {output_path}")
        else:
            print("警告: 未找到指定日期的FPLA数据。")
    except FileNotFoundError:
        print(f"错误: 原始FPLA文件 '{FPLA_XLSX_FILE}' 未找到。")

    print(f"\n===== 日期 {TARGET_DATE_STR} 的预处理任务已完成 =====")


if __name__ == "__main__":
    main()