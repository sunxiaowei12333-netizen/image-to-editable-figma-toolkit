---
name: image-to-editable-figma
description: 将界面截图或本地图片高保真还原为分层可编辑 HTML，并在明确审批后导入 Figma。默认一次生图；明显比例、颜色或严重 Alpha 失败最多一次受控纠正；保留有效像素、Alpha、构图和 Figma 语义门槛。
---

# 图片转 Figma

## 适用边界

本 Skill 由 2026-09-20 的备份优化版迁移为当前正式入口，调用名为 `image-to-editable-figma`；原正式版保留在 `image-to-editable-figma-formal-copy`，仅用于回滚和对照。脚本、references 和依赖都从本目录读取；不得修改历史任务、正式版副本或当前 lab，也不得把单次测试结果自动推广为所有图片都通过。

目标是把截图重建为高保真 HTML，再在用户审批当前 HTML 后导入 Figma：

- 纯场景背景、完整人物/IP、复杂材质画框、完整插画、照片和无需内部编辑的视觉原子保持独立 `IMAGE`；
- 文案保持 Text；规则 UI 使用 Rectangle/Ellipse/Auto Layout；UI 图标使用 Hugeicons/Icon Library；
- 图片直接作为叶子节点，不用无职责 Frame/Group 包裹；
- “可替换”不等于“内部必须矢量化”，编辑粒度停在有实际价值的视觉原子边界。

## 渐进读取

开始任务先完整读取：

1. [测试模式、执行档与计时](references/lab-test-protocol.md)
2. [HTML 基础规范](references/html-basic-standards.md)
3. [资源类型路由](references/resource-routing.md)
4. [构图保真契约](references/composition-fidelity.md)

仅在需要时读取：

- 生成透明前景前：[色键提取](references/alpha-extraction.md)
- 新建流式/响应式 HTML 前：[HTML-first Auto Layout](references/html-first-auto-layout.md)
- 用户明确要求规则回归或同输入重新生图稳定性时：[实验生图契约](references/generation-contract.md)
- HTML 已获用户审批、准备导入 Figma 时：[Figma 规范化](references/figma-normalization.md)；同时必须加载 `figma-use` Skill
- 发生异常时：[异常处理](references/exception-handling.md)；涉及稳定预览服务时再读 [预览服务](references/preview-service.md)
- 只有用户明确要求初始化环境时：[首次安装](references/first-install-setup.md)

不要为正常路径预读异常、安装或实验分支。

## 模式与执行档

模式自动选择，不要求用户理解内部名称：

- 默认 `delivery`：真实交付；一次目标边界判断，轻量提示词冻结，不做实验两遍测量。
- `rule-regression`：仅用户明确要求检查 Skill/脚本规则时使用；不调用图片模型。
- `fresh-generation-stability`：仅用户明确要求相同输入重新生图并比较稳定性时使用；必须做两遍测量、实验计划和基线比较。

执行档：

- 默认 `cold-start`：只读当前输入和本轮目录；禁止查看其他对话、扫描历史任务或搜索旧资源。
- `warm-reuse`：仅精确参考 SHA、可信资源清单、审批指纹和资产哈希均已直接提供或由可信索引精确命中时使用；当前副本仍重新验收。

不同模式或执行档的耗时不能直接比较。

## 硬门槛

### 画布

用户指定尺寸或设备类型/方向时优先遵循。未指定时按参考图宽高比选择最接近的标准画布，不能按像素总量猜设备：

- Pad：`1024 × 640`
- 横屏手机：`812 × 375`
- 竖屏手机：`375 × 812`

参考图与目标画布比例不同时，只能延展/裁切纯场景背景、调整留白和重新排布；不得拉伸主体、改变主体数量或复制前景。

### 位图与 Alpha

- 新生成、重型编辑和可替换裁切首选有效 `2×`，宽高最低倍率不得低于 `1.5×`；插值不算有效分辨率。
- 最终画布 `100%` 决定普通视觉相似度。约 `200%` 只检查 Alpha、细边、发光、白毛、金属细框等风险，不用放大后才可见的细差阻断交付。
- 透明前景必须是真 Alpha，不能烘焙棋盘格、纯色底、截图背景或相邻 UI；浅色、高光、手指、头发、服饰、道具和真实镂空都要保留。
- 生成透明前景固定走“一次安全纯色底生成 → 同一文件确定性色键提取”；不得先尝试直接透明，不得用全局 HSV/白底阈值强抠。

