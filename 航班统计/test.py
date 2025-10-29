import pandas as pd
import warnings

# 忽略一些pandas在处理Excel时可能产生的警告
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')


def analyze_flight_data():
    """
    最终版分析脚本：
    1. 分析周期严格限定在指定日期的00:00至24:00。
    2. 识别并导出在24:00点仍未执行的航班明细。
    3. 将所有结果整合到一个多Sheet的Excel文件中。
    """
    # --- 1. 配置参数 ---
    FPLA_FILE = '23-fpla.xlsx'
    FODC_FILE = '23-fodc.xlsx'
    AIRPORT_CODE = 'ZGGG'
    ANALYSIS_DATE_STR = '2025-09-23'

    # 【关键修改】不再延长统计时间
    EXTENSION_HOURS = 0

    OUTPUT_FILE = f'航班掌握情况分析报告_仅23日当天.xlsx'

    # --- 2. 数据加载与预处理 ---
    try:
        fpla_df = pd.read_excel(FPLA_FILE)
        fodc_df = pd.read_excel(FODC_FILE)
    except FileNotFoundError as e:
        print(f"错误：找不到文件 {e.filename}。请确保脚本和Excel文件在同一目录下。")
        return

    # 统一列名为大写并清洗CALLSIGN
    for df in [fpla_df, fodc_df]:
        df.columns = [col.upper() for col in df.columns]
        df['CALLSIGN'] = df['CALLSIGN'].astype(str).str.strip()

    # 过滤FODC中的外航
    foreign_airline_regex = '^(AAR|AIH|AIQ|ALK|ANA|ATC|AXM|BBC|BDJ|CAL|CNW|CPA|CSG|ETH|FDX|GFA|GTI|HVN|JAL|KAL|KME|KHV|LAO|MAS|MFX|MMA|MSR|MXD|MZT|QNT|QTR|RMY|SIA|SVA|T7RDJ|TAG|TGW|THA|THY|TLM|TNU|TXJ|UAE|VJC|VPCKG)'
    fodc_df_filtered = fodc_df[~fodc_df['CALLSIGN'].str.match(foreign_airline_regex)].copy()

    # 时间格式转换
    def to_datetime_safe(series):
        return pd.to_datetime(series, format='%Y%m%d%H%M%S', errors='coerce')

    msg_time_col = 'SENDTIME' if 'SENDTIME' in fpla_df.columns else 'CREATETIME'
    fpla_df['MSG_TIME'] = pd.to_datetime(fpla_df[msg_time_col], errors='coerce')
    fpla_df['SOBT'] = to_datetime_safe(fpla_df['SOBT'])
    fpla_df['SIBT'] = to_datetime_safe(fpla_df['SIBT'])
    fodc_df_filtered.loc[:, 'ATOT'] = to_datetime_safe(fodc_df_filtered['ATOT'])
    fodc_df_filtered.loc[:, 'ALDT'] = to_datetime_safe(fodc_df_filtered['ALDT'])

    # 清理无效数据
    fpla_df.dropna(subset=['MSG_TIME', 'CALLSIGN'], inplace=True)
    fodc_df_filtered.dropna(subset=['CALLSIGN'], inplace=True)

    # --- 3. 按小时进行迭代分析 ---
    results = []
    analysis_date = pd.to_datetime(ANALYSIS_DATE_STR)
    total_analysis_points = 25 + EXTENSION_HOURS  # 结果为25，循环25次 (0-24)

    print(f"开始进行航班情况分析，分析周期为 {ANALYSIS_DATE_STR} 00:00 至 24:00...")

    for hour in range(total_analysis_points):
        current_node_time = analysis_date + pd.Timedelta(hours=hour)
        plan_day_start = analysis_date
        plan_day_end = analysis_date + pd.Timedelta(days=1)

        # FPLA 分析
        fpla_known_at_node = fpla_df[fpla_df['MSG_TIME'] <= current_node_time].copy()
        fpla_latest = fpla_known_at_node.sort_values('MSG_TIME').drop_duplicates('CALLSIGN', keep='last')
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
        plan_exec_callsigns = fpla_today[~is_cancelled]['CALLSIGN'].unique()

        # FODC 分析
        fodc_of_interest = fodc_df_filtered[fodc_df_filtered['CALLSIGN'].isin(plan_exec_callsigns)]
        actual_dep_done = (fodc_of_interest['RDEPAP'] == AIRPORT_CODE) & (fodc_of_interest['ATOT'] <= current_node_time)
        actual_arr_done = (fodc_of_interest['RARRAP'] == AIRPORT_CODE) & (fodc_of_interest['ALDT'] <= current_node_time)
        actual_exec_dep = fodc_of_interest[actual_dep_done]['CALLSIGN'].nunique()
        actual_exec_arr = fodc_of_interest[actual_arr_done]['CALLSIGN'].nunique()
        fodc_executed = fodc_of_interest[actual_dep_done | actual_arr_done]
        total_actual_exec = fodc_executed['CALLSIGN'].nunique()

        # 汇总计算
        total_plan_exec = plan_exec_dep + plan_exec_arr

        node_time_str = current_node_time.strftime('%Y-%m-%d %H:%M:%S')
        if hour == 24:
            node_time_str = f"{ANALYSIS_DATE_STR} 24:00:00"

        results.append({
            '统计节点': node_time_str,
            '计划执行离港': plan_exec_dep, '计划取消离港': plan_cnl_dep,
            '计划执行进港': plan_exec_arr, '计划取消进港': plan_cnl_arr,
            '总班次': plan_exec_dep + plan_cnl_dep + plan_exec_arr + plan_cnl_arr,
            '总计划执行': total_plan_exec,
            '总取消': plan_cnl_dep + plan_cnl_arr,
            '实际执行离港': actual_exec_dep, '实际执行进港': actual_exec_arr,
            '实际执行': total_actual_exec,
            '待执行': total_plan_exec - total_actual_exec
        })

    # --- 4. 识别最终未执行的航班 ---
    print("分析完成，正在识别在24:00点仍未执行的航班...")

    # 获取在24:00点时，当天的最终计划航班列表
    final_plan_callsigns = set(plan_exec_callsigns)

    # 获取在24:00点时，已执行的航班列表
    final_executed_callsigns = set(fodc_executed['CALLSIGN'].unique())

    # 计算差集得到未执行航班的CALLSIGN
    unexecuted_callsigns = final_plan_callsigns - final_executed_callsigns

    # 从最新的FPLA记录中筛选出这些未执行航班的详细信息
    final_fpla_latest = fpla_df.sort_values('MSG_TIME').drop_duplicates('CALLSIGN', keep='last')
    unexecuted_flights_df = final_fpla_latest[final_fpla_latest['CALLSIGN'].isin(unexecuted_callsigns)]

    print(f"识别完成，共找到 {len(unexecuted_callsigns)} 个在24:00点仍未执行的航班。")

    # --- 5. 生成并保存多Sheet的Excel报告 ---
    summary_df = pd.DataFrame(results)

    print(f"正在生成Excel报告文件：{OUTPUT_FILE}")
    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='航班掌握情况分析', index=False)
        unexecuted_flights_df.to_excel(writer, sheet_name='未执行航班明细', index=False)
        fpla_df.to_excel(writer, sheet_name='FPLA原始明细', index=False)
        fodc_df_filtered.to_excel(writer, sheet_name='FODC原始明细', index=False)

    print("\n报告生成成功！")


if __name__ == '__main__':
    analyze_flight_data()