import pandas as pd
from datetime import datetime

# ==============================================================================
# --- 1. 配置区 ---
# ==============================================================================
TARGET_DATE_STR = "2025-07-08"
AFTN_PROCESSED_FILE = f'processed_aftn_dynamic_final_{TARGET_DATE_STR}.csv'
FPLA_PROCESSED_FILE = f'processed_fpla_plan_final_{TARGET_DATE_STR}.csv'

# 输出的Markdown文件名
MD_REPORT_FILE = f'flight_timeline_report_{TARGET_DATE_STR}.md'

# 设置要分析的航班数量（-1代表所有航班，可以设置为一个较小的数如5来进行快速测试）
FLIGHTS_TO_ANALYZE = -1


# ==============================================================================
# --- 2. 主分析与生成逻辑 ---
# ==============================================================================

def generate_timeline_report():
    """
    读取预处理后的AFTN和FPLA数据，为每个航班生成一个双轨时间轴，
    并输出到一个易于阅读的Markdown文件中。
    """
    print("--- 开始生成航班动态时间轴分析报告 ---")

    # --- 1. 数据加载 ---
    try:
        aftn_df = pd.read_csv(AFTN_PROCESSED_FILE, low_memory=False)
        fpla_df = pd.read_csv(FPLA_PROCESSED_FILE, low_memory=False)
    except FileNotFoundError as e:
        print(f"错误: 无法找到输入文件。请确保以下文件存在: \n{AFTN_PROCESSED_FILE}\n{FPLA_PROCESSED_FILE}")
        print(f"详细错误: {e}")
        return

    # --- 2. 数据准备与合并 ---
    aftn_df['Source'] = 'AFTN'
    fpla_df['Source'] = 'FPLA'

    # 为了方便展示，我们将FPLA的MessageType重命名，避免与AFTN的混淆
    fpla_df.rename(columns={'MessageType': 'FPLA_Status'}, inplace=True)

    # 统一时间格式以便排序
    for df in [aftn_df, fpla_df]:
        df['ReceiveTime'] = pd.to_datetime(df['ReceiveTime'], errors='coerce')
    fpla_df['SOBT'] = pd.to_datetime(fpla_df['SOBT'], errors='coerce')
    fpla_df['SIBT'] = pd.to_datetime(fpla_df['SIBT'], errors='coerce')

    # 合并两个数据源
    timeline_df = pd.concat([aftn_df, fpla_df], ignore_index=True)
    timeline_df.dropna(subset=['ReceiveTime'], inplace=True)

    # 按航班和时间排序，构建时间轴
    timeline_df.sort_values(by=['FlightKey', 'ReceiveTime'], inplace=True)

    print(f"数据加载与合并完成，共计 {len(timeline_df)} 条时间轴记录。")

    # --- 3. 生成Markdown报告 ---
    unique_flights = timeline_df['FlightKey'].unique()

    # 根据配置决定分析多少航班
    if FLIGHTS_TO_ANALYZE != -1:
        flights_to_process = unique_flights[:FLIGHTS_TO_ANALYZE]
    else:
        flights_to_process = unique_flights

    print(f"将为 {len(flights_to_process)} 个航班生成详细时间轴...")

    with open(MD_REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"# 航班动态时间轴分析报告 ({TARGET_DATE_STR})\n\n")
        f.write("本报告旨在清晰展示AFTN和FPLA两个数据源关于同一航班的动态消息序列，以便进行深度分析。\n\n")

        for i, flight_key in enumerate(flights_to_process):
            f.write(f"## {i + 1}. 航班: `{flight_key}`\n\n")

            flight_timeline = timeline_df[timeline_df['FlightKey'] == flight_key]

            # --- 创建一个美观的表格 ---
            f.write(
                "| No. | Source | ReceiveTime (UTC) | Message Type | SOBT / New Time | RegNo / New RegNo | Route / New Route | Raw Message / Other Info |\n")
            f.write(
                "|:---:|:------:|:------------------|:-------------|:----------------|:------------------|:--------------------|:-------------------------|\n")

            for index, row in flight_timeline.iterrows():
                # 提取并格式化各列信息
                source = row['Source']
                receive_time = row['ReceiveTime'].strftime('%Y-%m-%d %H:%M:%S') if pd.notna(
                    row['ReceiveTime']) else "N/A"

                if source == 'AFTN':
                    msg_type = row.get('MessageType', '')
                    time_info = row.get('New_Departure_Time', '')
                    reg_info = row.get('New_RegNo', row.get('RegNo', ''))  # 优先显示变更后的
                    route_info = f"`{str(row.get('New_Route_Info', ''))[:50]}...`" if pd.notna(
                        row.get('New_Route_Info')) else ''  # 截断过长的航路
                    other_info = f"```{row.get('RawMessage', '')}```"
                else:  # FPLA
                    msg_type = row.get('FPLA_Status', '')
                    time_info = row['SOBT'].strftime('%H:%M') if pd.notna(row['SOBT']) else ''
                    reg_info = row.get('RegNo', '')
                    route_info = f"`{str(row.get('Route', ''))[:50]}...`" if pd.notna(row.get('Route')) else ''
                    other_info = f"SIBT: {row['SIBT'].strftime('%H:%M') if pd.notna(row['SIBT']) else ''}, MissionType: {row.get('MissionType', '')}"

                # 写入表格行
                f.write(
                    f"| {index + 1} | **{source}** | {receive_time} | `{msg_type}` | {time_info} | `{reg_info}` | {route_info} | {other_info} |\n")

            f.write("\n---\n\n")  # 每个航班后加分割线

    print(f"\n报告生成完毕！请查看文件: {MD_REPORT_FILE}")


# ==============================================================================
# --- 4. 程序入口 ---
# ==============================================================================
if __name__ == "__main__":
    generate_timeline_report()