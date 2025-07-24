import re

import pandas as pd
from datetime import datetime

# ==============================================================================
# --- 1. 配置区 ---
# ==============================================================================
TARGET_DATE_STR = "2025-07-08"
AFTN_ANALYSIS_FILE = f'analysis_aftn_data_{TARGET_DATE_STR}.csv'
FPLA_ANALYSIS_FILE = f'analysis_fpla_data_{TARGET_DATE_STR}.csv'
MD_REPORT_FILE = f'unified_flight_timeline_report_{TARGET_DATE_STR}.md'
FLIGHTS_TO_ANALYZE = -1


# ==============================================================================
# --- 2. 辅助格式化函数 (核心修正！) ---
# ==============================================================================

def format_fpla_info(row):
    """【V4修正版】格式化FPLA行的核心信息，补全起降机场"""
    parts = []

    # 航站与时刻信息
    dep_ap = row.get('DepAirport', 'N/A')
    arr_ap = row.get('ArrAirport', 'N/A')

    sobt_str = "----"
    sibt_str = "----"

    if pd.notna(row.get('SOBT')):
        try:
            sobt_val_str = str(int(float(row['SOBT'])))
            sobt_dt = pd.to_datetime(sobt_val_str, format='%Y%m%d%H%M', errors='coerce')
            if pd.isna(sobt_dt):
                sobt_dt = pd.to_datetime(sobt_val_str, format='%Y%m%d%H%M%S', errors='coerce')
            if pd.notna(sobt_dt):
                sobt_str = sobt_dt.strftime('%H:%M')
        except:
            pass

    if pd.notna(row.get('SIBT')):
        try:
            sibt_val_str = str(int(float(row['SIBT'])))
            sibt_dt = pd.to_datetime(sibt_val_str, format='%Y%m%d%H%M', errors='coerce')
            if pd.isna(sibt_dt):
                sibt_dt = pd.to_datetime(sibt_val_str, format='%Y%m%d%H%M%S', errors='coerce')
            if pd.notna(sibt_dt):
                sibt_str = sibt_dt.strftime('%H:%M')
        except:
            pass

    parts.append(f"**航程**: `{dep_ap}` -> `{arr_ap}`")
    parts.append(f"**时刻 (SOBT-SIBT)**: `{sobt_str}` - `{sibt_str}`")

    # 航空器信息
    if pd.notna(row.get('RegNo')): parts.append(f"**机号 (RegNo)**: `{row['RegNo']}`")

    # 航路信息
    if pd.notna(row.get('Route')):
        route_info = str(row['Route'])
        parts.append(f"**航路 (Route)**: `{route_info[:40]}...`" if len(route_info) > 40 else f"`{route_info}`")

    # 任务信息
    if pd.notna(row.get('MissionType')): parts.append(f"**任务类型**: `{row['MissionType']}`")
    if pd.notna(row.get('MissionProperty')): parts.append(f"**任务性质**: `{row['MissionProperty']}`")

    return ' <br> '.join(parts) if parts else "No detailed info"


def format_aftn_info(row):
    """【V4版】格式化AFTN行的核心信息，保持与上一版一致"""
    parts = []
    msg_type = row.get('MessageType', '')

    if msg_type == 'FPL':
        if pd.notna(row.get('RegNo')): parts.append(f"**机号 (REG)**: `{row['RegNo']}`")
        match = re.search(r'-\w{4}(\d{4})\s', row.get('RawMessage', ''))
        if match: parts.append(f"**计划时刻 (EOBT)**: `{match.group(1)}`")
        if pd.notna(row.get('DepAirport')): parts.append(f"**起飞 (DEP)**: `{row.get('DepAirport')}`")
        if pd.notna(row.get('ArrAirport')): parts.append(f"**目的地 (DEST)**: `{row['ArrAirport']}`")

    elif msg_type == 'DLA':
        if pd.notna(row.get('New_Departure_Time')):
            time_val = str(row['New_Departure_Time'])
            if '.' in time_val: time_val = time_val.split('.')[0]
            parts.append(f"**延误至 (EOBT)**: `{time_val.zfill(4)}`")

    elif msg_type == 'CHG':
        if pd.notna(row.get('New_RegNo')):
            parts.append(f"**机号变更 (REG)**: -> `{row['New_RegNo']}`")
        if pd.notna(row.get('New_Departure_Time')):
            parts.append(f"**时刻变更 (EOBT)**: -> `{str(row['New_Departure_Time']).zfill(4)}`")
        if pd.notna(row.get('New_Destination')):
            detail = f"`{row.get('ArrAirport')}` -> `{row['New_Destination']}`"
            if pd.notna(row.get('New_Alternate_1')):
                alt_info = f"{row['New_Alternate_1']} {row.get('New_Alternate_2', '')}".strip()
                detail += f" (备降场: `{alt_info}`)"
            parts.append(f"**航站变更 (DEST)**: {detail}")
        if pd.notna(row.get('New_Route')):
            parts.append(f"**航路变更**: `...`")
        if pd.notna(row.get('New_Mission_STS')):
            parts.append(f"**任务变更 (STS)**: `{row['New_Mission_STS']}`")

    if not parts:
        raw_msg = str(row.get('RawMessage', ''))
        return f"```{raw_msg[:120].strip()}...```" if len(raw_msg) > 120 else f"```{raw_msg.strip()}```"

    return ' <br> '.join(parts)


