# 图片转可编辑 Figma 工具包

这是团队内部使用的 Codex 工具包，包含两个彼此独立的 Skill：

- `image-to-editable-figma`：把参考图高保真还原为可编辑 Figma。
- `image-to-editable-figma-updater`：只在用户明确要求时检查和安装主 Skill 更新。

主 Skill 不执行后台更新，不在普通图片任务中访问本仓库。更新器也不会在未获确认时覆盖已安装文件。

## 首次安装

先确认当前 GitHub 账号有权访问本私有仓库，然后让 Codex 执行：

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo sunxiaowei12333-netizen/image-to-editable-figma-toolkit \
  --path skills/image-to-editable-figma skills/image-to-editable-figma-updater
```

安装完成后开启一个新的 Codex 任务，并发送：

```text
首次安装后，帮我初始化图片转 Figma 的全部环境。
```

初始化会自动处理安全的 Skill 私有依赖；Figma、Chrome、Computer Use 与 macOS 持久权限使用真实授权界面，无法自动完成的步骤会提供官方链接或精确设置路径。

## 日常使用

```text
使用 $image-to-editable-figma 把这张参考图转成可编辑 Figma。
```

主 Skill 会先交付 HTML 预览和最终截图，只有用户明确批准当前版本并授权导入 Figma 后才执行 Figma 写入。

## 检查与安装更新

```text
使用 $image-to-editable-figma-updater 检查图片转 Figma Skill 更新。
```

检查是只读的。发现新版后，更新器会展示当前版本、最新版本和变更说明；只有用户明确确认对应版本后才安装。安装成功后需要开启新任务加载新版。

## 分发边界

仓库不包含以下本机内容：

- `tooling/node_modules/`
- `tooling/.local-state.json`
- npm lockfile
- 用户任务输出、浏览器 profile、账号信息、Token 或 Cookie

