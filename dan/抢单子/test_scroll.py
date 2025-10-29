import pyautogui
import time

# --- 脚本配置 ---
# 滚动的幅度。负数代表向下滚动，正数代表向上滚动。
# 这个值可以根据你的屏幕和鼠标设置进行调整，1000是一个比较大的值，效果会很明显。
SCROLL_AMOUNT = 1000

# 倒计时秒数，让你有时间准备
COUNTDOWN_SECONDS = 5

# --- 脚本主逻辑 ---

print("--- 模拟鼠标滚动测试脚本 ---")
print(f"\n请在 {COUNTDOWN_SECONDS} 秒内，将你的鼠标光标移动到你想要测试滚动的窗口上。")
print("例如：一个长网页、一个文档、或者企业微信的工单详情页面。")
print("-" * 30)

# 开始倒计时
for i in range(COUNTDOWN_SECONDS, 0, -1):
    # 使用 \r 让光标回到行首，实现单行刷新倒计时
    print(f"准备开始... {i}", end='\r')
    time.sleep(1)

# 清除倒计时那一行并换行
print("\n" + "-" * 30)

try:
    # 1. 测试向下滚动
    print(f">>> 正在执行向下滚动（滚动幅度: {-SCROLL_AMOUNT}）...")
    pyautogui.scroll(-SCROLL_AMOUNT)
    print("向下滚动指令已发送。请观察窗口是否滚动。")

    # 等待几秒钟，让你观察效果
    time.sleep(3)

    # 2. 测试向上滚动
    print(f"\n>>> 正在执行向上滚动（滚动幅度: {SCROLL_AMOUNT}）...")
    pyautogui.scroll(SCROLL_AMOUNT)
    print("向上滚动指令已发送。窗口应该会滚回顶部。")

except Exception as e:
    print(f"\n脚本执行出错: {e}")
    print("请确保已在 macOS 的'辅助功能'中为你的终端或IDE授予权限。")

print("\n--- 测试完成 ---")