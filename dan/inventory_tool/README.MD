# 库存更新工具 (Inventory Stock Updater)

这是一个图形用户界面（GUI）的桌面应用程序，旨在自动化更新库存文件的流程。它可以读取四个不同的数据源文件（三个CSV，一个XLSX），根据预设的逻辑匹配数据，计算最新的库存量，并允许用户导出一个更新后的库存CSV文件。

## 功能特性

- **图形用户界面**: 简洁直观的界面，无需任何编程知识即可操作。
- **文件选择**: 为四个必需的输入文件提供独立的文件浏览器按钮。
- **跨平台兼容**: 核心脚本可在 Windows 和 macOS 上运行和打包。
- **实时状态反馈**: 在界面上提供清晰的日志，显示当前处理进度或任何错误信息。
- **错误处理**: 能够捕获常见错误（如列名不匹配、数据类型冲突）并以弹窗形式友好地提示用户。
- **导出功能**: 处理完成后，用户可以方便地将更新后的库存表导出为新的CSV文件。

## 环境准备

在运行或打包此脚本之前，您需要确保您的计算机上已安装以下软件和库。

1.  **安装 Python**:
    *   请从 [Python官网](https://www.python.org/downloads/) 下载并安装最新版本的 Python。
    *   **重要**: 在安装过程中，请务必勾选 "Add Python to PATH" 选项。

2.  **安装必要的 Python 库**:
    *   打开命令提示符（CMD）或 PowerShell，然后运行以下命令来安装 `pandas`, `openpyxl` 和 `pyinstaller`：
    ```bash
    pip install pandas openpyxl pyinstaller
    ```
    *   `pandas`: 用于核心的数据读取和处理。
    *   `openpyxl`: `pandas` 读取 `.xlsx` Excel 文件时需要它。
    *   `pyinstaller`: 用于将 `.py` 脚本打包成独立的可执行文件。

## 如何直接运行脚本 (用于开发和测试)

在打包成最终的应用程序之前，您可以直接运行Python脚本来测试其功能。

1.  将 `inventory_tool.py` 文件保存在一个文件夹中。
2.  打开命令提示符（CMD）或 PowerShell，并使用 `cd` 命令进入该文件夹。
3.  运行以下命令：
    ```bash
    python inventory_tool.py
    ```
4.  程序的图形界面将会启动。

## 如何打包成 Windows 应用程序 (.exe)

以下步骤将指导您如何将 `inventory_tool.py` 脚本打包成一个独立的、带有自定义图标的 Windows 可执行文件 (`.exe`)。

### 第1步：准备文件

在开始打包之前，请确保您的项目文件夹结构如下。**所有文件必须位于同一个文件夹内**。

```
/你的项目文件夹/
├── inventory_tool.py   # 你的Python脚本
└── app.ico             # 你的应用程序图标文件
```

- **`app.ico`**: 这是您的应用程序图标。
    - 文件名**必须**是 `app.ico`。
    - 文件格式**必须**是 `.ico`。如果您只有 `.png` 或 `.jpg` 格式的图片，可以使用在线转换工具（例如搜索 "png to ico converter"）将其转换为 `.ico` 格式。

### 第2步：运行打包命令

1.  打开命令提示符（CMD）或 PowerShell。
2.  使用 `cd` 命令导航到您的项目文件夹（即包含 `inventory_tool.py` 和 `app.ico` 的文件夹）。
3.  执行以下命令：

    ```bash
    pyinstaller --onefile --windowed --icon=app.ico --name InventoryTool inventory_tool.py
    ```

### 命令参数详解：

-   `--onefile`: 将所有依赖项和脚本打包成一个**单一的 `.exe` 文件**。如果不加此参数，会生成一个包含很多文件的文件夹。
-   `--windowed`: 在运行应用程序时，**隐藏黑色的命令行窗口**。对于GUI程序，这是必须的。
-   `--icon=app.ico`: **指定应用程序的图标**。PyInstaller会查找当前目录下的 `app.ico` 文件并将其嵌入到 `.exe` 文件中。
-   `--name InventoryTool`: 设置生成的 **`.exe` 文件的名称**为 `InventoryTool.exe`。
-   `inventory_tool.py`: 你要打包的**主脚本文件**。

### 第3步：找到你的应用程序

打包过程可能需要一两分钟。完成后，PyInstaller 会在您的项目文件夹中创建几个新文件夹 (`build`, `dist` 等)。

-   您最终的可执行文件位于 **`dist`** 文件夹中。
-   在这个例子中，您会找到 **`InventoryTool.exe`**。

现在，您可以将这个 `InventoryTool.exe` 文件单独发送给您的客户。他们可以直接双击运行，无需安装Python或任何库。

## 如何使用应用程序

1.  双击运行 `InventoryTool.exe`。
2.  点击四个 "Browse..." 按钮，依次选择对应的文件：
    -   `Inventory File`
    -   `SKU Map File`
    -   `Warehouse Map File`
    -   `Warehouse Details File`
3.  当所有文件都选择完毕后，点击 "Update Inventory" 按钮。
4.  等待状态日志显示 "Processing complete. Ready to export."。
5.  点击 "Export Updated Inventory (.csv)" 按钮，选择您想要保存的位置和文件名，然后点击保存。
6.  操作完成！