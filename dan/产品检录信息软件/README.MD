这是一个为你准备的 `README.MD` 文件内容。它包含了环境准备、打包指令以及打包时的注意事项。

---

# 产品检录信息管理系统 Pro - 打包指南

本手册旨在指导如何将 Python 源代码打包成可以在 Windows 系统上独立运行的 `.exe` 程序。

## 1. 环境准备

在打包之前，请确保你的开发环境已经安装了必要的第三方库：

```bash
# 安装基础依赖
pip install PyQt6 openpyxl Pillow lxml

# 安装打包工具
pip install pyinstaller
```

## 2. 准备图标
请确保你的项目根目录下有一个名为 `app.ico` 的图标文件。
*   **建议尺寸**：256x256 像素。
*   **格式**：必须是标准的 `.ico` 格式（不能直接把 .png 改名为 .ico）。

## 3. Windows 打包指令

打开终端（CMD 或 PowerShell），定位到项目根目录，执行以下指令：

```bash
pyinstaller --noconsole --onefile --icon=app.ico --name="产品检录管理系统Pro" main_gui.py
```

### 指令参数说明：
*   `--noconsole` (或 `-w`): 运行程序时不显示黑色的命令行窗口（仅显示 GUI 界面）。
*   `--onefile` (或 `-F`): 将所有依赖项和脚本打包成一个独立的 `.exe` 文件，方便分发。
*   `--icon=app.ico`: 指定程序在 Windows 资源管理器中显示的图标。
*   `--name="产品检录管理系统Pro"`: 指定生成的 .exe 文件名称。
*   `main_gui.py`: 你的主程序文件名（请根据实际文件名修改）。

## 4. 获取结果

打包完成后，目录中会生成以下文件夹：
*   **`dist/`**: 最终生成的 `产品检录管理系统Pro.exe` 就在这里。
*   **`build/`**: 打包过程中的临时文件，打包完成后可以手动删除。
*   **`产品检录管理系统Pro.spec`**: 配置文件，可以删除。

## 5. 注意事项 (必读)

1.  **数据库文件**：打包后的 `.exe` 运行后会自动在当前目录下创建 `products_pro_v2.db`。请不要删除该文件，否则数据会丢失。
2.  **试用期提示**：
    *   当前代码内置硬编码过期日期为 `2026-04-07`。
    *   一旦打包完成，该日期即锁定。如需更改过期时间，请修改源码中的 `EXPIRY_DATE` 后重新执行打包指令。
3.  **杀毒软件误报**：使用 PyInstaller 打包的单文件程序有时会被 Windows Defender 误报。如果遇到此情况，建议将打包方式改为目录模式（去掉 `--onefile`）或将生成的 `dist` 文件夹加入白名单。
4.  **资源路径**：如果你的代码将来需要调用外部图片（非数据库存储），请确保这些图片相对于 `.exe` 文件的路径是正确的。

---

### 💡 进阶技巧（减小体积）
如果生成的 `.exe` 体积过大，可以考虑在一个干净的虚拟环境中打包：
```bash
python -m venv venv_build
source venv_build/bin/activate  # Mac/Linux
# 或
.\venv_build\Scripts\activate  # Windows

pip install PyQt6 openpyxl Pillow lxml pyinstaller
# 重新执行打包指令
```