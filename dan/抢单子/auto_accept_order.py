import cv2
import numpy as np
import os

# --- 配置 ---
# 源图片和模板图片的路径
source_image_path = '1.png'  # 你的原始截图
template_image_path = 'img_1.png'  # 你的“接单”按钮模板
output_image_path = 'result_with_box.png'  # 保存结果图片的文件名
# 匹配的置信度阈值
confidence_threshold = 0.8

print(f"--- 开始验证匹配位置，源文件: '{source_image_path}' ---")

# 1. 检查文件是否存在
if not os.path.exists(source_image_path) or not os.path.exists(template_image_path):
    print(f"错误：请确保源文件 '{source_image_path}' 和模板文件 '{template_image_path}' 存在。")
else:
    # 2. 加载源图片和模板图片
    source_image = cv2.imread(source_image_path, cv2.IMREAD_COLOR)
    template_image = cv2.imread(template_image_path, cv2.IMREAD_COLOR)

    if source_image is None or template_image is None:
        print("错误：图片加载失败，请检查文件是否正确。")
    else:
        # 获取模板的宽度和高度
        template_h, template_w, _ = template_image.shape

        # 3. 执行模板匹配
        result = cv2.matchTemplate(source_image, template_image, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        print(f"模板匹配完成，最高相似度: {max_val:.2f}")

        # 4. 检查相似度是否超过阈值
        if max_val >= confidence_threshold:
            # 匹配成功的左上角坐标
            top_left = max_loc
            # 计算右下角坐标
            bottom_right = (top_left[0] + template_w, top_left[1] + template_h)

            print(f"成功找到匹配区域！")
            print(f"  -> 左上角坐标: {top_left}")
            print(f"  -> 宽度: {template_w}, 高度: {template_h}")

            # --- 核心修改：在这里绘制矩形框 ---
            # 为了不修改原始图片，我们先创建一个副本
            image_with_box = source_image.copy()

            # 定义矩形框的颜色 (B, G, R 格式) - 这里是绿色
            box_color = (0, 255, 0)
            # 定义线条的粗细
            box_thickness = 2

            # 使用 cv2.rectangle 函数绘制矩形
            cv2.rectangle(image_with_box, top_left, bottom_right, box_color, box_thickness)

            # --- 核心修改：保存带有矩形框的图片 ---
            cv2.imwrite(output_image_path, image_with_box)

            print(f"\n[成功] 已将带有标记框的图片保存为: '{output_image_path}'")

            # (可选) 如果你想立即看到结果，可以取消下面三行代码的注释
            # cv2.imshow('Verification Result', image_with_box)
            # cv2.waitKey(0)
            # cv2.destroyAllWindows()

        else:
            print(f"匹配失败。最高相似度 ({max_val:.2f}) 未达到阈值 ({confidence_threshold})。")

print("\n--- 脚本执行完毕 ---")