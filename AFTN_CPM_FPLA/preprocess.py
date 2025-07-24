import pandas as pd
import json
import re
from datetime import datetime

# ==============================================================================
# --- 1. 配置区 ---
# ==============================================================================
# 请将此日期修改为您需要处理的目标日期
TARGET_DATE_STR = "2025-07-08"

# 输入文件名 (请确保这些文件与脚本在同一目录下，或提供完整路径)
AFTN_CSV_FILE = 'sqlResult_1.csv'
FPLA_XLSX_FILE = f'fpla_message-{TARGET_DATE_STR}.xlsx'

# 输出文件名 (脚本会自动生成带有日期的文件名)
PROCESSED_AFTN_OUTPUT_FILE = f'processed_aftn_dynamic_final_{TARGET_DATE_STR}.csv'
PROCESSED_FPLA_OUTPUT_FILE = f'processed_fpla_plan_final_{TARGET_DATE_STR}.csv'


# ==============================================================================
# --- 2. 辅助函数 ---
# ==============================================================================

def generate_flight_key(exec_date, flight_no, dep_icao, arr_icao):
    """根据核心航班信息生成唯一的、可用于关联的键。"""
    if not all([exec_date, flight_no, dep_icao, arr_icao]):
        return "KEY_GENERATION_FAILED"
    if isinstance(exec_date, datetime):
        exec_date = exec_date.date()
    return f"{exec_date.strftime('%Y-%m-%d')}_{flight_no}_{dep_icao}_{arr_icao}"


def get_flight_date_from_aftn(data, tele_body):
    """从AFTN消息中稳健地提取航班执行日期。"""
    # 优先从编组18的DOF字段获取，最准确
    dof_match = re.search(r'DOF/(\d{6})', tele_body)
    if dof_match:
        try:
            return datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date()
        except (ValueError, IndexError):
            pass
    # 其次尝试从解析后的JSON字段获取
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
    return None


def parse_change_items_complete(body):
    """
    【AFTN CHG报文解析器】: 全面、深度解析CHG报文的核心变更项。
    能够解析编组 7, 8, 9, 13, 15, 16, 18 的变更信息，并将备降场拆分。
    """
    changes = {}
    pattern = r'-\s*(\d{1,2})\s*/\s*(.*?)(?=\s*-\s*\d{1,2}\s*/|\)$)'
    matches = re.findall(pattern, body)

    for item_num_str, content_raw in matches:
        content = content_raw.strip().replace('\r\n', ' ').replace('\n', ' ')

        if item_num_str == '7':
            parts = content.split('/')
            changes['New_Callsign'] = parts[0]
            if len(parts) > 1: changes['New_SSR_Info'] = '/'.join(parts[1:])

        elif item_num_str == '8':
            if len(content) > 0: changes['New_FlightRules'] = content[0]
            if len(content) > 1: changes['New_FlightType'] = content[1]

        elif item_num_str == '9':
            parts = content.split('/')
            changes['New_CraftType'] = parts[0]
            if len(parts) > 1: changes['New_WakeCategory'] = parts[1]

        elif item_num_str == '13':
            if len(content) == 8:
                changes['New_Departure_Airport'] = content[:4]
                changes['New_Departure_Time'] = content[4:]

        elif item_num_str == '15':
            changes['New_Route_Info'] = content

        elif item_num_str == '16':
            parts = content.split()
            if parts:
                dest_eet = parts[0]
                if len(dest_eet) >= 8:
                    changes['New_Destination'] = dest_eet[:-4]
                    changes['New_EET'] = dest_eet[-4:]
                else:
                    changes['New_Destination'] = dest_eet
                if len(parts) > 1: changes['Alternate_Airport_1'] = parts[1]
                if len(parts) > 2: changes['Alternate_Airport_2'] = parts[2]

        elif item_num_str == '18':
            changes['Item18_Content'] = content
            reg_match = re.search(r'REG/(\S+)', content)
            if reg_match: changes['New_RegNo'] = reg_match.group(1)
            dof_match = re.search(r'DOF/(\d{6})', content)
            if dof_match: changes['New_DOF'] = dof_match.group(1)
            typ_match = re.search(r'TYP/(\S+)', content)
            if typ_match: changes['New_Aircraft_Type_Spec'] = typ_match.group(1)
            opr_match = re.search(r'OPR/(\S+)', content)
            if opr_match: changes['New_Operator'] = opr_match.group(1)
            sts_match = re.search(r'STS/(\S+)', content)
            if sts_match: changes['New_Mission_STS'] = sts_match.group(1)

    return changes


# ==============================================================================
# --- 3. 核心处理函数 ---
# ==============================================================================

