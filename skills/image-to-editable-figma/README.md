# 图片转可编辑 Figma Skill

## 团队安装

本仓库同时分发主 Skill 和独立更新器。建议按仓库根目录的安装命令一次安装两个 Skill，不要只复制 `SKILL.md`。主 Skill 还依赖 `agents/`、`assets/`、`references/`、`scripts/` 和 `tooling/package.json`。

主 Skill 安装位置为：

```text
~/.codex/skills/image-to-editable-figma/
```

本机需要：

- Codex，以及在 Figma 阶段可用的 Figma MCP/相关 Skill；
- Node.js 与 npm；
- Python 3 与 Pillow：`python3 -m pip install -r requirements.txt`；
- Google Chrome。

新机器安装后，在新的 Codex 任务中发送：

```text
首次安装后，帮我初始化图片转 Figma 的全部环境。
```

初始化会集中检查本地依赖、Figma、Chrome、Computer Use 和 macOS 权限。安全的 Skill 私有依赖可自动修复；持久授权使用真实授权界面，必须人工完成的步骤提供官方链接或精确设置路径。也可以单独运行本地依赖准备：

```bash
node scripts/setup_environment.mjs --prepare
```

首次初始化不是每次任务的前置步骤；普通图片任务不读取初始化状态，也不会因扩展已安装而改变默认导入通道。

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

## Figma 浏览器扩展与授权

只有在用户明确执行首次环境初始化时，Skill 才检查可能涉及的 Codex 插件、Figma 授权、Chrome 扩展与系统权限。Figma 官方扩展入口为：

- 名称：Figma
- 安装：[Chrome Web Store 官方页面](https://chromewebstore.google.com/detail/figma/fkmaohpngenfoccdgceedjkfhkdcohmg)
- 扩展 ID：`fkmaohpngenfoccdgceedjkfhkdcohmg`
- 发布者：`Figma, Inc.`

扩展允许用户把 Skill 交付的 HTML 预览链接导入 Figma。添加扩展和持久授权必须通过 Chrome 或系统提供的真实确认界面；未安装扩展不影响普通页面使用 Figma 官方自动 Capture。

初始化状态只保存在被 Git 忽略的 `tooling/.local-state.json`，日常任务不读取它，也不根据它决定生成、构建或导入通道。

## 更新

更新由并列安装的 `image-to-editable-figma-updater` 处理。它只在用户明确要求时检查私有仓库；发现新版后必须先展示版本与变更，获得确认后才能替换主 Skill。更新成功后开启新的 Codex 任务加载新版。
