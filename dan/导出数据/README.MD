# 自动化查询导出工具 - 打包与使用说明

本指南介绍了如何将该 Python 脚本打包为 Windows 环境下可独立运行的 `.exe` 应用程序。

## 1. 环境准备

在开始打包之前，请确保你的开发电脑（Windows系统）上已安装 Python 环境，并且已经安装了打包所需的第三方库。

打开终端（CMD 或 PowerShell），运行以下命令安装必要的依赖：

```bash
pip install selenium webdriver-manager pandas openpyxl pyinstaller
```

## 2. 文件准备

请确保在同一个文件夹目录下包含以下两个文件：
1. **主程序源码**：`query_tool.py` （即我们的 Python 脚本文件）
2. **程序图标**：`app.ico` （用于生成 exe 文件的图标，必须是标准的 .ico 格式）

*目录结构示例：*
```text
你的项目文件夹/
 ├── query_tool.py
 └── app.ico
```

## 3. 开始打包

在刚才那个包含着 `.py` 和 `.ico` 文件的文件夹空白处，按住 `Shift` 键的同时点击鼠标右键，选择“在此处打开 PowerShell 窗口” 或 “在此处打开命令提示符”。

输入以下打包命令并按回车运行：

```bash
pyinstaller -F -w -i app.ico main.py
```

**命令参数解释：**
* `-F` (或 `--onefile`)：将所有依赖打包成一个独立的 `.exe` 文件，方便发送给客户。
* `-w` (或 `--noconsole`)：运行程序时不显示黑色的命令行窗口（因为我们有自己的 GUI 界面）。
* `-i app.ico`：指定应用程序的图标。

## 4. 获取打包结果

打包过程可能需要 1 到 3 分钟，取决于电脑性能（因为 `pandas` 库比较大）。
看到 `Completed successfully.` 提示后，表示打包完成。

此时你的项目文件夹下会多出几个文件夹：
* `build/` （打包过程中的临时文件，可删除）
* `__pycache__/` （缓存文件，可删除）
* `query_tool.spec` （打包配置文件，可删除）
* **`dist/`** （**重要！** 你的 `.exe` 文件就在这里面）

进入 `dist/` 文件夹，你就能看到带有你指定图标的 **`query_tool.exe`**。直接将这个文件发送给客户即可运行。

## 5. ⚠️ 客户使用注意事项（重要）

1. **首次运行较慢**：因为打包了 `pandas` 等重型数据处理库，`.exe` 文件体积一般在 50MB~80MB 左右。客户双击后解压到内存需要几秒钟时间，请耐心等待界面弹出。
2. **需要网络连接**：由于程序内置了 `webdriver-manager`，客户首次运行点击“开始执行”时，程序会自动在后台请求网络下载与当前电脑 Chrome 浏览器版本匹配的驱动（以后运行就不会下载了）。
3. **杀毒软件误报**：使用 PyInstaller 打包的单文件 `.exe` 极易被 360、火绒或 Windows Defender 误报为病毒（这是 Python 打包界的通病）。如果被拦截，请引导客户将其**添加至信任区/白名单**。
4. **Excel 环境支持**：即使客户电脑没有安装 Microsoft Office，该工具也能正常生成 `.xlsx` 文件；但若要在运行期间不报错，推荐客户电脑上至少装有 WPS 或 Office 用于查看表格。
```

***

**给你的额外提示：**
* 客户电脑上**必须安装有 Google Chrome 浏览器**，因为脚本使用的是 Chrome WebDriver。
* 如果你在打包时遇到 `recursion limit` 或者 `pandas` 缺失的报错，可以在打包命令中加上 `--hidden-import pandas` 强制导入，不过通常最新版的 PyInstaller 已经能自动识别处理了。