def process_aftn_dynamic_data(input_file, target_date):
    """
    【最终修正版 - 精准航班号解析】
    从原始报文中直接提取完整的航班号信息，确保FlightKey的正确性。
    """
    print(f"--- 开始处理AFTN动态电报 (精准航班号解析模式): {input_file} ---")
    try:
        df = pd.read_csv(input_file, header=None, on_bad_lines='skip')
        json_col_index = 1
        db_time_col_index = -1
    except FileNotFoundError:
        print(f"错误: AFTN输入文件 '{input_file}' 未找到。")
        return pd.DataFrame()

    processed_records = []
    for index, row in df.iterrows():
        try:
            data = json.loads(row.iloc[json_col_index])
            tele_body = data.get('teleBody', '')
            msg_type = tele_body[1:4].strip()

            if msg_type in ['DEP', 'ARR']: continue

            flight_date = get_flight_date_from_aftn(data, tele_body)
            if not flight_date or flight_date != target_date: continue

            # --- 【核心修正逻辑】 ---
            # 直接从报文正文中提取最完整的航班号
            # FPL/CHG/DLA等报文的格式通常是 (TYP-FLIGHTNO-...)
            # 例如 (FPL-CES2104-IS...) 或 (DLA-CFI057-...)
            match = re.search(r'^\([A-Z]{3}-([A-Z0-9\-]+)-', tele_body)
            if match:
                full_flight_no = match.group(1)
            else:
                # 如果正则匹配失败，使用备用方案（可能不含后缀）
                airline_code = data.get('airlineIcaoCode', '')
                flight_no = str(data.get('flightNo', '')).lstrip('0')
                full_flight_no = f"{airline_code}{flight_no}"
            # -------------------------

            dep_icao = data.get('depAirportIcaoCode')
            arr_icao = data.get('arrAirportIcaoCode')

            record = {
                'FlightKey': generate_flight_key(flight_date, full_flight_no, dep_icao, arr_icao),
                'MessageType': msg_type,
                'FlightNo': full_flight_no,
                'DepAirport': dep_icao,
                'ArrAirport': arr_icao,
                'RegNo': data.get('regNo'),
                'CraftType': data.get('aerocraftTypeIcaoCode'),
                'ReceiveTime': row.iloc[db_time_col_index],
                'RawMessage': tele_body
            }

            change_details = {}
            if msg_type == 'CHG':
                change_details = parse_change_items_complete(tele_body)
            elif msg_type == 'DLA':
                dla_match = re.search(r'-(\w{4,7})(\d{4})-', tele_body)
                if dla_match:
                    change_details['New_Departure_Time'] = dla_match.group(2)

            record.update(change_details)
            processed_records.append(record)
        except (json.JSONDecodeError, IndexError, TypeError) as e:
            print(f"警告: AFTN文件第 {index + 2} 行处理失败，原因: {e}。 跳过此行。")
            continue

    print(f"AFTN数据处理完成，共解析出 {len(processed_records)} 条目标日期的计划/动态报文。")
    return pd.DataFrame(processed_records)

def process_fpla_data(input_file, target_date):
    """【FPLA预处理器 - 增强版】"""
    print(f"--- 开始处理FPLA计划文件: {input_file} ---")
    try:
        df = pd.read_excel(input_file)
        df.columns = [str(col).strip().upper() for col in df.columns]
    except FileNotFoundError:
        print(f"错误: FPLA输入文件 '{input_file}' 未找到。程序将退出。")
        return pd.DataFrame()

    processed_records = []
    for index, row in df.iterrows():
        try:
            sobt_raw = row.get('SOBT')
            sobt_str = str(int(sobt_raw)) if pd.notna(sobt_raw) else ""
            if len(sobt_str) < 8: continue

            flight_date = datetime.strptime(sobt_str[:8], "%Y%m%d").date()
            if flight_date != target_date: continue

            flight_no, dep_icao, arr_icao = row.get('CALLSIGN'), row.get('DEPAP'), row.get('ARRAP')

            record = {
                'FlightKey': generate_flight_key(flight_date, flight_no, dep_icao, arr_icao),
                'MessageType': row.get('PSCHEDULESTATUS'),
                'FlightNo': flight_no,
                'CraftType': row.get('PSAIRCRAFTTYPE'),
                'RegNo': row.get('EREGNUMBER') or row.get('REGNUMBER'),
                'DepAirport': dep_icao,
                'SOBT': datetime.strptime(sobt_str, "%Y%m%d%H%M%S") if len(sobt_str) == 14 else (
                    datetime.strptime(sobt_str, "%Y%m%d%H%M") if len(sobt_str) == 12 else None),
                'ArrAirport': arr_icao,
                'SIBT': datetime.strptime(str(int(row.get('SIBT'))), "%Y%m%d%H%M%S") if pd.notna(
                    row.get('SIBT')) and len(str(int(row.get('SIBT')))) == 14 else (
                    datetime.strptime(str(int(row.get('SIBT'))), "%Y%m%d%H%M") if pd.notna(row.get('SIBT')) and len(
                        str(int(row.get('SIBT')))) == 12 else None),
                'Alternate_Airport_1': row.get('ALTAP1'),
                'Alternate_Airport_2': row.get('ALTAP2'),
                'New_Route_Info': row.get('SROUTE'),
                'MissionProperty': row.get('PMISSIONPROPERTY'),
                'MissionType': row.get('PMISSIONTYPE'),
                'ReceiveTime': row.get('SENDTIME'),
            }
            processed_records.append(record)
        except Exception as e:
            print(f"警告: FPLA文件第 {index + 2} 行处理失败，原因: {e}。 跳过此行。")
            continue

    print(f"FPLA数据处理完成，共处理 {len(processed_records)} 条目标日期的记录。")
    return pd.DataFrame(processed_records)


