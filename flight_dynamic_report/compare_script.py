import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- 配置区 ---
TARGET_DATE_STR = "2025-07-08"
AFTN_PROCESSED_FILE = f'processed_aftn_dynamic_{TARGET_DATE_STR}.csv'
FPLA_PROCESSED_FILE = f'processed_fpla_plan_{TARGET_DATE_STR}.csv'
FINAL_COMPARISON_REPORT_FILE = f'final_comparison_report_{TARGET_DATE_STR}.csv'


def get_aftn_final_summary(df_aftn):
    """【最终版核心函数】：创建“AFTN最终动态综合体”，集成“信息前向填充”"""
    if df_aftn.empty: return pd.DataFrame()
    print("开始生成AFTN最终动态综合体 (含信息前向填充)...")
    df_aftn['ReceiveTime'] = pd.to_datetime(df_aftn['ReceiveTime'])
    df_aftn_sorted = df_aftn.sort_values(by=['FlightKey', 'ReceiveTime'])
    fill_cols = ['RegNo', 'CraftType', 'FlightNo', 'DepAirport', 'ArrAirport']
    df_aftn_sorted[fill_cols] = df_aftn_sorted.groupby('FlightKey')[fill_cols].fillna(method='ffill')
    final_summaries = []
    for flight_key, group in df_aftn_sorted.groupby('FlightKey'):
        latest_dep = group[group['MessageType'] == 'DEP'].nlargest(1, 'ReceiveTime')
        latest_arr = group[group['MessageType'] == 'ARR'].nlargest(1, 'ReceiveTime')
        summary_record = {}
        if not latest_dep.empty and not latest_arr.empty:
            dep_row = latest_dep.iloc[0]
            arr_row = latest_arr.iloc[0]
            summary_record['FlightKey'] = flight_key
            summary_record['ReceiveTime'] = max(dep_row['ReceiveTime'], arr_row['ReceiveTime'])
            summary_record['MessageType'] = 'DEP_ARR_MERGED'
            summary_record['FlightNo'] = dep_row['FlightNo']
            summary_record['DepAirport'] = dep_row['DepAirport']
            summary_record['ArrAirport'] = dep_row['ArrAirport']
            summary_record['RegNo'] = arr_row['RegNo']
            summary_record['CraftType'] = arr_row['CraftType']
            summary_record['SOBT_EOBT_ATOT'] = dep_row['SOBT_EOBT_ATOT']
            summary_record['SIBT_EIBT_AIBT'] = arr_row['SIBT_EIBT_AIBT']
        else:
            latest_record = group.nlargest(1, 'ReceiveTime')
            if not latest_record.empty:
                summary_record = latest_record.iloc[0].to_dict()
        if summary_record:
            final_summaries.append(summary_record)
    print(f"AFTN最终动态综合体生成完毕，共 {len(final_summaries)} 条记录。")
    return pd.DataFrame(final_summaries)


def get_fpla_final_summary(df_fpla):
    """核心函数：获取FPLA的最新动态"""
    if df_fpla.empty: return pd.DataFrame()
    print("开始提取FPLA最新动态...")
    df_fpla['ReceiveTime'] = pd.to_datetime(df_fpla['ReceiveTime'])
    return df_fpla.sort_values('ReceiveTime').drop_duplicates('FlightKey', keep='last')


def compare_fields(fpla_val, aftn_val):
    """辅助函数：对比单个字段并返回明确的对比状态"""
    # isnull() 也能处理 None, np.nan 等情况
    fpla_exists = pd.notna(fpla_val) and str(fpla_val).strip() != ''
    aftn_exists = pd.notna(aftn_val) and str(aftn_val).strip() != ''

    if fpla_exists and aftn_exists:
        return 'MATCHED' if str(fpla_val) == str(aftn_val) else 'MISMATCHED'
    elif fpla_exists and not aftn_exists:
        return 'AFTN_MISSING'
    elif not fpla_exists and aftn_exists:
        return 'FPLA_MISSING'
    else:
        return 'BOTH_MISSING'


