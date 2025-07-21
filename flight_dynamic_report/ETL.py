import pandas as pd
import json

# --- 配置 ---
INPUT_CSV_FILE = 'sqlResult_1.csv'
OUTPUT_EXCEL_FILE = 'telegram_comparison_ready_data.xlsx'


def etl_json_to_comparison_model_simplified(input_file: str, output_file: str):
    """
    轻量级ETL脚本 (精简版):
    1. 读取CSV中的JSON。
    2. 将 AirlineICAO 和 Callsign 合并为统一的 Callsign 列。
    3. 输出到Excel，不增加任何额外列。
    """
    try:
        df = pd.read_csv(input_file, dtype=str).fillna('')
    except FileNotFoundError:
        print(f"错误: 文件 '{input_file}' 未找到。")
        return

    processed_records = []

    print(f"开始精简版ETL流程: {input_file} -> {output_file}")

    for index, row in df.iterrows():
        try:
            json_str = row.get('解析后的json数据', '{}')
            json_data = json.loads(json_str) if json_str and json_str.strip() != '{}' else {}

            if not json_data:
                continue

            # 从JSON中提取所有键值对，形成一个记录
            record = json_data.copy()

            # --- 核心修正：统一Callsign格式 ---
            airline_icao = str(record.get('airlineIcaoCode', '')).strip()
            numeric_callsign = str(record.get('flightNo', '')).strip()

            # 直接修改'flightNo'字段，使其变为完整的航班号
            # 我们将使用 'flightNo' 作为后续的Callsign匹配字段
            record['flightNo'] = f"{airline_icao}{numeric_callsign}"

            # 保留其他元数据
            record['MessageType_Full'] = row.get('报文类型', '')  # 保留原始报文类型
            record['MessageTimestamp'] = row.get('入库时间', '')

            processed_records.append(record)

        except Exception as e:
            print(f"严重错误: 处理行 {index} 时发生异常，已跳过。错误: {e}\n原始JSON: {json_str}\n")
            continue

    if not processed_records:
        print("处理完成，但未生成任何有效的记录。")
        return

    output_df = pd.DataFrame(processed_records)

    # 为了后续方便，重命名 flightNo 为 Callsign
    output_df.rename(columns={'flightNo': 'Callsign', 'MessageType_Full': 'MessageType'}, inplace=True)

    output_df.to_excel(output_file, index=False, engine='openpyxl')
    print(f"\n精简版ETL流程成功完成！")
    print(f"共处理了 {len(df)} 行原始数据，生成了 {len(output_df)} 条记录。")
    print(f"结果已加载到文件: '{output_file}'")


if __name__ == '__main__':
    etl_json_to_comparison_model_simplified(INPUT_CSV_FILE, OUTPUT_EXCEL_FILE)