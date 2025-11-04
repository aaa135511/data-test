# 车辆查找脚本打包指南 (PyInstaller)

本指南将指导您如何使用 PyInstaller 将 Python 脚本打包成一个独立的 Windows 可执行文件 (`.exe`)。

## 1. 打包前准备

### a. 安装依赖库
确保您的 Python 环境中已经安装了脚本所需的所有库。在命令行中运行：
```bash
pip install customtkinter pillow pyautogui pytesseract opencv-python-headless
```

### b. 安装 Tesseract-OCR (至关重要！)
PyInstaller **不会** 将 Tesseract-OCR 引擎本身打包进 `.exe` 文件。这意味着，**任何要运行此 `.exe` 程序的电脑，都必须预先独立安装 Tesseract-OCR**。

- **下载地址**: [Tesseract at UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
- **安装注意**:
    1. 在安装过程中，请务必勾选 "Additional language data" 下的简体中文 (`chi_sim`) 语言包。
    2. 强烈建议将 Tesseract **添加到系统的 PATH 环境变量**中。这会让打包后的程序在任何电脑上都能自动找到它。
    3. 如果您不添加到 PATH，请确保脚本中指定的 Tesseract 路径 (`C:\Program Files\Tesseract-OCR\tesseract.exe`) 与目标电脑上的安装路径完全一致。

## 2. 安装 PyInstaller

如果尚未安装 PyInstaller，请在命令行中运行：
```bash
pip install pyinstaller
```

## 3. 执行打包命令

1.  打开命令提示符 (cmd) 或 PowerShell。
2.  使用 `cd` 命令切换到您的 Python 脚本 (`vin_finder_windows.py`) 所在的文件夹。
3.  执行以下命令进行打包：

    ```bash
    pyinstaller --name VinFinder --onefile --windowed --icon=app.ico vin_finder_windows.py
    ```

### 命令详解
- `--name VinFinder`: 指定生成的可执行文件名，最终会生成 `VinFinder.exe`。
- `--onefile`: 将所有依赖项打包成一个单一的 `.exe` 文件，方便分发。
- `--windowed` (或 `--noconsole`): 这是**必须**的选项。它指定这是一个图形界面程序，运行时不会显示黑色的命令行窗口。
- `--icon=app.ico`: (可选) 为您的程序指定一个自定义图标。您需要自己准备一个 `.ico` 格式的图标文件，并将其命名为 `app.ico`（或任何您喜欢的名字），与脚本放在同一目录下。
- `vin_finder_windows.py`: 您要打包的主脚本文件。

## 4. 打包后操作

- 打包过程可能需要几分钟。完成后，您的文件夹中会出现几个新文件夹 (`build`, `dist`) 和一个 `.spec` 文件。
- 您最终需要的可执行文件位于 **`dist`** 文件夹内，即 `dist/VinFinder.exe`。
- 您可以将这个 `.exe` 文件复制到任何**已经安装了 Tesseract-OCR** 的 Windows 电脑上运行。

## 5. 常见问题 (Troubleshooting)

#### Q1: 程序运行后提示 "Tesseract is not installed or it's not in your PATH" 错误。
**A1:** 这是最常见的问题。说明程序找不到 Tesseract 引擎。
- **解决方案**: 在运行 `.exe` 的电脑上，确保 Tesseract-OCR 已经正确安装，并且其安装目录（例如 `C:\Program Files\Tesseract-OCR`）已经被添加到了系统的 PATH 环境变量中。

#### Q2: 双击 `.exe` 文件后，程序闪退，没有任何反应。
**A2:** 这通常意味着程序在启动时遇到了致命错误，但由于 `--windowed` 选项隐藏了错误信息，您看不到。
- **解决方案**:
    1. 返回命令行，重新打包，但**移除 `--windowed` 选项**：
       ```bash
       pyinstaller --name VinFinder --onefile vin_finder_windows.py
       ```
    2. 再次运行新生成的 `.exe` 文件。这次，如果程序崩溃，会弹出一个显示详细错误信息的命令行窗口。根据错误信息来修复代码或环境问题。

#### Q3: 防病毒软件将我生成的 `.exe` 报为病毒。
**A3:** 这是 PyInstaller 打包的程序常见的误报。因为打包过程会将 Python 解释器和脚本捆绑在一起，某些杀毒软件的启发式扫描会认为这种行为可疑。
- **解决方案**: 如果这是您自己电脑上打包的程序，可以暂时信任或将其添加到杀毒软件的白名单中。