import pandas as pd
import requests
import pymysql
import pymysql.cursors
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import logging
from collections import defaultdict

# --- 配置日志记录 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- 1. 环境设置与数据加载 ---
def load_and_filter_data(filepath):
    """加载并筛选需要分析的航班数据。"""
    if not os.path.exists(filepath):
        logging.error(f"输入文件未找到: {filepath}")
        return None
    logging.info(f"正在从 {filepath} 加载数据...")
    df = pd.read_excel(filepath)
    # 确保关键列存在
    required_cols = ['实际起飞时间', '前序航班键', '实际执飞机号', '计划离港时间', '计划起飞机场', '航空器识别标志',
                     '计划执行日期']
    for col in required_cols:
        if col not in df.columns:
            logging.error(f"输入文件缺少必需的列: {col}")
            return None

    df_filtered = df.dropna(subset=['实际起飞时间']).copy()
    df_mismatched = df_filtered[df_filtered['前序航班键'].isnull()].copy()
    logging.info(f"数据加载完成。共发现 {len(df_mismatched)} 条未匹配到前序的航班需要分析。")
    return df_mismatched


# --- 2. 数据库连接与查询工具 ---
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


def batch_query_fpla_for_regnumbers(connection, reg_numbers, report_date_str):
    """根据机号列表，批量查询报告日及前一日的FPLA数据。"""
    if not reg_numbers:
        return []
    logging.info(f"正在为 {len(reg_numbers)} 个机号批量查询FPLA源数据...")

    report_date = datetime.strptime(report_date_str, '%Y%m%d')
    prev_date_str = (report_date - timedelta(days=1)).strftime('%Y%m%d')

    placeholders = ', '.join(['%s'] * len(reg_numbers))
    sql = f"""
        SELECT * FROM gxpt_aloi_fpla 
        WHERE 
            (REGNUMBER IN ({placeholders}) OR EREGNUMBER IN ({placeholders}))
            AND (SOBT LIKE %s OR SOBT LIKE %s)
    """
    params = list(reg_numbers) * 2 + [f"{report_date_str}%", f"{prev_date_str}%"]

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            results = cursor.fetchall()
            logging.info(f"FPLA源数据查询完毕，获取到 {len(results)} 条记录。")
            return results
    except pymysql.MySQLError as e:
        logging.error(f"批量查询FPLA数据时出错: {e}")
        return []


def find_potential_preceding_in_fpla_data(current_flight_row, fpla_source_data):
    """在内存中的FPLA数据里，为当前航班查找一个有效的潜在前序航班。"""
    current_reg = current_flight_row.get('实际执飞机号')
    current_dep_ap = current_flight_row.get('计划起飞机场')
    current_sobt = str(int(current_flight_row.get('计划离港时间')))

    if not all([current_reg, current_dep_ap, current_sobt]):
        return None

    # 寻找最接近当前航班起飞时间的前序航班
    best_candidate = None
    for candidate in fpla_source_data:
        candidate_reg = candidate.get('REGNUMBER') or candidate.get('EREGNUMBER')
        candidate_arr_ap = candidate.get('ARRAP')
        candidate_sobt = candidate.get('SOBT')

        if not all([candidate_reg, candidate_arr_ap, candidate_sobt]):
            continue

        if current_reg == candidate_reg and current_dep_ap == candidate_arr_ap and candidate_sobt < current_sobt:
            if best_candidate is None or candidate_sobt > best_candidate['SOBT']:
                best_candidate = candidate
    return best_candidate


def batch_query_aggregation_for_preceding(connection, preceding_flights_to_check):
    """批量查询聚合表中是否存在指定的前序航班。"""
    if not preceding_flights_to_check:
        return set()

    logging.info(f"正在聚合表中批量查询 {len(preceding_flights_to_check)} 个潜在前序航班的存在性...")
    conditions, params = [], []
    for callsign, sobt in preceding_flights_to_check:
        exec_date = sobt[:8]
        conditions.append("(callSign = %s AND sobt LIKE %s)")
        params.extend([callsign, f"{exec_date}%"])

    where_clause = " OR ".join(conditions)
    sql = f"SELECT callSign, sobt FROM dsp_flight_aggregation WHERE {where_clause}"

    found_flights = set()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            results = cursor.fetchall()
            for res in results:
                found_flights.add((res['callSign'], res['sobt']))
        logging.info(f"聚合表查询完成，找到了 {len(found_flights)} 个匹配的记录。")
        return found_flights
    except pymysql.MySQLError as e:
        logging.error(f"批量查询聚合表失败: {e}")
        return set()


# --- 3. API调用工具 (作为辅助验证) ---
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
                "callSign": row['航空器识别标志'], "regNumber": row.get('实际执飞机号'),
                "depAP": row['计划起飞机场'], "arrAP": row['计划降落机场'],
                "sobt": sobt_formatted, "sibt": sibt_formatted
            })
    return payload


def query_preceding_flight_api(payload):
    api_url = "http://10.230.146.110:8080/api/flight-leg/relationship/batch"
    if not payload: return []
    logging.info(f"正在向API发送 {len(payload)} 条航班的查询请求以作辅助验证...")
    try:
        response = requests.post(api_url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"API请求失败: {e}")
        return []