### 资源路由

- 每个新任务必须先建 schema v3 `resource-manifest.json` 和 `composition-contract.json`。
- 木质牌板、复杂画框、材质装饰、不规则完整插画等只要出现复杂度信号，就不得走 `native-rebuild`。
- `native-rebuild` 必须完整填写 `nativeRebuildEvidence`；复杂度信号非空时预检直接失败。
- 资源一旦确定为 `IMAGE`，失败后只能换合规图片取得方式或修同一文件；不能静默降级为 CSS/SVG/Rectangle。
- 同一视觉原子默认一次高质量生成/重型编辑调用；仅普通 `delivery` 的明显比例、整体颜色或严重 Alpha 失败可按[受控纠正](references/composition-fidelity.md#受控纠正)追加一次，最多两次，不生成候选。工具已可能执行但返回不明时先查结果和新文件，不得重发。
- 生成次数按视觉原子限制，不设整页上限；不能为了省调用合并、遗漏或降级视觉原子。

### 审批与 Figma

Figma 是 HTML 审批后的第二阶段。审批前禁止新建 Figma 文件、创建 Capture ID、调用插件导入或写入节点。审批必须绑定当前内部 HTML、`*-capture.html`、依赖哈希和最终截图；任何内容变化都使审批失效。

## 唯一执行顺序

### 0. 先启动记录

在看参考图或历史内容之前：

```bash
python3 scripts/delivery_record.py init <version-dir>/test-timing.json \
  --mode delivery --profile cold-start
```

新任务输出到 `image-to-editable-figma/<source-slug>-<timestamp>-<id>/v001/`。同一任务明确修改时才沿用该任务并递增版本；不覆盖历史任务，也不写入正式版副本或当前 lab 的任务目录。

### 1. 一次分析完成两个契约

只分析当前参考图一次，并同时产出（原图目标边界冻结后不随生成结果改写）：

- `resource-manifest.json`：参考 SHA、`executionProfile`、视觉原子类型、来源、复杂度、Figma 类型、复用/原生/缓存证据和 fallback；
- `composition-contract.json`：高视觉权重对象的 selector、数量、锚点、目标边界、比例、层级和节点类型。

`delivery` 清单必须写 `deliveryPromptPlanVersion: 1`，不得写 `labGenerationContractVersion`。有精确 SHA 可信基线时传 `--baseline-manifest`，任何分类或路线漂移都先停止并解释证据。

分类依据是原图的实际材质与轮廓；不能把有木纹、金属角花等特征的对象填成“无复杂度”，再用清单自洽代替保真。沿用本次分析记录，不另开分类审核轮次。

### 2. 预检并冻结提示词

```bash
python3 scripts/generation_contract.py delivery-plan \
  <resource-manifest.json> --out <delivery-generation-plan.json>
```

有可信精确 SHA 基线时在命令末尾追加 `--baseline-manifest <trusted-baseline.json>`。该命令内部只运行一次完整资源预检，再独占写入冻结计划；不要在普通流程中先重复调用 `preflight_resource_plan.py`。命令通过后才生成或编码。调用图片生成/编辑工具前加载 `imagegen` Skill；优先用当前环境的内置 `image_gen`，只有明确不可用时才用现有备用通道。不要为显式选择模型、尺寸或路径改走不必要的插件/API。

对于从页面提取的独立画框、牌板等素材，先按本次分析的边界裁切局部参考，保留完整轮廓和必要上下文；记录输入路径、裁切范围与 SHA，随冻结计划一起保存。纯背景或确需整页上下文的资源保留整页输入。裁切只服务模型输入，不能直接冒充干净最终素材。

生成项必须原样使用冻结 plan 的 prompt。批量准备全部视觉原子和图标；工具允许时并行执行独立资源。每项首次就用最终参考、尺寸、Alpha 方案和不变量；不生成草稿、候选或为轻微差异重试；明显失败仅走受控纠正。

页面需要 Hugeicons 时，在此次批量准备中一次核验所选包及真实导出名，例如：

```bash
node scripts/bootstrap.mjs --ensure-hugeicons --source-dir <version-dir> \
  --icons Idea01Icon,Mic01Icon
```

示例名称必须换成本页实际选用项。包缺失才初始化；导出名不存在时从已解析包中选择实际名称，不重装、不自绘，也不删除或改名 `data-icon-library` / `data-icon-name` 绕过构建器。无图标页面跳过此项。

资源落盘后立即标记：

```bash
python3 scripts/delivery_record.py mark <test-timing.json> generationFinishedAt
```

只做一张全资源联系表统一检查。除非发现明确问题，不反复查看同一头像/人物/装饰，不重复搜索 Hugeicons，不运行无关格式探测。透明项按 alpha reference 做一次确定性提取和风险检查；修同一文件不算新生成，但不能把不可分离产物强行修成通过。紧接提取运行 `measure_alpha_bbox.py <asset.png> --plan <delivery-generation-plan.json> --asset-id <id>`，合并记录实际可见边界、相对原图的像素及百分比偏差。仅 DOM 外框按透明留白反算，不替换冻结的原图目标；检查不另开浏览器或截图。

### 3. 四分钟内做首个完整页面

生成结束后先写最小但完整的整页 HTML：背景、全部主要视觉原子、可编辑文案和核心布局都出现，再做局部精修。固定测试夹具要求 `generationFinishedAt → firstPreviewAt ≤ 240s`。

首次整页出现后：

```bash
python3 scripts/delivery_record.py mark <test-timing.json> firstPreviewAt
```

HTML 按基础规范实现：

- `#canvas` 尺寸严格等于目标画布，首个直接子节点是纯背景 `<img>`；
- V2 流式容器使用 `data-figma-layout` 和 Auto Layout 语义；图片为直接 `<img data-figma-node-type="IMAGE">`；
- 文案、卡片、按钮、媒体槽位和图标保持正确的可编辑职责；
- 字体、字号、行高、字距、颜色和 Hugeicons 规则以 HTML 基础规范为唯一来源，不在本文件重复维护。所有字色与 UI 图标色在现有分析和验收中按分类及差异边界匹配；不为颜色增加采样、截图或单独复核轮次。

### 4. 只跑一条最终流水线

内部保留可维护源 HTML；对外只输出一个 `*-capture.html`。用 `build_offline_capture.mjs --asset-mode auto` 在写文件前一次决定 Inline 或 External，禁止 Inline 失败后再重建 External。

最终流水线按顺序执行并留证：

1. `resource-preflight`
2. `capture-build`
3. `html-preflight`
4. `composition-check`
5. `browser-preview`：唯一稳定 HTTP URL、一次浏览器会话、最终整页截图
6. `approval-fingerprint`

`delivery-plan` 已做资源预检：最终清单哈希与冻结计划 `manifestSha256` 一致时，直接复用该计划作为 `resource-preflight` 证据；清单改变才重检。将相邻的构建、预检和记录命令放在同一次工具执行中，任一步失败立即停止后续步骤。

构图检查已在独立 Chrome 会话加载页面、等待图片/字体、检查运行状态并截图；同一次成功结果同时作为 `composition-check` 和 `browser-preview` 证据。没有新异常就不再另开浏览器重截图，直接查看这张图与原图对照。

每阶段只有一次最终 `passed`；明确失败才可修复并重试，且必须记录原因。使用：

```bash
python3 scripts/delivery_record.py attempt <test-timing.json> \
  --stage <stage> --status passed --evidence <existing-result-file>
```

Capture 前至少运行：

```bash
python3 scripts/preflight_html.py <capture.html> \
  --manifest <resource-manifest.json> \
  --contract <composition-contract.json>

node scripts/check_composition.mjs \
  <stable-url> <composition-contract.json> \
  --mode delivery --output <report.json> --screenshot <preview.png>
```

自包含 Capture 文件在 `preflight_html.py` 命令末尾追加 `--offline`。

稳定预览沿用原 Skill 的服务身份与 `127.0.0.1:41972`，只注册本轮独立任务 ID；普通任务不得安装/替换服务、换端口或覆盖路由。注册后校验本地文件字节、HTTP 字节和 SHA 一致。

### 5. 技术与视觉分别验收

技术通过只写 `technicalStatus`，不能自动写视觉通过。一次查看原图与最终画布截图，以相同目标尺寸对照：高视觉权重对象的材质/轮廓与比例、人物姿态/裁切、文字尺寸/字重/换行；高风险 Alpha 再局部放大。沿用已有构图条目，在 review note 简述实际差异；不能仅写“主体齐全、语义一致，所以通过”，不增加单独评分表或截图轮次。分别记录：

```bash
python3 scripts/delivery_record.py technical <test-timing.json> \
  --status passed --note "最终流水线通过"

python3 scripts/delivery_record.py review <test-timing.json> \
  --status <passed|warning|failed> --reference <original-reference.png> \
  --evidence <visual-evidence> --note "填写本次对照观察到的材质、轮廓、排版及边缘差异"

python3 scripts/delivery_record.py mark <test-timing.json> htmlReadyAt
python3 scripts/delivery_record.py validate <test-timing.json>
```

主体缺失/重复、错误文字、明显比例/主色/身份偏差、Alpha/结构损伤必须失败。正常画布下不明显、且不改变角色辨识、材质类别、层级与布局的明暗或人物细节差异可以接受并记 warning，不为追求逐像素一致返工。比例同时看实际像素、对象规模与正常尺寸观感，不能用单一百分比自动判通过或失败。上述比例、主色、明暗及人物细节的素材纠正规则仅适用于图片；文字与 UI 图标的字色按 [HTML 基础规范](references/html-basic-standards.md) 独立执行，不因图片纠正而改为优先保留参考色。

记录器保存原图与验收证据哈希，文件改变后必须重新对照；哈希只绑定证据，不能自动证明视觉相似。失败仍可交付明确标注的诊断预览，但不得称视觉通过或请求按合格稿导入。

### 6. HTML 审批门

向用户只展示当前版本的：

- 一张刚通过验收的整画布预览图；
- 一个清晰命名的唯一稳定预览 URL，并说明可用于浏览器 Figma 插件采集；
- 简短的尺寸、资源路由、技术状态和视觉状态。

HTML 验收完成后，回复末尾使用独立引用块、`🟠` 锚点及整段加粗，固定使用以下文案：

> **🟠 HTML 已完成。可以手动打开预览链接使用Figma插件导入；也可以回复 “同意” 或明确授权导入 Figma，即可自动导入Figma；如需修改，请直接描述或标注问题，收到明确审批前不会导入 Figma。**

用户模糊回复或提出修改不算批准；修改后重做受影响的最终阶段并生成新审批指纹。

### 7. 审批后导入 Figma

先加载 `figma-use` Skill，再完整读取 Figma 规范化 reference。优先使用用户给定文件；未给定时先读取当前账号的 `whoami`/plan 结果：

- 如果当前账号对「猿辅导体验设计」plan（`team::1634053011581078191`）的 `seat` 为 `Full`，自动在该 plan 的 Drafts 中新建设计文件，不再询问团队归属；
- 如果该 plan 不存在、不可写或当前账号没有 `Full` 权限，才向用户询问目标团队/plan，再使用用户选定的可写 Drafts；不得擅自猜测或切换团队；
- 用户提供 Figma 文件链接时始终优先使用该文件，不触发 plan 选择。

保护已有文件：在独立 Page/新文件或明确安全副本内工作，不覆盖历史节点。

导入后验证：

- 根画布尺寸正确，纯背景是最底层独立图片节点并覆盖四边；
- composition contract 中的数量、锚点、边界、比例和 z-order 一致；
- Text 字体/样式/换行/度量正确，UI 图标为可追溯 Instance；
- 图片为正确视觉原子叶子层，规则 UI 为原生节点，流式容器为 Auto Layout；
- 无纯样式 Frame、无职责叶子 Frame、无多余图片包装；
- 最终 Figma 截图与已审批 HTML 没有视觉漂移。

Capture `completed` 只代表导入结束，不代表字体、结构或视觉验收通过。不要把脚本通过当作 Figma 完成。

## 交付

HTML 阶段交付预览图、唯一 URL、任务 ID、画布尺寸，以及分开的技术/视觉状态；内部路径默认不展示。Figma 阶段再交付文件/节点链接、最终截图、字体与图层语义审计结果。未执行的阶段明确写“未执行”，不得以局部完成冒充端到端完成。

出现异常时只加载对应 reference，从最近稳定阶段恢复；不要从头重跑已通过流程。预计延长时说明真实瓶颈，不为赶时间降低资源语义、分辨率、Alpha 或审批门槛。
