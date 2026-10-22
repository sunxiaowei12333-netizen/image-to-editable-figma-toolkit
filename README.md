# Figma 设计工具包

这是面向团队公开分发的 Codex 工具包，包含两个业务 Skill 和一个专用更新器，各自位于独立目录：

- `image-to-editable-figma`：把参考图高保真还原为可编辑 Figma。
- `image-to-editable-figma-updater`：只在用户明确要求时检查和安装主 Skill 更新。
- `editable-design-basic-standards`（规范设计稿）：整理已有可编辑 Figma 设计稿，分阶段完成基础视觉规范、组件库联动和本地组件整理。

主 Skill 不执行后台更新，不在普通图片任务中访问本仓库。更新器也不会在未获确认时覆盖已安装文件。

仓库名称和原有 Skill 路径保持不变，之前分享的安装命令仍可使用。

## 安装规范设计稿

只需要规范已有设计稿的同事，可把下面整段发送给 Codex：

````text
请从公开 GitHub 仓库安装“规范设计稿”Skill。如果本地已经存在同名 Skill，不要覆盖，先告诉我。

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo sunxiaowei12333-netizen/image-to-editable-figma-toolkit \
  --path skills/editable-design-basic-standards
```

安装后检查 figma-use、figma-generate-design 依赖是否可用，并确认 Figma 连接支持 use_figma；缺少时告诉我。安装成功后提醒我新开一个 Codex 任务。
````

需要目标设计稿的编辑权限，以及固定组件库「【规范和组件】猿辅导学生端App」的访问权限。安装 Skill 本身不授予 Figma 权限，也不附带两个 Figma 依赖 Skill。

日常使用示例：

```text
使用 $editable-design-basic-standards，帮我做基础视觉规范：
[待处理的 Figma 节点链接]
```

默认直接编辑链接指定范围，从第一步开始；后续阶段按 Skill 的授权规则执行。只整理组件时可说“帮我整理组件”。它不负责截图重建，也不会因为安装而自动修改设计稿。

## 一次安装全部 Skill

需要两个业务 Skill 和图片转 Figma 更新器时，把下面整段发送给 Codex：

````text
请执行下面命令安装三个 Skill。如果本地已经存在任何同名 Skill，不要覆盖，先告诉我。

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo sunxiaowei12333-netizen/image-to-editable-figma-toolkit \
  --path skills/image-to-editable-figma skills/image-to-editable-figma-updater skills/editable-design-basic-standards
```

安装后检查规范设计稿所需的 figma-use、figma-generate-design 和 Figma use_figma 连接，缺少时告诉我；安装成功后提醒我新开一个 Codex 任务。
````

## 单独安装图片转 Figma 与更新器

仓库公开可读，不需要 GitHub 登录或仓库邀请。把下面整段发送给 Codex：

````text
请执行下面命令，从公开 GitHub 仓库安装两个 Codex Skill。如果本地已经存在同名 Skill，不要覆盖，先告诉我。

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo sunxiaowei12333-netizen/image-to-editable-figma-toolkit \
  --path skills/image-to-editable-figma skills/image-to-editable-figma-updater
```

安装成功后告诉我，并提醒我新开一个 Codex 任务。
````

安装完成后开启一个新的 Codex 任务，并发送：

```text
首次安装后，帮我初始化图片转 Figma 的全部环境。
```

初始化会自动处理安全的 Skill 私有依赖；Figma、Chrome、Computer Use 与 macOS 持久权限使用真实授权界面，无法自动完成的步骤会提供官方链接或精确设置路径。

## 图片转 Figma 日常使用

```text
使用 $image-to-editable-figma 把这张参考图转成可编辑 Figma。
```

主 Skill 会先交付 HTML 预览和最终截图，只有用户明确批准当前版本并授权导入 Figma 后才执行 Figma 写入。

## 检查与安装图片转 Figma 更新

```text
使用 $image-to-editable-figma-updater 检查图片转 Figma Skill 更新。
```

检查是只读的。发现新版后，更新器会展示当前版本、最新版本和变更说明；只有用户明确确认对应版本后才安装。安装成功后需要开启新任务加载新版。

这个更新器只管理 `image-to-editable-figma`，不管理 `editable-design-basic-standards`。规范设计稿目前通过明确请求 Codex 从本仓库更新完整目录；更新前备份已安装版本，并核对本地修改，不直接覆盖。

## 分发边界

仓库不包含以下本机内容：

- `tooling/node_modules/`
- `tooling/.local-state.json`
- npm lockfile
- 用户任务输出、浏览器 profile、账号信息、Token 或 Cookie

仓库公开可读不代表进入公有领域或采用开源许可。团队内部使用及其他使用边界见 [LICENSE](LICENSE)。
