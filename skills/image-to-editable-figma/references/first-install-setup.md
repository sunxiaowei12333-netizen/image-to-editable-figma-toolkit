# 首次安装环境初始化

本参考只在用户明确要求首次安装初始化时读取。普通图片还原、HTML 审批、Figma 导入与后续修改任务不得读取或执行本流程。

## 目标与边界

一次性准备以下三类能力：

- 官方自动导入：Chrome 应用、Figma Codex 插件/连接器及授权。
- 本机字体隔离：Codex Chrome 插件、ChatGPT 浏览器扩展、Figma 官方 Chrome 扩展。
- 零人工点击：Codex Computer Use 插件，以及 macOS 辅助功能和屏幕录制权限。

初始化完成不改变正常路由。普通字体页面仍使用隔离 Chrome + Figma 官方 `capture.js`；不得因为扩展和 Computer Use 已就绪，就在普通任务中打开或读取用户日常 Chrome。

本流程不扫描 Chrome profile，不读取 Cookie、登录数据、密码、历史标签或其他账号数据。只通过 Codex 已公开的插件/工具能力、无副作用连接测试、系统授权结果和用户在安装流程中的明确确认判断就绪状态。

## 一次性执行顺序

### 1. 本地依赖准备

运行：

```bash
node scripts/setup_environment.mjs --prepare
```

脚本复用现有 `bootstrap.mjs --check` 检查 Node、npm、Python、Pillow、NumPy、OpenCV、Chrome 和 Hugeicons。只有 Hugeicons 缺失时允许在 Skill 私有 `tooling/` 中自动初始化；不得自动安装或升级系统 Node、Python、图片处理依赖、Chrome，也不得改变系统 Python 环境。

脚本输出 JSON。先读取 `local.ok`、`missingLocal`、`runtimeRequirements` 和 `manualActions`，再继续 Codex 运行时检查。缺少 Chrome、Node、Python、Pillow、NumPy 或 OpenCV 时，集中给出对应官方链接/命令并暂停初始化，用户完成后重新运行 `--prepare`。

### 2. Codex 与 Figma 连接

按以下顺序检查，但不创建 Figma 文件或写入设计节点：

1. 检查 Figma 插件/连接器工具是否存在。
2. 调用最小只读身份或计划查询确认连接状态；若连接器返回登录、Connect 或 Authorize UI，原样转发该真实授权按钮并等待用户完成，禁止自行伪造按钮。
3. 若运行时没有可用授权 UI，提供精确路径：`Codex → 设置 → 插件 → Figma`。
4. 用户提供目标 Figma 链接时，可只读确认文件和页面可访问；不得在 HTML 审批前创建测试节点。目标文件真实编辑权限若接口不能只读证明，明确标为“当前文件写权限待审批后首次写入确认”，不得伪报已验证。

### 3. Chrome 控制能力

检查 Codex 是否提供 `Chrome` 插件能力。能力存在时，只建立无导航、无标签读取的 Chrome 连接测试；不得打开用户标签、读取现有页面或检查账号状态。

连接不可用时按以下顺序提供安装入口：

- Codex 插件：`Codex → 设置 → 插件 → Chrome`。
- ChatGPT 浏览器扩展：`Codex → 设置 → Computer use → 安装 Chrome 扩展`。

Chrome 控制文档明确返回安装/连接按钮时，转发该真实按钮；没有按钮时只提供上述设置路径。不得读取 Chrome 扩展目录或用户 profile 来“检测”扩展。

### 4. Computer Use 与 macOS 权限

检查 Codex 是否提供 `Computer Use` 插件。存在时执行一次无副作用的只读应用状态探针；该探针只用于让系统显示必要的权限请求并验证能力，不点击用户应用内容。

系统出现真实授权按钮时，向用户说明用途并让用户点击授权。若没有弹窗或权限仍不可用，提供以下精确路径：

- Codex 插件：`Codex → 设置 → 插件 → Computer Use`。
- 辅助功能：`系统设置 → 隐私与安全性 → 辅助功能`。
- 屏幕录制：`系统设置 → 隐私与安全性 → 屏幕与系统音频录制`。