def compare_final_states(df_aftn_final, df_fpla_final):
    """【全新重构】核心函数：进行一对一匹配，并生成结构化的对比报告"""
    print("开始进行最终动态对比分析 (结构化报告版)...")
    comparison_df = pd.merge(df_fpla_final, df_aftn_final, on='FlightKey', how='outer', suffixes=('_FPLA', '_AFTN'))
    results = []
    for index, row in comparison_df.iterrows():
        # --- 1. 初始化，先填充数据列 ---
        result_row = {
            'FlightKey': row['FlightKey'],
            'FPLA_MessageType': row.get('MessageType_FPLA'),
            'FPLA_ReceiveTime': row.get('ReceiveTime_FPLA'),
            'FPLA_RegNo': row.get('RegNo_FPLA'),
            'FPLA_CraftType': row.get('CraftType_FPLA'),
            'FPLA_SOBT': row.get('SOBT_EOBT_ATOT_FPLA'),
            'FPLA_SIBT': row.get('SIBT_EIBT_AIBT_FPLA'),
            'AFTN_MessageType': row.get('MessageType_AFTN'),
            'AFTN_ReceiveTime': row.get('ReceiveTime_AFTN'),
            'AFTN_RegNo': row.get('RegNo_AFTN'),
            'AFTN_CraftType': row.get('CraftType_AFTN'),
            'AFTN_ATOT': row.get('SOBT_EOBT_ATOT_AFTN'),
            'AFTN_AIBT': row.get('SIBT_EIBT_AIBT_AFTN'),
        }

        # --- 2. 计算对比结论，并将结论列追加到末尾 ---
        fpla_exists = pd.notna(row.get('ReceiveTime_FPLA'))
        aftn_exists = pd.notna(row.get('ReceiveTime_AFTN'))

        # 总体对比结论
        if fpla_exists and not aftn_exists:
            result_row['ComparisonResult'] = 'FPLA_ONLY'
        elif not fpla_exists and aftn_exists:
            result_row['ComparisonResult'] = 'AFTN_ONLY'
        elif fpla_exists and aftn_exists:
            result_row['ComparisonResult'] = 'MATCHED'
        else:
            continue

        # 及时性对比结论
        if result_row['ComparisonResult'] == 'MATCHED':
            time_diff = (row['ReceiveTime_AFTN'] - row['ReceiveTime_FPLA']).total_seconds()
            result_row['Timeliness_FPLA_Lead_Seconds'] = time_diff
        else:
            result_row['Timeliness_FPLA_Lead_Seconds'] = None

        # 机号准确性对比结论
        result_row['RegNo_Comparison'] = compare_fields(row.get('RegNo_FPLA'), row.get('RegNo_AFTN'))

        # 机型准确性对比结论
        result_row['CraftType_Comparison'] = compare_fields(row.get('CraftType_FPLA'), row.get('CraftType_AFTN'))

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

        # --- 打印更详细的统计摘要 ---
        print("\n--- 对比结果摘要 ---")
        if 'ComparisonResult' in final_report_df.columns:
            print("\n[整体覆盖度对比]")
            print(final_report_df['ComparisonResult'].value_counts())

        if 'Timeliness_FPLA_Lead_Seconds' in final_report_df.columns:
            matched_df = final_report_df[final_report_df['ComparisonResult'] == 'MATCHED']
            if not matched_df.empty:
                avg_lead_time = matched_df['Timeliness_FPLA_Lead_Seconds'].mean()
                fpla_leading_count = (matched_df['Timeliness_FPLA_Lead_Seconds'] > 0).sum()
                total_matched = len(matched_df)
                if total_matched > 0:
                    print("\n[及时性对比 (仅限匹配成功的航班)]")
                    print(f"FPLA平均领先时间: {avg_lead_time:.2f} 秒 ({timedelta(seconds=abs(avg_lead_time))})")
                    print(f"FPLA领先率: {fpla_leading_count / total_matched:.2%}")

        if 'RegNo_Comparison' in final_report_df.columns:
            print("\n[航空器注册号准确性对比]")
            print(final_report_df['RegNo_Comparison'].value_counts())

        if 'CraftType_Comparison' in final_report_df.columns:
            print("\n[机型准确性对比]")
            print(final_report_df['CraftType_Comparison'].value_counts())