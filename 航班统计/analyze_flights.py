import pandas as pd
import warnings

# 忽略一些pandas在处理Excel时可能产生的警告
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')


def analyze_flight_data():
    """
    分析指定日期的航班计划与实际执行情况。
    读取FPLA和FODC的Excel文件，按小时统计掌握情况，并生成结果Excel。
    【新增】过滤FODC数据中的外航航班。
    """
    # --- 1. 配置参数 ---
    FPLA_FILE = '23-fpla.xlsx'
    FODC_FILE = '23-fodc.xlsx'
    OUTPUT_FILE = '航班掌握情况分析结果_已过滤外航.xlsx'
    AIRPORT_CODE = 'ZGGG'  # 广州白云机场 ICAO 代码
    ANALYSIS_DATE_STR = '2025-09-23'  # 请根据您的数据修改此日期

    # --- 2. 数据加载与预处理 ---
    try:
        fpla_df = pd.read_excel(FPLA_FILE)
        fodc_df = pd.read_excel(FODC_FILE)
    except FileNotFoundError as e:
        print(f"错误：找不到文件 {e.filename}。请确保脚本和Excel文件在同一目录下。")
        return

    # 统一将列名转为大写，以匹配SQL schema
    fpla_df.columns = [col.upper() for col in fpla_df.columns]
    fodc_df.columns = [col.upper() for col in fodc_df.columns]

    # 【关键修改】定义外航正则表达式并过滤FODC数据
    foreign_airline_regex = '^(AAR|AIH|AIQ|ALK|ANA|ATC|AXM|BBC|BDJ|CAL|CAO|CNW|CPA|CSG|ETH|FDX|GFA|GTI|HVN|JAL|KAL|KME|KHV|LAO|MAS|MFX|MMA|MSR|MXD|MZT|QNT|QTR|RMY|SIA|SVA|T7RDJ|TAG|TGW|THA|THY|TLM|TNU|TXJ|UAE|VJC|VPCKG)'

    # 确保CALLSIGN列是字符串类型，并将NaN值替换为空字符串以避免匹配错误
    fodc_df['CALLSIGN'] = fodc_df['CALLSIGN'].astype(str).fillna('')

    # 使用正则表达式过滤，保留那些CALLSIGN不匹配外航模式的航班
    original_fodc_count = len(fodc_df)
    fodc_df = fodc_df[~fodc_df['CALLSIGN'].str.match(foreign_airline_regex)]
    filtered_fodc_count = len(fodc_df)
    print(f"FODC数据过滤：已从 {original_fodc_count} 条记录中排除外航航班，剩余 {filtered_fodc_count} 条记录用于分析。")

    # 定义日期时间转换函数
    def to_datetime_safe(series):
        return pd.to_datetime(series, format='%Y%m%d%H%M%S', errors='coerce')

    # 转换FPLA相关时间列
    msg_time_col = 'SENDTIME' if 'SENDTIME' in fpla_df.columns else 'CREATETIME'
    fpla_df['MSG_TIME'] = pd.to_datetime(fpla_df[msg_time_col], errors='coerce')
    fpla_df['SOBT'] = to_datetime_safe(fpla_df['SOBT'])
    fpla_df['SIBT'] = to_datetime_safe(fpla_df['SIBT'])

    # 转换FODC相关时间列
    fodc_df['ATOT'] = to_datetime_safe(fodc_df['ATOT'])
    fodc_df['ALDT'] = to_datetime_safe(fodc_df['ALDT'])

    # 删除转换后为空的关键时间列或唯一标识列的行
    fpla_df.dropna(subset=['MSG_TIME', 'FLIGHTKEY'], inplace=True)
    fodc_df.dropna(subset=['FLIGHTKEY'], inplace=True)

    # --- 3. 按小时进行迭代分析 ---
    results = []
    analysis_date = pd.to_datetime(ANALYSIS_DATE_STR)

    for hour in range(25):
        current_node_time = analysis_date + pd.Timedelta(hours=hour)
        day_start = analysis_date
        day_end = analysis_date + pd.Timedelta(days=1)

        # --- FPLA 分析 ---
        fpla_known_at_node = fpla_df[fpla_df['MSG_TIME'] <= current_node_time].copy()
        fpla_latest = fpla_known_at_node.sort_values('MSG_TIME').drop_duplicates('FLIGHTKEY', keep='last')
        is_departure = (fpla_latest['DEPAP'] == AIRPORT_CODE) & (fpla_latest['SOBT'] >= day_start) & (
                fpla_latest['SOBT'] < day_end)
        is_arrival = (fpla_latest['ARRAP'] == AIRPORT_CODE) & (fpla_latest['SIBT'] >= day_start) & (
                fpla_latest['SIBT'] < day_end)
        fpla_today = fpla_latest[is_departure | is_arrival]
        is_cancelled = fpla_today['PSCHEDULESTATUS'] == 'CNL'
        plan_exec_dep = fpla_today[is_departure & ~is_cancelled].shape[0]
        plan_cnl_dep = fpla_today[is_departure & is_cancelled].shape[0]
        plan_exec_arr = fpla_today[is_arrival & ~is_cancelled].shape[0]
        plan_cnl_arr = fpla_today[is_arrival & is_cancelled].shape[0]

        # --- FODC 分析 ---
        actual_dep_done = (fodc_df['RDEPAP'] == AIRPORT_CODE) & (fodc_df['ATOT'] <= current_node_time)
        actual_arr_done = (fodc_df['RARRAP'] == AIRPORT_CODE) & (fodc_df['ALDT'] <= current_node_time)
        actual_dep_today = (fodc_df['ATOT'] >= day_start) & (fodc_df['ATOT'] < day_end)
        actual_arr_today = (fodc_df['ALDT'] >= day_start) & (fodc_df['ALDT'] < day_end)
        actual_exec_dep = fodc_df[actual_dep_done & actual_dep_today]['FLIGHTKEY'].nunique()
        actual_exec_arr = fodc_df[actual_arr_done & actual_arr_today]['FLIGHTKEY'].nunique()

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
    print("\n最终结果预览：")
    print(result_df.to_string(index=False))


if __name__ == '__main__':
    analyze_flight_data()