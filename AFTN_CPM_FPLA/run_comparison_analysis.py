import pandas as pd
import numpy as np
import re
from datetime import datetime, timedelta

# ==============================================================================
# --- 1. 配置与加载区 ---
# ==============================================================================
TARGET_DATE_STR = "2025-07-08"
AFTN_PROCESSED_FILE = f'processed_aftn_dynamic_final_{TARGET_DATE_STR}.csv'
FPLA_PROCESSED_FILE = f'processed_fpla_plan_final_{TARGET_DATE_STR}.csv'
COMPARISON_REPORT_FILE = f'comparison_report_final_{TARGET_DATE_STR}.csv'


# ==============================================================================
# --- 2. 辅助函数与映射关系 ---
# ==============================================================================

def convert_to_comparable_sobt(row, target_date):
    """将AFTN的时刻和日期信息转换为标准的datetime对象。"""
    time_str = row.get('New_Departure_Time')
    if pd.isna(time_str):
        return None

    time_str = str(int(time_str)).zfill(4)

    date_part = target_date
    dof_str = row.get('New_DOF')
    if pd.notna(dof_str):
        try:
            date_part = datetime.strptime(f"20{int(dof_str)}", "%Y%m%d").date()
        except:
            pass  # 如果格式错误，则使用target_date

    return datetime.combine(date_part, datetime.strptime(time_str, "%H%M").time())


def identify_aftn_event(current_row, timeline_group):
    """识别单条AFTN消息代表的核心变更事件。"""
    msg_type = current_row['MessageType']

    # 获取此AFTN消息之前，该航班的最新状态
    previous_states = timeline_group[timeline_group['ReceiveTime'] < current_row['ReceiveTime']]

    # 获取最新的AFTN状态
    previous_aftn_state = previous_states[previous_states['Source'] == 'AFTN'].iloc[-1] if not previous_states[
        previous_states['Source'] == 'AFTN'].empty else {}

    if msg_type == 'FPL': return 'ADD', None
    if msg_type == 'CNL': return 'CNL', None

    if msg_type == 'DLA' or (msg_type == 'CHG' and pd.notna(current_row['New_Departure_Time'])):
        return 'TIME_CHANGE', convert_to_comparable_sobt(current_row, TARGET_DATE_OBJ)

    if msg_type == 'CHG':
        # 机号变更
        new_reg = current_row.get('New_RegNo')
        if pd.notna(new_reg) and new_reg != previous_aftn_state.get('RegNo', previous_aftn_state.get('New_RegNo')):
            return 'REG_CHANGE', new_reg

        # 任务变更
        if pd.notna(current_row['New_Mission_STS']) or pd.notna(current_row['New_FlightType']):
            return 'MISSION_CHANGE', f"STS:{current_row.get('New_Mission_STS')}, Type:{current_row.get('New_FlightType')}"

        # 航站变更
        new_dest = current_row.get('New_Destination')
        if pd.notna(new_dest):
            orig_dep = previous_aftn_state.get('DepAirport', previous_aftn_state.get('New_Departure_Airport'))
            orig_dest = previous_aftn_state.get('ArrAirport', previous_aftn_state.get('New_Destination'))
            if new_dest == orig_dep:
                return 'RETURN', new_dest
            elif new_dest != orig_dest:
                return 'TERMINAL_CHANGE', new_dest

    return 'OTHER_UPDATE', None


def find_fpla_correspondence(aftn_event_type, aftn_event_time, aftn_event_detail, fpla_timeline):
    """在FPLA时间轴上寻找与AFTN事件对应的消息。"""
    # 从AFTN事件发生时间之后开始查找
    future_fpla_messages = fpla_timeline[fpla_timeline['ReceiveTime'] >= aftn_event_time]

    for index, fpla_row in future_fpla_messages.iterrows():
        fpla_status = fpla_row['MessageType']

        if aftn_event_type == 'ADD' and fpla_status == 'ADD':
            return fpla_row
        if aftn_event_type == 'CNL' and fpla_status == 'CNL':
            return fpla_row
        if aftn_event_type == 'REG_CHANGE' and fpla_row['RegNo'] == aftn_event_detail:
            return fpla_row
        if aftn_event_type == 'TIME_CHANGE' and fpla_row['SOBT'] == aftn_event_detail:
            return fpla_row
        if aftn_event_type == 'RETURN' and fpla_status == 'RTN':
            return fpla_row
        if aftn_event_type == 'TERMINAL_CHANGE':
            if fpla_status == 'ALN' and fpla_row['ArrAirport'] == aftn_event_detail:
                return fpla_row
            # 也可以匹配UPD中目的地变更的情况
            if fpla_status == 'UPD' and fpla_row['ArrAirport'] == aftn_event_detail:
                return fpla_row

    return None  # 如果找不到，返回None


