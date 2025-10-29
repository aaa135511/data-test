import cv2
import numpy as np
import pyautogui
import os

# --- 配置 ---
# 主图片和模板图片的路径
main_image_path = '1.png'
template_path = 'img.png'
# 匹配的置信度阈值（0.8 表示 80% 的相似度）
confidence_threshold = 0.8

# --- 脚本主逻辑 ---

# 1. 检查文件是否存在
if not os.path.exists(main_image_path) or not os.path.exists(template_path):
    print(f"错误：请确保 '{main_image_path}' 和 '{template_path}' 文件与脚本在同一个目录下。")
else:
    # 2. 加载主图片和模板图片
    # 使用 imread_color 模式加载
    main_image = cv2.imread(main_image_path, cv2.IMREAD_COLOR)
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)

    # 检查图片是否成功加载
    if main_image is None or template is None:
        print("错误：无法加载一张或多张图片，请检查文件路径和文件是否损坏。")
    else:
        # 获取模板的宽度和高度
        template_h, template_w, _ = template.shape

        # 3. 使用模板匹配算法
        # TM_CCOEFF_NORMED 是一个比较可靠的匹配算法
        result = cv2.matchTemplate(main_image, template, cv2.TM_CCOEFF_NORMED)

        # 4. 找到最佳匹配位置
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        print(f"检测到的最高相似度为: {max_val:.2f}")

        # 5. 检查相似度是否超过阈值
        if max_val >= confidence_threshold:
            # max_loc 是匹配到的区域的左上角坐标
            top_left = max_loc
            bottom_right = (top_left[0] + template_w, top_left[1] + template_h)

            # 计算按钮的中心点坐标
            center_x = top_left[0] + template_w // 2
            center_y = top_left[1] + template_h // 2

            print(f"成功找到 '接单' 按钮！")
            print(f"-> 左上角坐标: {top_left}")
            print(f"-> 中心点坐标: ({center_x}, {center_y})")

            # --- 模拟鼠标点击 (为了安全，默认是注释掉的) ---
            # 在实际使用时，请取消下面这行代码的注释
            # pyautogui.click(center_x, center_y)
            # print("已模拟点击按钮中心。")

            # --- (可选) 在图片上绘制矩形框以进行可视化 ---
            # 在主图上画一个绿色的框来标记找到的位置
            cv2.rectangle(main_image, top_left, bottom_right, (0, 255, 0), 2)

            # 显示结果图片
            cv2.imshow('Result - Button Found', main_image)
            print("\n已显示结果窗口，按任意键退出...")
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        else:
            print(f"未能找到 '接单' 按钮。最高相似度 ({max_val:.2f}) 未达到阈值 ({confidence_threshold})。")