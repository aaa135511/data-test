import pandas as pd
import numpy as np
from datetime import datetime

# --- 配置 ---
FPLA_EXCEL_FILE = 'fpla_message-20250708.xlsx'
TELEGRAM_EXCEL_FILE = 'telegram_comparison_ready_data.xlsx'
TARGET_EXEC_DATE = '2025-07-08'
OUTPUT_COMPARISON_RESULT_FILE = f'comparison_result_v7.0_correct_{TARGET_EXEC_DATE.replace("-", "")}.xlsx'

# --- 匹配规则引擎 (v2.0 - 保持不变) ---
MATCHING_RULES = {
    'DLA': ['DLA', 'SLOTCHG'],
    'CHG': ['UPD', 'SLOTCHG', 'CNLPART'],
    'CNL': ['CNL'],
    'FPL': ['ADD'],
}
CPL_MATCHING_RULES = {
    'ALTERNATE': ['ALN', 'ALNADD'],
    'RETURN': ['RTN', 'RTNADD']
}


# --- 主对比函数 ---
def correct_match_logic(fpla_file, telegram_file, target_date):
    """
    主对比程序：采用最终正确逻辑，在匹配前彻底过滤掉DEP和ARR报文。
    """
    print("--- [步骤 0] 开始加载和预处理数据 ---")
    try:
        fpla_df = pd.read_excel(fpla_file, dtype=str)
        fpla_df['UPDATETIME'] = pd.to_datetime(fpla_df['UPDATETIME'], errors='coerce')
        fpla_df = fpla_df.dropna(subset=['UPDATETIME', 'CALLSIGN', 'DEPAP', 'SOBT'])
        fpla_df['CALLSIGN'] = fpla_df['CALLSIGN'].str.strip()
        fpla_df['FPLA_ExecDate'] = pd.to_datetime(fpla_df['SOBT'].str.slice(0, 8), format='%Y%m%d',
                                                  errors='coerce').dt.strftime('%Y-%m-%d')
        fpla_df_target = fpla_df[fpla_df['FPLA_ExecDate'] == target_date].copy()
        print(f"[LOG] FPLA文件加载成功，筛选出 {len(fpla_df_target)} 条目标日期的记录。")

        tg_df = pd.read_excel(telegram_file, dtype=str)
        tg_df['MessageTimestamp'] = pd.to_datetime(tg_df['MessageTimestamp'], errors='coerce')
        tg_df = tg_df.dropna(subset=['MessageTimestamp', 'Callsign', 'dofExecDate'])
        tg_df['dofExecDate'] = pd.to_datetime(tg_df['dofExecDate']).dt.strftime('%Y-%m-%d')
        tg_df_target = tg_df[tg_df['dofExecDate'] == target_date].copy()
        tg_df_target['MessageType'] = tg_df_target['MessageType'].str.replace('AFTN_', '')
        print(f"[LOG] 电报文件加载成功，筛选出 {len(tg_df_target)} 条目标日期的记录。")

    except Exception as e:
        print(f"致命错误: 加载或预处理文件时出错 - {e}")
        return

    # --- [步骤 1] 核心修正：从源头过滤掉DEP和ARR ---
    matchable_types = ['DLA', 'CHG', 'CNL', 'CPL', 'FPL']
    tg_plan_changes_df = tg_df_target[tg_df_target['MessageType'].isin(matchable_types)].copy()

    print(f"\n--- [步骤 1] 核心逻辑变更 ---")
    print(f"[LOG] 已从目标日期的电报数据中过滤，只保留计划变更类报文。剩余 {len(tg_plan_changes_df)} 条。")
    if not tg_plan_changes_df.empty:
        print("[DEBUG] 剩余的计划变更类报文分布情况:")
        print(tg_plan_changes_df['MessageType'].value_counts())
    print("-" * 30)

    # --- [步骤 2] 获取每个航班最新的“计划变更”事件 ---
    if tg_plan_changes_df.empty:
        print("警告：在目标日期内，未找到任何计划变更类电报 (DLA, CHG, CNL, CPL, FPL)。程序结束。")
        return

    latest_tg_events = tg_plan_changes_df.sort_values('MessageTimestamp').groupby('Callsign').tail(1)
    print(f"--- [步骤 2] 完成: 找到 {len(latest_tg_events)} 个在 {target_date} 有最新“计划变更”的航班。---\n")

    comparison_results = []
    all_tg_flights = set(tg_df_target['Callsign'].unique())
    processed_tg_flights = set(latest_tg_events['Callsign'].unique())

    # --- [步骤 3] 遍历最新的计划变更事件进行匹配 ---
    for _, tg_event in latest_tg_events.iterrows():
        callsign = tg_event['Callsign']
        result = {'Callsign': callsign, 'Match_Result': '', 'Details': ''}
        result['Telegram_Latest_Type'] = tg_event['MessageType']
        result['Telegram_Latest_Time'] = tg_event['MessageTimestamp']

        fpla_group_df = fpla_df_target[fpla_df_target['CALLSIGN'] == callsign]

        if fpla_group_df.empty:
            result['Match_Result'] = 'FPLA中未找到对应航班'
            comparison_results.append(result)
            continue

        tg_type = tg_event['MessageType']
        equivalent_statuses = []
        if tg_type == 'CPL':
            tg_abnormal_status = tg_event.get('abnormalStatus', '')
            if tg_abnormal_status in CPL_MATCHING_RULES: equivalent_statuses = CPL_MATCHING_RULES[tg_abnormal_status]
        elif tg_type in MATCHING_RULES:
            equivalent_statuses = MATCHING_RULES[tg_type]

        if not equivalent_statuses: continue

        fpla_candidates = fpla_group_df[fpla_group_df['PSCHEDULESTATUS'].isin(equivalent_statuses)].copy()

        if fpla_candidates.empty:
            result['Match_Result'] = '事件类型不匹配'
            result['Details'] = f"电报最新计划变更({tg_type})在FPLA中无对应类型({equivalent_statuses})的动态"
            comparison_results.append(result)
            continue

        fpla_candidates['Time_Diff'] = (
                fpla_candidates['UPDATETIME'] - tg_event['MessageTimestamp']).dt.total_seconds().abs()
        fpla_best_match = fpla_candidates.loc[fpla_candidates['Time_Diff'].idxmin()]

        result['Match_Result'] = '成功匹配'
        result['FPLA_Matched_Type'] = fpla_best_match['PSCHEDULESTATUS']
        result['FPLA_Matched_Time'] = fpla_best_match['UPDATETIME']
        time_diff_minutes = (fpla_best_match['UPDATETIME'] - tg_event['MessageTimestamp']).total_seconds() / 60
        result['Time_Diff_Minutes'] = round(time_diff_minutes, 2)

        comparison_results.append(result)

    # --- [步骤 4] 标记那些只有DEP/ARR的航班 ---
    flights_without_plan_changes = all_tg_flights - processed_tg_flights
    for flight in flights_without_plan_changes:
        result = {'Callsign': flight, 'Match_Result': '无计划变更事件',
                  'Details': '该航班在电报中只有起飞/落地等非计划变更类消息'}
        comparison_results.append(result)

    # --- [步骤 5] 输出结果 ---
    result_df = pd.DataFrame(comparison_results).fillna('')
    result_df.to_excel(OUTPUT_COMPARISON_RESULT_FILE, index=False, engine='openpyxl')
    print(f"\n--- 对比程序执行完毕！ ---")
    print(f"结果已保存到文件: '{OUTPUT_COMPARISON_RESULT_FILE}'")


if __name__ == '__main__':
    correct_match_logic(FPLA_EXCEL_FILE, TELEGRAM_EXCEL_FILE, TARGET_EXEC_DATE)