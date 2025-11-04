import tkinter as tk
from tkinter import messagebox

# 创建主窗口
root = tk.Tk()
root.title("嵌入式系统界面")  # 窗口标题
root.geometry("800x600")  # 设置窗口大小

# 设置背景颜色
root.configure(bg='#99CCFF')

# 定义框架来模拟不同的区域
frame_left = tk.Frame(root, bg='#99CCFF')
frame_left.place(x=10, y=10, width=380, height=550)

frame_right = tk.Frame(root, bg='#99CCFF')
frame_right.place(x=400, y=10, width=380, height=550)

frame_bottom = tk.Frame(root, bg='#99CCFF')
frame_bottom.place(x=10, y=480, width=780, height=80)

# 添加标签和数值框
# 左侧框架（例如：液体量，矿浆称重等）
labels = [
    "液体原料", "液体工业水", "液体清洗水", "影响土", "瓶装影响土",
    "BB原封油", "EP2润滑油", "瓶尾原封", "刀盘啮水"
]
values = [
    "54.8", "3633.8", "2858.4", "0.0", "0.0",
    "0.0", "0.0", "0.0", "0.0"
]

for i, label_text in enumerate(labels):
    label = tk.Label(frame_left, text=label_text, bg='#99CCFF', font=("Arial", 12))
    label.grid(row=i, column=0, sticky="w", padx=10, pady=5)

    value_entry = tk.Entry(frame_left, font=("Arial", 12), width=10)
    value_entry.insert(0, values[i])  # 设置初始值
    value_entry.grid(row=i, column=1, padx=10, pady=5)

# 右侧框架（例如：矿浆称重、环境数据等）
right_labels = [
    "矿浆称重", "毛重", "环境监控量", "结果计量", "矿浆称重左皮"
]
right_values = [
    "0.0", "0.0", "0.0", "1.80", "0.0"
]

for i, label_text in enumerate(right_labels):
    label = tk.Label(frame_right, text=label_text, bg='#99CCFF', font=("Arial", 12))
    label.grid(row=i, column=0, sticky="w", padx=10, pady=5)

    value_entry = tk.Entry(frame_right, font=("Arial", 12), width=10)
    value_entry.insert(0, right_values[i])  # 设置初始值
    value_entry.grid(row=i, column=1, padx=10, pady=5)

# 下面框架（例如：总量计数、按钮等）
btn_clear = tk.Button(frame_bottom, text="总量计量清零", font=("Arial", 12), bg='#FFCC00', width=20)
btn_clear.pack(pady=20)

# 保存数据函数
def save_data():
    # 在此处你可以处理保存数据的逻辑
    messagebox.showinfo("保存", "数据已保存！")

# 添加保存按钮
btn_save = tk.Button(frame_bottom, text="保存数据", font=("Arial", 12), bg='#FFCC00', width=20, command=save_data)
btn_save.pack(pady=20)

# 运行GUI
root.mainloop()
