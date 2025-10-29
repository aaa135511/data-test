import pandas as pd
import os
import glob

# 定义单日退伙标准额度，方便统一修改
DAILY_REFUND_RATE = 35.0

def analyze_meal_refunds(folder_path="."):
    """
    分析指定文件夹内所有Excel文件中的伙食退伙数据，
    并生成一个只包含姓名、天数和金额的精简报告。
    """
    excel_files = glob.glob(os.path.join(folder_path, '*.xlsx'))
    if not excel_files:
        print(f"在文件夹 '{folder_path}' 中未找到任何Excel (.xlsx) 文件。")
        return

    try:
        # 跳过第一行标题，将第二行作为表头
        all_data_df = pd.concat(
            (pd.read_excel(f, header=1) for f in excel_files),
            ignore_index=True
        )
    except Exception as e:
        print(f"读取Excel文件时出错: {e}")
        print("请确保文件格式正确，且数据表头在第二行。")
        return

    # --- 数据清洗和预处理 ---
    all_data_df['停伙开始时间'] = pd.to_datetime(all_data_df['停伙开始时间'])
    all_data_df['停伙结束时间'] = pd.to_datetime(all_data_df['停伙结束时间'])
    all_data_df['停伙天数'] = pd.to_numeric(all_data_df['停伙天数'], errors='coerce')
    all_data_df.dropna(subset=['停伙天数', '退伙人', '停伙开始时间', '停伙结束时间'], inplace=True)

    # --- 规则1：检查报销天数是否与实际休假天数相符 ---
    all_data_df['实际休假天数'] = (all_data_df['停伙结束时间'] - all_data_df['停伙开始时间']).dt.days + 1
    mismatched_days_df = all_data_df[all_data_df['停伙天数'] != all_data_df['实际休假天数']].copy()

    # --- 规则2：检查年度累计报销天数是否超过30天 ---
    all_data_df['年份'] = all_data_df['停伙开始时间'].dt.year
    yearly_summary = all_data_df.groupby(['年份', '退伙人'])['停伙天数'].sum().reset_index()
    over_limit_df = yearly_summary[yearly_summary['停伙天数'] > 30].copy()

    # --- 生成并打印报告 ---
    print("-" * 60)
    print("伙食费报销数据核对报告")
    print("-" * 60)

    # 【新版报告】报告天数不符项
    if not mismatched_days_df.empty:
        print("\n[!] 发现“报销天数”与“实际休假天数”不符的记录：\n")
        # 添加单日额度列
        mismatched_days_df['单日退伙额度'] = DAILY_REFUND_RATE
        # 选取需要的列
        report_df = mismatched_days_df[['退伙人', '实际休假天数', '停伙天数', '单日退伙额度', '退伙金额']]
        print(report_df.rename(columns={
            '退伙人': '姓名',
            '实际休假天数': '应报天数',
            '停伙天数': '实报天数',
            '退伙金额': '报销金额'
        }).to_string(index=False))
    else:
        print("\n[*] 所有记录的报销天数均与实际休假天数相符。")

    # 【新版报告】报告年度超标项
    if not over_limit_df.empty:
        print("\n\n[!] 发现年度报销总天数超过30天的员工：\n")
        # 添加单日额度列和计算年度总额
        over_limit_df['单日退伙额度'] = DAILY_REFUND_RATE
        over_limit_df['年度报销总额'] = round(over_limit_df['停伙天数'] * DAILY_REFUND_RATE, 2)
        # 选取需要的列
        report_df = over_limit_df[['退伙人', '停伙天数', '单日退伙额度', '年度报销总额']]
        print(report_df.rename(columns={
            '退伙人': '姓名',
            '停伙天数': '年度总天数'
        }).to_string(index=False))
    else:
        print("\n\n[*] 所有员工的年度报销总天数均未超过30天。")

    print("\n" + "-" * 60)
    print("报告结束")
    print("-" * 60)

if __name__ == "__main__":
    # 将 '伙食费报销单' 替换为你的Excel文件所在的文件夹名称
    target_folder = "/Users/xiaoming/Documents/work/workspace/code/DataTest/dan/统计伙食/伙食费报销单"
    analyze_meal_refunds(target_folder)