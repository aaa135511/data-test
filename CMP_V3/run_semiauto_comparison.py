import os
import re
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# ==============================================================================
# --- 1. 配置加载 ---
# ==============================================================================
load_dotenv()
TARGET_DATE_STR = os.getenv("TARGET_DATE")
if not TARGET_DATE_STR:
    print("错误: 未在 .env 文件中找到 TARGET_DATE 设置。");
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREPROCESSED_DIR = os.path.join(BASE_DIR, 'preprocessed_files')
COMPARE_RESULT_DIR = os.path.join(BASE_DIR, 'compare_result')
AFTN_ANALYSIS_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_aftn_data_{TARGET_DATE_STR}.csv')
FPLA_ANALYSIS_FILE = os.path.join(PREPROCESSED_DIR, f'analysis_fpla_data_{TARGET_DATE_STR}.csv')
PLAN_COMPARISON_FILE = os.path.join(COMPARE_RESULT_DIR, f'plan_comparison_report_{TARGET_DATE_STR}.xlsx')
DYNAMIC_COMPARISON_FILE = os.path.join(COMPARE_RESULT_DIR, f'dynamic_comparison_report_{TARGET_DATE_STR}.xlsx')


# ==============================================================================
# --- 2. 辅助函数 ---
# ==============================================================================
def convert_utc_str_to_bjt(time_str, date_obj):
    """
    将UTC时间字符串转换为北京时间 (BJT)。
    Args:
        time_str (str): UTC时间字符串，例如 '1230'。
        date_obj (datetime.date): 对应的日期对象。
    Returns:
        datetime.datetime: 转换后的北京时间 datetime 对象，如果转换失败则为 pd.NaT。
    """
    if pd.isna(time_str): return pd.NaT
    try:
        # 确保时间字符串是4位，不足补零
        time_val_str = str(time_str).split('.')[0].zfill(4)
        utc_dt = datetime.combine(date_obj, datetime.strptime(time_val_str, "%H%M").time())
        return utc_dt + timedelta(hours=8)  # UTC+8 为北京时间
    except Exception:
        return pd.NaT


def format_time(dt_obj):
    """
    格式化 datetime 对象为 'MM-DD HH:MM' 字符串。
    Args:
        dt_obj (datetime.datetime): 要格式化的 datetime 对象。
    Returns:
        str: 格式化后的时间字符串，如果为 pd.NaT 则返回空字符串。
    """
    if pd.isna(dt_obj): return ''
    return dt_obj.strftime('%m-%d %H:%M')


def parse_fpla_time(time_val):
    """
    解析 FPLA 中的时间字符串为 datetime 对象。
    Args:
        time_val (str): FPLA 时间字符串，可能是 'YYYYMMDDHHMM' 或 'YYYYMMDDHHMMSS'。
    Returns:
        datetime.datetime: 解析后的 datetime 对象，如果解析失败则为 pd.NaT。
    """
    if pd.isna(time_val): return pd.NaT
    try:
        time_str = str(time_val).split('.')[0]
        # 根据字符串长度选择日期时间格式
        format_str = '%Y%m%d%H%M%S' if len(time_str) == 14 else '%Y%m%d%H%M'
        return pd.to_datetime(time_str, format=format_str, errors='coerce')
    except Exception:
        return pd.NaT


def auto_set_column_width(df, writer, sheet_name):
    """
    根据DataFrame内容自动设置Excel工作表的列宽。
    Args:
        df (pd.DataFrame): 要写入的DataFrame。
        writer (pd.ExcelWriter): Excel写入器对象。
        sheet_name (str): 工作表名称。
    """
    # 获取工作表对象
    worksheet = writer.sheets[sheet_name]

    # 遍历DataFrame的每一列及其索引
    for i, col in enumerate(df.columns):
        # 计算列标题的长度
        max_len_header = len(str(col))

        # 计算列中所有值的最大长度
        # 将所有值转换为字符串，并处理NaN值（转换为0长度的字符串或特定表示）
        # .astype(str) 会将NaN转换为'nan'，因此需要进一步处理或确保数据类型合适
        max_len_values = df[col].astype(str).apply(lambda x: len(x) if pd.notna(x) else 0).max()

        # 确定该列的最终最大长度，取标题和内容中的最大值
        actual_max_len = max(max_len_header, max_len_values)

        # 添加一个缓冲区（例如5个字符）以提供更好的可读性
        column_width = actual_max_len + 5

        # 设置列宽 (从0开始的列索引, 到0开始的列索引, 宽度)
        worksheet.set_column(i, i, column_width)


