这是一个非常实用的需求。为了实现跨平台（Windows 和 macOS）并支持 `PyInstaller` 打包，我建议使用 Python 自带的 `tkinter` 库来构建 GUI。它轻量、无需额外安装依赖，且在两个系统上运行都很稳定。

以下是完整的 Python 代码实现。

### 1. 准备工作
你需要安装必要的库：
```bash
pip install -U google-genai
```

### 2. 代码关键点说明

1.  **多线程处理 (`threading`)**: AI 的识别过程通常需要 10-20 秒，如果不使用多线程，GUI 界面会卡死（显示为“未响应”）。这里将 API 调用放在了后台线程。
2.  **Prompt 设计**: 明确告诉模型如何查看坐标（纵轴字母，横轴数字）以及寻找“带方框的字母”，并强制要求它按你给出的格式输出。
3.  **日志系统**: 通过 `scrolledtext` 模拟了一个控制台，实时向用户反馈“正在连接”、“正在分析”等状态。
4.  **跨平台**: `tkinter` 是 Python 标准库，在 Windows、macOS 上行为一致。在 macOS 上打包时，它会自动适配系统菜单。

### 3. 如何使用 PyInstaller 打包

你可以根据你的系统（Windows 或 Mac）运行以下命令来生成可执行文件：

#### 安装 PyInstaller
```bash
pip install pyinstaller
```

#### 执行打包命令
在终端/命令行进入脚本所在目录：

```bash
# Windows (生成一个 .exe 文件)
pyinstaller --noconsole --onefile drawing_scanner.py

# macOS (生成一个 .app 文件)
pyinstaller --noconsole --onefile --windowed drawing_scanner.py
```

*   `--noconsole`: 运行时不显示黑色的命令行窗口。
*   `--onefile`: 将所有依赖打包进一个文件。
*   `--windowed`: (macOS专用) 确保生成的是图形界面的 .app。

### 4. 注意事项
*   **模型名称**: 代码中默认填写的模型是 `gemini-2.0-flash`。如果 Google 发布了 `gemini-3-flash-preview` 且该名称生效，你可以在 GUI 界面直接修改。
*   **API 额度**: PDF 处理消耗的 Token 较多，请确保你的 API Key 有足够的配额。
*   **图纸清晰度**: 如果图纸非常复杂，建议使用 `pro` 性能更强的模型以获得更高的坐标准确度。