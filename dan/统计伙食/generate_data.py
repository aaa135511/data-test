import pandas as pd
from faker import Faker
import random
from datetime import date, timedelta
import os
# openpyxl的样式模块，用于美化标题
from openpyxl.styles import Font, Alignment

# 初始化Faker库，用于生成中文名
fake = Faker('zh_CN')


def save_df_with_title_to_excel(df, file_path, title):
    """
    将DataFrame保存到Excel，并在顶部添加一个居中的大标题。

    Args:
        df (pandas.DataFrame): 要保存的数据。
        file_path (str): Excel文件保存路径。
        title (str): 要添加的大标题。
    """
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        # 将数据写入到Excel，从第二行开始（第一行留给标题）
        df.to_excel(writer, index=False, startrow=1)

        # 访问工作簿和工作表对象
        workbook = writer.book
        worksheet = writer.sheets['Sheet1']

        # 设置标题样式
        title_font = Font(name='宋体', size=20, bold=True)
        title_alignment = Alignment(horizontal='center', vertical='center')

        # 合并单元格以放置标题
        # df.shape[1] 获取DataFrame的列数
        worksheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=df.shape[1])

        # 写入标题并应用样式
        title_cell = worksheet.cell(row=1, column=1)
        title_cell.value = title
        title_cell.font = title_font
        title_cell.alignment = title_alignment

        # 简单调整列宽
        for col_idx, col in enumerate(df.columns, 1):
            worksheet.column_dimensions[chr(64 + col_idx)].width = 15


def generate_virtual_data(num_records=25):
    """
    生成虚拟的伙食退伙数据。
    （此函数内部逻辑与之前版本相同）
    """
    data = []
    names = [fake.name() for _ in range(10)]

    name_for_over_limit = names[0]  # 王强 -> 用于超标测试
    name_for_mismatch = names[1]  # 李丽 -> 用于天数不符测试

    # 生成超标数据
    for _ in range(2):
        duration = random.randint(18, 22)
        start_date = date(2025, random.randint(1, 10), random.randint(1, 28))
        end_date = start_date + timedelta(days=duration - 1)
        record = {"退伙人": name_for_over_limit, "停伙开始时间": start_date, "停伙结束时间": end_date,
                  "停伙天数": float(duration)}
        data.append(record)

    # 生成天数不符数据
    duration = random.randint(10, 15)
    start_date = date(2025, random.randint(1, 11), random.randint(1, 28))
    end_date = start_date + timedelta(days=duration - 1)
    mismatched_days = duration + random.choice([-2, 2])
    data.append({"退伙人": name_for_mismatch, "停伙开始时间": start_date, "停伙结束时间": end_date,
                 "停伙天数": float(mismatched_days)})

    # 生成其余合规数据
    remaining_records = num_records - len(data)
    for _ in range(remaining_records):
        person = random.choice(names)
        duration = random.randint(2, 28)
        start_date = date(2025, random.randint(1, 11), random.randint(1, 28))
        end_date = start_date + timedelta(days=duration - 1)
        data.append(
            {"退伙人": person, "停伙开始时间": start_date, "停伙结束时间": end_date, "停伙天数": float(duration)})

    df = pd.DataFrame(data)
    df["序号"] = range(1, len(df) + 1)
    df["退伙时间"] = df["停伙结束时间"] + timedelta(days=random.randint(5, 30))
    df["停伙结束餐"] = [random.choice(["早餐", "午餐", "晚餐"]) for _ in range(len(df))]
    df["停伙开始餐"] = [random.choice(["早餐", "午餐", "晚餐"]) for _ in range(len(df))]
    df["退伙金额"] = round(df["停伙天数"] * 35.0, 2)

    column_order = ["序号", "退伙时间", "退伙人", "停伙结束时间", "停伙结束餐", "停伙开始时间", "停伙开始餐",
                    "停伙天数", "退伙金额"]
    df = df[column_order]

    df['退伙时间'] = df['退伙时间'].apply(lambda x: x.strftime('%Y-%m-%d'))
    df['停伙结束时间'] = df['停伙结束时间'].apply(lambda x: x.strftime('%Y-%m-%d'))
    df['停伙开始时间'] = df['停伙开始时间'].apply(lambda x: x.strftime('%Y-%m-%d'))

    return df


if __name__ == "__main__":
    output_dir = "伙食费报销单"
    os.makedirs(output_dir, exist_ok=True)

    full_df = generate_virtual_data(num_records=25)
    df1 = full_df.iloc[:13]
    df2 = full_df.iloc[13:]

    file_path1 = os.path.join(output_dir, "伙食退伙凭证_1.xlsx")
    file_path2 = os.path.join(output_dir, "伙食退伙凭证_2.xlsx")

    # 使用新的保存函数
    save_df_with_title_to_excel(df1, file_path1, "伙食退伙凭证")
    save_df_with_title_to_excel(df2, file_path2, "伙食退伙凭证")

    print(f"成功生成了两个带标题的示例Excel文件，保存在 '{output_dir}' 文件夹中。")