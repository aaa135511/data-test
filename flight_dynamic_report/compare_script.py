import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- 配置区 ---
TARGET_DATE_STR = "2025-07-08"
AFTN_PROCESSED_FILE = f'processed_aftn_dynamic_{TARGET_DATE_STR}.csv'
FPLA_PROCESSED_FILE = f'processed_fpla_plan_{TARGET_DATE_STR}.csv'
FINAL_COMPARISON_REPORT_FILE = f'final_comparison_report_{TARGET_DATE_STR}.csv'


def get_aftn_final_summary(df_aftn):
    """
    【最终版核心函数】：创建“AFTN最终动态综合体”，集成“信息前向填充”
    """
    if df_aftn.empty:
        return pd.DataFrame()

    print("开始生成AFTN最终动态综合体 (含信息前向填充)...")

    # 确保ReceiveTime是datetime类型，方便排序
    df_aftn['ReceiveTime'] = pd.to_datetime(df_aftn['ReceiveTime'])

    # --- 【关键升级】: 信息前向填充 ---
    # 1. 首先对整个DataFrame按航班和时间排序
    df_aftn_sorted = df_aftn.sort_values(by=['FlightKey', 'ReceiveTime'])

    # 2. 定义需要继承的关键信息列
    fill_cols = ['RegNo', 'CraftType', 'FlightNo', 'DepAirport', 'ArrAirport']

    # 3. 按FlightKey分组，并对指定列进行前向填充
    # 这会将一个航班前一条消息的有效信息，填充到后一条消息的空值中
    df_aftn_sorted[fill_cols] = df_aftn_sorted.groupby('FlightKey')[fill_cols].fillna(method='ffill')
    # ------------------------------------

    final_summaries = []
    # 使用填充和排序后的DataFrame进行后续处理
    for flight_key, group in df_aftn_sorted.groupby('FlightKey'):
        # 查找最新的DEP和ARR报文 (现在这些报文已经包含了继承来的信息)
        latest_dep = group[group['MessageType'] == 'DEP'].nlargest(1, 'ReceiveTime')
        latest_arr = group[group['MessageType'] == 'ARR'].nlargest(1, 'ReceiveTime')

        summary_record = {}

        if not latest_dep.empty and not latest_arr.empty:
            # --- 情况一：DEP和ARR都存在，进行合并 ---
            dep_row = latest_dep.iloc[0]
            arr_row = latest_arr.iloc[0]
            summary_record['FlightKey'] = flight_key
            summary_record['ReceiveTime'] = max(dep_row['ReceiveTime'], arr_row['ReceiveTime'])
            summary_record['MessageType'] = 'DEP_ARR_MERGED'
            summary_record['FlightNo'] = dep_row['FlightNo']
            summary_record['DepAirport'] = dep_row['DepAirport']
            summary_record['ArrAirport'] = dep_row['ArrAirport']
            # 注意：ARR报文的RegNo和CraftType可能为空，但现在已经被dep_row或更早的报文填充了
            summary_record['RegNo'] = arr_row['RegNo']  # 取最终状态ARR时的RegNo
            summary_record['CraftType'] = arr_row['CraftType']
            summary_record['SOBT_EOBT_ATOT'] = dep_row['SOBT_EOBT_ATOT']
            summary_record['SIBT_EIBT_AIBT'] = arr_row['SIBT_EIBT_AIBT']
        else:
            # --- 情况二：不满足合并条件，直接取最后一条记录 ---
            # 这条最后记录现在也已经包含了所有前序的有效信息
            latest_record = group.nlargest(1, 'ReceiveTime')
            if not latest_record.empty:
                summary_record = latest_record.iloc[0].to_dict()

        if summary_record:
            final_summaries.append(summary_record)

    print(f"AFTN最终动态综合体生成完毕，共 {len(final_summaries)} 条记录。")
    return pd.DataFrame(final_summaries)


# 其他函数保持不变
def get_fpla_final_summary(df_fpla):
    if df_fpla.empty: return pd.DataFrame()
    print("开始提取FPLA最新动态...")
    df_fpla['ReceiveTime'] = pd.to_datetime(df_fpla['ReceiveTime'])
    return df_fpla.sort_values('ReceiveTime').drop_duplicates('FlightKey', keep='last')


