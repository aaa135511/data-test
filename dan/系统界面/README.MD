# 工业界面模拟程序打包指南 (Windows)

本项目使用 PyQt6 创建一个工业监控界面的模拟程序。本文档将指导您如何在 Windows 环境下设置、运行和打包此应用程序。

## 1. 项目结构

为了顺利打包，请确保您的项目文件夹包含以下文件：

```
your_project_folder/
├── main.py          # 主程序代码
├── requirements.txt   # 依赖库列表
└── README.md        # 本说明文档
```

## 2. 准备环境

在打包之前，建议使用虚拟环境来隔离项目依赖。

**第一步：创建并激活虚拟环境**

打开命令提示符 (cmd) 或 PowerShell，进入您的项目文件夹，然后运行以下命令：

```bash
# 创建一个名为 venv 的虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\activate
```

激活成功后，您会看到命令行提示符前面出现 `(venv)` 字样。

**第二步：安装依赖库**

在激活的虚拟环境中，运行以下命令来安装所需的库和打包工具：

```bash
# 安装 requirements.txt 中列出的所有库 (PyQt6)
pip install -r requirements.txt

# 安装 PyInstaller 打包工具
pip install pyinstaller
```

## 3. 使用 PyInstaller 打包

现在，您可以运行 PyInstaller 命令来创建独立的 `.exe` 可执行文件。

### 命令详解

*   `pyinstaller`: 启动打包工具。
*   `--name IndustrialUI`: 指定生成的可执行文件的名字为 `IndustrialUI.exe`。
*   `--onefile`: 将所有依赖项和代码打包成一个**单一的 `.exe` 文件**，方便分发。
*   `--windowed` (或 `--noconsole`): 这是**必须的**步骤。它会告诉程序这是一个图形界面应用，运行时**不要显示黑色的命令行窗口**。
*   `--icon=your_icon.ico` (可选): 为您的 `.exe` 文件指定一个自定义图标。您需要自己准备一个 `.ico` 格式的图标文件，并将其放在项目文件夹中。

### 打包命令

在激活的虚拟环境中，运行以下命令之一：

**基础命令 (无图标):**

```bash
pyinstaller --name IndustrialUI --onefile --windowed main.py
```

**带图标的命令 (推荐):**

(请先将您的图标文件，例如 `app.ico`，放入项目文件夹)

```bash
pyinstaller --name IndustrialUI --onefile --windowed --icon=app.ico main.py
```

## 4. 运行程序

打包过程可能需要一些时间。完成后，PyInstaller 会在您的项目文件夹中创建几个新目录，包括 `build` 和 `dist`。

您最终需要的可执行文件位于 **`dist`** 文件夹中。

进入 `dist` 文件夹，您会找到 `IndustrialUI.exe`。双击它即可运行您的应用程序，无需在目标计算机上安装Python或任何库。