Computer Use 只为本机字体分支中自动操作 Chrome 工具栏、Figma 扩展弹窗或必要的原生界面准备。普通任务不得主动调用它。

### 5. Figma 官方 Chrome 扩展

安装入口：

- [Figma 官方 Chrome 扩展](https://chromewebstore.google.com/detail/figma/fkmaohpngenfoccdgceedjkfhkdcohmg)
- 扩展 ID：`fkmaohpngenfoccdgceedjkfhkdcohmg`
- 发布者：`Figma, Inc.`

安装、Chrome 权限和 Figma 登录属于持久授权，不得静默执行。若当前安装请求已明确授权 Computer Use 代操作，且系统政策允许，可用 Computer Use 打开官方商店并完成普通安装步骤；浏览器或系统要求用户确认持久权限时，必须展示真实确认界面。Computer Use 本身尚未获得权限时，提供上方链接由用户完成。

不要把 Figma 扩展安装状态仅根据本地标记判为已验证。优先通过扩展提供的正常可见状态或一次无设计写入的连接检查确认；无法可靠验证时记录为 `user-confirmed`，不得扫描 Chrome profile。

### 6. 稳定预览服务（单独授权，可选）

稳定预览服务不属于上述插件、连接器或系统权限初始化，也不参与 `--mark-complete` 的能力列表。若用户另外明确同意安装常驻预览服务，完整读取 [preview-service.md](preview-service.md)，先运行 `install --dry-run` 检查固定端口和安装位置，再执行带 `--confirm-persistent-install` 的正式安装。macOS 用户级 `launchd` 属于持久环境修改，普通首次初始化不得顺带安装。

用户未授权时跳过本项，不得用临时服务器伪装成已经安装；后续普通图片任务首次需要稳定链接时，再单独说明并请求一次授权。服务在线只解决本地 URL 生命周期，不改变 HTML、Capture、审批或 Figma 写入规则。

## 安装结果与状态

完成本地检查和运行时验证后，能力列表必须包含：

```text
figma-codex-plugin
figma-connector-auth
chrome-codex-plugin
chatgpt-browser-extension
computer-use-plugin
macos-accessibility
macos-screen-recording
figma-browser-extension
```

确认每项实际完成后运行：

```bash
node scripts/setup_environment.mjs --mark-complete \
  --verified-capabilities figma-codex-plugin,figma-connector-auth,chrome-codex-plugin,chatgpt-browser-extension,computer-use-plugin,macos-accessibility,macos-screen-recording,figma-browser-extension
```

该命令只写入 Git 忽略的 `tooling/.local-state.json`：`setupVersion / status / completedAt / verifiedCapabilities`。不得写入账号、Token、Cookie、文件内容或系统权限数据库。

状态可通过以下命令人工查看：

```bash
node scripts/setup_environment.mjs --status
```

普通图片转 Figma 任务不得运行 `--status`，也不应根据状态文件决定普通任务路由。若未来某项能力实际失败，只修复该项；不要清空或重做全部初始化。

## 用户提示方式

首次初始化只发一份合并结果，按以下顺序组织：

1. 已就绪。
2. 已自动修复。
3. 等待授权：展示连接器或系统真实返回的按钮。
4. 需要人工完成：每项提供一个官方链接或精确设置路径。
5. 完成后重新验证的命令。

不要把一个安装流程拆成多轮零散提示；能够并行完成的用户步骤放在同一份清单中。不要把 Markdown 链接伪装成授权按钮，也不要声称未验证的插件已经安装。

## 时间预期

- 大部分依赖已存在：`2–5 分钟`。
- 常规全新环境：`8–15 分钟`。
- 需要重启 Codex/Chrome 或重新登录 Figma：`15–25 分钟`。
- 企业策略限制安装或权限：可能超过 `30 分钟`，必要时报告管理员阻塞。

这些时间只属于首次安装。完成后普通图片转 Figma 任务不增加初始化检查或提示。若用户同时授权稳定预览服务，另增加一次端口检查和 LaunchAgent 安装，通常只需秒级；该时间不包含异常端口冲突排查。