# --- 4. 主执行流程 ---
def main():
    """主执行函数"""
    load_dotenv()
    report_date = os.getenv('REPORT_DATE')
    if not report_date:
        logging.error("未在.env文件中设置REPORT_DATE，程序终止。")
        return

    # --- 文件路径设置 ---
    start_date_str = f"{report_date}000000"
    end_date_dt = datetime.strptime(report_date, '%Y%m%d') + timedelta(days=1)
    end_date_str = end_date_dt.strftime('%Y%m%d%H%M%S')
    input_filename = f"Flight-Normality-Dynamic---{start_date_str}-{end_date_str}.xlsx"
    output_filename = f"Flight-Normality-Dynamic-Result---{report_date}.xlsx"
    input_path = os.path.join('input', input_filename)
    output_path = os.path.join('output', output_filename)

    # --- 步骤1: 加载并筛选数据 ---
    mismatched_df = load_and_filter_data(input_path)
    if mismatched_df is None or mismatched_df.empty:
        logging.info("没有需要处理的数据，程序结束。")
        return

    # --- 步骤2: 层级0 - 数据库源头存在性校验 ---
    db_conn = get_db_connection()
    if not db_conn: return

    all_conclusions = {}
    flights_to_continue = []  # 存储 (index, found_preceding_flight)

    try:
        reg_numbers_to_query = mismatched_df['实际执飞机号'].dropna().unique()
        fpla_source_data = batch_query_fpla_for_regnumbers(db_conn, list(reg_numbers_to_query), report_date)

        logging.info("开始进行层级0 - 数据库源头存在性校验...")
        for index, row in mismatched_df.iterrows():
            potential_preceding = find_potential_preceding_in_fpla_data(row, fpla_source_data)
            if potential_preceding is None:
                all_conclusions[index] = "结论：数据库源头缺失有效的前序航班数据。匹配失败是由于上游FPLA数据不满足（机号、机场、时间）连续性条件。"
            else:
                flights_to_continue.append((index, potential_preceding))
    finally:
        db_conn.close()
        logging.info("数据库连接已关闭。")

    logging.info(
        f"层级0校验完成。{len(all_conclusions)} 条记录已确认问题。{len(flights_to_continue)} 条记录将进入下一层级分析。")

    # --- 步骤3: 层级1 - 下游数据完整性校验 ---
    flights_for_final_level = []  # 存储 index
    if flights_to_continue:
        preceding_to_check_in_agg = {(f['CALLSIGN'], f['SOBT']) for _, f in flights_to_continue}

        db_conn = get_db_connection()
        if not db_conn: return

        try:
            found_in_agg = batch_query_aggregation_for_preceding(db_conn, preceding_to_check_in_agg)

            logging.info("开始进行层级1 - 下游数据完整性校验...")
            for index, preceding_flight in flights_to_continue:
                preceding_key = (preceding_flight['CALLSIGN'], preceding_flight['SOBT'])
                if preceding_key not in found_in_agg:
                    all_conclusions[
                        index] = f"数据处理问题：在源头FPLA中找到了有效前序航班({preceding_key[0]}-{preceding_key[1]})，但该航班未能成功进入聚合表，导致匹配链断裂。"
                else:
                    flights_for_final_level.append(index)
        finally:
            db_conn.close()
            logging.info("数据库连接已关闭。")

    logging.info(
        f"层级1校验完成。{len(flights_to_continue) - len(flights_for_final_level)} 条记录已确认问题。{len(flights_for_final_level)} 条记录将进入最终分析。")

    # --- 步骤4: 层级2 - API交叉验证与最终结论 ---
    if flights_for_final_level:
        df_final_level = mismatched_df.loc[flights_for_final_level]
        api_payload = prepare_api_payload(df_final_level)
        api_results = query_preceding_flight_api(api_payload)
        api_results_map = {f"{res['request']['callSign']}-{res['request']['depAP']}-{res['request']['sobt']}": res for
                           res in api_results}

        logging.info("开始进行层级2 - 最终结论生成...")
        for index, row in df_final_level.iterrows():
            base_conclusion = "系统问题：航班环匹配程序逻辑问题。原因：有效的源头数据存在，且已成功进入下游聚合表，但匹配程序未能将二者正确关联。"

            # 附加API旁证信息
            sobt_formatted = format_time_for_api(row['计划离港时间'])
            lookup_key = f"{row['航空器识别标志']}-{row['计划起飞机场']}-{sobt_formatted}"
            api_result = api_results_map.get(lookup_key)

            if not api_result or 'previous' not in api_result or not api_result.get('previous'):
                base_conclusion += " (备注：外部API也未能识别此关联，可能存在普遍的识别难点)"
            else:
                base_conclusion += " (备注：外部API可正确识别此关联，进一步印证为内部程序问题)"

            all_conclusions[index] = base_conclusion

    # --- 步骤5: 汇总与输出 ---
    mismatched_df['分析结论'] = mismatched_df.index.map(all_conclusions)
    if not os.path.exists('output'): os.makedirs('output')
    mismatched_df.to_excel(output_path, index=False, engine='openpyxl')
    logging.info(f"全部分析完成，报告已保存至: {output_path}")


if __name__ == "__main__":
    main()