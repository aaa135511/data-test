import pandas as pd
import numpy as np
import os
import re  # 导入正则表达式模块

# --- 用户配置 ---
# 您现在只需要配置下面两个变量
EXCEL_FILE_PATH = 'FPDI明细—2025-07-09T00_00-2025-07-10T00_00.xlsx'  # <-- 修改为您的输入Excel文件名
TARGET_AIRPORT = 'ZGGG'  # <-- 修改为您要分析的目标降落机场

# --- 字段定义 ---
# (此部分保持不变)
CUSTOM_FIELD_STATUS = {
    "航空器识别标志": "是", "全球航班计划唯一标识符": "否", "共享单位航班标识符": "是",
    "预先飞行计划标识符": "是", "航空器注册号": "是", "航空器地址码": "否",
    "计划离港时间": "是", "计划到港时间": "是", "计划起飞机场": "是",
    "计划目的地机场": "是", "预计撤轮挡时间": "是", "目标撤轮挡时间": "是",
    "开始保洁时间": "是", "完成保洁时间": "是", "开始配餐时间": "是",
    "完成配餐时间": "是", "开始供油时间": "是", "完成供油时间": "是",
    "开始排污时间": "否", "完成排污时间": "否", "开始加清水时间": "否",
    "完成加清水时间": "否", "开始除冰时间": "是", "完成除冰时间": "是",
    "除冰位置": "否", "除冰方式": "否", "除冰坪号码": "否",
    "货邮行李装载开始时间": "否", "货邮行李装载完成时间": "否", "开始登机时间": "是",
    "完成登机时间": "是", "离港客梯车撤离时间": "是", "离港摆渡车撤离时间": "否",
    "拖车到位时间": "否", "离桥时间": "是", "机务维修人员到位时间": "否",
    "机务放行时间": "是", "值机开放时间": "是", "值机关闭时间": "是",
    "实际离港时间": "是", "离港航班停机位": "是", "离港航班登机口": "是",
    "值机人数": "是", "已过安检旅客人数": "是", "登机人数": "是",
    "计算撤轮挡时间": "否", "计算起飞时间": "否", "实际关舱门时间": "是",
    "实际关客舱门时间": "是", "实际关货舱门时间": "是", "共享航班号": "否",
    "可变滑行时间": "否"
}

# 校验结果列的名称
COL_FORMAT_VALIDATION = '格式校验结果'
COL_LOGIC_VALIDATION = '逻辑校验结果'
COL_TIMELINESS_VALIDATION = '及时性'
COL_DEST_AIRPORT = '计划目的地机场'


def generate_output_filename(input_path, airport_code):
    """根据输入文件路径和机场代码生成更智能的输出文件名。"""
    base_name = os.path.basename(input_path)
    file_stem, _ = os.path.splitext(base_name)
    clean_stem = file_stem.replace('明细', '')
    match = re.search(r'\d{4}-\d{2}-\d{2}', clean_stem)
    date_part = match.group(0) if match else "日期未知"
    return f"{airport_code}-{date_part}-数据质量分析报告.xlsx"


def auto_adjust_xlsx_columns(writer, df, sheet_name):
    """自动调整Excel列宽"""
    workbook = writer.book
    worksheet = writer.sheets[sheet_name]
    for idx, col in enumerate(df):
        series = df[col]
        max_len = max((
            series.astype(str).map(len).max(),
            len(str(series.name))
        )) + 3  # 增加一点缓冲空间
        worksheet.set_column(idx, idx, max_len)


