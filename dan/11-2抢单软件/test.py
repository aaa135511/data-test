import base64
import logging
import time
import os

try:
    import requests
    from PIL import Image, ImageDraw, ImageFont
except ImportError as e:
    print(f"--- [严重错误] 缺少必要的库: {e} ---")
    print("--- [提示] 请确保已安装 requests 和 Pillow 库: pip install requests Pillow ---")
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
# 您的 2Captcha API Key
CAPTCHA_API_KEY = "458052ad6cbd988616664b8e13a67c0b"

# 要测试的验证码图片的文件名
IMAGE_FILENAME = "captcha_test.png"

# 从图片中看到的、需要按顺序点击的文字/数字
# 根据您的截图，指令是 "请依次点击: 0 1 7"
INSTRUCTIONS = "请依次点击: 0 1 7"


# ==================================================================


def solve_captcha_from_file(api_key, image_path, instructions):
    """
    从本地图片文件解决点选验证码。
    """
    if not os.path.exists(image_path):
        logging.error(f"图片文件未找到: {image_path}")
        return None

    logging.info(f"开始请求 2Captcha 服务解决点选验证码, 指令: '{instructions}'")

    # 1. 读取图片并进行 Base64 编码
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    base64_image = base64.b64encode(image_bytes).decode('utf-8')

    # 2. 准备并发送创建任务的请求
    task_payload = {
        "clientKey": api_key,
        "task": {
            "type": "CoordinatesTask",
            "body": base64_image,
            "comment": instructions
        }
    }
    try:
        create_response = requests.post("https://api.2captcha.com/createTask", json=task_payload, timeout=30)
        create_result = create_response.json()
        if create_result.get("errorId") != 0:
            logging.error(f"2Captcha 创建任务失败: {create_result.get('errorDescription')}")
            return None

        task_id = create_result["taskId"]
        logging.info(f"2Captcha 任务创建成功, Task ID: {task_id}. 等待识别结果...")

        # 3. 轮询获取结果
        result_payload = {"clientKey": api_key, "taskId": task_id}
        for i in range(60):  # 最多等待120秒
            logging.info(f"第 {i + 1} 次查询识别结果...")
            time.sleep(2)
            result_response = requests.post("https://api.2captcha.com/getTaskResult", json=result_payload, timeout=30)
            result = result_response.json()
            if result.get("status") == "ready":
                coordinates = result["solution"]["coordinates"]
                logging.info(f"✅ 验证码识别成功! 获得坐标: {coordinates}")
                return coordinates
            elif result.get("status") != "processing":
                logging.error(f"2Captcha 任务处理失败: {result}")
                return None

        logging.warning("等待 2Captcha 结果超时。")
        return None

    except Exception as e:
        logging.error(f"请求 2Captcha 服务时发生异常: {e}")
        return None


def visualize_clicks(image_path, coordinates, output_path="captcha_result.png"):
    """
    在图片上将识别出的坐标点画出来，方便验证。
    """
    try:
        with Image.open(image_path) as img:
            draw = ImageDraw.Draw(img)

            # 尝试加载一个字体，如果失败则使用默认字体
            try:
                # 在macOS上，这个字体通常存在
                font = ImageFont.truetype("Arial.ttf", 24)
            except IOError:
                logging.warning("未找到Arial字体，将使用默认字体。")
                font = ImageFont.load_default()

            for i, point in enumerate(coordinates):
                x, y = point['x'], point['y']
                radius = 10
                # 定义圆的边界框
                box = [x - radius, y - radius, x + radius, y + radius]
                # 画一个红色的圆圈
                draw.ellipse(box, outline="red", width=3)
                # 在圆旁边写上点击顺序
                draw.text((x + radius + 5, y - radius), str(i + 1), fill="red", font=font)

            img.save(output_path)
            logging.info(f"💡 识别结果已可视化，并保存在: {output_path}")
    except Exception as e:
        logging.error(f"可视化结果时出错: {e}")


if __name__ == "__main__":
    logging.info("--- 开始验证码识别功能独立测试 ---")

    # 调用核心识别函数
    result_coordinates = solve_captcha_from_file(CAPTCHA_API_KEY, IMAGE_FILENAME, INSTRUCTIONS)

    # 如果成功，则将结果可视化
    if result_coordinates:
        visualize_clicks(IMAGE_FILENAME, result_coordinates)
    else:
        logging.error("--- 测试失败，未能获取坐标 ---")

    logging.info("--- 测试结束 ---")