import pandas as pd
import numpy as np
import os
import glob
import re

# --- 用户配置 ---
# 存放所有每日报告的文件夹名称
SOURCE_DIRECTORY = ''
# 最终生成的汇总报告的文件名
OUTPUT_FILENAME = 'ZUTF-2025-09-月度数据质量汇总报告.xlsx'
# 目标机场代码，用于从文件名中提取日期
TARGET_AIRPORT = 'ZUTF'

def auto_adjust_xlsx_columns(writer, df, sheet_name):
    """自动调整Excel列宽"""
    workbook = writer.book
    worksheet = writer.sheets[sheet_name]
    for idx, col in enumerate(df):
        series = df[col]
        # 计算列宽，考虑中文字符
        max_len = max((
            series.astype(str).map(lambda x: len(x.encode('gbk', 'ignore'))).max(), # 使用ignore处理无法编码的字符
            len(str(series.name).encode('gbk', 'ignore'))
        )) + 3 # 增加缓冲空间
        worksheet.set_column(idx, idx, max_len)

def extract_date_from_filename(filename, airport_code):
    """从文件名中提取日期部分"""
    # 正则表达式匹配 YYYY-MM-DD 格式的日期
    match = re.search(r'\d{4}-\d{2}-\d{2}', filename)
    if match:
        return match.group(0)
    # 如果没有找到，返回一个基础的文件名作为备用
    return os.path.splitext(os.path.basename(filename))[0]


def summarize_quality_reports(source_dir, output_file, airport_code):
    """
    汇总指定文件夹内所有数据质量报告，生成一个包含总览和每日详情的Excel文件。
    """
    print(f"--- 开始汇总数据质量报告 ---")
    print(f"源文件夹: {source_dir}")

    # 1. 查找所有符合条件的日报文件
    file_pattern = os.path.join(source_dir, f"{airport_code}-*-数据质量分析报告.xlsx")
    daily_report_files = glob.glob(file_pattern)

    if not daily_report_files:
        print(f"错误：在文件夹 '{source_dir}' 中未找到任何匹配的报告文件。")
        print(f"请确保文件命名格式为 '{airport_code}-YYYY-MM-DD-数据质量分析报告.xlsx'")
        return

    print(f"找到 {len(daily_report_files)} 个日报文件进行处理。")

    # 2. 读取所有日报数据
    all_daily_data = []
    for f in daily_report_files:
        try:
            df = pd.read_excel(f)
            # 从文件名提取日期作为Sheet名
            sheet_name = extract_date_from_filename(f, airport_code)
            all_daily_data.append({'sheet_name': sheet_name, 'data': df})
            print(f"  > 已读取: {os.path.basename(f)}")
        except Exception as e:
            print(f"读取文件 {f} 时出错: {e}")
            continue

    if not all_daily_data:
        print("未能成功读取任何报告文件，程序终止。")
        return

    # 3. 创建一个包含所有天数数据的大表，用于计算
    combined_df = pd.concat([item['data'] for item in all_daily_data], ignore_index=True)

    # --- 核心计算逻辑 ---
    print("\n--- 正在计算月度汇总数据... ---")

    # a. 计算数值，处理'N/A'等非数字情况
    # pd.to_numeric 会将无法转换的值变为 NaN, fillna(0) 将其替换为0
    for col in ['覆盖率 (%)', '格式正确率 (%)', '逻辑正确率 (%)', '及时性 (%)']:
        combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce').fillna(0)

    # b. 计算每日的“正确航班数”
    # 如果覆盖数为0，则正确航班数也为0
    combined_df['格式正确航班数'] = (combined_df['覆盖航班数'] * (combined_df['格式正确率 (%)'] / 100)).round().astype(int)
    combined_df['逻辑正确航班数'] = (combined_df['覆盖航班数'] * (combined_df['逻辑正确率 (%)'] / 100)).round().astype(int)
    combined_df['及时性航班数'] = (combined_df['覆盖航班数'] * (combined_df['及时性 (%)'] / 100)).round().astype(int)

    # c. 按字段名称进行分组汇总
    summary = combined_df.groupby('字段名称').agg(
        # is_required 是固定的，取第一个即可
        是否必填=('是否必填', 'first'),
        总航班数=('总航班数', 'sum'),
        覆盖航班数=('覆盖航班数', 'sum'),
        格式正确航班数=('格式正确航班数', 'sum'),
        逻辑正确航班数=('逻辑正确航班数', 'sum'),
        及时性航班数=('及时性航班数', 'sum')
    ).reset_index()

    # d. 修正总航班数（因为每天每个字段都重复记录了当天的总数）
    # 正确的总航班数应该是所有日报的“总航班数”去重后的和
    total_flights_overall = sum(df['总航班数'].iloc[0] for df in [item['data'] for item in all_daily_data if not item['data'].empty])
    summary['总航班数'] = total_flights_overall

    # e. 计算最终的总体百分比 (!!! 关键修正 !!!)
    # 使用Pandas的 .div() 方法进行安全的除法操作，然后用 fillna(0) 处理除以0产生的NaN
    summary['覆盖率 (%)'] = (summary['覆盖航班数'] * 100).div(summary['总航班数']).fillna(0)
    summary['格式正确率 (%)'] = (summary['格式正确航班数'] * 100).div(summary['覆盖航班数']).fillna(0)
    summary['逻辑正确率 (%)'] = (summary['逻辑正确航班数'] * 100).div(summary['覆盖航班数']).fillna(0)
    summary['及时性 (%)'] = (summary['及时性航班数'] * 100).div(summary['覆盖航班数']).fillna(0)

    # f. 整理最终输出的列顺序
    final_summary_df = summary[[
        '字段名称', '是否必填', '总航班数', '覆盖航班数', '覆盖率 (%)',
        '格式正确率 (%)', '逻辑正确率 (%)', '及时性 (%)'
    ]]

    print("--- 汇总计算完成 ---")

    # 4. 写入到最终的Excel文件
    try:
        with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
            # 写入汇总页
            final_summary_df.to_excel(writer, sheet_name='月度汇总报告', index=False)
            auto_adjust_xlsx_columns(writer, final_summary_df, '月度汇总报告')
            print(f"\n--- 正在写入Excel文件: {output_file} ---")
            print(f"  > 已写入汇总Sheet: 月度汇总报告")

            # 写入每日详情页
            # 对日报按日期排序，确保Sheet顺序正确
            sorted_daily_data = sorted(all_daily_data, key=lambda x: x['sheet_name'])
            for item in sorted_daily_data:
                sheet_name = item['sheet_name']
                daily_df = item['data']
                daily_df.to_excel(writer, sheet_name=sheet_name, index=False)
                auto_adjust_xlsx_columns(writer, daily_df, sheet_name)
                print(f"  > 已写入每日Sheet: {sheet_name}")

        print(f"\n--- 报告导出成功 ---")
        print(f"汇总分析结果已保存到文件: {output_file}")

    except Exception as e:
        print(f"\n--- 报告导出失败 ---")
        print(f"导出到Excel时发生错误: {e}")


if __name__ == '__main__':
    summarize_quality_reports(SOURCE_DIRECTORY, OUTPUT_FILENAME, TARGET_AIRPORT)