def analyze_fpdi_quality(file_path, airport_code, output_path):
    """分析FPDI数据质量，打印报告并导出到格式美化的Excel。"""
    print(f"--- 开始分析数据质量 ---")
    print(f"输入文件: {file_path}")
    print(f"目标机场: {airport_code}\n")

    try:
        # 指定dtype=str，防止pandas自动转换数字格式
        df = pd.read_excel(file_path, dtype=str).fillna('')
    except Exception as e:
        print(f"读取Excel文件时发生错误: {e}")
        return

    filtered_df = df[df[COL_DEST_AIRPORT] == airport_code].copy()
    total_flights = len(filtered_df)

    if total_flights == 0:
        print(f"在文件中未找到降落机场为 '{airport_code}' 的航班。")
        return

    print(f"共找到 {total_flights} 个飞往 {airport_code} 的航班进行分析。\n")

    results_list = []
    for field_name, is_required in CUSTOM_FIELD_STATUS.items():
        covered_flights_df = filtered_df[filtered_df[field_name] != '']
        num_covered = len(covered_flights_df)
        coverage_rate = (num_covered / total_flights) * 100 if total_flights > 0 else 0

        if num_covered == 0:
            format_correct_rate, logic_correct_rate, timeliness_rate = "N/A", "N/A", "N/A"
        else:
            # --- 【核心逻辑更新】 ---
            # 使用正则表达式匹配真正的错误，忽略“字段值为空”的描述。
            # re.escape确保字段名中的特殊字符被正确处理。
            # (?!...) 是负向先行断言，表示其后的模式不能匹配。
            error_pattern = f"{re.escape(field_name)}(?!字段值为空)"

            # 必须设置 regex=True 才能让 str.contains 使用正则表达式引擎
            format_errors = covered_flights_df[COL_FORMAT_VALIDATION].str.contains(error_pattern, regex=True,
                                                                                   na=False).sum()
            logic_errors = covered_flights_df[COL_LOGIC_VALIDATION].str.contains(error_pattern, regex=True,
                                                                                 na=False).sum()
            timeliness_errors = covered_flights_df[COL_TIMELINESS_VALIDATION].str.contains(error_pattern, regex=True,
                                                                                           na=False).sum()

            format_correct_rate = ((num_covered - format_errors) / num_covered) * 100
            logic_correct_rate = ((num_covered - logic_errors) / num_covered) * 100
            timeliness_rate = ((num_covered - timeliness_errors) / num_covered) * 100

        results_list.append({
            '字段名称': field_name, '是否必填': is_required, '覆盖航班数': num_covered,
            '覆盖率 (%)': coverage_rate, '格式正确率 (%)': format_correct_rate,
            '逻辑正确率 (%)': logic_correct_rate, '及时性 (%)': timeliness_rate
        })

    results_df = pd.DataFrame(results_list)
    results_df['总航班数'] = total_flights
    column_order = [
        '字段名称', '是否必填', '总航班数', '覆盖航班数', '覆盖率 (%)',
        '格式正确率 (%)', '逻辑正确率 (%)', '及时性 (%)'
    ]
    results_df = results_df[column_order]

    try:
        sheet_name = '数据质量分析报告'
        writer = pd.ExcelWriter(output_path, engine='xlsxwriter')
        results_df.to_excel(writer, index=False, sheet_name=sheet_name)
        auto_adjust_xlsx_columns(writer, results_df, sheet_name)
        writer.close()
        print(f"--- 报告导出成功 ---")
        print(f"分析结果已保存到文件: {output_path}\n")
    except Exception as e:
        print(f"--- 报告导出失败 ---")
        print(f"导出到Excel时发生错误: {e}\n")

    display_df = results_df.copy()
    for col in ['覆盖率 (%)', '格式正确率 (%)', '逻辑正确率 (%)', '及时性 (%)']:
        display_df[col] = display_df[col].apply(
            lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x
        )

    print("--- 分析结果报告 (控制台预览) ---")
    print(display_df.to_string(index=False))
    print("\n--- 分析完成 ---")


if __name__ == '__main__':
    output_filename = generate_output_filename(EXCEL_FILE_PATH, TARGET_AIRPORT)
    analyze_fpdi_quality(EXCEL_FILE_PATH, TARGET_AIRPORT, output_filename)