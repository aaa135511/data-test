import pandas as pd
import json
import re
from datetime import datetime

# --- 配置 ---
INPUT_CSV_FILE = 'sqlResult_1.csv'
TARGET_FLIGHT_DATE_STR = '2025-06-08'  # 我们选定这一天作为目标分析日期
OUTPUT_EXCEL_FILE = f'telegram_events_{TARGET_FLIGHT_DATE_STR}.xlsx'


def parse_dof(dof_str: str) -> str:
    """将 YYMMDD 格式的日期字符串解析为 YYYY-MM-DD"""
    if not dof_str or len(dof_str) != 6:
        return None
    # 假设年份为20xx
    return f"20{dof_str[0:2]}-{dof_str[2:4]}-{dof_str[4:6]}"


def get_flight_date(json_data: dict, raw_text: str) -> str:
    """从解析后的JSON或原始报文中提取航班执行日期 (DOF)"""
    # 优先从JSON的dofExecDate字段获取
    if 'dofExecDate' in json_data and pd.notna(json_data['dofExecDate']):
        # d.o.f字段可能是完整日期或YYMMDD，这里做个兼容
        dof_val = str(json_data['dofExecDate'])
        if len(dof_val) == 6:  # YYMMDD
            return parse_dof(dof_val)
        return dof_val.split(' ')[0]  # YYYY-MM-DD HH:MM:SS, 取日期部分

    # 如果JSON中没有，则从原始报文的 'DOF/YYMMDD' 字段中提取
    match = re.search(r'DOF/(\d{6})', raw_text)
    if match:
        return parse_dof(match.group(1))

    return None


def process_telegrams_to_excel(input_file: str, target_date: str, output_file: str):
    """
    处理电报CSV数据，将指定日期的航班事件导出到Excel。
    """
    try:
        df = pd.read_csv(input_file)
    except FileNotFoundError:
        print(f"错误: 文件 '{input_file}' 未找到。请检查文件名和路径。")
        return

    processed_events = []

    # 定义输出Excel的列顺序，与设计的Schema保持一致
    schema_columns = [
        'FLIGHT_KEY', 'GUFI', 'MESSAGE_TYPE', 'MESSAGE_TIMESTAMP',
        'CALLSIGN', 'AIRLINE_ICAO_CODE', 'DOF_EXEC_DATE', 'DEPAP', 'ARRAP',
        'REGNUMBER', 'AIRCRAFT_TYPE', 'EOBT', 'ATOT', 'ALDT',
        'CPL_STATUS', 'NEW_ARRAP', 'ALTN_AP_1', 'ALTN_AP_2', 'ROUTE',
        'SOURCE_TELEGRAM_ID', 'RAW_TELEGRAM_BODY'
    ]

    print(f"开始处理文件 '{input_file}', 目标日期: {target_date}")

    for _, row in df.iterrows():
        try:
            raw_body = row['原始报文正文']
            json_data = json.loads(row['解析后的json数据']) if pd.notna(row['解析后的json数据']) else {}

            # 1. 确定航班的执行日期
            flight_date = get_flight_date(json_data, raw_body)
            if not flight_date or flight_date != target_date:
                continue  # 如果不是目标日期的航班，跳过

            # 2. 如果是目标日期的航班，则开始映射数据
            callsign = json_data.get('flightNo')
            if not callsign:
                continue  # 没有航班号的报文无法处理

            flight_key = f"{json_data.get('airlineIcaoCode', '')}{callsign}-{flight_date}"

            # 准备要填充到Excel行的数据字典
            event_data = {
                'FLIGHT_KEY': flight_key,
                'GUFI': None,  # 初始为空，待与FPLA关联后填充
                'MESSAGE_TYPE': row['报文类型'],
                'MESSAGE_TIMESTAMP': row['入库时间'],  # 假设CSV中有此列，如果没有请替换为实际的时间列名
                'CALLSIGN': callsign,
                'AIRLINE_ICAO_CODE': json_data.get('airlineIcaoCode'),
                'DOF_EXEC_DATE': flight_date,
                'DEPAP': json_data.get('depAirportIcaoCode'),
                'ARRAP': json_data.get('arrAirportIcaoCode'),
                'REGNUMBER': json_data.get('newRegNo') or json_data.get('regNo'),  # CHG报文有newRegNo
                'AIRCRAFT_TYPE': json_data.get('newAerocraftTypeIcaoCode') or json_data.get('aerocraftTypeIcaoCode'),
                'EOBT': json_data.get('etot'),  # 简化处理：DLA/FPL的etot作为EOBT
                'ATOT': json_data.get('atot'),  # DEP报文的实际起飞时间
                'ALDT': json_data.get('aldt'),  # ARR报文的实际落地时间
                'CPL_STATUS': json_data.get('abnormalStatus'),
                'NEW_ARRAP': json_data.get('actlArrAirportIcaoCode'),
                'ALTN_AP_1': json_data.get('altStationIcao'),
                'ALTN_AP_2': json_data.get('altStationIcao1'),
                'ROUTE': json_data.get('route'),
                'SOURCE_TELEGRAM_ID': json_data.get('teleId'),
                'RAW_TELEGRAM_BODY': raw_body
            }
            processed_events.append(event_data)

        except (json.JSONDecodeError, KeyError) as e:
            print(f"警告: 处理行 {_.name} 时发生错误，已跳过。错误信息: {e}")
            continue

    if not processed_events:
        print("处理完成，但未找到与目标日期相关的任何航班事件。")
        return

    # 3. 创建DataFrame并导出到Excel
    output_df = pd.DataFrame(processed_events)

    # 按照Schema的顺序重新排列列
    # 对于可能在processed_events中不存在的列（如果所有报文都没有该字段），填充为None
    for col in schema_columns:
        if col not in output_df.columns:
            output_df[col] = None
    output_df = output_df[schema_columns]

    output_df.to_excel(output_file, index=False, engine='openpyxl')
    print(f"\n处理成功！")
    print(f"共处理了 {len(processed_events)} 条与 {target_date} 航班相关的电报事件。")
    print(f"结果已保存到文件: '{output_file}'")


if __name__ == '__main__':
    # 确保您的CSV文件中有一列名为 '入库时间'，或者修改脚本中对应的列名
    process_telegrams_to_excel(INPUT_CSV_FILE, TARGET_FLIGHT_DATE_STR, OUTPUT_EXCEL_FILE)