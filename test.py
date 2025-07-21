import pandas as pd
import os


def analyze_flight_data_with_custom_field_status(
    excel_file_path, output_excel_filename="flight_null_report_custom_fields.xlsx",
    destination_airport_filter="ZUTF", aircraft_id_col="航空器识别标志",
    destination_airport_col="计划目的地机场",
    field_status_map={}  # Directly pass the required fields map here
):
    """
    分析 Excel 文件中按航班分组的字段空值情况，生成单一 Sheet 的 Excel 报告，
    并在顶部添加总体统计行。列名中包含字段的“是否必填”信息。
    必填且空值率超过30%的列头将标红。必填项根据提供的 custom_field_status_map 确定。

    Args:
        excel_file_path (str): 要分析的原始 Excel 文件路径。
        output_excel_filename (str): 生成的 Excel 报告的文件名。
        destination_airport_filter (str): 用于筛选的计划目的地机场代码。
        aircraft_id_col (str): 航空器识别标志的列名。
        destination_airport_col (str): 计划目的地机场的列名。
        field_status_map (dict): 包含中文列名及其必填状态（"是"或"否"）的字典。
    """
    try:
        df = pd.read_excel(excel_file_path)
    except FileNotFoundError:
        print(f"错误：文件 '{excel_file_path}' 未找到。请检查文件路径是否正确。")
        return
    except Exception as e:
        print(f"读取 Excel 文件时发生错误：{e}")
        return

    # 直接使用传入的 field_status_map 作为必填字段的真理来源
    excel_column_name_map = field_status_map

    print(f"[DEBUG] 最终的必填字段映射 (excel_column_name_map): {excel_column_name_map}")

    # 2. 筛选数据：只保留计划目的地机场为指定值的消息
    df_filtered = df[df[destination_airport_col] == destination_airport_filter].copy()

    if df_filtered.empty:
        print(f"在 '{excel_file_path}' 中未找到 '计划目的地机场' 为 '{destination_airport_filter}' 的消息。")
        return

    # 获取所有需要分析的字段
    # 确保只包含df_filtered中实际存在的列，并且在excel_column_name_map中有定义的列
    columns_to_analyze = [
        col for col in df_filtered.columns
        if col not in [aircraft_id_col, destination_airport_col] and col in excel_column_name_map
    ]
    print(f"\n[DEBUG] 过滤后的原始数据列: {df_filtered.columns.tolist()}")
    print(f"[DEBUG] 确定要分析的字段 (已在必填信息中): {columns_to_analyze}")

    # 存储所有航班的分析结果，每个元素代表 Excel 中的一行
    all_flights_data = []

    # 用于计算总体统计：记录每个字段在多少个航班中是“空”的
    flight_level_null_counts_per_column = {col: 0 for col in columns_to_analyze}

    # 2. 按照 航空器识别标志 进行分组
    grouped_flights = df_filtered.groupby(aircraft_id_col)
    total_flights = len(grouped_flights)  # 满足筛选条件的总航班数

    # --- 3. 定义最终报告的列名顺序，并添加必填标记 ---
    # 基本列
    final_report_columns_order = [aircraft_id_col, "航班总消息数", "总体统计备注"]
    # 动态添加分析字段的列名，加上 (必填) / (选填) 标记
    for col in columns_to_analyze:
        required_tag = "(必填)" if excel_column_name_map.get(col) == "是" else "(选填)"
        final_report_columns_order.append(f"{col}{required_tag}")
    print(f"[DEBUG] 最终报告的列名顺序: {final_report_columns_order}")

    for aircraft_id, group_df in grouped_flights:
        flight_total_messages = len(group_df)

        # 初始化当前航班的行数据，确保所有列都存在，默认为空字符串
        current_flight_row = {col_name: "" for col_name in final_report_columns_order}

        current_flight_row[aircraft_id_col] = aircraft_id
        current_flight_row["航班总消息数"] = flight_total_messages

        for column in columns_to_analyze:
            # 判断航班层面该字段是否为空
            is_flight_level_null = group_df[column].isnull().all()

            # 获取带必填标记的列名，这个列名将作为字典的键
            required_tag = "(必填)" if excel_column_name_map.get(column) == "是" else "(选填)"
            col_key_in_row = f"{column}{required_tag}"  # 这是字典的键

            # --- 航班行的内容调整 ---
            if column.endswith('_备注'):
                # 原始备注列处理
                field_value_or_status = ""  # 默认值为空
                if not group_df[column].isnull().all():
                    non_null_values = group_df[column].dropna()
                    if not non_null_values.empty:
                        field_value_or_status = non_null_values.iloc[0]
                current_flight_row[col_key_in_row] = field_value_or_status

            else:  # 非备注列（常规字段）
                field_value_or_status = "空" if is_flight_level_null else "非空"
                if is_flight_level_null:
                    field_value_or_status += " 🚨"  # 在内容中添加标记
                    flight_level_null_counts_per_column[column] += 1
                current_flight_row[col_key_in_row] = field_value_or_status

        all_flights_data.append(current_flight_row)

    # --- 创建总体统计行 ---
    summary_row = {col_name: "" for col_name in final_report_columns_order}  # 初始化所有列为空字符串

    summary_row[aircraft_id_col] = "总体统计"
    summary_row["航班总消息数"] = f"总航班数: {total_flights}"
    summary_row["总体统计备注"] = "(空航班占比)"

    # 用于存储需要标红的列的原始字段名
    columns_to_highlight_red_original_names = []

    for column in columns_to_analyze:
        null_flights_for_column = flight_level_null_counts_per_column.get(column, 0)
        null_flights_percentage = (null_flights_for_column / total_flights) * 100 if total_flights > 0 else 0

        # 获取带必填标记的列名
        required_tag = "(必填)" if excel_column_name_map.get(column) == "是" else "(选填)"
        col_key_in_row = f"{column}{required_tag}"  # 这是字典的键

        # --- 总体统计行的内容调整 ---
        percentage_str = f"{null_flights_percentage:.2f}%"
        if null_flights_percentage > 30:
            percentage_str = f"🚨 {percentage_str}"
            # 如果是必填且空值率超过30%，则将原始字段名加入待标红列表
            if excel_column_name_map.get(column) == "是":
                columns_to_highlight_red_original_names.append(col_key_in_row)  # 存储带标签的列名

        summary_row[col_key_in_row] = percentage_str

    # 将总体统计行添加到所有航班数据列表的**开头**
    all_flights_data.insert(0, summary_row)

    # 将所有航班的数据转换为 DataFrame
    if not all_flights_data:
        print("没有可用于生成报告的数据。")
        return

    # 确保 DataFrame 的列顺序与我们定义的 final_report_columns_order 一致
    report_df = pd.DataFrame(all_flights_data, columns=final_report_columns_order)

    # 写入 Excel 文件
    try:
        with pd.ExcelWriter(output_excel_filename, engine='xlsxwriter') as writer:
            report_df.to_excel(writer, sheet_name="航班空值分析", index=False)

            workbook = writer.book
            worksheet = writer.sheets["航班空值分析"]

            # 定义红色字体格式
            red_format = workbook.add_format({'font_color': 'red', 'bold': True})

            # 遍历列，如果该列需要标红，则设置列头的格式
            for col_idx, col_name_with_tag in enumerate(report_df.columns):
                if col_name_with_tag in columns_to_highlight_red_original_names:
                    # 将格式应用到列头（第一行）
                    worksheet.write(0, col_idx, col_name_with_tag, red_format)
                else:
                    # 对于不需要标红的列，也需要重新写入列头，因为report_df.to_excel会先写一遍
                    # 这样可以确保所有列头都显示正确，且标红的才有格式
                    worksheet.write(0, col_idx, col_name_with_tag)

                # 自动调整列宽
                max_len = max(report_df[col_name_with_tag].astype(str).map(len).max(), len(str(col_name_with_tag)))
                worksheet.set_column(col_idx, col_idx, max_len + 2)

            summary_info_df = pd.DataFrame({
                "报告名称": [f"航班维度空值分析报告：{os.path.basename(excel_file_path)}"],
                "筛选条件": [f"计划目的地机场为 '{destination_airport_filter}'"],
                "总览说明": ["每个航班为一行，报告的第一行为总体统计数据。",
                             "列名中包含 (必填) 或 (选填) 标记。",
                             "必填且总体空值率 >30% 的列，其列名将显示为红色。",
                             "常规字段列：空值标记为 '空 🚨'，非空为 '非空'。",
                             "原始备注列：如果该备注字段在航班层面非空，显示其内容，否则为空。",
                             "总体统计行中，所有字段列均显示空航班占比，高占比（>30%）则有 '🚨' 标记。"]
            })
            summary_info_df.to_excel(writer, sheet_name="报告概览", index=False)
            worksheet_summary = writer.sheets['报告概览']
            worksheet_summary.set_column(0, 1, 50)

        print(f"航班维度空值分析报告（含必填信息，列头标红）已生成到 Excel 文件：'{output_excel_filename}'")

    except Exception as e:
        print(f"写入 Excel 文件时发生错误：{e}")
        print("请检查文件是否被占用或Excel文件中是否存在非常规字符。")


