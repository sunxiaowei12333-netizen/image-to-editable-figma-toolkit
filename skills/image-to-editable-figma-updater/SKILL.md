---
name: image-to-editable-figma-updater
description: 检查并更新公开发布仓库中的 image-to-editable-figma Skill。仅当用户明确要求检查更新、安装新版或恢复该 Skill 时使用；普通图片还原、HTML 预览和 Figma 导入任务不得调用。
---

# 图片转可编辑 Figma 更新器

## 目标与边界

只负责 `image-to-editable-figma` 的版本检查和受控更新。不得执行图片还原、HTML 构建或 Figma 写入，不得在后台、任务开始时或普通图片转 Figma 请求中检查更新。

检查更新是只读操作；安装更新会替换已安装 Skill，必须在展示明确版本和变更说明后获得用户针对该版本的确认。用户说“把图片转成 Figma”“继续导入”或批准 HTML，均不构成更新授权。

## 检查更新

用户明确要求检查时运行：

```bash
python3 scripts/update_skill.py --check
```

读取 JSON 结果并向用户说明：

- 当前版本与最新版本；
- `status` 是 `current`、`update-available`、`not-installed` 或 `local-modified`；
- 发布说明 `changes`；
- 本地是否存在未发布修改；
- 更新会保留哪些本机状态。

公开仓库不可访问时，报告实际网络或 GitHub 错误，并提供仓库主页 `https://github.com/sunxiaowei12333-netizen/image-to-editable-figma-toolkit` 供用户检查；不得要求用户提供 Token，也不得把登录 GitHub 当作公开仓库的安装前置条件。

没有新版时停止，不重复下载或要求用户确认。存在本地未发布修改时必须明确警告；除非用户明确同意覆盖本地修改，否则不得继续。

## 安装更新

用户明确确认输出中的最新版本后运行：

```bash
python3 scripts/update_skill.py --apply --confirm-version <最新版本>
```

仅当用户已经看过并确认 `local-modified` 警告时，才追加：

```bash
--allow-local-modifications
```

脚本必须先下载到临时目录并验证 Skill 结构、Python/Node 语法和发布指纹，再执行可恢复替换。它会保留 `tooling/.local-state.json`，不读取或写入 Token、Cookie、Figma 文件、用户任务输出或浏览器 profile。安装失败时恢复旧版本；成功时保留一个可恢复备份并返回路径。

更新成功后提示用户开启新的 Codex 任务。不得在当前已经加载旧版主 Skill 的任务里声称新版规则已生效，也不得自动重新执行正在进行的图片任务。

## 更新器自身

本 Skill 不在运行中更新自身。若仓库发布了更新器新版，使用首次安装命令单独重新安装更新器，避免运行中的脚本覆盖自己。

## 触发示例

- “检查图片转 Figma Skill 有没有更新。”
- “更新 image-to-editable-figma 到最新版。”
- “恢复图片转 Figma Skill 的已发布版本。”
