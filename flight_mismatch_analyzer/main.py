import pandas as pd
import requests
import pymysql
import pymysql.cursors
from dotenv import load_dotenv
import os
from datetime import datetime
import logging
from collections import defaultdict

# --- 配置日志记录 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- 1. 环境设置与数据加载 (No changes from previous version) ---
def load_and_filter_data(filepath):
    if not os.path.exists(filepath):
        logging.error(f"输入文件未找到: {filepath}")
        return None
    logging.info(f"正在从 {filepath} 加载数据...")
    df = pd.read_excel(filepath)
    df_filtered = df.dropna(subset=['实际起飞时间']).copy()
    df_mismatched = df_filtered[df_filtered['前序航班键'].isnull()].copy()
    logging.info(f"数据加载完成。共发现 {len(df_mismatched)} 条未匹配到前序的航班需要分析。")
    return df_mismatched


# --- 2. 调用外部接口查询前序航班 (No changes from previous version) ---
def format_time_for_api(time_val):
    if pd.isna(time_val): return None
    try:
        time_str = str(int(time_val))
        if len(time_str) != 12: return None
        return datetime.strptime(time_str, '%Y%m%d%H%M').strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return None


def prepare_api_payload(df):
    payload = []
    for _, row in df.iterrows():
        sobt_formatted = format_time_for_api(row['计划离港时间'])
        sibt_formatted = format_time_for_api(row['计划到港时间'])
        if all([row.get('航空器识别标志'), row.get('计划起飞机场'), row.get('计划降落机场'), sobt_formatted,
                sibt_formatted]):
            payload.append({
                "callSign": row['航空器识别标志'], "regNumber": row.get('实际执行飞机号'),
                "depAP": row['计划起飞机场'], "arrAP": row['计划降落机场'],
                "sobt": sobt_formatted, "sibt": sibt_formatted
            })
    return payload


def query_preceding_flight_api(payload):
    api_url = "http://10.230.146.110:8080/api/flight-leg/relationship/batch"
    if not payload:
        logging.warning("API请求体为空，跳过接口查询。")
        return []
    logging.info(f"正在向API发送 {len(payload)} 条航班的查询请求...")
    try:
        response = requests.post(api_url, json=payload, timeout=120)
        response.raise_for_status()
        logging.info("API请求成功。")
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"API请求失败: {e}")
        return []


# --- 3. 数据库深度排查与分析 (REFACTORED FOR BATCHING) ---

def get_db_connection():
    """建立并返回一个MySQL数据库连接"""
    try:
        db_config = {
            'host': '10.230.146.110', 'port': 3306, 'user': 'root',
            'password': '101-FvlOP.pAjiWr6jFTdHt_698bdUgBAli_', 'database': 'data_core',
            'charset': 'utf8mb4', 'cursorclass': pymysql.cursors.DictCursor
        }
        connection = pymysql.connect(**db_config)
        logging.info("数据库连接成功。")
        return connection
    except pymysql.MySQLError as e:
        logging.error(f"数据库连接失败: {e}")
        return None


def normalize_sobt_to_date_str(sobt):
    """从不同格式的SOBT字段中提取YYYYMMDD格式的日期字符串"""
    if isinstance(sobt, datetime):
        return sobt.strftime('%Y%m%d')
    if isinstance(sobt, str) and len(sobt) >= 8:
        return sobt[:8]
    return None


def batch_investigate_flights_in_db(connection, flights_to_query):
    """
    在数据库中批量查询所有需要的航班信息，并按 (callsign, execute_date) 组织。
    :param connection: 数据库连接对象
    :param flights_to_query: 一个包含 (callsign, execute_date) 元组的集合
    :return: 一个嵌套字典，结构为: {(callsign, date): {'FPLA': [...], 'FODC': [...]}, ...}
    """
    if not flights_to_query:
        return {}

    logging.info(f"准备从数据库批量查询 {len(flights_to_query)} 个唯一航班的数据...")

    # 构建动态的WHERE IN子句
    conditions = []
    params = []
    for callsign, exec_date in flights_to_query:
        conditions.append("(CALLSIGN = %s AND SOBT LIKE %s)")
        params.extend([callsign, f"{exec_date}%"])

    where_clause = " OR ".join(conditions)

    # 对于FLSC_FLIGHT，条件不同
    flsc_conditions = []
    flsc_params = []
    for callsign, exec_date in flights_to_query:
        flsc_conditions.append("(CALLSIGN = %s AND DATE(SOBT) = STR_TO_DATE(%s, '%%Y%%m%%d'))")
        flsc_params.extend([callsign, exec_date])
    flsc_where_clause = " OR ".join(flsc_conditions)

    queries = {
        "FPLA": (f"SELECT * FROM gxpt_aloi_fpla WHERE {where_clause}", params),
        "FODC": (f"SELECT * FROM gxpt_osci_fodc WHERE {where_clause}", params),
        "AGG": (f"SELECT * FROM dsp_flight_aggregation WHERE {where_clause}", params),
        "FLSC_FLIGHT": (f"SELECT * FROM gxpt_osci_flsc_flight WHERE {flsc_where_clause}", flsc_params)
    }

    # 执行所有批量查询
    raw_results = {}
    try:
        with connection.cursor() as cursor:
            for name, (sql, query_params) in queries.items():
                cursor.execute(sql, query_params)
                raw_results[name] = cursor.fetchall()
    except pymysql.MySQLError as e:
        logging.error(f"批量数据库查询失败: {e}")
        return {}

    # 将平铺的结果组织成按航班标识的嵌套字典
    organized_data = defaultdict(lambda: defaultdict(list))
    for table_name, records in raw_results.items():
        for record in records:
            callsign = record.get('CALLSIGN') or record.get('callSign')
            sobt = record.get('SOBT') or record.get('sobt')
            exec_date = normalize_sobt_to_date_str(sobt)
            if callsign and exec_date:
                organized_data[(callsign, exec_date)][table_name].append(record)

    logging.info("批量查询和数据组织完成。")
    return organized_data


