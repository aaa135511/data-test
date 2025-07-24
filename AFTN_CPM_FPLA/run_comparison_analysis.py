import pandas as pd
import numpy as np
import re
from datetime import datetime, timedelta

# ==============================================================================
# --- 1. 配置区 ---
# ==============================================================================
TARGET_DATE_STR = "2025-07-08"
AFTN_PROCESSED_FILE = f'processed_aftn_dynamic_final_{TARGET_DATE_STR}.csv'
FPLA_PROCESSED_FILE = f'processed_fpla_plan_final_{TARGET_DATE_STR}.csv'

# 输出文件名
COMPARISON_ADD_FILE = f'comparison_ADD_{TARGET_DATE_STR}.csv'
COMPARISON_CNL_FILE = f'comparison_CNL_{TARGET_DATE_STR}.csv'
COMPARISON_TIME_CHANGE_FILE = f'comparison_TIME_CHANGE_{TARGET_DATE_STR}.csv'
COMPARISON_REG_CHANGE_FILE = f'comparison_REG_CHANGE_{TARGET_DATE_STR}.csv'
COMPARISON_INCONSISTENT_FILE = f'comparison_INCONSISTENT_{TARGET_DATE_STR}.csv'


# ==============================================================================
# --- 2. 辅助函数 ---
# ==============================================================================
def convert_to_comparable_sobt(row, target_date):
    """将AFTN的时刻和日期信息转换为标准的datetime对象，以便比较。"""
    time_str = row.get('New_Departure_Time')
    if pd.isna(time_str) or time_str == '': return None
    try:
        time_str = str(int(float(time_str))).zfill(4)
        date_part = target_date
        dof_str = row.get('New_DOF')
        if pd.notna(dof_str):
            date_part = datetime.strptime(f"20{int(dof_str)}", "%Y%m%d").date()
        return datetime.combine(date_part, datetime.strptime(time_str, "%H%M").time())
    except (ValueError, TypeError):
        return None


# ==============================================================================
# --- 3. 主对比逻辑 ---
# ==============================================================================