# ==============================================================================
# --- 3. 主对比逻辑 ---
# ==============================================================================
def run_comparison_analysis():
    """执行完整的对比分析流程。"""
    print("--- 开始执行AFTN与FPLA的精确对比分析 ---")

    # --- 1. 数据加载 ---
    try:
        aftn_df = pd.read_csv(AFTN_PROCESSED_FILE, low_memory=False)
        fpla_df = pd.read_csv(FPLA_PROCESSED_FILE, low_memory=False)
    except FileNotFoundError as e:
        print(f"错误: 无法找到输入文件。请确保以下文件存在: \n{AFTN_PROCESSED_FILE}\n{FPLA_PROCESSED_FILE}")
        print(f"详细错误: {e}")
        return

    # --- 2. 数据预处理与合并 ---
    aftn_df['Source'] = 'AFTN'
    fpla_df['Source'] = 'FPLA'

    # 统一时间格式以便排序和计算
    for df in [aftn_df, fpla_df]:
        df['ReceiveTime'] = pd.to_datetime(df['ReceiveTime'], errors='coerce')
    fpla_df['SOBT'] = pd.to_datetime(fpla_df['SOBT'], errors='coerce')

    timeline_df = pd.concat([aftn_df, fpla_df], ignore_index=True)
    timeline_df.dropna(subset=['ReceiveTime'], inplace=True)
    timeline_df.sort_values(by=['FlightKey', 'ReceiveTime'], inplace=True)

    print(f"数据加载与合并完成，共计 {len(timeline_df)} 条时间轴记录。")

    # --- 3. 逐事件对比 ---
    comparison_results = []

    # 筛选出所有AFTN消息进行遍历
    aftn_messages = timeline_df[timeline_df['Source'] == 'AFTN']

    for index, aftn_row in aftn_messages.iterrows():
        flight_key = aftn_row['FlightKey']

        # 获取该航班的完整时间轴
        flight_timeline = timeline_df[timeline_df['FlightKey'] == flight_key]

        # 识别AFTN事件
        event_type, event_detail = identify_aftn_event(aftn_row, flight_timeline)

        if event_type is None: continue  # 忽略无法识别的事件

        # 在FPLA轨道上寻找对应消息
        fpla_timeline = flight_timeline[flight_timeline['Source'] == 'FPLA']
        fpla_corr_row = find_fpla_correspondence(event_type, aftn_row['ReceiveTime'], event_detail, fpla_timeline)

        # --- 4. 记录对比结果 ---
        result_record = {
            'FlightKey': flight_key,
            'AFTN_Event_Type': event_type,
            'AFTN_ReceiveTime': aftn_row['ReceiveTime'],
            'AFTN_Change_Detail': str(event_detail),
            'AFTN_RawMessage': aftn_row.get('RawMessage', '')
        }

        if fpla_corr_row is not None:
            time_diff = (fpla_corr_row['ReceiveTime'] - aftn_row['ReceiveTime']).total_seconds() / 60.0

            result_record.update({
                'FPLA_Found': 'Yes',
                'FPLA_ReceiveTime': fpla_corr_row['ReceiveTime'],
                'FPLA_Status': fpla_corr_row['MessageType'],
                'Time_Diff_Minutes': round(time_diff, 2),
                'Match_Status': 'Consistent'
            })

            # 识别FPLA的优越性
            if event_type in ['RETURN', 'TERMINAL_CHANGE'] and fpla_corr_row['MessageType'] in ['RTN', 'ALN']:
                result_record['Match_Status'] = 'Superior (More Specific)'

        else:
            result_record.update({
                'FPLA_Found': 'No',
                'FPLA_ReceiveTime': None,
                'FPLA_Status': None,
                'Time_Diff_Minutes': None,
                'Match_Status': 'FPLA_MISSING'
            })

        comparison_results.append(result_record)

    # --- 5. 保存报告 ---
    report_df = pd.DataFrame(comparison_results)
    report_df.to_csv(COMPARISON_REPORT_FILE, index=False, encoding='utf-8-sig')
    print(f"\n对比分析完成！详细报告已保存至: {COMPARISON_REPORT_FILE}")


# ==============================================================================
# --- 4. 程序入口 ---
# ==============================================================================
if __name__ == "__main__":
    TARGET_DATE_OBJ = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d").date()
    run_comparison_analysis()