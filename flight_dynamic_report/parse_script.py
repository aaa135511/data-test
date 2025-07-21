import pandas as pd
import json
import re
from datetime import datetime

# --- 配置区 ---
TARGET_DATE_STR = "2025-07-08"
TARGET_DATE = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d").date()

AFTN_CSV_FILE = 'sqlResult_1.csv'
FPLA_XLSX_FILE = 'fpla_message-20250708.xlsx'

PROCESSED_AFTN_OUTPUT_FILE = f'processed_aftn_dynamic_{TARGET_DATE_STR}.csv'
PROCESSED_FPLA_OUTPUT_FILE = f'processed_fpla_plan_{TARGET_DATE_STR}.csv'  # 文件名改回标准


# --- 核心功能函数 ---

def generate_flight_key(exec_date, flight_no, dep_icao, arr_icao):
    """生成包含降落机场的统一航班标识键"""
    if not all([exec_date, flight_no, dep_icao, arr_icao]):
        return "KEY_GENERATION_FAILED"
    if isinstance(exec_date, datetime):
        exec_date = exec_date.date()
    return f"{exec_date.strftime('%Y-%m-%d')}_{flight_no}_{dep_icao}_{arr_icao}"


def get_flight_date_from_aftn(data):
    """获取AFTN报文的航班执行日期"""
    tele_body = data.get('teleBody', '')
    dof_match = re.search(r'DOF/(\d{6})', tele_body)
    if dof_match:
        try:
            return datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date()
        except (ValueError, IndexError):
            pass
    etot_str = data.get('etot')
    if etot_str:
        try:
            return datetime.strptime(etot_str.split(" ")[0], "%Y-%m-%d").date()
        except (ValueError, IndexError):
            pass
    dof_str = data.get('dofExecDate')
    if dof_str:
        try:
            return datetime.strptime(dof_str.split(" ")[0], "%Y-%m-%d").date()
        except (ValueError, IndexError):
            pass
    aldt_str = data.get('aldt')
    if aldt_str:
        try:
            return datetime.strptime(aldt_str.split(" ")[0], "%Y-%m-%d").date()
        except (ValueError, IndexError):
            pass
    return None


def process_aftn_dynamic_data(input_file):
    """处理飞行动态电报CSV文件"""
    print(f"开始处理AFTN动态电报文件: {input_file}...")
    try:
        df = pd.read_csv(input_file, header=None)
        json_col_index = 1
        db_time_col_index = -1
    except FileNotFoundError:
        print(f"错误: 文件 '{input_file}' 未找到。")
        return pd.DataFrame()

    processed_records = []
    for index, row in df.iterrows():
        try:
            json_str = row.iloc[json_col_index]
            data = json.loads(json_str)
            flight_date = get_flight_date_from_aftn(data)

            if not flight_date or flight_date != TARGET_DATE:
                continue

            receive_time = row.iloc[db_time_col_index]
            flight_no = f"{data.get('airlineIcaoCode', '')}{data.get('flightNo', '')}"
            dep_icao = data.get('depAirportIcaoCode')
            arr_icao = data.get('arrAirportIcaoCode')
            actual_arr_icao = data.get('actlArrAirportIcaoCode') if data.get('abnormalStatus') in ['ALTERNATE',
                                                                                                   'RETURN'] else arr_icao

            record = {
                'FlightKey': generate_flight_key(flight_date, flight_no, dep_icao, arr_icao),
                'MessageType': data.get('teleBody', '')[1:4].strip(),
                'FlightNo': flight_no,
                'DepAirport': dep_icao,
                'ArrAirport': arr_icao,
                'ActualArrAirport': actual_arr_icao,
                'RegNo': data.get('regNo') or data.get('newRegNo'),
                'CraftType': data.get('aerocraftTypeIcaoCode'),
                'ReceiveTime': receive_time,
                'SOBT_EOBT_ATOT': data.get('etot') or data.get('atot'),
                'SIBT_EIBT_AIBT': receive_time if data.get('teleBody', '').startswith('(ARR') else None,
                'RawMessage': data.get('teleBody')
            }
            processed_records.append(record)
        except (json.JSONDecodeError, IndexError, KeyError, TypeError) as e:
            print(f"警告: AFTN文件第 {index + 2} 行处理失败，原因: {e}。 跳过此行。")
            continue

    print(f"AFTN数据处理完成，共解析出 {len(processed_records)} 条 {TARGET_DATE_STR} 的记录。")
    return pd.DataFrame(processed_records)


