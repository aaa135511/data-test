# 车辆查找脚本打包指南 (捆绑Tesseract版)

本指南将指导您如何使用 PyInstaller 将 Python 脚本和 **Tesseract-OCR 引擎** 一同打包，创建一个完全独立的、无需额外安装任何依赖的 Windows 可执行文件 (`.exe`)。

## 1. 打包前准备

### a. 文件结构
在开始打包前，请确保您的项目文件夹结构清晰。您只需要准备好您的 Python 脚本即可。
```
your_project_folder/
└── vin_finder_windows_bundle.py
└── app.ico  (可选的图标文件)
```

### b. 安装本地依赖
确保您的**开发环境**中已经安装了所有必要的库。在命令行中运行：
```bash
pip install customtkinter pillow pyautogui pytesseract opencv-python-headless pyinstaller
```

### c. 确认 Tesseract-OCR 安装路径
您必须在**您的开发电脑**上安装 Tesseract-OCR，因为 PyInstaller 需要从那里复制文件。
- **默认安装路径**: `C:\Program Files\Tesseract-OCR`
- 如果您安装在其他位置，请记下该路径，打包时需要用到。

## 2. 执行打包命令 (核心步骤)

这是将所有东西捆绑在一起的关键。

1.  打开命令提示符 (cmd) 或 PowerShell。
2.  使用 `cd` 命令切换到您的 Python 脚本 (`vin_finder_windows_bundle.py`) 所在的文件夹。
3.  **复制并执行**以下命令。如果您的 Tesseract 安装路径不同，请相应修改 `"C:\Program Files\Tesseract-OCR"` 部分。

    ```bash
    pyinstaller --name VinFinder --onefile --windowed --icon=app.ico --add-data "C:\Program Files\Tesseract-OCR;tesseract" vin_finder_windows_bundle.py
    ```

### 命令详解
- `--name VinFinder`: 指定生成的可执行文件名 (`VinFinder.exe`)。
- `--onefile`: 将所有内容打包成一个 `.exe` 文件。
- `--windowed`: 以无控制台的窗口模式运行程序，这是GUI应用的必需选项。
- `--icon=app.ico`: (可选) 为程序指定图标。
- `--add-data "C:\Program Files\Tesseract-OCR;tesseract"`: **这是最重要的部分**。
    - `C:\Program Files\Tesseract-OCR`: 这是**源路径**，即您电脑上 Tesseract 的安装文件夹。
    - `tesseract`: 这是**目标路径**。它告诉 PyInstaller，在打包后的程序内部创建一个名为 `tesseract` 的文件夹，并将源路径的所有内容复制进去。
    - 我们的 Python 脚本经过修改，会自动在程序内部的这个 `tesseract` 文件夹里寻找 `tesseract.exe`。
- `vin_finder_windows_bundle.py`: 您要打包的主脚本文件。

## 3. 打包后操作

- 打包完成后，您需要的可执行文件 `VinFinder.exe` 会位于 **`dist`** 文件夹内。
- 现在，您可以将这个**单一的 `.exe` 文件**分发给任何 Windows 用户。他们**无需安装 Python，也无需安装 Tesseract-OCR**，双击即可直接运行！

## 4. 常见问题 (Troubleshooting)

#### Q1: 打包时报错，提示找不到 `"C:\Program Files\Tesseract-OCR"`。
**A1:** 这意味着您的 Tesseract 安装路径与命令中指定的不符。请找到您电脑上 Tesseract 的实际安装文件夹，并用该路径替换命令中的 `"C:\Program Files\Tesseract-OCR"`。

#### Q2: 双击 `.exe` 文件后，程序闪退或无法识别文字。
**A2:** 这很可能是 Tesseract 的某些文件没有被正确打包。
- **解决方案**:
    1.  重新打包，但暂时**移除 `--windowed` 和 `--onefile`** 选项：
        ```bash
        pyinstaller --name VinFinder --add-data "C:\Program Files\Tesseract-OCR;tesseract" vin_finder_windows_bundle.py
        ```
    2.  这会在 `dist/VinFinder` 文件夹下生成一大堆文件和一个 `.exe`。进入该文件夹，检查是否存在一个名为 `tesseract` 的子文件夹，并且其中包含了 `tesseract.exe` 和 `tessdata` 文件夹。
    3.  直接在该文件夹中运行 `VinFinder.exe`。如果出现错误，命令行窗口会显示详细信息，帮助您定位问题。

#### Q3: 防病毒软件将我生成的 `.exe` 报为病毒。
**A3:** 这是 PyInstaller 打包的程序（尤其是 `--onefile` 模式）常见的误报。
- **解决方案**: 在您自己的电脑上，可以将文件添加到杀毒软件的白名单中。在分发给他人时，可以提前告知这属于正常误报。