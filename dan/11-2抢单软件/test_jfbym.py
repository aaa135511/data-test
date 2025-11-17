import base64
import logging
import time
import os
import json

try:
    import requests
    from PIL import Image, ImageDraw, ImageFont
except ImportError as e:
    print(f"--- [严重错误] 缺少必要的库: {e} ---")
    print(f"--- [提示] 请确保已安装 requests 和 Pillow 库: pip install requests Pillow ---")
    exit()

# --- 配置日志输出 ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ==================================================================
# --- 请在这里填写您的配置信息 ---
# ==================================================================
# 您在 jfbym.com 用户中心获取的 Token
TOKEN = "Sq83S53mcjz1AkA54_SXfYvrXxiTNVnya8bfIKe-ITE"

# API 请求地址
API_URL = "http://api.jfbym.com/api/YmServer/customApi"

# 新的定制验证码类型
CAPTCHA_TYPE = "30340"

# 要测试的验证码图片的文件名
# 【重要】这个定制接口可能需要一张“拼接图”，即把指令和图片区域拼在一起。
# 但我们先用原始截图测试，如果不行再拼接。
IMAGE_FILENAME = "captcha_test.png"


# ==================================================================


def solve_captcha_jfbym_custom(image_path):
    """
    使用 jfbym.com 的【定制】API 从本地图片文件解决点选验证码。
    """
    if not os.path.exists(image_path):
        logging.error(f"图片文件未找到: {image_path}")
        return None

    logging.info("开始请求 jfbym.com 【定制 API - 30340】服务...")

    # 1. 读取图片并进行 Base64 编码
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    base64_image = base64.b64encode(image_bytes).decode('utf-8')

    # 2. 准备请求参数 (参数比通用接口更少)
    payload = {
        'image': base64_image,
        'token': TOKEN,
        'type': CAPTCHA_TYPE
    }

    start_time = time.time()

    try:
        # 3. 发送 POST 请求
        response = requests.post(API_URL, data=payload, timeout=60)
        response.raise_for_status()

        end_time = time.time()
        duration = end_time - start_time
        logging.info(f"⏱️ API 响应耗时: {duration:.3f} 秒")

        # 4. 解析返回的 JSON 数据
        result = response.json()

        if result.get('code') != 10000:
            logging.error(f"API 请求失败: Code={result.get('code')}, Msg='{result.get('msg')}'")
            return None

        recognition_data = result.get('data', {})

        # 根据文档，定制接口的 data.code 也是 0 代表成功
        if recognition_data.get('code') != 0:
            logging.error(f"打码服务出错: Code={recognition_data.get('code')}, Data='{recognition_data.get('data')}'")
            return None

        coordinates_str = recognition_data.get('data')
        if not coordinates_str:
            logging.error("未能从 API 返回的数据中找到坐标字符串。")
            return None

        logging.info(f"✅ 识别成功! 原始坐标字符串: '{coordinates_str}'")

        parsed_coordinates = []
        for part in coordinates_str.split('|'):
            try:
                x, y = part.split(',')
                parsed_coordinates.append({'x': int(x), 'y': int(y)})
            except ValueError:
                logging.error(f"坐标格式错误，无法解析: '{part}'")
                return None

        logging.info(f"解析后的坐标: {parsed_coordinates}")
        return parsed_coordinates

    except requests.exceptions.RequestException as e:
        logging.error(f"网络请求时发生异常: {e}")
        return None
    except json.JSONDecodeError:
        logging.error(f"无法解析返回的 JSON 数据: {response.text}")
        return None
    except Exception as e:
        logging.error(f"处理过程中发生未知错误: {e}")
        return None


def visualize_clicks(image_path, coordinates, output_path="captcha_result_jfbym_custom.png"):
    """
    在图片上将识别出的坐标点画出来，方便验证。
    """
    try:
        with Image.open(image_path) as img:
            draw = ImageDraw.Draw(img)
            font = ImageFont.load_default()

            for i, point in enumerate(coordinates):
                x, y = point['x'], point['y']
                radius = 10
                box = [x - radius, y - radius, x + radius, y + radius]
                draw.ellipse(box, outline="magenta", width=3)  # 使用洋红色以区分
                draw.text((x + radius + 5, y - radius), str(i + 1), fill="magenta", font=font)

            img.save(output_path)
            logging.info(f"💡 识别结果已可视化，并保存在: {output_path}")
    except Exception as e:
        logging.error(f"可视化结果时出错: {e}")


if __name__ == "__main__":
    logging.info("--- 开始 jfbym.com 【定制 API - 30340】 速度测试 ---")

    if TOKEN == "在此处粘贴您的用户中心Token":
        logging.error("错误：请在脚本顶部的 TOKEN 变量中填入您自己的 Token！")
    else:
        result_coordinates = solve_captcha_jfbym_custom(IMAGE_FILENAME)

        if result_coordinates:
            visualize_clicks(IMAGE_FILENAME, result_coordinates)
        else:
            logging.error("--- 测试失败，未能获取坐标 ---")

    logging.info("--- 测试结束 ---")