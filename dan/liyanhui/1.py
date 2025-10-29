import pandas as pd
import re
import os
from datetime import datetime, timedelta

# --- 1. 动态日期和文件路径配置 ---
# 脚本运行时，会自动处理 *第二天* 的数据。
# 例如，在 9月15日 运行，将查找并处理 "20250916...-20250917..." 的文件。
run_date = datetime.now()
start_day_of_data = run_date + timedelta(days=1)
end_day_of_data = start_day_of_data + timedelta(days=1)

# 格式化日期字符串，例如 '20250916000000'
start_date_str = start_day_of_data.strftime('%Y%m%d000000')
end_date_str = end_day_of_data.strftime('%Y%m%d000000')

# 定义文件所在的基础路径
BASE_DOWNLOAD_PATH = '/Users/qiangliang/Documents/work/workspace/code/DataTest/dan/liyanhui'
BASE_OUTPUT_PATH = '/Users/qiangliang/Documents/work/workspace/code/DataTest/dan/liyanhui'

# 动态生成完整的文件路径
EXCEL1_PATH = os.path.join(BASE_DOWNLOAD_PATH, f'Data-operation-alert-{start_date_str}-{end_date_str}.xlsx')
EXCEL2_PATH = os.path.join(BASE_DOWNLOAD_PATH, f'FPLA-Details-{start_date_str}-{end_date_str}.xlsx')
# 输出文件名也反映 *数据* 的日期，防止覆盖
OUTPUT_TXT_PATH = os.path.join(BASE_OUTPUT_PATH, f'problematic_flights_{start_day_of_data.strftime("%Y%m%d")}.txt')


# --- 2. 核心逻辑参数 (保持不变) ---
# --- 第一个Excel文件 (Data-operation-alert...) 的配置 ---
FILTER_COLUMN_EXCEL1 = '校验结论'
ERROR_KEYWORD = '联程航班航段数量缺少'
DATA_COLUMN_EXCEL1 = '及时性校验结果'

# --- 通用配置 ---
# 需要检查的目标机场代码列表
TARGET_AIRPORTS = ['ZLIC', 'ZGGG', 'ZUUU', 'ZLLL', 'ZLXY']

# --- 第二个Excel文件 (FPLA-Details...) 的配置 ---
COL2_FLIGHT_NUM = '航空器识别标志'
COL2_UNIQUE_ID = '全球唯一飞行标识符'
COL2_SEND_TIME = '消息发送时间'
COL2_PLANNED_SEGMENT = '预执行航段'


# --- 辅助函数：检查航段是否为完整的联程航段 (保持不变) ---
def is_through_flight_segment_complete(segment_str):
    """
    检查一个航段字符串是否代表一个完整的联程航班计划。
    一个完整的联程计划应至少包含3个机场代码 (例如 A-B-C)。
    """
    if not isinstance(segment_str, str) or not segment_str:
        return False
    airports_found = re.findall(r'[A-Z]{4}', segment_str)
    return len(airports_found) >= 3

