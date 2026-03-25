好的，这是一个为你的项目量身定制的 `README.md` 文件，包含了项目介绍、使用说明和完整的 PyInstaller 打包指令。

---

# WhatsApp 智能营销助手 (V6.5)

这是一个基于 Python、PyQt6 和 Selenium 的自动化桌面软件，旨在批量添加 WhatsApp 联系人，专为营销和客户关系管理设计。软件通过调用 [HubStudio](https://www.hubstudio.com/) 指纹浏览器的本地 API，在隔离且防关联的环境中执行操作，确保了账户的安全性。

## ✨ 核心功能

- **自动化批量加人**: 自动读取 Excel 表格，将指定列（`WhatsApp 1`, `WhatsApp 2`）的手机号码批量添加为联系人。
- **智能数据映射**: 支持将 Excel 中的“备注”列作为联系人“名字”，将“网站”列作为“姓氏”进行填充。
- **防重复与状态回写**:
    - 自动检测并跳过已在通讯录或未注册 WhatsApp 的号码。
    - 每处理完一行数据，会自动在 Excel 中新增或更新“是否完成”列（“是”或“否”），并**实时保存**，防止进度丢失。
    - 支持断点续传，下次运行时会自动跳过已标记“是”的行。
- **HubStudio 集成**: 通过本地 API 控制 HubStudio，确保每个操作都在独立的指纹环境中进行，极大降低了账户被风控的风险。
- **多平台兼容**: 软件可在 Windows 和 macOS 系统上运行和打包。
- **安全账户体系**:
    - **机器码绑定**: 普通用户账号需由管理员绑定唯一的电脑机器码才能登录，杜绝了账号共享。
    - **管理员后台**: 管理员拥有独立的后台，可以增删改普通用户账号及绑定的机器码。
- **用户友好界面**:
    - 使用 PyQt6 构建了现代、美观的图形用户界面。
    - 实时日志输出，任务进度一目了然。
    - 支持自定义添加间隔时间，模拟人工操作，降低风险。
    - 提供“强制停止”和“导出结果”功能。

## 🛠️ 技术栈

- **图形界面**: PyQt6
- **浏览器自动化**: Selenium
- **Excel 处理**: Pandas
- **指纹浏览器**: HubStudio (通过 Local HTTP API 控制)
- **数据库**: SQLite (用于存储用户账户信息)
- **打包**: PyInstaller

## 🚀 快速开始

### 1. 环境准备

确保你的电脑上已经安装了 Python (建议 3.9+)。然后，在终端或命令行中执行以下命令安装所有必要的库：

```bash
pip install PyQt6 pandas openpyxl selenium requests webdriver-manager
```
**注意**: 在 Mac 上，首次运行 Selenium 可能会弹出“无法验证开发者”的系统提示。请前往 **系统设置 -> 隐私与安全性**，点击“仍要打开”以授予 Chromedriver 运行权限。

### 2. HubStudio 配置

1.  下载并安装 [HubStudio](https://www.hubstudio.com/) 客户端。
2.  登录你的账号，并创建一个浏览器环境。记下这个环境的 **ID**。
3.  在 HubStudio 左侧菜单找到 **API**，确认本地 **API 端口**（默认通常是 `6873`）。
4.  确保你已购买了支持 API 功能的套餐。

### 3. 运行软件

1.  将 `main.py` 文件放在一个独立的文件夹中。
2.  在终端中进入该文件夹，运行：
    ```bash
    python main.py
    ```
3.  **首次登录**: 使用默认管理员账号 `admin`，密码 `whatsappadmin_5566`。
4.  **配置任务**: 在“自动化加人”页面，填入 HubStudio 的环境 ID 和 API 端口，并上传你的 Excel 表。
5.  **开始任务**: 点击“启动批量任务”，软件会自动打开 HubStudio 浏览器。如果提示扫码，请用手机 WhatsApp 完成登录。

## 📦 打包为可执行文件

使用 PyInstaller 可以将此 Python 脚本打包成无需安装环境的 `.exe` (Windows) 或 `.app` (Mac) 文件。

### Windows (带图标)

1.  将你的应用图标文件 `app.ico` 放在与 `main.py` 相同的目录下。
2.  打开命令行（CMD 或 PowerShell），进入项目目录。
3.  执行以下命令：

    ```bash
    pyinstaller --onefile --noconsole --name="WhatsApp 智能营销助手" --icon="app.ico" --collect-all selenium main.py
    ```

    - `--onefile`: 生成单个可执行文件。
    - `--noconsole` 或 `--windowed`: 运行时不显示黑色的命令行窗口。
    - `--name`: 指定生成的文件名。
    - `--icon`: 指定应用的图标。
    - `--collect-all selenium`: 确保 Selenium 的所有依赖项都被正确打包。

    打包完成后，在 `dist` 文件夹里可以找到 `WhatsApp 智能营销助手.exe`。

### macOS

1.  打开终端（Terminal），进入项目目录。
2.  执行以下命令：

    ```bash
    pyinstaller --onefile --noconsole --name="WhatsApp 智能营销助手" --collect-all selenium main.py
    ```

    - **注意**: Mac 的图标打包比较复杂，通常需要在生成 `.app` 文件后手动编辑 `Info.plist` 并添加 `.icns` 图标文件。上述命令会生成一个无图标的 `.app` 应用。

    打包完成后，在 `dist` 文件夹里可以找到 `WhatsApp 智能营销助手.app`。

---