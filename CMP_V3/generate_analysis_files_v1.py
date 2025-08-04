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
FPLA_XLSX_FILE = os.path.join(RAW_DATA_DIR, 'data_core_gxpt_aloi_fpla_message.xlsx')
PREPROCESSED_DIR = os.path.join(BASE_DIR, 'preprocessed_files')

try:
    target_date_obj_for_filename = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d")
    start_date_str = target_date_obj_for_filename.strftime('%Y%m%d')
    end_date_str = (target_date_obj_for_filename + timedelta(days=1)).strftime('%Y%m%d')
    FODC_XLSX_FILE = os.path.join(RAW_DATA_DIR,
                                  f'FODC-Details-{AIRPORT_ICAO}-{start_date_str}000000-{end_date_str}000000.xlsx')
except ValueError:
    print(f"错误: 日期格式无效 ({TARGET_DATE_STR})。请使用 YYYY-MM-DD。")
    sys.exit(1)


# ==============================================================================
# --- 2. 辅助函数 (保持不变) ---
# ==============================================================================
def generate_flight_key(exec_date, flight_no, dep_icao, arr_icao):
    if not all([exec_date, flight_no, dep_icao, arr_icao]): return "KEY_GENERATION_FAILED"
    flight_no = str(flight_no).strip();
    dep_icao = str(dep_icao).strip();
    arr_icao = str(arr_icao).strip()
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
    pattern = r'-\s*(\d{1,2})\s*/\s*(.*?)(?=\s+-\d{1,2}\s*/|\s*\)$)'
    matches = re.findall(pattern, body + ' ')
    for item_num_str, content_raw in matches:
        content = content_raw.strip().replace('\r\n', ' ').replace('\n', ' ')
        if item_num_str == '7':
            changes['New_FlightNo'] = content.split('/')[0].strip()
        elif item_num_str == '9':
            changes['New_CraftType'] = content.split('/')[0].strip()
        elif item_num_str == '13' and len(content) >= 8:
            changes['New_Departure_Time'] = content[-4:]
        elif item_num_str == '16':
            parts = content.split()
            if parts:
                dest_eet = parts[0]
                changes['New_Destination'] = dest_eet[:-4] if len(dest_eet) >= 8 else dest_eet
                if len(parts) > 1: changes['New_Alternate_1'] = parts[1]
                if len(parts) > 2: changes['New_Alternate_2'] = parts[2]
        elif item_num_str == '18':
            if re.search(r'REG/(\S+)', content): changes['New_RegNo'] = re.search(r'REG/(\S+)', content).group(1)
    return changes


# ==============================================================================
# --- 3. 核心处理函数 ---
# ==============================================================================
def process_aftn_for_analysis(df, target_date):
    # 此函数保持不变
    processed_records = []
    for index, row in df.iterrows():
        try:
            data = json.loads(row.iloc[1]);
            tele_body = data.get('teleBody', '');
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
    # 此函数保持不变
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
    """【已更新】预处理FODC数据，强制生成FlightKey以保证一致性。"""
    processed_records = []
    df.columns = [str(col).strip().upper() for col in df.columns]

    for index, row in df.iterrows():
        try:
            sobt_str = str(row.get('计划离港时间')).split('.')[0]
            if pd.isna(sobt_str) or len(sobt_str) < 12: continue

            flight_date = datetime.strptime(sobt_str[:8], "%Y%m%d").date()
            if flight_date != target_date: continue

            # 【核心修正】忽略FODC原有的“飞行匹配符”，强制使用统一函数生成FlightKey
            flight_key = generate_flight_key(
                flight_date,
                row.get('航空器识别标志'),
                row.get('计划起飞机场'),
                row.get('计划降落机场')
            )

            record = {
                'FlightKey': flight_key,
                'ReceiveTime': row.get('消息发送时间'),
                'FlightNo': row.get('航空器识别标志'),
                'RegNo': row.get('航空器注册号'),
                'DepAirport': row.get('计划起飞机场'),
                'ArrAirport': row.get('计划降落机场'),
                'SOBT': sobt_str,
                'CraftType': row.get('航空器机型'),
                'FODC_ATOT': str(row.get('实际起飞时间')).split('.')[0]
            }
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
        aftn_raw_df = pd.read_csv(AFTN_CSV_FILE, header=None, on_bad_lines='skip')
        aftn_df = process_aftn_for_analysis(aftn_raw_df, target_date_obj)
        if not aftn_df.empty:
            aftn_df.to_csv(os.path.join(PREPROCESSED_DIR, f'analysis_aftn_data_{TARGET_DATE_STR}.csv'), index=False,
                           encoding='utf-8-sig')
            print(f"√ AFTN分析文件已生成")
    except FileNotFoundError:
        print(f"错误: 原始AFTN文件 '{AFTN_CSV_FILE}' 未找到。")

    try:
        print(f"--- 正在读取原始FPLA文件: {FPLA_XLSX_FILE} ---")
        fpla_raw_df = pd.read_excel(FPLA_XLSX_FILE)
        fpla_df = process_fpla_for_analysis(fpla_raw_df, target_date_obj)
        if not fpla_df.empty:
            fpla_df.to_csv(os.path.join(PREPROCESSED_DIR, f'analysis_fpla_data_{TARGET_DATE_STR}.csv'), index=False,
                           encoding='utf-8-sig')
            print(f"√ FPLA分析文件已生成")
    except FileNotFoundError:
        print(f"错误: 原始FPLA文件 '{FPLA_XLSX_FILE}' 未找到。")

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