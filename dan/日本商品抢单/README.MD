# Rakuten RMS 智能抢单系统 (Rakuten RMS Auto-Purchase Bot)

这是一个专为 Rakuten RMS 后台设计的自动化抢单工具。它能够模拟人工操作，自动登录、扫描收藏夹、监控库存状态，并在广告开售的瞬间通过 JS 强制点击完成加购和结算。

支持多账号同时运行（多开），支持循环复购模式。

## 核心功能

*   **全自动登录**：自动处理 R-Login、邮箱两步验证，以及登录后的安全须知、RMS 跳转等拦截页面。
*   **可视化监控**：提供 GUI 界面，实时显示收藏夹内商品的名称、ID、监控状态和加购结果。
*   **精准抢单**：
    *   支持手动勾选/取消勾选特定商品。
    *   **防漏单机制**：采用 JS 强制点击 + 智能等待策略，防止高并发下请求丢失。
    *   **状态实时同步**：准确识别“等待开售”、“已加购”、“按钮不可用”等状态。
*   **循环复购**：支持结算完成后自动返回收藏夹，重置状态继续下一轮抢单。
*   **多开支持**：基于 Selenium 独立配置，支持在同一台电脑上开启多个窗口，登录不同账号互不干扰。
*   **安全模式**：提供“测试模式（不真实下单）”和“正式模式（真实下单）”切换。

## 环境依赖

*   Python 3.8+
*   Google Chrome 浏览器 (最新版)

## 安装步骤

1.  克隆或下载本项目代码。
2.  安装所需的 Python 库：

```bash
pip install -r requirements.txt
```

*(requirements.txt 内容见下方)*

## 使用说明

1.  **运行程序**：
    *   源码运行：`python main.py`
    *   打包版运行：双击 `RakutenBot.exe` (Win) 或 `RakutenBot.app` (Mac)。
2.  **账号设置**：
    *   界面默认预填了测试账号，请根据需要修改为实际的 R-Login ID、密码、邮箱及邮箱密码。
    *   **多开提示**：若需多账号抢单，请直接双击运行多次程序，在每个窗口填入不同的账号即可。
3.  **模式选择**：
    *   建议先使用 **"测试模式"** 跑通流程。
    *   勾选 **"下单后继续抢单"** 可开启无限循环模式。
4.  **操作流程**：
    *   点击 **[1. 登录并进入收藏夹]** -> 等待浏览器进入收藏页面。
    *   点击 **[2. 扫描列表]** -> 确认商品加载到表格中。
    *   (可选) 双击表格中的 "监控" 列，排除不需要抢的商品。
    *   点击 **[3. 启动死循环监控]** -> 脚本开始自动刷新和抢购。

## 注意事项

*   **IP 限制**：虽然支持无限多开，但所有窗口共享本机 IP。建议不要超过 5-10 个并发，以免触发 Rakuten 的 IP 风控。
*   **正式下单风险**：在“正式抢单”模式下，脚本会真实点击购买按钮。请务必确认目标商品无误，以免产生不必要的退单费用。

---
© 2026 Rakuten RMS Bot Project
```

---

### 第二部分：准备工作

在打包之前，请确保你已经准备好了图标文件，并安装了打包工具。

#### 1. 依赖文件 (requirements.txt)
请在项目根目录创建一个 `requirements.txt`，内容如下：
```text
selenium
webdriver-manager
tk
```

#### 2. 图标准备 (Icon)
PyInstaller 对不同系统的图标格式有严格要求，请确保你的目录下有以下两个文件：

*   **Windows**: 需要 `.ico` 格式。文件名：`app.ico`
*   **macOS**: 需要 `.icns` 格式。文件名：`app.icns`

> **提示**：如果你只有一张 `app.png` 图片，可以使用在线转换工具（如 convertio.co）分别转换为 .ico 和 .icns。不要直接修改后缀名，那样会报错。

#### 3. 安装 PyInstaller
打开终端（Terminal 或 CMD），运行：
```bash
pip install pyinstaller
```

---

### 第三部分：打包命令 (Windows)

在 Windows 系统下，使用 `app.ico` 进行打包。

1.  打开 CMD 或 PowerShell，进入脚本所在目录。
2.  执行以下命令：

```powershell
pyinstaller --noconfirm --onefile --windowed --icon "app.ico" --name "RakutenBot_Win" --hidden-import "tkinter" "main.py"
```

**参数解释：**
*   `--onefile`: 打包成单个 `.exe` 文件（方便分发）。
*   `--windowed`: 运行时不显示黑色的命令行窗口（因为我们有 GUI）。
*   `--icon "app.ico"`: 指定 Windows 图标。
*   `--name "RakutenBot_Win"`: 生成的文件名为 `RakutenBot_Win.exe`。

**生成结果：**
打包完成后，前往 `dist` 文件夹，你会找到 `RakutenBot_Win.exe`。

---

### 第四部分：打包命令 (macOS)

在 macOS 系统下，使用 `app.icns` 进行打包。

1.  打开终端 (Terminal)，进入脚本所在目录。
2.  执行以下命令：

```bash
pyinstaller --noconfirm --onefile --windowed --icon "app.icns" --name "RakutenBot_Mac" --hidden-import "tkinter" "main.py"
```

**参数解释：**
*   `--icon "app.icns"`: 指定 Mac 图标。
*   `--name "RakutenBot_Mac"`: 生成的文件名为 `RakutenBot_Mac.app` (实际上在 dist 文件夹里是一个 Unix 可执行文件，或者是 .app 包，取决于 PyInstaller 版本，通常 `--onefile` 在 Mac 上生成的是一个 Unix 可执行文件，带图标)。

**Mac 特殊注意事项 (重要)：**

1.  **权限问题**：
    打包后的程序第一次运行时，可能会被 macOS 安全机制拦截（显示“无法打开，因为无法验证开发者”）。
    *   **解决方法**：在 Finder 中找到 `dist/RakutenBot_Mac`，**右键点击** -> 选择 **打开 (Open)** -> 在弹窗中点击 **打开**。做一次之后，以后就可以直接双击了。

2.  **ChromeDriver 权限**：
    由于脚本使用了 `webdriver-manager` 自动下载驱动。第一次在 Mac 上运行打包软件时，它会下载 `chromedriver` 到用户目录。
    如果 macOS 提示 `chromedriver 无法打开`：
    *   你需要去 `~/.wdm/drivers/chromedriver/.../` 目录下，手动运行一次 `xattr -cr chromedriver`，或者在“系统设置 -> 隐私与安全性”中允许它运行。
    *   *通常只要按照上面第一点，右键打开主程序，后续调用的驱动一般会被信任。*

---

### 第五部分：多开测试

打包完成后，请立即测试多开功能：

1.  **Windows**: 连续双击 `RakutenBot_Win.exe` 三次，看是否弹出了三个带有不同 `[实例ID]` 的窗口。
2.  **macOS**:
    *   在终端运行：`open -n dist/RakutenBot_Mac` (运行多次)。
    *   或者直接双击文件多次（部分 Mac 版本可能需要右键 -> Duplicate 复制一份 App 才能多开，但在 `--onefile` 模式下通常可以直接多开）。

这样你就拥有了一个完整的、可分发的、支持多账号的专业抢单系统了！