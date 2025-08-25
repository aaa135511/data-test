import pandas as pd
import json
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
AIRPORT_ICAO = os.getenv("AIRPORT")

if not TARGET_DATE_STR or not AIRPORT_ICAO:
    print("错误: 请确保 .env 文件中已设置 TARGET_DATE 和 AIRPORT。")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DATA_DIR = os.path.join(BASE_DIR, 'raw_data')
AFTN_CSV_FILE = os.path.join(RAW_DATA_DIR, 'sqlResult_8_25.csv')
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
# --- 2. 辅助函数 ---
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


def get_flight_date_from_aftn(tele_body, receive_time):
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
                dest_eet = parts[0]
                changes['New_Destination'] = dest_eet[:-4] if len(dest_eet) >= 8 else dest_eet
                if len(parts) > 1: changes['New_Alternate_1'] = parts[1]
                if len(parts) > 2: changes['New_Alternate_2'] = parts[2]
        elif item_num_str == '18':
            if re.search(r'REG/(\S+)', content): changes['New_RegNo'] = re.search(r'REG/(\S+)', content).group(1).strip(
                ')')
            if re.search(r'STS/(\S+)', content): changes['New_Mission_STS'] = re.search(r'STS/(\S+)', content).group(1)
    return changes


# ==============================================================================
# --- 3. 核心处理函数 ---
# ==============================================================================
def process_aftn_for_analysis(df, target_date):
    processed_records = []
    for index, row in df.iterrows():
        try:
            data = json.loads(row.iloc[1])
            tele_body = str(row.iloc[3])
            receive_time = pd.to_datetime(row.iloc[4], errors='coerce')

            msg_type = tele_body[1:4].strip()
            if msg_type in ['DEP', 'ARR']: continue
            if pd.isna(receive_time): continue

            flight_date = get_flight_date_from_aftn(tele_body, receive_time)
            if not flight_date or flight_date != target_date: continue

            flight_no_match = re.search(r'^\(\w{3}-([A-Z0-9]+)', tele_body)
            if flight_no_match:
                full_flight_no = flight_no_match.group(1).strip()
            else:
                full_flight_no = f"{data.get('airlineIcaoCode', '')}{str(data.get('flightNo', '')).lstrip('0')}"

            dep_icao = data.get('depAirportIcaoCode')
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
    """
    修改后 (V4): 不再对任何输出进行去重，保留完整的消息历史。
    plan_df 和 dynamic_df 将是同一个包含所有记录的DataFrame，只是列的选择不同。
    """
    processed_records = []
    for index, row in df.iterrows():
        try:
            sobt_str = str(row.get('SOBT')).split('.')[0]
            if len(sobt_str) < 8: continue
            flight_date = datetime.strptime(sobt_str[:8], "%Y%m%d").date()
            if flight_date != target_date: continue

            flight_key = generate_flight_key(flight_date, row.get('CALLSIGN'), row.get('DEPAP'), row.get('ARRAP'))

            record = {
                'FlightKey': flight_key, 'ReceiveTime': row.get('SENDTIME'),
                'FPLA_Status': row.get('PSCHEDULESTATUS'), 'FlightNo': row.get('CALLSIGN'),
                'RegNo': row.get('EREGNUMBER') or row.get('REGNUMBER'),
                'CraftType': row.get('PSAIRCRAFTTYPE'),
                'SOBT': row.get('SOBT'), 'SIBT': row.get('SIBT'),
                'DepAirport': row.get('DEPAP'), 'ArrAirport': row.get('ARRAP'),
                'APTSOBT': row.get('APTSOBT'), 'APTSIBT': row.get('APTSIBT'),
                'APTDEPAP': row.get('APTDEPAP'), 'APTARRAP': row.get('APTARRAP'),
                'Route': row.get('SROUTE'),
            }
            processed_records.append(record)
        except Exception:
            continue

    if not processed_records:
        return pd.DataFrame(), pd.DataFrame()

    # 直接返回包含所有记录的DataFrame
    full_df = pd.DataFrame(processed_records)

    # 为了接口统一，我们仍然返回两个df，但它们都包含所有数据
    plan_df = full_df.copy()
    dynamic_df = full_df.copy()

    return plan_df, dynamic_df