def process_fpla_data_streamlined(input_file):
    """
    【全新重构】处理FPLA Excel文件，只保留核心字段，并统一时间戳名称
    """
    print(f"开始处理FPLA计划文件 (精简建模模式): {input_file}...")
    try:
        df = pd.read_excel(input_file)
        df.columns = [str(col).strip().upper() for col in df.columns]
    except FileNotFoundError:
        print(f"错误: 文件 '{input_file}' 未找到。")
        return pd.DataFrame()

    processed_records = []
    # 遍历所有行，不过滤
    for index, row in df.iterrows():
        try:
            # --- 生成Key所需的信息 ---
            sobt_raw = row.get('SOBT')
            sobt_str = str(int(sobt_raw)) if pd.notna(sobt_raw) else ""

            flight_date = None
            if len(sobt_str) >= 8:
                flight_date = datetime.strptime(sobt_str[:8], "%Y%m%d").date()

            flight_no = row.get('CALLSIGN')
            dep_icao = row.get('DEPAP')
            arr_icao = row.get('ARRAP')

            # --- 【关键修正】: 精简建模 ---
            record = {
                'FlightKey': generate_flight_key(flight_date, flight_no, dep_icao, arr_icao),
                # MessageType 对应 ScheduleStatus
                'MessageType': row.get('PSCHEDULESTATUS'),
                'FlightNo': flight_no,
                'DepAirport': dep_icao,
                'ArrAirport': arr_icao,
                # FPLA中没有ActualArrAirport的概念，留空以对齐列
                'ActualArrAirport': None,
                'RegNo': row.get('EREGNUMBER') or row.get('REGNUMBER'),
                'CraftType': row.get('PSAIRCRAFTTYPE'),
                # 将 sendTime (假设列名为SENDTIME) 放入 ReceiveTime 列
                'ReceiveTime': row.get('SENDTIME'),
                # SOBT_EOBT_ATOT 对应 FPLA 的 SOBT
                'SOBT_EOBT_ATOT': datetime.strptime(sobt_str, "%Y%m%d%H%M") if len(sobt_str) == 12 else None,
                # SIBT_EIBT_AIBT 对应 FPLA 的 SIBT
                'SIBT_EIBT_AIBT': datetime.strptime(str(int(row.get('SIBT'))), "%Y%m%d%H%M") if pd.notna(
                    row.get('SIBT')) and len(str(int(row.get('SIBT')))) == 12 else None,
                # RawMessage 在 FPLA 中不存在，留空
                'RawMessage': None
            }
            processed_records.append(record)

        except (KeyError, ValueError, TypeError) as e:
            print(f"警告: FPLA文件第 {index + 2} 行处理失败，原因: {e}。 跳过此行。")
            continue

    print(f"FPLA数据处理完成，共处理 {len(processed_records)} 条记录。")
    return pd.DataFrame(processed_records)


# --- 主程序入口 ---
if __name__ == "__main__":
    aftn_processed_df = process_aftn_dynamic_data(AFTN_CSV_FILE)
    if not aftn_processed_df.empty:
        aftn_processed_df.to_csv(PROCESSED_AFTN_OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"处理后的AFTN数据已保存至: {PROCESSED_AFTN_OUTPUT_FILE}")

    print("\n" + "=" * 50 + "\n")

    # 使用新的精简函数处理FPLA数据
    fpla_processed_df_streamlined = process_fpla_data_streamlined(FPLA_XLSX_FILE)
    if not fpla_processed_df_streamlined.empty:
        fpla_processed_df_streamlined.to_csv(PROCESSED_FPLA_OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"处理后的FPLA数据已保存至: {PROCESSED_FPLA_OUTPUT_FILE}")