def analyze_and_get_conclusion(flight_row, api_result, all_db_data):
    """核心分析逻辑，使用预先获取的数据库数据进行分析"""
    if 'previous' not in api_result or not api_result.get('previous'):
        return "结论：接口未查询到前序航班信息，匹配失败属正常。"

    preceding_flight = api_result['previous']
    preceding_callsign = preceding_flight.get('callSign')

    try:
        preceding_sobt_dt = datetime.strptime(preceding_flight['sobt'], '%Y-%m-%d %H:%M:%S')
        preceding_exec_date = preceding_sobt_dt.strftime('%Y%m%d')
    except (ValueError, TypeError):
        return f"结论：接口返回的前序航班({preceding_callsign})时间格式不正确。"

    # 从预加载的数据中查找前序航班的记录
    preceding_db_records = all_db_data.get((preceding_callsign, preceding_exec_date), {})

    if not preceding_db_records.get('AGG'):
        return f"数据问题：接口查到前序航班({preceding_callsign})，但该航班记录未在聚合表(dsp_flight_aggregation)中找到，导致无法关联。"

    if not preceding_db_records.get('FODC'):
        return f"数据问题：接口查到前序航班({preceding_callsign})，但核心实飞数据表(gxpt_osci_fodc)中无此记录，聚合可能因此失败。"

    # 查找当前航班的数据库记录
    current_callsign = flight_row['航空器识别标志']
    current_exec_date = str(int(flight_row['计划执行日期']))
    current_db_records = all_db_data.get((current_callsign, current_exec_date), {})

    if not current_db_records.get('AGG'):
        return f"数据问题：当前航班({current_callsign})自身记录在聚合表中缺失。"

    current_reg = current_db_records['AGG'][0].get('regNumber')
    preceding_reg = preceding_db_records['AGG'][0].get('regNumber')

    if current_reg and preceding_reg and current_reg != preceding_reg:
        return f"数据不一致：当前航班注册号({current_reg})与前序航班注册号({preceding_reg})在聚合表中不匹配。"

    return "系统问题：接口能查到前序，且数据库中源数据和聚合数据基本齐全。问题可能出在航班环匹配程序的内部逻辑（如时间窗口、机场代码转换等）。"


# --- 4. 主执行流程 ---

def main():
    """主执行函数"""
    load_dotenv()
    report_date = os.getenv('REPORT_DATE')
    if not report_date:
        logging.error("未在.env文件中设置REPORT_DATE，程序终止。")
        return

    start_date_str = f"{report_date}000000"
    end_date_dt = datetime.strptime(report_date, '%Y%m%d') + pd.Timedelta(days=1)
    end_date_str = end_date_dt.strftime('%Y%m%d%H%M%S')

    input_filename = f"Flight-Normality-Dynamic---{start_date_str}-{end_date_str}.xlsx"
    output_filename = f"Flight-Normality-Dynamic-Result---{report_date}.xlsx"
    input_path = os.path.join('input', input_filename)
    output_path = os.path.join('output', output_filename)

    # 步骤1: 加载并筛选数据
    mismatched_df = load_and_filter_data(input_path)
    if mismatched_df is None or mismatched_df.empty:
        logging.info("没有需要处理的数据，程序结束。")
        return

    # 步骤2: 调用API
    api_payload = prepare_api_payload(mismatched_df)
    api_results = query_preceding_flight_api(api_payload)
    api_results_map = {f"{res['request']['callSign']}-{res['request']['depAP']}-{res['request']['sobt']}": res for res
                       in api_results}

    # 步骤3.1: 收集所有需要查询数据库的航班
    flights_to_query_db = set()
    for _, row in mismatched_df.iterrows():
        flights_to_query_db.add((row['航空器识别标志'], str(int(row['计划执行日期']))))

    for result in api_results:
        if 'previous' in result and result.get('previous'):
            pre_flight = result['previous']
            try:
                pre_sobt_dt = datetime.strptime(pre_flight['sobt'], '%Y-%m-%d %H:%M:%S')
                pre_exec_date = pre_sobt_dt.strftime('%Y%m%d')
                flights_to_query_db.add((pre_flight['callSign'], pre_exec_date))
            except (ValueError, TypeError):
                continue

    # 步骤3.2: 批量查询数据库并组织数据
    db_conn = get_db_connection()
    if not db_conn: return

    all_db_data = {}
    try:
        all_db_data = batch_investigate_flights_in_db(db_conn, flights_to_query_db)
    finally:
        db_conn.close()
        logging.info("数据库连接已关闭。")

    # 步骤3.3: 逐条分析（使用内存中的数据）
    conclusions = []
    for _, row in mismatched_df.iterrows():
        sobt_formatted = format_time_for_api(row['计划离港时间'])
        lookup_key = f"{row['航空器识别标志']}-{row['计划起飞机场']}-{sobt_formatted}"
        api_result = api_results_map.get(lookup_key)

        if not api_result:
            conclusion = "结论：在API批量查询的返回结果中未找到此航班，可能请求失败或被过滤。"
        else:
            conclusion = analyze_and_get_conclusion(row, api_result, all_db_data)
        conclusions.append(conclusion)

    # 步骤4: 输出结果
    mismatched_df['分析结论'] = conclusions
    if not os.path.exists('output'): os.makedirs('output')
    mismatched_df.to_excel(output_path, index=False, engine='openpyxl')
    logging.info(f"分析完成，包含结论的报告已保存至: {output_path}")


if __name__ == "__main__":
    main()