def process_fodc_for_analysis(df, target_date):
    """
    修改后 (V4): 不再对任何输出进行去重，保留完整的消息历史。
    """
    plan_records = []
    dynamic_records = []
    df.columns = [str(col).strip() for col in df.columns]

    for index, row in df.iterrows():
        try:
            sobt_str = str(row.get('计划离港时间')).split('.')[0]
            if pd.isna(sobt_str) or len(sobt_str) < 12: continue
            flight_date = datetime.strptime(sobt_str[:8], "%Y%m%d").date()
            if flight_date != target_date: continue

            flight_key = generate_flight_key(flight_date, row.get('航空器识别标志'), row.get('计划起飞机场'),
                                             row.get('计划降落机场'))

            plan_record = {
                'FlightKey': flight_key, 'ReceiveTime': row.get('消息发送时间'),
                'FlightNo': row.get('航空器识别标志'), 'RegNo': row.get('航空器注册号'),
                'DepAirport': row.get('计划起飞机场'), 'ArrAirport': row.get('计划降落机场'),
                'SOBT': sobt_str, 'CraftType': row.get('航空器机型')
            }
            plan_records.append(plan_record)

            if pd.notna(row.get('实际起飞时间')) or pd.notna(row.get('实际起飞机场')):
                dynamic_record = {
                    'FlightKey': flight_key, 'ReceiveTime': row.get('消息发送时间'),
                    'FlightNo': row.get('航空器识别标志'), 'RegNo': row.get('航空器注册号'),
                    'CraftType': row.get('航空器机型'),
                    'DepAirport': row.get('实际起飞机场') or row.get('计划起飞机场'),
                    'ArrAirport': row.get('实际降落机场') or row.get('计划降落机场'),
                    'FODC_ATOT': str(row.get('实际起飞时间')).split('.')[0]
                }
                dynamic_records.append(dynamic_record)
        except Exception:
            continue

    # 直接返回包含所有记录的DataFrame
    plan_df = pd.DataFrame(plan_records) if plan_records else pd.DataFrame()
    dynamic_df = pd.DataFrame(dynamic_records) if dynamic_records else pd.DataFrame()

    return plan_df, dynamic_df


# ==============================================================================
# --- 4. 主程序入口 ---
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

        original_count = len(fpla_raw_df)
        fpla_filtered_df = fpla_raw_df[fpla_raw_df['PSCHEDULESTATUS'] != 'CNL'].copy()
        filtered_count = len(fpla_filtered_df)
        print(f"FPLA数据过滤: 原始记录数 {original_count}, 过滤'CNL'状态后剩余 {filtered_count} 条记录。")

        fpla_plan_df, fpla_dynamic_df = process_fpla_for_analysis(fpla_filtered_df, target_date_obj)

        if not fpla_plan_df.empty:
            fpla_plan_df.to_csv(os.path.join(PREPROCESSED_DIR, f'analysis_fpla_plan_data_{TARGET_DATE_STR}.csv'),
                                index=False, encoding='utf-8-sig')
            print(f"√ FPLA计划分析文件已生成")
        else:
            print(f"警告: 在文件 {FPLA_XLSX_FILE} 中未找到指定日期的FPLA计划数据。")

        if not fpla_dynamic_df.empty:
            fpla_dynamic_df.to_csv(os.path.join(PREPROCESSED_DIR, f'analysis_fpla_dynamic_data_{TARGET_DATE_STR}.csv'),
                                   index=False, encoding='utf-8-sig')
            print(f"√ FPLA动态分析文件已生成")
        else:
            print(f"警告: 在文件 {FPLA_XLSX_FILE} 中未找到指定日期的FPLA动态数据。")

    except FileNotFoundError:
        print(f"错误: 原始FPLA文件 '{FPLA_XLSX_FILE}' 未找到。")
    except Exception as e:
        print(f"处理FPLA文件时发生错误: {e}")

    try:
        print(f"--- 正在读取原始FODC文件: {FODC_XLSX_FILE} ---")
        fodc_raw_df = pd.read_excel(FODC_XLSX_FILE, engine='openpyxl')
        fodc_plan_df, fodc_dynamic_df = process_fodc_for_analysis(fodc_raw_df, target_date_obj)

        if not fodc_plan_df.empty:
            fodc_plan_df.to_csv(os.path.join(PREPROCESSED_DIR, f'analysis_fodc_plan_data_{TARGET_DATE_STR}.csv'),
                                index=False, encoding='utf-8-sig')
            print(f"√ FODC计划分析文件已生成")
        else:
            print("警告: 未找到指定日期的FODC计划数据。")

        if not fodc_dynamic_df.empty:
            fodc_dynamic_df.to_csv(os.path.join(PREPROCESSED_DIR, f'analysis_fodc_dynamic_data_{TARGET_DATE_STR}.csv'),
                                   index=False, encoding='utf-8-sig')
            print(f"√ FODC动态分析文件已生成")
        else:
            print("警告: 未找到指定日期的FODC动态数据。")

    except FileNotFoundError:
        print(f"错误: 原始FODC文件 '{FODC_XLSX_FILE}' 未找到。")
    except Exception as e:
        print(f"处理FODC文件时发生错误: {e}")

    print(f"\n===== 日期 {TARGET_DATE_STR} 的预处理任务已完成 =====")


if __name__ == "__main__":
    main()