# --- 3. 主程序 (核心逻辑保持不变) ---
def main():
    print("--- 开始航班数据分析 ---")
    print(f"[*] 脚本运行于: {run_date.strftime('%Y-%m-%d')}")
    print(f"[*] 正在查找和处理 *第二天* ({start_day_of_data.strftime('%Y-%m-%d')}) 的文件...")
    print(f"[*] 输入文件1: {os.path.basename(EXCEL1_PATH)}")
    print(f"[*] 输入文件2: {os.path.basename(EXCEL2_PATH)}")
    print(f"[*] 输出报告: {os.path.basename(OUTPUT_TXT_PATH)}")

    # 1. 加载 Excel 文件
    try:
        # 确保输出目录存在
        output_dir = os.path.dirname(OUTPUT_TXT_PATH)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        df1 = pd.read_excel(EXCEL1_PATH)
        df2 = pd.read_excel(EXCEL2_PATH)
        print(f"\n成功加载 '{os.path.basename(EXCEL1_PATH)}' 和 '{os.path.basename(EXCEL2_PATH)}'。")
    except FileNotFoundError as e:
        print(f"\n错误：文件未找到。请确认以下文件是否存在于您的下载目录中：")
        print(f" - {os.path.basename(EXCEL1_PATH)}")
        print(f" - {os.path.basename(EXCEL2_PATH)}")
        print(f"详细信息：{e}")
        return
    except Exception as e:
        print(f"读取 Excel 文件时发生意外错误：{e}")
        return

    # 3. 预处理数据
    df2[COL2_SEND_TIME] = pd.to_datetime(df2[COL2_SEND_TIME], errors='coerce')
    problematic_flights_output = []
    processed_full_ids = set()

    # 用于存储按机场分类的问题航班号，用于最后汇总
    summary_by_airport = {}

    # 4. 【第一步】筛选告警
    filtered_df1 = df1[df1[FILTER_COLUMN_EXCEL1].astype(str).str.contains(ERROR_KEYWORD, na=False)]
    print(f"在 '{FILTER_COLUMN_EXCEL1}' 列中找到 {len(filtered_df1)} 行包含 '{ERROR_KEYWORD}' 的告警。")

    if not filtered_df1.empty:
        # 5. 遍历筛选出的每一行
        for index, row in filtered_df1.iterrows():
            source_text = str(row.get(DATA_COLUMN_EXCEL1, ''))

            match = re.search(r'([A-Z0-9]+-[A-Z]{4}-[A-Z]{4})', source_text)
            if not match:
                continue

            flight_full_id = match.group(1)

            if flight_full_id in processed_full_ids:
                continue
            processed_full_ids.add(flight_full_id)

            flight_number = flight_full_id.split('-')[0]

            matching_airport = next((airport for airport in TARGET_AIRPORTS if airport in flight_full_id), None)

            if not matching_airport:
                continue

            print(f"\n处理告警条目：{flight_full_id} (匹配机场：{matching_airport})")

            flight_data_in_df2 = df2[df2[COL2_FLIGHT_NUM] == flight_number].copy()

            if flight_data_in_df2.empty:
                print(f"  航班号 '{flight_number}' 未在 '{os.path.basename(EXCEL2_PATH)}' 中找到。跳过。")
                continue

            unique_guids = flight_data_in_df2[COL2_UNIQUE_ID].dropna().unique()
            if len(unique_guids) <= 1:
                print(f"  航班号 '{flight_number}' 在FPL详情中不表现为联程航班 (仅有 {len(unique_guids)} 个唯一GUID)。跳过。")
                continue

            if matching_airport == 'ZGGG':
                print(f"  -> 告警关联到ZGGG，应用特殊规则：检查最早的两条飞行计划。")
                sorted_flight_data = flight_data_in_df2.dropna(subset=[COL2_SEND_TIME]).sort_values(
                    by=COL2_SEND_TIME, ascending=True
                )

                if len(sorted_flight_data) < 2:
                    segment_info = "无" if sorted_flight_data.empty else sorted_flight_data.iloc[0][COL2_PLANNED_SEGMENT]
                    output_line = (
                        f"发现问题航班：{flight_number} (关联机场: {matching_airport})\n"
                        f"  原始告警标识: {flight_full_id}\n"
                        f"  问题描述: ZGGG关联航班告警，但在FPL详情中只找到 {len(sorted_flight_data)} 条记录，不满足联程要求。\n"
                        f"  找到的计划航段: {segment_info}\n"
                        f"----------------------------------------"
                    )
                    problematic_flights_output.append(output_line)
                    if matching_airport not in summary_by_airport:
                        summary_by_airport[matching_airport] = set()
                    summary_by_airport[matching_airport].add(flight_number)
                    print(f"  -> 发现问题：FPL详情中记录少于2条！已记录到输出文件。")
                    continue

                segment1 = sorted_flight_data.iloc[0][COL2_PLANNED_SEGMENT]
                segment2 = sorted_flight_data.iloc[1][COL2_PLANNED_SEGMENT]
                is_seg1_complete = is_through_flight_segment_complete(segment1)
                is_seg2_complete = is_through_flight_segment_complete(segment2)
                print(f"    - 最早记录1的航段: '{segment1}' (是否完整: {is_seg1_complete})")
                print(f"    - 最早记录2的航段: '{segment2}' (是否完整: {is_seg2_complete})")

                if not is_seg1_complete or not is_seg2_complete:
                    output_line = (
                        f"发现问题航班：{flight_number} (关联机场: {matching_airport})\n"
                        f"  原始告警标识: {flight_full_id}\n"
                        f"  问题描述: ZGGG关联航班告警，且其最早的两条飞行计划中至少有一条不完整。\n"
                        f"  最早计划1: {segment1}\n"
                        f"  最早计划2: {segment2}\n"
                        f"----------------------------------------"
                    )
                    problematic_flights_output.append(output_line)
                    if matching_airport not in summary_by_airport:
                        summary_by_airport[matching_airport] = set()
                    summary_by_airport[matching_airport].add(flight_number)
                    print(f"  -> 发现问题：最早的两条记录中存在不完整的航段！已记录到输出文件。")
                else:
                    print(f"  -> ZGGG航班检查通过：最早的两条记录航段均完整。")
            else:
                print(f"  -> 告警未关联ZGGG，应用通用规则：检查最新的飞行计划。")
                latest_entry_df = flight_data_in_df2.dropna(subset=[COL2_SEND_TIME]).sort_values(
                    by=COL2_SEND_TIME, ascending=False
                )
                if latest_entry_df.empty:
                    print(f"  警告：航班号 '{flight_number}' 无有效发送时间记录。跳过。")
                    continue

                latest_entry = latest_entry_df.iloc[0]
                planned_segment = latest_entry[COL2_PLANNED_SEGMENT]

                if not is_through_flight_segment_complete(planned_segment):
                    output_line = (
                        f"发现问题航班：{flight_number} (关联机场: {matching_airport})\n"
                        f"  原始告警标识: {flight_full_id}\n"
                        f"  问题描述: 告警为“联程航班缺少航段”，且其最新飞行计划仅为单段航程。\n"
                        f"  不完整的计划航段: {planned_segment}\n"
                        f"----------------------------------------"
                    )
                    problematic_flights_output.append(output_line)
                    if matching_airport not in summary_by_airport:
                        summary_by_airport[matching_airport] = set()
                    summary_by_airport[matching_airport].add(flight_number)
                    print(f"  -> 发现问题：最新计划 '{planned_segment}' 不完整！已记录到输出文件。")
                else:
                    print(f"  航班号 '{flight_number}' 的最新计划 '{planned_segment}' 航段完整。")

    # 6. 将结果输出到文本文件 (已按要求修改)
    with open(OUTPUT_TXT_PATH, 'w', encoding='utf-8') as f:
        # --- 1. 写入详细的问题航班报告 (如果存在) ---
        if problematic_flights_output:
            f.write(f"--- 航班分析报告 ({start_day_of_data.strftime('%Y-%m-%d')}) ---\n")
            f.write(f"本报告识别出那些被系统告警为“联程缺少航段”，并且根据特定规则确认其飞行计划确实存在问题的航班。\n\n")
            f.write("="*40 + "\n\n")
            for line in problematic_flights_output:
                f.write(line + '\n\n')
            f.write("="*40 + "\n\n") # 分隔符

        # --- 2. 写入您要求的固定格式结尾 ---

        # 2a. 写入带标题的汇总
        f.write("--- 问题航班按机场汇总 ---\n")
        if summary_by_airport:
            for airport, flights in sorted(summary_by_airport.items()):
                flight_list_str = ' '.join(sorted(list(flights)))
                summary_line = f"预执行航段不全问题 {airport} {flight_list_str}\n"
                f.write(summary_line)
        
        f.write("\n") # 为格式美观，添加一个空行

        # 2b. 写入校验结果部分
        today_str = run_date.strftime('%Y%m%d')
        next_day_str = start_day_of_data.strftime('%Y%m%d')
        
        f.write(f"今日（{today_str}）查看次日（{next_day_str}）格式与逻辑校验结果\n")
        f.write("总共 0 项错误\n\n")
        f.write("1.共0项格式错误\n\n")
        f.write("2.共0项逻辑错误\n\n")
        
        # 2c. 再次写入不带标题的汇总
        if summary_by_airport:
            for airport, flights in sorted(summary_by_airport.items()):
                flight_list_str = ' '.join(sorted(list(flights)))
                summary_line = f"预执行航段不全问题 {airport} {flight_list_str}\n"
                f.write(summary_line)

    # 更新最终的控制台打印信息
    if problematic_flights_output:
        print(f"\n--- 分析完成。共发现 {len(problematic_flights_output)} 个有问题航班条目。")
        print(f"[*] 详细信息及最终总结已写入: '{os.path.basename(OUTPUT_TXT_PATH)}'")
    else:
        print(f"\n--- 分析完成。未发现问题航班。")
        print(f"[*] 已根据要求生成总结报告: '{os.path.basename(OUTPUT_TXT_PATH)}'")


if __name__ == "__main__":
    main()