def run_comparison_analysis():
    print("--- 开始执行基于数据洞察的精确对比分析 V4 (已修正) ---")

    # --- 1. 数据加载 ---
    try:
        aftn_df = pd.read_csv(AFTN_PROCESSED_FILE, low_memory=False)
        fpla_df = pd.read_csv(FPLA_PROCESSED_FILE, low_memory=False)
    except FileNotFoundError as e:
        print(f"错误: 无法找到输入文件。请确保预处理文件存在。\n{e}")
        return

    # --- 2. 数据准备与统一化 ---
    # 对AFTN数据进行转换，生成可比较的字段
    aftn_df['ReceiveTime'] = pd.to_datetime(aftn_df['ReceiveTime'], errors='coerce')
    aftn_df['ComparableSOBT'] = aftn_df.apply(lambda row: convert_to_comparable_sobt(row, TARGET_DATE_OBJ), axis=1)

    # 对FPLA数据进行准备
    fpla_df['ReceiveTime'] = pd.to_datetime(fpla_df['ReceiveTime'], errors='coerce')
    fpla_df['SOBT'] = pd.to_datetime(fpla_df['SOBT'], errors='coerce')

    all_flight_keys = set(aftn_df['FlightKey'].dropna()) | set(fpla_df['FlightKey'].dropna())
    print(f"共发现 {len(all_flight_keys)} 个独立航班进行分析。")

    results = {
        'ADD': [], 'CNL': [], 'TIME_CHANGE': [], 'REG_CHANGE': [], 'INCONSISTENT': []
    }

    # --- 3. 逐航班进行对比分析 ---
    for flight_key in all_flight_keys:
        aftn_timeline = aftn_df[aftn_df['FlightKey'] == flight_key].sort_values('ReceiveTime').reset_index(drop=True)
        fpla_timeline = fpla_df[fpla_df['FlightKey'] == flight_key].sort_values('ReceiveTime').reset_index(drop=True)

        # 1. 对比航班新增 (ADD)
        aftn_add_time = aftn_timeline[aftn_timeline['MessageType'] == 'FPL']['ReceiveTime'].min()
        fpla_add_time = fpla_timeline[fpla_timeline['MessageType'].isin(['ADD', 'ALL'])]['ReceiveTime'].min()
        results['ADD'].append({
            'FlightKey': flight_key,
            'FPLA_First_Receive': fpla_add_time,
            'AFTN_First_Receive': aftn_add_time,
            'Lead_Time_Hours': round((aftn_add_time - fpla_add_time).total_seconds() / 3600, 2) if pd.notna(
                aftn_add_time) and pd.notna(fpla_add_time) else np.nan
        })

        # 2. 对比航班取消 (CNL)
        aftn_cnl_time = aftn_timeline[aftn_timeline['MessageType'] == 'CNL']['ReceiveTime'].min()
        fpla_cnl_time = fpla_timeline[fpla_timeline['MessageType'] == 'CNL']['ReceiveTime'].min()
        if pd.notna(aftn_cnl_time) or pd.notna(fpla_cnl_time):
            results['CNL'].append({
                'FlightKey': flight_key,
                'FPLA_CNL_Time': fpla_cnl_time,
                'AFTN_CNL_Time': aftn_cnl_time
            })

        # 3. 对比机号变更 (以FPLA为基准)
        fpla_timeline['RegNo_lag'] = fpla_timeline['RegNo'].shift(1)
        fpla_reg_changes = fpla_timeline[fpla_timeline['RegNo'] != fpla_timeline['RegNo_lag']]
        for idx, change in fpla_reg_changes.iterrows():
            if idx == 0 and pd.notna(change['RegNo']):  # 首次出现机号也算一次事件
                pass
            elif idx == 0:
                continue

            event_time = change['ReceiveTime'];
            new_reg = change['RegNo']
            aftn_corr = aftn_timeline[
                (aftn_timeline['New_RegNo'] == new_reg) & (aftn_timeline['ReceiveTime'] >= event_time)]
            results['REG_CHANGE'].append({
                'FlightKey': flight_key, 'FPLA_Event_Time': event_time, 'New_RegNo': new_reg,
                'AFTN_Match_Time': aftn_corr['ReceiveTime'].min()
            })

        # 4. 对比时刻变更 (以FPLA为基准)
        fpla_timeline['SOBT_lag'] = fpla_timeline['SOBT'].shift(1)
        fpla_time_changes = fpla_timeline[fpla_timeline['SOBT'] != fpla_timeline['SOBT_lag']]
        for idx, change in fpla_time_changes.iterrows():
            if idx == 0 and pd.notna(change['SOBT']):
                pass
            elif idx == 0:
                continue
            event_time = change['ReceiveTime'];
            new_sobt = change['SOBT']
            aftn_corr = aftn_timeline[aftn_timeline['ComparableSOBT'] == new_sobt]
            results['TIME_CHANGE'].append({
                'FlightKey': flight_key, 'FPLA_Event_Time': event_time, 'New_SOBT': new_sobt,
                'AFTN_Match_Time': aftn_corr['ReceiveTime'].min()
            })

        # 5. 检查严重不一致 (以AFTN的DLA为基准)
        if not fpla_timeline.empty and not aftn_timeline.empty:
            last_fpla_sobt = fpla_timeline.iloc[-1]['SOBT']
            dla_messages = aftn_timeline[aftn_timeline['MessageType'] == 'DLA']
            for idx, dla in dla_messages.iterrows():
                aftn_sobt = dla['ComparableSOBT']
                if pd.notna(last_fpla_sobt) and pd.notna(aftn_sobt) and abs(
                    (last_fpla_sobt - aftn_sobt).total_seconds()) > 60:  # 超过1分钟差异就算不一致
                    results['INCONSISTENT'].append({
                        'FlightKey': flight_key, 'FPLA_Final_SOBT': last_fpla_sobt, 'AFTN_DLA_Time': aftn_sobt,
                        'AFTN_Receive_Time': dla['ReceiveTime'], 'AFTN_RawMessage': dla['RawMessage']
                    })

    # --- 4. 保存报告 ---
    pd.DataFrame(results['ADD']).to_csv(COMPARISON_ADD_FILE, index=False, encoding='utf-8-sig')
    pd.DataFrame(results['CNL']).to_csv(COMPARISON_CNL_FILE, index=False, encoding='utf-8-sig')
    pd.DataFrame(results['TIME_CHANGE']).to_csv(COMPARISON_TIME_CHANGE_FILE, index=False, encoding='utf-8-sig')
    pd.DataFrame(results['REG_CHANGE']).to_csv(COMPARISON_REG_CHANGE_FILE, index=False, encoding='utf-8-sig')
    pd.DataFrame(results['INCONSISTENT']).to_csv(COMPARISON_INCONSISTENT_FILE, index=False, encoding='utf-8-sig')

    print(f"\n对比分析完成！已生成以下5份详细报告:")
    print(f" - {COMPARISON_ADD_FILE} (航班新增对比)")
    print(f" - {COMPARISON_CNL_FILE} (航班取消对比)")
    print(f" - {COMPARISON_TIME_CHANGE_FILE} (时刻变更对比)")
    print(f" - {COMPARISON_REG_CHANGE_FILE} (机号变更对比)")
    print(f" - {COMPARISON_INCONSISTENT_FILE} (严重不一致记录)")


# ==============================================================================
# --- 4. 程序入口 ---
# ==============================================================================
if __name__ == "__main__":
    TARGET_DATE_OBJ = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d").date()
    run_comparison_analysis()