def compare_final_states(df_aftn_final, df_fpla_final):
    print("开始进行最终动态对比分析...")
    comparison_df = pd.merge(df_fpla_final, df_aftn_final, on='FlightKey', how='outer', suffixes=('_FPLA', '_AFTN'))
    results = []
    for index, row in comparison_df.iterrows():
        result_row = {'FlightKey': row['FlightKey']}
        fpla_exists = pd.notna(row.get('ReceiveTime_FPLA'))
        aftn_exists = pd.notna(row.get('ReceiveTime_AFTN'))
        if fpla_exists and not aftn_exists:
            result_row['ComparisonResult'] = 'FPLA_ONLY'
        elif not fpla_exists and aftn_exists:
            result_row['ComparisonResult'] = 'AFTN_ONLY'
        elif fpla_exists and aftn_exists:
            result_row['ComparisonResult'] = 'MATCHED'
        else:
            continue
        if result_row['ComparisonResult'] == 'MATCHED':
            time_diff = (row['ReceiveTime_AFTN'] - row['ReceiveTime_FPLA']).total_seconds()
            result_row['Timeliness_FPLA_Lead_Seconds'] = time_diff
        mismatched_fields = []
        if result_row['ComparisonResult'] == 'MATCHED':
            if str(row.get('RegNo_FPLA', '')) != str(row.get('RegNo_AFTN', '')):
                mismatched_fields.append(
                    f"RegNo(FPLA:{row.get('RegNo_FPLA', 'N/A')}, AFTN:{row.get('RegNo_AFTN', 'N/A')})")
            if str(row.get('CraftType_FPLA', '')) != str(row.get('CraftType_AFTN', '')):
                mismatched_fields.append(
                    f"CraftType(FPLA:{row.get('CraftType_FPLA', 'N/A')}, AFTN:{row.get('CraftType_AFTN', 'N/A')})")
        result_row['Accuracy_Mismatch'] = "; ".join(mismatched_fields) if mismatched_fields else None
        result_row['FPLA_MessageType'] = row.get('MessageType_FPLA')
        result_row['FPLA_ReceiveTime'] = row.get('ReceiveTime_FPLA')
        result_row['FPLA_RegNo'] = row.get('RegNo_FPLA')
        result_row['FPLA_CraftType'] = row.get('CraftType_FPLA')
        result_row['FPLA_SOBT'] = row.get('SOBT_EOBT_ATOT_FPLA')
        result_row['FPLA_SIBT'] = row.get('SIBT_EIBT_AIBT_FPLA')
        result_row['AFTN_MessageType'] = row.get('MessageType_AFTN')
        result_row['AFTN_ReceiveTime'] = row.get('ReceiveTime_AFTN')
        result_row['AFTN_RegNo'] = row.get('RegNo_AFTN')
        result_row['AFTN_CraftType'] = row.get('CraftType_AFTN')
        result_row['AFTN_ATOT'] = row.get('SOBT_EOBT_ATOT_AFTN')
        result_row['AFTN_AIBT'] = row.get('SIBT_EIBT_AIBT_AFTN')
        results.append(result_row)
    print("对比分析完成！")
    return pd.DataFrame(results)


# --- 主程序入口 ---
if __name__ == "__main__":
    try:
        df_aftn = pd.read_csv(AFTN_PROCESSED_FILE)
        df_fpla = pd.read_csv(FPLA_PROCESSED_FILE)
    except FileNotFoundError as e:
        print(f"错误: 无法找到预处理文件，请先运行预处理脚本。 {e}")
        exit()

    aftn_final = get_aftn_final_summary(df_aftn)
    fpla_final = get_fpla_final_summary(df_fpla)
    final_report_df = compare_final_states(aftn_final, fpla_final)

    if not final_report_df.empty:
        final_report_df.to_csv(FINAL_COMPARISON_REPORT_FILE, index=False, encoding='utf-8-sig')
        print(f"\n最终对比报告已生成: {FINAL_COMPARISON_REPORT_FILE}")

        print("\n--- 对比结果摘要 ---")
        if 'ComparisonResult' in final_report_df.columns:
            print(final_report_df['ComparisonResult'].value_counts())
        if 'Timeliness_FPLA_Lead_Seconds' in final_report_df.columns:
            matched_df = final_report_df[final_report_df['ComparisonResult'] == 'MATCHED']
            if not matched_df.empty:
                avg_lead_time = matched_df['Timeliness_FPLA_Lead_Seconds'].mean()
                fpla_leading_count = (matched_df['Timeliness_FPLA_Lead_Seconds'] > 0).sum()
                total_matched = len(matched_df)
                if total_matched > 0:
                    print(f"\nFPLA平均领先时间: {avg_lead_time:.2f} 秒 ({timedelta(seconds=abs(avg_lead_time))})")
                    print(f"FPLA领先率: {fpla_leading_count / total_matched:.2%}")