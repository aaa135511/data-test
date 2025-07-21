import json

import pandas as pd

# --- 配置 ---
FPLA_EXCEL_FILE = 'fpla_message-20250708-old.xlsx'
SAMPLE_COUNT_PER_STATUS = 3  # 每种变更状态提取的样本数量
# 定义我们关心的、可能发生变更的核心字段
# (基于gxpt_aloi_fpla_message表的schema)
KEY_DYNAMIC_FIELDS = [
    'CALLSIGN', 'GUFI', 'REGNUMBER', 'ADDRESSCODE', 'SOBT', 'SIBT', 'DEPAP', 'ARRAP',
    'PSAIRCRAFTTYPE', 'PMISSIONPROPERTY', 'PMISSIONTYPE', 'SROUTE',
    'PSCHEDULESTATUS', 'PFLIGHTLAG', 'PSHAREFLIGHTNO', 'EREGNUMBER', 'EADDRESSCODE',
    'EOBT', 'APTCALLSIGN', 'APTREGNUMBER', 'APTSOBT', 'APTSIBT', 'APTDEPAP', 'APTARRAP',
    'PDELAYREASON'
]


def analyze_fpla_dynamics(file_path: str, sample_count: int, key_fields: list) -> str:
    """
    分析FPLA消息Excel文件，为每种动态变更类型提取样本，并高亮变化字段。
    """
    try:
        df = pd.read_excel(file_path)
    except FileNotFoundError:
        return f"# 错误\n\n文件未找到: `{file_path}`。请检查文件名和路径是否正确。"
    except Exception as e:
        return f"# 错误\n\n读取Excel文件时发生错误: {e}"

    # 确保关键列存在
    if 'PSCHEDULESTATUS' not in df.columns or 'flightKey' not in df.columns or 'UPDATETIME' not in df.columns:
        return "# 错误\n\nExcel文件缺少'PSCHEDULESTATUS', 'flightKey', 或 'UPDATETIME'等关键列。"

    # 将时间列转为datetime方便排序，并处理空值
    df['UPDATETIME'] = pd.to_datetime(df['UPDATETIME'], errors='coerce')
    df = df.dropna(subset=['UPDATETIME'])
    df = df.sort_values(by=['flightKey', 'UPDATETIME'])

    # 筛选出所有动态变更消息
    dynamic_df = df[df['PSCHEDULESTATUS'] != 'ALL']
    unique_statuses = dynamic_df['PSCHEDULESTATUS'].unique()

    # --- 构建Markdown报告 ---
    markdown_report = ["# FPLA动态变更消息分析报告\n"]
    markdown_report.append(
        f"本文档分析了文件 `{file_path}` 中的FPLA动态消息，旨在理解每种变更类型的业务字段变化规则，为设计匹配引擎提供依据。\n")
    markdown_report.append(
        f"共发现 **{len(unique_statuses)}** 种动态变更类型: `{', '.join(map(str, unique_statuses))}`\n")

    for status in sorted(unique_statuses):
        markdown_report.append(f"\n---\n## 变更类型 (`PSCHEDULESTATUS`): `{status}`\n")

        # 找到所有这种状态的消息，并随机取样
        status_indices = dynamic_df[dynamic_df['PSCHEDULESTATUS'] == status].index

        # 为了找到变化，我们需要找到这些消息的前一条消息
        # 我们对每个flightKey的消息进行分组和编号
        df['msg_order'] = df.groupby('flightKey').cumcount()

        # 找出样本消息的前一条消息的索引
        prev_indices = [idx - 1 for idx in status_indices if
                        idx > 0 and df.loc[idx, 'flightKey'] == df.loc[idx - 1, 'flightKey']]

        # 从这些“有前一条消息”的样本中随机取样
        valid_sample_indices = [idx for idx in status_indices if idx - 1 in prev_indices]

        if not valid_sample_indices:
            markdown_report.append("\n未找到包含清晰变更的样本（或该类消息都是航班的第一条消息）。\n")
            continue

        actual_sample_count = min(sample_count, len(valid_sample_indices))
        sampled_indices = pd.Series(valid_sample_indices).sample(actual_sample_count).tolist()

        sample_num = 1
        for current_idx in sampled_indices:
            prev_idx = current_idx - 1
            current_msg = df.loc[current_idx]
            prev_msg = df.loc[prev_idx]

            markdown_report.append(f"\n### 示例 {sample_num} (航班: `{current_msg['flightKey']}`)\n")

            # --- 找出变化的字段 ---
            changed_fields_info = []
            for field in key_fields:
                if field not in df.columns: continue

                prev_val = str(prev_msg.get(field, ''))
                current_val = str(current_msg.get(field, ''))

                if prev_val != current_val:
                    info = f"- **{field}**: `{prev_val}`  ->  `{current_val}`"
                    changed_fields_info.append(info)

            if not changed_fields_info:
                markdown_report.append("\n*与前一条消息相比，在核心字段中未检测到明显变化。*\n")
            else:
                markdown_report.append("**核心字段变化详情:**\n")
                markdown_report.extend(changed_fields_info)

            markdown_report.append(
                f"\n**当前消息 (`PSCHEDULESTATUS`: `{current_msg['PSCHEDULESTATUS']}`, 更新时间: `{current_msg['UPDATETIME']}`):**")
            markdown_report.append("```json")
            # 只展示核心字段的JSON，避免过长
            current_msg_dict = current_msg[key_fields].dropna().to_dict()
            markdown_report.append(json.dumps(current_msg_dict, indent=2, ensure_ascii=False, default=str))
            markdown_report.append("```")

            sample_num += 1

    return "\n".join(markdown_report)


if __name__ == '__main__':
    final_report = analyze_fpla_dynamics(FPLA_EXCEL_FILE, SAMPLE_COUNT_PER_STATUS, KEY_DYNAMIC_FIELDS)

    print(final_report)

    # 保存报告到文件
    with open('fpla_analysis_report.md', 'w', encoding='utf-8') as f:
        f.write(final_report)
    print("\n报告已生成并保存到 fpla_analysis_report.md")