# --- 使用示例 ---
if __name__ == "__main__":
    excel_file = "FPDI明细—2025-06-28T00_00-2025-06-29T00_00.xlsx"  # <--- 请确保这里的文件路径和文件名正确
    output_excel_file = "FPDI明细_航班空值分析_最终标准.xlsx"

    # 根据您提供的最新必填项列表进行配置
    custom_field_status = {
        "航空器识别标志": "是",
        "全球航班计划唯一标识符": "否",
        "共享单位航班标识符": "是",
        "预先飞行计划标识符": "是",
        "航空器注册号": "是",
        "航空器地址码": "否",
        "计划离港时间": "是",
        "计划到港时间": "是",
        "计划起飞机场": "是",
        "计划目的地机场": "是",
        "预计撤轮挡时间": "是",
        "目标撤轮挡时间": "是",
        "开始保洁时间": "是",
        "完成保洁时间": "是",
        "开始配餐时间": "是",
        "完成配餐时间": "是",
        "开始供油时间": "是",
        "完成供油时间": "是",
        "开始排污时间": "否",
        "完成排污时间": "否",
        "开始加清水时间": "否",
        "完成加清水时间": "否",
        "开始除冰时间": "是",
        "完成除冰时间": "是",
        "除冰位置": "否",
        "除冰方式": "否",
        "除冰坪号码": "否",
        "货邮行李装载开始时间": "否",
        "货邮行李装载完成时间": "否",
        "开始登机时间": "是",
        "完成登机时间": "是",
        "离港客梯车撤离时间": "是",
        "离港摆渡车撤离时间": "否",
        "拖车到位时间": "否",
        "离桥时间": "是",
        "机务维修人员到位时间": "否",
        "机务放行时间": "是",
        "值机开放时间": "是",
        "值机关闭时间": "是",
        "实际离港时间": "是",
        "离港航班停机位": "是",
        "离港航班登机口": "是",
        "值机人数": "是",
        "已过安检旅客人数": "是",
        "登机人数": "是",
        "计算撤轮挡时间": "否",
        "计算起飞时间": "否",
        "实际关舱门时间": "是",
        "实际关客舱门时间": "是",
        "实际关货舱门时间": "是",
        "共享航班号": "否",
        "可变滑行时间": "否"
    }

    analyze_flight_data_with_custom_field_status(
        excel_file,
        output_excel_file,
        aircraft_id_col="航空器识别标志",
        destination_airport_col="计划目的地机场",
        field_status_map=custom_field_status
    )