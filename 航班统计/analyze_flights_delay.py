import pandas as pd
import warnings

# 忽略一些pandas在处理Excel时可能产生的警告
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')


def analyze_flight_data():
    """
    分析指定日期的航班计划与实际执行情况。
    【已恢复】分析周期仅为指定日期当天的00:00至24:00。
    """
    # --- 1. 配置参数 ---
    FPLA_FILE = '23-fpla.xlsx'
    FODC_FILE = '23-fodc.xlsx'
    AIRPORT_CODE = 'ZGGG'
    ANALYSIS_DATE_STR = '2025-09-23'

    OUTPUT_FILE = '航班掌握情况分析结果_仅23日当天_用于核对.xlsx'

    # --- 2. 数据加载与预处理 ---
    try:
        fpla_df = pd.read_excel(FPLA_FILE)
        fodc_df = pd.read_excel(FODC_FILE)
    except FileNotFoundError as e:
        print(f"错误：找不到文件 {e.filename}。请确保脚本和Excel文件在同一目录下。")
        return

    # 统一列名为大写
    fpla_df.columns = [col.upper() for col in fpla_df.columns]
    fodc_df.columns = [col.upper() for col in fodc_df.columns]

    # 过滤FODC中的外航
    foreign_airline_regex = '^(AAR|AIH|AIQ|ALK|ANA|ATC|AXM|BBC|BDJ|CAL|CNW|CPA|CSG|ETH|FDX|GFA|GTI|HVN|JAL|KAL|KME|KHV|LAO|MAS|MFX|MMA|MSR|MXD|MZT|QNT|QTR|RMY|SIA|SVA|T7RDJ|TAG|TGW|THA|THY|TLM|TNU|TXJ|UAE|VJC|VPCKG)'
    fodc_df['CALLSIGN'] = fodc_df['CALLSIGN'].astype(str).fillna('')
    fodc_df = fodc_df[~fodc_df['CALLSIGN'].str.match(foreign_airline_regex)]

    # 时间格式转换
    def to_datetime_safe(series):
        return pd.to_datetime(series, format='%Y%m%d%H%M%S', errors='coerce')

    msg_time_col = 'SENDTIME' if 'SENDTIME' in fpla_df.columns else 'CREATETIME'
    fpla_df['MSG_TIME'] = pd.to_datetime(fpla_df[msg_time_col], errors='coerce')
    fpla_df['SOBT'] = to_datetime_safe(fpla_df['SOBT'])
    fpla_df['SIBT'] = to_datetime_safe(fpla_df['SIBT'])
    fodc_df['ATOT'] = to_datetime_safe(fodc_df['ATOT'])
    fodc_df['ALDT'] = to_datetime_safe(fodc_df['ALDT'])

    # 清理无效数据
    fpla_df.dropna(subset=['MSG_TIME', 'FLIGHTKEY'], inplace=True)
    fodc_df.dropna(subset=['FLIGHTKEY'], inplace=True)

    # --- 3. 按小时进行迭代分析 ---
    results = []
    analysis_date = pd.to_datetime(ANALYSIS_DATE_STR)

    # 【关键修改】循环恢复为25个节点 (00:00 to 24:00)
    print("开始进行航班情况分析，分析周期为当天00:00至24:00...")

    for hour in range(25):
        current_node_time = analysis_date + pd.Timedelta(hours=hour)
        plan_day_start = analysis_date
        plan_day_end = analysis_date + pd.Timedelta(days=1)

        # --- FPLA 分析 ---
        fpla_known_at_node = fpla_df[fpla_df['MSG_TIME'] <= current_node_time].copy()
        fpla_latest = fpla_known_at_node.sort_values('MSG_TIME').drop_duplicates('FLIGHTKEY', keep='last')

        is_departure = (fpla_latest['DEPAP'] == AIRPORT_CODE) & (fpla_latest['SOBT'] >= plan_day_start) & (
                fpla_latest['SOBT'] <= plan_day_end)
        is_arrival = (fpla_latest['ARRAP'] == AIRPORT_CODE) & (fpla_latest['SIBT'] >= plan_day_start) & (
                fpla_latest['SIBT'] <= plan_day_end)

        fpla_today = fpla_latest[is_departure | is_arrival]
        is_cancelled = fpla_today['PSCHEDULESTATUS'] == 'CNL'

        plan_exec_dep = fpla_today[is_departure & ~is_cancelled].shape[0]
        plan_cnl_dep = fpla_today[is_departure & is_cancelled].shape[0]
        plan_exec_arr = fpla_today[is_arrival & ~is_cancelled].shape[0]
        plan_cnl_arr = fpla_today[is_arrival & is_cancelled].shape[0]

        plan_exec_flightkeys = fpla_today[~is_cancelled]['FLIGHTKEY'].unique()

        # --- FODC 分析 ---
        fodc_of_interest = fodc_df[fodc_df['FLIGHTKEY'].isin(plan_exec_flightkeys)]
        actual_dep_done = (fodc_of_interest['RDEPAP'] == AIRPORT_CODE) & (fodc_of_interest['ATOT'] <= current_node_time)
        actual_arr_done = (fodc_of_interest['RARRAP'] == AIRPORT_CODE) & (fodc_of_interest['ALDT'] <= current_node_time)
        actual_exec_dep = fodc_of_interest[actual_dep_done]['FLIGHTKEY'].nunique()
        actual_exec_arr = fodc_of_interest[actual_arr_done]['FLIGHTKEY'].nunique()

        # --- 汇总计算 ---
        total_flights = plan_exec_dep + plan_cnl_dep + plan_exec_arr + plan_cnl_arr
        total_plan_exec = plan_exec_dep + plan_exec_arr
        total_cancelled = plan_cnl_dep + plan_cnl_arr
        total_actual_exec = actual_exec_dep + actual_exec_arr
        pending_exec = total_plan_exec - total_actual_exec

        node_time_str = current_node_time.strftime('%Y-%m-%d %H:%M:%S')
        if hour == 24:
            node_time_str = f"{ANALYSIS_DATE_STR} 24:00:00"

        results.append({
            '统计节点': node_time_str,
            '计划执行离港': plan_exec_dep,
            '计划取消离港': plan_cnl_dep,
            '计划执行进港': plan_exec_arr,
            '计划取消进港': plan_cnl_arr,
            '总班次': total_flights,
            '总计划执行': total_plan_exec,
            '总取消': total_cancelled,
            '实际执行离港': actual_exec_dep,
            '实际执行进港': actual_exec_arr,
            '实际执行': total_actual_exec,
            '待执行': pending_exec
        })

    # --- 5. 生成并保存结果 ---
    result_df = pd.DataFrame(results)
    column_order = [
        '统计节点', '计划执行离港', '计划取消离港', '计划执行进港', '计划取消进港',
        '总班次', '总计划执行', '总取消', '实际执行离港', '实际执行进港', '实际执行', '待执行'
    ]
    result_df = result_df[column_order]

    result_df.to_excel(OUTPUT_FILE, index=False)
    print(f"\n分析完成！结果已保存至文件：{OUTPUT_FILE}")
    print("\n最终结果预览 (全天)：")
    print(result_df.to_string(index=False))


if __name__ == '__main__':
    analyze_flight_data()