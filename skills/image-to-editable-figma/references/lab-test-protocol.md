# 模式、执行档与计时协议

本文件负责避免三类耗时膨胀：读取无关历史、生成后迟迟不做整页合成、同一终检命令反复运行。它不降低视觉或编辑性门槛。

## 1. 模式和执行档是两条独立轴

`testMode`：

- `delivery`：默认真实交付。使用轻量 `delivery-generation-plan.json` 冻结最终提示词；不做实验专用的两遍测量和分项 `assess`。
- `rule-regression`：只运行固定夹具与脚本测试，不调用图片模型。
- `fresh-generation-stability`：相同输入重新产生像素并比较稳定性；使用版本 2 生图契约、两遍测量和基线计划比较。

只有用户明确要求规则回归或同输入生图稳定性时，才选对应实验模式。“测试版”名称本身不等于实验授权。

`executionProfile`：

- `cold-start`：默认。只读当前任务输入和本轮目录，不查看其他对话，不扫描历史任务或资源目录。
- `warm-reuse`：仅当当前任务直接获得精确参考 SHA、可信基线清单、审批指纹和批准资产哈希时使用。资产复制到当前版本目录后重新检查 Alpha 和有效倍率；不允许按文件名或相似度寻找旧资源。

耗时只能在同一模型/推理档、`testMode + executionProfile`、相近资源数量、相同复用范围和交付终点下比较。

## 2. 第一动作必须启动计时

在读取参考图、历史产物或其他任务内容之前执行：

```bash
python3 scripts/delivery_record.py init <test-timing.json> \
  --mode delivery --profile cold-start
```

该命令独占创建文件，自动写 `startedAt`。不得事后估算或补写一个更晚的开始时间。生成结束、首次整页预览、HTML 就绪和交付就绪分别执行：

```bash
python3 scripts/delivery_record.py mark <test-timing.json> generationFinishedAt
python3 scripts/delivery_record.py mark <test-timing.json> firstPreviewAt
python3 scripts/delivery_record.py mark <test-timing.json> htmlReadyAt
python3 scripts/delivery_record.py mark <test-timing.json> handoffReadyAt
```

Codex UI 显示的排队、上下文加载和最终回复总耗时若可获得，另记 `codexUiElapsed`；不得把内部 `startedAt → handoffReadyAt` 冒充 UI 端到端时长。

## 3. 生成后先做整页，不在单素材上打转

同一次参考图分析中完成资源路由、构图契约和全部生成项的提示词字段。一次性预检并冻结计划后，批量准备裁切、图标和生成输入；工具允许时并行处理独立视觉原子。每个需生成的视觉原子默认一次高质量调用；普通 delivery 的明确失败仅按[受控纠正](composition-fidelity.md#受控纠正)执行，不把纠正后结果计作首次成功。

最后一项生成工具返回且文件已落盘时立即标记 `generationFinishedAt`，不把抠图/整理完成时间当作生图结束；不得事后手填所有资源相同的起止时间。全部资源首次落盘后只制作一张联系表，统一检查数量、主体、透明度、有效倍率和明显结构问题。除非联系表发现明确异常，不连续打开或反复裁切查看同一个头像、人物、画框或装饰；不得为同一页面重复搜索同一图标库候选，图标名称在分析阶段一次确定。

`generationFinishedAt` 后立即写最小但完整的整页 HTML：背景、主要视觉原子、全部可编辑文案和核心布局都必须出现。对本 Skill 的固定测试夹具，`firstPreviewAt - generationFinishedAt` 必须不超过 240 秒；超过即记为流程失败，不能用后续精修掩盖。真实外部故障导致超时时仍如实记录原因。

## 4. 最终流水线只保留一次成功结果

最终交付记录以下阶段：

- `resource-preflight`
- `capture-build`
- `html-preflight`
- `composition-check`
- `browser-preview`（证据为最终整页截图）
- `approval-fingerprint`

每阶段最终必须恰好有一次 `passed`。只有上一尝试明确失败并记录原因时才允许重试；不要为了“再确认一次”重复运行已通过命令。每次运行后用以下命令记账：

```bash
python3 scripts/delivery_record.py attempt <test-timing.json> \
  --stage html-preflight --status passed --evidence <result-file>
```

冻结计划的 manifestSha256 与最终清单一致时，复用 delivery-plan 的资源预检证据；清单改变才重检。构图命令已包含浏览器加载、字体/图片检查和截图，成功报告及截图同时入账 composition-check 与 browser-preview，不另开第二个会话。相邻命令和记账合并到一次工具执行，失败即停止后续步骤。

失败重试必须加 `--reason`。资源预检、Capture 构建、HTML 预检、构图检查、稳定 URL 浏览器预览和审批指纹形成一条最终链；不要先构建 Inline 再因体积改 External，`build_offline_capture.mjs --asset-mode auto` 必须一次选择最终模式。

## 5. 技术状态与视觉状态永远分开

脚本成功只代表结构、文件和记录通过，不能自动写视觉通过：

```bash
python3 scripts/delivery_record.py technical <test-timing.json> \
  --status passed --note "最终流水线各阶段通过"

python3 scripts/delivery_record.py review <test-timing.json> \
  --status <passed|warning|failed> --reference <original-reference.png> \
  --evidence <final-screenshot-or-review-file> \
  --note "填写与原图对照后的材质、轮廓、排版、Alpha 实际差异"
```

视觉判断必须来自原图与最终截图在相同目标尺寸下的直接对照，不能仅按清单、自述或加载成功判断；哈希绑定两份证据不等于自动评估图像相似度。新版记录器要求原图和证据文件存在且哈希未变，仍可读取旧版记录。

视觉状态仅允许写在 `visualReview.status`，根部 `visualStatus` 会被校验器拒绝。`technicalStatus=passed` 而 `visualReview=pending` 时只能称“技术检查通过、视觉待审”。最终执行：

```bash
python3 scripts/delivery_record.py validate <test-timing.json>
```

最终画布 `100%` 决定普通相似度；约 `200%` 只用于 Alpha、边缘和结构风险，不把正常尺寸不可见的细差升级为失败。

## 6. 结果范围

记录真实生成调用、复用项、失败资产、有效倍率和各阶段证据。单次更快或更慢都不能证明普遍趋势；报告必须拆开模型等待、生成后到首次整页预览、最终 QA 和用户审批等待。规则回归通过不能称图片模型稳定，技术检查通过不能称视觉一致，未完成 HTML/Figma 的轮次不能称端到端完成。

## 增量耗时的记录边界

局部输入裁切与原图目标冻结并入生成前准备；比例报告紧接 Alpha 提取；图片整体偏色检查合并最终截图，不增加独立截图、浏览器或审色轮次。受控纠正单独记录准备、模型实际等待、生成后合成、最终检查及异常恢复时间；并行调用报告实际墙钟时间，不把每项时间相加。

已有页面局部纠正与整页首次生成不能直接相减。脚本执行不足一秒不代表分析和编排也不足一秒；一次测试不证明普遍时长或成功率。对本次类似复杂度页面，可仅作粗估给出 HTML 到验收约 8–10 分钟、遇明显失败纠正约 10–13 分钟，必须标注尚无完整新流程验证，不含用户等待和 Figma 导入，不对其他页面套用或作为硬限时。