def generate_unified_report():
    """主函数"""
    print("--- 开始生成航班动态时间轴分析报告 (V4 - 完整信息修正版) ---")

    try:
        aftn_df = pd.read_csv(AFTN_ANALYSIS_FILE, low_memory=False)
        fpla_df = pd.read_csv(FPLA_ANALYSIS_FILE, low_memory=False)
    except FileNotFoundError as e:
        print(f"错误: 找不到输入文件。\n详细错误: {e}");
        return

    aftn_df['Source'] = 'AFTN'
    fpla_df['Source'] = 'FPLA'
    fpla_df.rename(columns={'MessageType': 'FPLA_Status'}, inplace=True)

    for df in [aftn_df, fpla_df]:
        df['ReceiveTime'] = pd.to_datetime(df['ReceiveTime'], errors='coerce')

    timeline_df = pd.concat([aftn_df, fpla_df], ignore_index=True)
    timeline_df.dropna(subset=['ReceiveTime', 'FlightKey'], inplace=True)
    timeline_df.sort_values(by=['FlightKey', 'ReceiveTime'], inplace=True)

    flights_with_aftn = set(aftn_df['FlightKey'].unique())
    all_flights = timeline_df['FlightKey'].unique()
    flights_to_process = [fk for fk in all_flights if fk in flights_with_aftn]

    print(f"共发现 {len(all_flights)} 个航班，将为其中 {len(flights_to_process)} 个包含AFTN消息的航班生成报告。")

    if FLIGHTS_TO_ANALYZE != -1:
        flights_to_process = flights_to_process[:FLIGHTS_TO_ANALYZE]

    with open(MD_REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"# 航班动态时间轴分析报告 ({TARGET_DATE_STR})\n\n")
        f.write(
            "本报告整合了AFTN和FPLA两个数据源的消息，**仅包含那些至少有一条AFTN消息的航班**，并按时间顺序排列以便分析。\n\n")

        for i, flight_key in enumerate(flights_to_process):
            if flight_key == 'KEY_GENERATION_FAILED': continue

            f.write(f"## {i + 1}. 航班: `{flight_key}`\n\n")

            flight_timeline = timeline_df[timeline_df['FlightKey'] == flight_key]

            f.write("| No. | Source | ReceiveTime (UTC) | Message Type | Core Business Information |\n")
            f.write("|:---:|:------:|:------------------|:-------------|:--------------------------|\n")

            for index, row in flight_timeline.iterrows():
                source = row['Source']
                receive_time = row['ReceiveTime'].strftime('%Y-%m-%d %H:%M:%S')
                msg_type = row.get('MessageType', '') if source == 'AFTN' else row.get('FPLA_Status', '')
                info = format_aftn_info(row) if source == 'AFTN' else format_fpla_info(row)

                f.write(f"| {index + 1} | **{source}** | {receive_time} | `{msg_type}` | {info} |\n")

            f.write("\n---\n\n")

    print(f"\n报告生成完毕！请查看文件: {MD_REPORT_FILE}")


# ==============================================================================
# --- 程序入口 ---
# ==============================================================================
if __name__ == "__main__":
    generate_unified_report()