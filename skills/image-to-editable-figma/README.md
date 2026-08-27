# 图片转可编辑 Figma Skill

## 团队安装

从 GitHub 下载或克隆后，请把完整的 `image-to-editable-figma/` 目录复制到每位用户的 Codex Skills 目录，例如：

```text
~/.codex/skills/image-to-editable-figma/
```

不要只复制 `SKILL.md`。本 Skill 还依赖 `agents/`、`assets/`、`references/`、`scripts/` 和 `tooling/package.json`。

本机需要：

- Codex，以及在 Figma 阶段可用的 Figma MCP/相关 Skill；
- Node.js 与 npm；
- Python 3 与 Pillow：`python3 -m pip install -r requirements.txt`；
- Google Chrome。

新机器可手动执行只读检查：

```bash
node scripts/bootstrap.mjs --check
```

该检查不是每次任务的强制前置步骤；Figma MCP 会在获批后的 Figma 阶段由 Codex 检查。

## 稳定预览服务（可选，需明确授权）

稳定预览服务只解决 `127.0.0.1` 预览链接随临时终端退出而失效的问题，不参与图片生成、HTML 构建、视觉渲染、审批或 Figma 写入。安装常驻服务是一次持久环境修改，不会在普通图片任务中静默执行。

先检查安装方案，不落盘：

```bash
node scripts/preview-service.mjs install --dry-run
```

用户明确同意后，在 macOS 安装用户级 LaunchAgent：

```bash
node scripts/preview-service.mjs install --confirm-persistent-install
```

日常任务只需 `status`、`register` 和 `verify`。默认固定地址为 `127.0.0.1:41972`，每个 URL 包含独立任务 ID 和版本，不提供 `/latest` 或整个工作区。端口被未知进程占用时命令会停止，不会静默换端口。详细命令、安全边界、恢复与卸载规则见 [`references/preview-service.md`](references/preview-service.md)。

卸载只移除保活包装并让历史链接暂时离线，不删除路由映射、任务 HTML、图片、字体、报告或审批指纹：

```bash
node scripts/preview-service.mjs uninstall
```

## Hugeicons

`tooling/package.json` 使用 `@hugeicons/core-free-icons: latest`，不锁定团队统一版本，也不提交 lockfile。构建器只在当前 HTML 实际出现 Hugeicons 标记时工作，并按以下顺序查找图标包：

1. 显式传入的 `--hugeicons-dir`；
2. 当前任务目录向上已有的 Hugeicons 包；
3. Skill 私有 `tooling/node_modules`。

三处均缺失时，构建器才在 Skill 私有目录完成一次 npm 初始化。npm 会下载 Hugeicons 包，但最终 Capture HTML 只嵌入页面实际使用的图标定义。没有 Hugeicons 标记的页面不会触发安装。

需要提前初始化时可手动执行：

```bash
node scripts/bootstrap.mjs --ensure-hugeicons
```

不要把 `tooling/node_modules`、`package-lock.json` 或本机状态文件提交到 GitHub。

## Figma 浏览器扩展（可选）

首次使用时，Skill 会提供一个可点击的官方安装入口：

- 名称：Figma
- 安装：[Chrome Web Store 官方页面](https://chromewebstore.google.com/detail/figma/fkmaohpngenfoccdgceedjkfhkdcohmg)
- 扩展 ID：`fkmaohpngenfoccdgceedjkfhkdcohmg`
- 发布者：`Figma, Inc.`

扩展允许用户自行把 Skill 交付的 HTML 预览链接导入 Figma。点击链接只会打开安装页面；添加扩展和授权必须由用户在 Chrome 中确认。未安装扩展不影响 Figma 官方自动 Capture 流程，也不会阻塞页面生成。

首次提示状态只保存在被 Git 忽略的 `tooling/.local-state.json`，只控制是否重复显示提示，不参与生成、构建或导入判断。