# ==============================================================================
# --- 3. 核心对比逻辑 ---
# ==============================================================================
def run_plan_comparison(aftn_df, fpla_df, target_date_obj):
    """
    执行第一阶段对比：最终计划状态快照对比。
    对比AFTN最新FPL消息与FPLA最新计划消息的机号和SOBT。
    Args:
        aftn_df (pd.DataFrame): 预处理后的AFTN数据。
        fpla_df (pd.DataFrame): 预处理后的FPLA数据。
        target_date_obj (datetime.date): 目标日期对象。
    Returns:
        pd.DataFrame: 计划对比结果报告。
    """
    print("--- 正在执行 [第一阶段]：最终计划状态快照对比 ---")
    plan_results = []
    # 找出AFTN和FPLA中都存在的航班键
    common_flight_keys = set(aftn_df['FlightKey'].unique()) & set(fpla_df['FlightKey'].unique())

    for flight_key in common_flight_keys:
        # 获取AFTN中该航班最新的FPL消息
        aftn_fpls = aftn_df[(aftn_df['FlightKey'] == flight_key) & (aftn_df['MessageType'] == 'FPL')].sort_values(
            'ReceiveTime', ascending=False)
        # 获取FPLA中该航班最新的计划消息 (ADD, ALL, UPD状态)
        fpla_plans = fpla_df[
            (fpla_df['FlightKey'] == flight_key) & (fpla_df['FPLA_Status'].isin(['ADD', 'ALL', 'UPD']))].sort_values(
            'ReceiveTime', ascending=False)

        if aftn_fpls.empty or fpla_plans.empty:
            continue

        latest_fpl = aftn_fpls.iloc[0]  # 最新FPL消息
        latest_fpla_plan = fpla_plans.iloc[0]  # 最新FPLA计划消息

        # 从FPL消息中解析EOBT (预计离港时间)
        fpl_time_match = re.search(r'-\w{4,7}(\d{4})\s', latest_fpl.get('RawMessage', ''))
        fpl_eobt_str = fpl_time_match.group(1) if fpl_time_match else np.nan

        # 从FPL消息中解析DOF (日期)
        dof_match = re.search(r'DOF/(\d{6})', latest_fpl.get('RawMessage', ''))
        # 如果找到DOF，则使用DOF作为基准日期，否则使用目标日期
        base_date = datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date() if dof_match else target_date_obj

        # 将FPL的EOBT转换为北京时间
        fpl_sobt_bjt = convert_utc_str_to_bjt(fpl_eobt_str, base_date)
        # 解析FPLA的SOBT
        fpla_sobt = parse_fpla_time(latest_fpla_plan['SOBT'])

        # 对比机号和SOBT
        reg_match = (str(latest_fpl.get('RegNo')).strip() == str(latest_fpla_plan.get('RegNo')).strip())
        sobt_match = (format_time(fpl_sobt_bjt) == format_time(fpla_sobt))

        status = []
        if not reg_match:
            status.append("机号不一致")
        if not sobt_match:
            status.append("时刻不一致")

        # 记录对比结果
        plan_results.append({
            'FlightKey': flight_key,
            'Latest_FPL_ReceiveTime': latest_fpl.get('ReceiveTime'),
            'Latest_FPLA_Plan_ReceiveTime': latest_fpla_plan.get('ReceiveTime'),
            'FPL_RegNo': latest_fpl.get('RegNo'),
            'FPLA_RegNo': latest_fpla_plan.get('RegNo'),
            'FPL_SOBT_BJT': format_time(fpl_sobt_bjt),
            'FPLA_SOBT': format_time(fpla_sobt),
            'Overall_Plan_Status': "完全一致" if not status else " | ".join(status)
        })
    return pd.DataFrame(plan_results)


