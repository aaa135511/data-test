import pandas as pd
import re
import numpy as np
import os


def get_material(row):
    """根据商品名和规格名识别材质（V5.0 最终版）"""
    product_name = str(row['商品名称']).lower()
    spec_name = str(row['规格名称']).lower()
    search_text = product_name + spec_name

    # ★★★★★ 新增规则 ★★★★★
    if '羊绒' in search_text or '仿羊绒' in search_text or '羊羔绒' in search_text or '细沙羊绒' in search_text:
        return '仿羊绒/羊羔绒'
    if '多尼尔' in search_text:
        return '多尼尔'
    # ★★★★★★★★★★★★★★★

    if '汽车坐垫' in product_name or '水晶绒' in search_text:
        return '水晶绒'
    if '硅藻泥' in search_text:
        return '硅藻泥'
    if '剑麻' in search_text:
        return '剑麻'
    if '棉布' in search_text:
        return '棉布'
    if '德芙绒' in search_text:
        return '德芙绒'
    if '毛绒' in search_text:
        return '毛绒'

    if any(keyword in product_name for keyword in ['地毯', '地垫', '床边毯']):
        return '仿羊绒/羊羔绒'

    return '未知'


def calculate_area(row):
    """计算单件商品的面积（平方米）。(V4.0 完美版)"""
    remark_text = str(row['备注'])
    spec_text = str(row['规格名称'])
    quantity = int(row['数量']) if pd.notna(row['数量']) and row['数量'] > 0 else 1

    if remark_text:
        quantity_match = re.search(r'(\d+)\s*件', remark_text)
        if quantity_match:
            quantity = int(quantity_match.group(1))

        match_cn = re.search(r'宽(\d+\.?\d*)\s*长(\d+\.?\d*)', remark_text, re.IGNORECASE)
        match_symbol = re.search(r'(\d+\.?\d*)\s*[x*乘×]\s*(\d+\.?\d*)', remark_text, re.IGNORECASE)

        match = match_cn or match_symbol
        if match:
            length = float(match.group(1)) / 100
            width = float(match.group(2)) / 100
            return length * width * quantity

    spec_lower = spec_text.lower()

    if '7件套' in spec_lower or '七件套' in spec_lower:
        return ((0.5 * 0.5 * 2) + (0.5 * 1.3 * 1) + (0.45 * 0.6 * 4)) * quantity

    if any(kw in spec_lower for kw in ['超值坐垫套装', '三件套', '3件套', '前二后一']):
        return ((0.5 * 0.5 * 2) + (0.5 * 1.3 * 1)) * quantity

    if any(kw in spec_lower for kw in ['4件套', '四件套', '前排4件套', '主副驾四件套', '主副四件套']):
        return ((0.5 * 0.5 * 2) + (0.45 * 0.6 * 2)) * quantity

    if any(kw in spec_lower for kw in ['主驾驶一套', '两件套', '2件套']):
        return ((0.5 * 0.5 * 1) + (0.45 * 0.6 * 1)) * quantity

    if '后排3件套' in spec_lower:
        return ((0.5 * 1.3 * 1) + (0.45 * 0.6 * 2)) * quantity

    if '后排坐垫' in spec_lower:
        return (0.5 * 1.3) * quantity

    if any(kw in spec_lower for kw in ['方垫', '前排坐垫', '单片', '坐垫1张']):
        if '2张' in spec_lower:
            return (0.5 * 0.5) * 2 * quantity
        return (0.5 * 0.5) * quantity

    if '靠背' in spec_lower:
        return (0.45 * 0.6) * quantity

    match_dia = re.search(r'(\d+\.?\d*)\s*cm\s*直径|直径\s*(\d+\.?\d*)', spec_text, re.IGNORECASE)
    if match_dia:
        diameter_str = match_dia.group(1) or match_dia.group(2)
        diameter = float(diameter_str) / 100
        radius = diameter / 2
        return (np.pi * (radius ** 2)) * quantity

    match_rect = re.search(r'(\d+\.?\d*)\s*(?:cm|厘米)?\s*[x*乘×]\s*(\d+\.?\d*)', spec_text, re.IGNORECASE)
    if match_rect:
        length = float(match_rect.group(1)) / 100
        width = float(match_rect.group(2)) / 100
        return (length * width) * quantity

    return 0


def process_orders_file(input_filename="8.1-8.3系统导出.xlsx", output_filename="订单面积统计结果.xlsx"):
    """主处理函数"""
    if not os.path.exists(input_filename):
        print(f"错误：输入文件 '{input_filename}' 不存在。")
        return

    df = pd.read_excel(input_filename)
    df = df.fillna('')

    manual_review_list = []
    processed_orders = []

    for index, row in df.iterrows():
        spec_name = str(row['规格名称'])
        remark = str(row['备注'])

        if '客服' in spec_name or '客服' in remark:
            manual_review_list.append(row.to_dict())
            continue

        area = calculate_area(row)

        if area == 0:
            if "补差价" not in str(row['商品名称']):
                manual_review_list.append(row.to_dict())
            continue

        material = get_material(row)

        processed_orders.append({
            '订单号': row['订单号'],
            '店铺名称': row['店铺名称'],
            '商品名称': row['商品名称'],
            '规格名称': row['规格名称'],
            '备注': row['备注'],
            '数量': row['数量'],
            '识别出的材质': material,
            '计算出的总面积': area
        })

    df_processed = pd.DataFrame(processed_orders)
    df_manual = pd.DataFrame(manual_review_list)

    summary = pd.DataFrame()
    if not df_processed.empty:
        summary = df_processed.groupby(['店铺名称', '识别出的材质'])['计算出的总面积'].sum().reset_index()
        summary.rename(columns={'识别出的材质': '材质', '计算出的总面积': '总面积(平方米)'}, inplace=True)

    print_and_save_results(summary, df_processed, df_manual, output_filename)


def print_and_save_results(summary, df_processed, df_manual, output_filename):
    """统一打印和保存结果"""
    print("\n" + "=" * 80)
    print(" " * 25 + "脚本处理结果预览 (V5.0 最终版)")
    print("=" * 80 + "\n")

    print("--- 1. 面积统计结果 ---")
    print(summary.to_string(index=False) if not summary.empty else "【无】")

    print("\n" + "-" * 80 + "\n")

    print("--- 2. 需人工处理的订单 ---")
    if not df_manual.empty:
        columns_to_show = ['订单号', '店铺名称', '商品名称', '规格名称', '备注', '数量']
        existing_columns = [col for col in columns_to_show if col in df_manual.columns]
        print(f"（共 {len(df_manual)} 条）")
        print(df_manual[existing_columns].to_string(index=False))
    else:
        print("【无】")

    print("\n" + "=" * 80)

    try:
        with pd.ExcelWriter(output_filename, engine='openpyxl') as writer:
            summary.to_excel(writer, sheet_name='面积统计', index=False)
            if not df_processed.empty:
                df_processed.to_excel(writer, sheet_name='处理明细', index=False)
            if not df_manual.empty:
                df_manual.to_excel(writer, sheet_name='需人工处理订单', index=False)

        print(f"\n处理完成！结果已保存到 '{output_filename}'。")
        print(f"共自动处理 {len(df_processed)} 条订单，剩余 {len(df_manual)} 条订单需要人工审核。")
    except Exception as e:
        print(f"\n保存Excel文件时出错: {e}")


# --- 运行脚本 ---
if __name__ == "__main__":
    process_orders_file()