# ==============================================================================
# --- 4. 主程序入口 ---
# ==============================================================================
if __name__ == "__main__":

    # ------------------ 定义主列结构 ------------------
    # AFTN输出文件的最终列顺序，确保结构固定
    MASTER_AFTN_COLS = [
        # 核心关联与身份信息
        'FlightKey', 'MessageType', 'FlightNo', 'New_Callsign',
        # 航空器信息
        'CraftType', 'New_CraftType', 'RegNo', 'New_RegNo',
        # 起飞与时刻信息
        'DepAirport', 'New_Departure_Airport', 'New_Departure_Time',
        # 目的地与时刻信息
        'ArrAirport', 'New_Destination', 'New_EET',
        # 备降场信息
        'Alternate_Airport_1', 'Alternate_Airport_2',
        # 航路信息
        'New_Route_Info',
        # 飞行性质与规则
        'New_FlightRules', 'New_FlightType', 'New_Mission_STS',
        # 其他技术性或补充性变更信息
        'New_WakeCategory', 'New_Operator', 'New_DOF', 'New_Aircraft_Type_Spec',
        'New_SSR_Info', 'Item18_Content',
        # 元数据 (置于最后)
        'ReceiveTime', 'RawMessage'
    ]

    # FPLA输出文件的最终列顺序，与AFTN保持逻辑对齐
    MASTER_FPLA_COLS = [
        # 核心关联与身份信息
        'FlightKey', 'MessageType', 'FlightNo',
        # 航空器信息
        'CraftType', 'RegNo',
        # 起飞与时刻信息
        'DepAirport', 'SOBT',
        # 目的地与时刻信息
        'ArrAirport', 'SIBT',
        # 备降场信息
        'Alternate_Airport_1', 'Alternate_Airport_2',
        # 航路信息
        'New_Route_Info',
        # 任务信息 (与AFTN的New_FlightType/New_Mission_STS对应)
        'MissionType', 'MissionProperty',
        # 元数据 (置于最后)
        'ReceiveTime'
    ]

    # ------------------ 执行数据处理 ------------------
    print("=" * 50)
    # 将TARGET_DATE作为参数传递，确保所有函数使用统一的日期
    TARGET_DATE_OBJ = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d").date()

    # --- 处理AFTN数据 ---
    aftn_df = process_aftn_dynamic_data(AFTN_CSV_FILE, TARGET_DATE_OBJ)
    if not aftn_df.empty:
        # 使用主列表来重新索引DataFrame，确保列结构和顺序固定
        aftn_df_final = aftn_df.reindex(columns=MASTER_AFTN_COLS)
        aftn_df_final.to_csv(PROCESSED_AFTN_OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"√ 处理后的AFTN数据已保存至: {PROCESSED_AFTN_OUTPUT_FILE}")

    print("\n" + "=" * 50 + "\n")

    # --- 处理FPLA数据 ---
    fpla_df = process_fpla_data(FPLA_XLSX_FILE, TARGET_DATE_OBJ)
    if not fpla_df.empty:
        # 使用主列表来重新索引DataFrame，确保列结构和顺序固定
        fpla_df_final = fpla_df.reindex(columns=MASTER_FPLA_COLS)
        fpla_df_final.to_csv(PROCESSED_FPLA_OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"√ 处理后的FPLA数据已保存至: {PROCESSED_FPLA_OUTPUT_FILE}")

    print("\n" + "=" * 50)
    print("所有数据预处理任务已完成！")