def run_dynamic_comparison(aftn_df, fpla_df, target_date_obj):
    """
    【V19最终版】第二阶段：AFTN动态 vs FPLA最新动态(或最新任何消息)
    对比AFTN的DLA/CHG/CPL消息与FPLA最新动态消息。
    Args:
        aftn_df (pd.DataFrame): 预处理后的AFTN数据。
        fpla_df (pd.DataFrame): 预处理后的FPLA数据。
        target_date_obj (datetime.date): 目标日期对象。
    Returns:
        pd.DataFrame: 动态变更事件溯源对比报告。
    """
    print("--- 正在执行 [第二阶段]：动态变更事件溯源对比 ---")
    dynamic_results = []
    # 筛选出AFTN中的动态消息 (DLA, CHG, CPL) 并按接收时间排序
    aftn_dynamics = aftn_df[aftn_df['MessageType'].isin(['DLA', 'CHG', 'CPL'])].sort_values('ReceiveTime')

    for index, aftn_row in aftn_dynamics.iterrows():
        flight_key = aftn_row.get('FlightKey')
        if pd.isna(flight_key):
            continue

        # 获取FPLA中该航班的所有消息时间线
        fpla_timeline = fpla_df[fpla_df['FlightKey'] == flight_key].sort_values('ReceiveTime')
        if fpla_timeline.empty:
            continue

        aftn_event_time = aftn_row['ReceiveTime']
        # 筛选FPLA中的动态消息，如果为空则取最新一条消息
        fpla_dynamic_msgs = fpla_timeline[fpla_timeline['FPLA_Status'].isin(['UPD', 'DLA', 'SLOTCHG', 'ALN', 'RTN'])]
        fpla_compare_state = fpla_dynamic_msgs.iloc[-1] if not fpla_dynamic_msgs.empty else fpla_timeline.iloc[-1]

        if aftn_row['MessageType'] == 'DLA':
            # 处理DLA消息 (时刻变更)
            dof_match = re.search(r'DOF/(\d{6})', aftn_row.get('RawMessage', ''))
            base_date = datetime.strptime(f"20{dof_match.group(1)}", "%Y%m%d").date() if dof_match else target_date_obj
            aftn_new_sobt = convert_utc_str_to_bjt(aftn_row.get('New_Departure_Time'), base_date)
            fpla_compare_sobt = parse_fpla_time(fpla_compare_state.get('SOBT'))

            # 计算时刻差异（分钟）
            time_diff = (aftn_new_sobt - fpla_compare_sobt).total_seconds() / 60.0 if pd.notna(
                aftn_new_sobt) and pd.notna(fpla_compare_sobt) else np.nan

            fpla_compare_status_type = fpla_compare_state.get('FPLA_Status', 'N/A')
            fpla_evidence = f"与FPLA最新动态({fpla_compare_status_type})SOBT: {format_time(fpla_compare_sobt)}对比"

            conclusion = "无法对比"
            if pd.notna(time_diff):
                abs_diff = abs(round(time_diff))
                if abs_diff <= 1:  # 允许1分钟的误差
                    conclusion = "时刻基本一致"
                else:
                    conclusion = f"时刻不一致 (相差 {abs_diff} 分钟)"

            dynamic_results.append({
                'FlightKey': flight_key,
                'AFTN_Event_Time': aftn_event_time,
                'AFTN_Event_Type': 'DLA (时刻变更)',
                'AFTN_Change_Detail': f"New SOBT: {format_time(aftn_new_sobt)} BJT",
                'FPLA_Evidence': fpla_evidence,
                'Conclusion': conclusion
            })

        elif aftn_row['MessageType'] in ['CHG', 'CPL']:
            # 处理CHG/CPL消息 (多字段变更)
            change_found = False

            # 1. 时刻变更 (编组13)
            if pd.notna(aftn_row.get('New_Departure_Time')):
                change_found = True
                aftn_new_sobt = convert_utc_str_to_bjt(aftn_row.get('New_Departure_Time'), aftn_event_time.date())
                fpla_compare_sobt = parse_fpla_time(fpla_compare_state.get('SOBT'))
                time_diff = (aftn_new_sobt - fpla_compare_sobt).total_seconds() / 60.0 if pd.notna(
                    aftn_new_sobt) and pd.notna(fpla_compare_sobt) else np.nan
                conclusion = f"时刻不一致 (相差 {round(time_diff)} 分钟)" if pd.notna(time_diff) and abs(
                    time_diff) > 1 else "时刻基本一致"
                dynamic_results.append({
                    'FlightKey': flight_key,
                    'AFTN_Event_Time': aftn_event_time,
                    'AFTN_Event_Type': f'{aftn_row["MessageType"]} (时刻变更)',
                    'AFTN_Change_Detail': f"New SOBT: {format_time(aftn_new_sobt)} BJT",
                    'FPLA_Evidence': f"与FPLA最新动态({fpla_compare_state.get('FPLA_Status')})SOBT: {format_time(fpla_compare_sobt)}对比",
                    'Conclusion': conclusion
                })
            # 2. 机号变更 (编组18 - REG)
            if pd.notna(aftn_row.get('New_RegNo')):
                change_found = True
                conclusion = "机号不一致"
                if str(fpla_compare_state.get('RegNo')).strip() == str(aftn_row.get('New_RegNo')).strip():
                    conclusion = "机号一致"
                dynamic_results.append({
                    'FlightKey': flight_key,
                    'AFTN_Event_Time': aftn_event_time,
                    'AFTN_Event_Type': f'{aftn_row["MessageType"]} (机号变更)',
                    'AFTN_Change_Detail': f"New RegNo: {aftn_row.get('New_RegNo')}",
                    'FPLA_Evidence': f"与FPLA最新动态({fpla_compare_state.get('FPLA_Status')})机号: {fpla_compare_state.get('RegNo')}对比",
                    'Conclusion': conclusion
                })
            # 3. 航站变更 (编组16)
            if pd.notna(aftn_row.get('New_Destination')):
                change_found = True
                alt1_val = aftn_row.get('New_Alternate_1')
                alt2_val = aftn_row.get('New_Alternate_2')
                alt1 = str(alt1_val) if pd.notna(alt1_val) else ''
                alt2 = str(alt2_val) if pd.notna(alt2_val) else ''
                alt_info = f"{alt1} {alt2}".strip()
                change_detail = f"New Dest: {aftn_row.get('New_Destination')}" + (
                    f", Alt: {alt_info}" if alt_info else "")
                conclusion = "航站信息不一致"
                if str(fpla_compare_state.get('ArrAirport')).strip() == str(aftn_row.get('New_Destination')).strip():
                    conclusion = "航站信息一致"
                dynamic_results.append({
                    'FlightKey': flight_key,
                    'AFTN_Event_Time': aftn_event_time,
                    'AFTN_Event_Type': f'{aftn_row["MessageType"]} (航站变更)',
                    'AFTN_Change_Detail': change_detail,
                    'FPLA_Evidence': f"与FPLA最新动态({fpla_compare_state.get('FPLA_Status')})航程: {fpla_compare_state.get('DepAirport')}->{fpla_compare_state.get('ArrAirport')}对比",
                    'Conclusion': conclusion
                })
            # 4. 机型变更 (编组9)
            if pd.notna(aftn_row.get('New_CraftType')):
                change_found = True
                conclusion = "机型不一致"
                if str(fpla_compare_state.get('CraftType')).strip() == str(aftn_row.get('New_CraftType')).strip():
                    conclusion = "机型一致"
                dynamic_results.append({
                    'FlightKey': flight_key,
                    'AFTN_Event_Time': aftn_event_time,
                    'AFTN_Event_Type': f'{aftn_row["MessageType"]} (机型变更)',
                    'AFTN_Change_Detail': f"New CraftType: {aftn_row.get('New_CraftType')}",
                    'FPLA_Evidence': f"与FPLA最新动态({fpla_compare_state.get('FPLA_Status')})机型: {fpla_compare_state.get('CraftType')}对比",
                    'Conclusion': conclusion
                })
            # 5. 航班号变更 (编组7)
            if pd.notna(aftn_row.get('New_FlightNo')):
                change_found = True
                conclusion = "航班号不一致"
                if str(fpla_compare_state.get('FlightNo')).strip() == str(aftn_row.get('New_FlightNo')).strip():
                    conclusion = "航班号一致"
                dynamic_results.append({
                    'FlightKey': flight_key,
                    'AFTN_Event_Time': aftn_event_time,
                    'AFTN_Event_Type': f'{aftn_row["MessageType"]} (航班号变更)',
                    'AFTN_Change_Detail': f"New FlightNo: {aftn_row.get('New_FlightNo')}",
                    'FPLA_Evidence': f"与FPLA最新动态({fpla_compare_state.get('FPLA_Status')})航班号: {fpla_compare_state.get('FlightNo')}对比",
                    'Conclusion': conclusion
                })

            if not change_found:
                # 如果CHG/CPL消息中未识别出核心字段变更
                dynamic_results.append({
                    'FlightKey': flight_key,
                    'AFTN_Event_Time': aftn_event_time,
                    'AFTN_Event_Type': f'{aftn_row["MessageType"]} (其他变更)',
                    'AFTN_Change_Detail': '未识别出核心字段变更',
                    'FPLA_Evidence': 'N/A',
                    'Conclusion': '不影响地面保障，忽略对比'
                })

    return pd.DataFrame(dynamic_results)


# ==============================================================================
# --- 5. 主程序入口 ---
# ==============================================================================
def main():
    """
    主程序入口，执行数据加载、对比和报告生成。
    """
    if not TARGET_DATE_STR:
        print("错误: 未在 .env 文件中找到 TARGET_DATE 设置。");
        sys.exit(1)
    try:
        target_date_obj = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d").date()
    except ValueError:  # 更明确的错误处理
        print(f"错误: .env 日期格式无效 ({TARGET_DATE_STR})。请确保格式为 YYYY-MM-DD。");
        return

    print(f"\n===== 开始为日期 {TARGET_DATE_STR} 生成对比报告 =====")
    os.makedirs(COMPARE_RESULT_DIR, exist_ok=True)  # 确保结果目录存在

    try:
        # 加载预处理的AFTN和FPLA数据
        aftn_df = pd.read_csv(AFTN_ANALYSIS_FILE, low_memory=False)
        fpla_df = pd.read_csv(FPLA_ANALYSIS_FILE, low_memory=False)
    except FileNotFoundError:
        print(f"错误: 找不到预处理文件。请确保已运行 `generate_analysis_files.py` 并生成了以下文件：")
        print(f" - {AFTN_ANALYSIS_FILE}")
        print(f" - {FPLA_ANALYSIS_FILE}")
        return

    # 将接收时间列转换为datetime对象
    for df in [aftn_df, fpla_df]:
        df['ReceiveTime'] = pd.to_datetime(df['ReceiveTime'], errors='coerce')

    # 运行第一阶段对比并生成报告
    plan_report_df = run_plan_comparison(aftn_df, fpla_df, target_date_obj)
    if not plan_report_df.empty:
        # 使用 ExcelWriter 和 xlsxwriter 引擎来写入Excel并自动调整列宽
        with pd.ExcelWriter(PLAN_COMPARISON_FILE, engine='xlsxwriter') as writer:
            plan_report_df.to_excel(writer, sheet_name='PlanComparison', index=False)
            auto_set_column_width(plan_report_df, writer, 'PlanComparison')
        print(f"\n√ [第一阶段] 最终计划对比报告已生成: {PLAN_COMPARISON_FILE}")
    else:
        print("\n[第一阶段] 未生成计划对比报告，因为没有共同的航班键或数据为空。")

    # 运行第二阶段对比并生成报告
    dynamic_report_df = run_dynamic_comparison(aftn_df, fpla_df, target_date_obj)
    if not dynamic_report_df.empty:
        # 重新排列列顺序以确保报告的一致性
        final_cols = ['FlightKey', 'AFTN_Event_Time', 'AFTN_Event_Type', 'AFTN_Change_Detail', 'FPLA_Evidence',
                      'Conclusion']
        dynamic_report_df = dynamic_report_df.reindex(columns=final_cols)

        # 使用 ExcelWriter 和 xlsxwriter 引擎来写入Excel并自动调整列宽
        with pd.ExcelWriter(DYNAMIC_COMPARISON_FILE, engine='xlsxwriter') as writer:
            dynamic_report_df.to_excel(writer, sheet_name='DynamicComparison', index=False)
            auto_set_column_width(dynamic_report_df, writer, 'DynamicComparison')
        print(f"√ [第二阶段] 动态变更溯源报告已生成: {DYNAMIC_COMPARISON_FILE}")
    else:
        print("\n[第二阶段] 未生成动态变更溯源报告，因为没有AFTN动态消息或相应FPLA数据。")

    print(f"\n===== 日期 {TARGET_DATE_STR} 的对比分析任务已完成 =====")


if __name__ == "__main__":
    # 在此直接调用main函数，因为TARGET_DATE_STR已在全局范围加载
    main()
