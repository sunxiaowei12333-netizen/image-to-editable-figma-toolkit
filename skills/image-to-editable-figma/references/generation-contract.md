# 生图契约与分项验收（仅明确实验模式）

本文件只在用户明确要求 `rule-regression` 或 `fresh-generation-stability` 时读取和执行。普通图片转 Figma、真实效果查看和其他 `delivery` 任务不得加载本文件、不得建立版本 2 两遍测量或分项 `assess`，也不得用这里的实验数值门槛阻断交付。

普通 `delivery` 仍须防止提示词在调用前后漂移，但走轻量路线：资源清单写 `deliveryPromptPlanVersion: 1`，生成项沿用本脚本所需的 `generationReason / targetVisibleBounds / alphaRequired / keyPlan / geometryPolicy / generationSpec`，不写 `measurementEvidence`；运行 `generation_contract.py delivery-plan ... --out delivery-generation-plan.json`。该命令内部只执行一次资源预检并冻结分析得到的提示词、画布、主体边界和哈希，不做两遍测量、实验基线比较或分项产物评估。`delivery` 与下文版本 2 实验计划不能同时声明。

## 先分类，后冻结请求

明确实验轮次在 schema v3 清单根部加入 `labGenerationContractVersion: 2`。版本 1 只用于历史读取/回放，不能开启新一轮实验。先按 resource-routing 判断资源职责，不规定整页生成数量：

- 普通提示条、圆角卡片和头像外圈默认原生 Rectangle/Ellipse；普通阴影、渐变或压缩噪点不是复杂材质证据。真实可见且影响还原的织物、金属或纸纹不能忽略，必要时独立 IMAGE。必须在实际目标尺寸判断并记录理由，不能为了复现某次“六张图”强行改分类。
- 圆形头像可复用**内部照片**，圆形裁切和描边原生实现。它不是从复杂人物轮廓抠图；但不能把带原背景/外圈的方形裁切叫干净照片。确认圆形有效区域没有其他 UI、无遮挡、倍率合格并填写既有 reuseEvidence；证据不成立才生成。
- 每个生成项必须填写 `generationReason`，说明为何无法使用原生节点或合格源素材。重复使用同一头像不重复生成。

生成项另加如下字段（其余 v3 字段照常保留）：

```json
{
  "generationReason": "完整角色受 UI 遮挡且有细毛边，无合格独立源素材",
  "targetVisibleBounds": {"x": 10, "y": 438, "width": 164, "height": 202},
  "measurementEvidence": {
    "method": "two-pass-reference-crop",
    "evidencePath": "/absolute/path/reference-pilot-crop.png",
    "firstBounds": {"x": 10, "y": 438, "width": 164, "height": 202},
    "secondBounds": {"x": 10, "y": 438, "width": 164, "height": 202}
  },
  "alphaRequired": true,
  "keyPlan": {"hex": "#FF00FF", "conflictCheck": "与本对象衣服、毛发、高光和道具不冲突"},
  "geometryPolicy": {"lockAxis": "height", "maxSizeDeltaPx": 4, "reason": "保持底部锚点和人物高度；另一方向最多偏移四像素"},
  "generationSpec": {
    "description": "Reconstruct only the single aviator character in the reference.",
    "invariants": ["Same face, pose, outfit and materials", "Opaque jacket continues to the bottom crop edge"],
    "exclusions": ["All text, UI and adjacent characters", "Extra hands or legs"],
    "canvasSize": [1024, 1280],
    "subjectTouchEdges": ["bottom"]
  }
}
```

`measurementEvidence` 必须在任何图片调用之前产生：用同一张参考图、同一对象边界独立量取两次，保存能看见完整边界的裁切证据；两次结果必须逐字段一致，并与 `targetVisibleBounds` 一致。脚本同时记录证据文件 SHA-256 和解码后 RGBA 像素 SHA-256。两次结果不一致时先修正边界，禁止先生成再选择对产物更有利的一组数字。路径和 PNG 编码元数据可以因任务目录不同而变化，固定测试只比较归一化像素哈希和边界，不比较路径或文件字节哈希。

描述必须具体到当前对象；示例不能替代看图。`invariants` 还应涵盖细框连续性、白毛、镂空、需保留的印刷文字等实际风险。`exclusions` 不要误删属于原子内部的必要内容。尺寸、比例和占比只写结构化字段；自由文字不再写 `95%`、`1940×172`、`5.4:1` 等第二套数字。脚本拦截常见数字写法；它不是自然语言语义证明，仍须检查描述有无相反要求。

`canvasSize` 可省略：按目标主体 2× 加非触边侧留白计算。指定时脚本按目标比例放入画布，不同时手写主体像素尺寸和画布百分比。不透明照片/场景要求画布与目标比例一致，不加色键。生成工具不支持尺寸参数时，将请求尺寸保留在提示词中；**请求尺寸不是实际像素保证**。

```bash
python3 scripts/generation_contract.py plan <manifest.json> \
  --mode <rule-regression|fresh-generation-stability> \
  --out <generation-plan.json>
```

第二条也执行完整预检，输出每项的最终 `prompt`、`promptSha256`、主体尺寸、测量证据哈希和清单指纹。调用时原样使用该 prompt，附对应参考图，不重新压缩/改写提示词；日志记录真实调用 prompt 的哈希与 plan 核对。输出文件独占创建，不能覆盖已执行轮次。生成前修订应另存计划并记录替代关系；生成后不得修改尺寸目标或容差来追认通过。历史无标记或版本 1 清单仍只用于读取/回放，不用于开启新轮次。

同一参考图用于“重新生图稳定性”测试时，必须先拿本轮计划与用户明确指定、当前对话提供或可信精确 SHA 索引中的基线计划比较：

```bash
python3 scripts/generation_contract.py compare <baseline-generation-plan.json> <candidate-generation-plan.json>
```

只有输出 `ok: true` 才能调用图片模型；它固定参考图 SHA、视觉原子集合、`referenceBounds`、测量证据哈希、提示词哈希、请求画布、主体边界、触边、Alpha 和几何策略。比较只复用元数据，不读取或复用历史生成图片。没有可信基线时可以建立首个基线，但本轮只能称“建立基线”，不能称“相同条件回归”。

## 分开判断路线、质量、几何

本节仅适用于 `fresh-generation-stability` 实验：生成仍只允许每个原子一次，不主动要求直接透明。普通 `delivery` 的严重失败按[受控纠正](composition-fidelity.md#受控纠正)执行，不套用本节的不追加限制。意外结果按三条轴记录，不把一个轴的失败伪装成另一个轴：

| 返回结果 | 记录和处理 |
| --- | --- |
| 正确色键文件 | 按 alpha-extraction 同文件提取，保留提取报告和源文件 |
| 意外真实 RGBA | `unexpected-alpha`；保留原始 alpha，**不再铺洋红底冒充原路线**。复核深浅底、最终背景、内部不透明区域、主体完整性。全部通过才可作为“路线偏离但画质合格”资源使用，不计为固定色键路线成功样本 |
| 白底/烘焙棋盘格/不兼容背景 | 质量未通过；不可用简单阈值硬抠，不追加生图 |
| 衣服渐隐、主体缺损、镂空误删、可见脏边 | 真实质量失败；路线标签不能掩盖它 |
| 比例偏差 | 按生成前锁定轴、容差计算，不直接等同于画质差，也不能任意拉伸 |

可用 `generation_contract.py assess <generation-plan.json> <observation.json>` 做分项记录。observation 示例：

```json
{
  "assetId": "pilot",
  "promptSha256": "实际调用提示词的SHA256，必须与计划一致",
  "rawPath": "/absolute/raw.png",
  "finalPath": "/absolute/alpha.png",
  "extractionReport": "/absolute/alpha.report.json",
  "visualReview": {"status": "pending"}
}
```

RGBA 原样复用时 raw/final 指向同一文件，省略 extractionReport。`visualReview.status` 默认为 pending；passed/warning/failed 必须附 `note` 和现存 `evidencePath`，证据包含当前文件的深浅底、内部完整性及显示尺寸检查；色键路线还需审核提取报告。脚本只检查文件、通道、边界和记录，不自动判断像不像、脏边、材质、真假棋盘格或报告内容。**检查脚本运行成功不等于资源通过**；读取输出各状态。最终页面合成仍待验收。新计划写入 `assessmentPolicyVersion: 3`；旧计划仍按其原策略回读，不会因新字段缺失而破坏历史审计。

视觉验收使用四种状态：`pending / passed / warning / failed`。`warning` 表示仅在放大或孤立素材中能发现、但在最终画布 `100%` 目标尺寸不可辨认，且不改变角色身份、对象语义、文字、主体数量或结构完整性的轻微差异；它允许资源继续进入 HTML，并在最终综合预览中保留非阻断记录。`failed` 只能用于最终画布 `100%` 已明显可见的偏差，或主体缺失/增加、结构损伤、错误文字、Alpha 缺陷等硬问题。不得用放大的原始生成图单独证明脸部、眼睛、眉毛、纹理或道具局部形状“明显不符”。

`warning` 和 `failed` 还必须记录 `evidenceScale` 与 `reasonCode`。普通视觉差异使用 `evidenceScale: "target-100%"`；局部约 `200%` 只能以 `alpha-risk-200%` 记录 Alpha 或结构缺损，不能用于阻断仅放大后才可见的身份细节。`warning` 的 `reasonCode` 使用 `minor-visual-difference / geometry-within-default-tolerance / geometry-outside-default-tolerance`；最后一项只用于“数值越界但在最终画布 100% 不可辨认”的透明前景。`failed` 只允许 `visible-at-target-size / structural-defect / alpha-defect / wrong-text / missing-or-extra-subject`。`warning` 可进入布局但不计为无警告的受控成功样本。

透明前景几何默认沿用构图检查的 4px 容差，且新计划不得把 `maxSizeDeltaPx` 收紧到 4px 以下；更细的差异交给最终目标尺寸视觉检查，不用不可感知的小数越界阻断任务。纯场景满铺等不透明资源只有在回归夹具明确验证“精确比例边界”时才使用 `0px`；普通稳定性实验也应按测试目的设置合理容差，不能把生成器的整数取整误差误报为视觉质量失败。历史计划若曾写入低于 4px 的透明前景容差，评估时保留原值供审计，但以 4px 作为有效下限；落在“原值之外、4px 以内”的结果记录 `geometryWarning=true` 并继续布局，不修改 `referenceBounds`。

版本 3 的评估中，超过有效容差先记录 `outside-plan`，但它不再单独决定整轮停止。只有同时满足“透明前景、生成前两遍测量已验证、最终画布 `100%` 证据确认不可辨认、`warning + geometry-outside-default-tolerance`”时，记录 `geometryDisposition=warning-accepted-at-target` 并继续 HTML；不透明满铺资源、未验证测量、普通 `passed`、泛化 `minor-visual-difference` 或任何目标尺寸可见差异都不能走该例外。目标尺寸可见时使用 `failed + visible-at-target-size` 并硬停该资源。禁止事后扩大容差、修改 `referenceBounds` 或以更新规则追认旧轮次。

## 回归与结果范围

修改本文件或脚本后先做 `rule-regression`：运行 `python3 -m unittest discover -s tests -p 'test_*.py'`，固定覆盖尺寸矛盾、两遍测量不一致、计划输入漂移、低有效像素、边界裁切、旧清单兼容、几何边界、意外 alpha 和视觉未审/失败。它不调用图片模型，只能证明规则没有回归。需要证明生图稳定性时另开 `fresh-generation-stability`，使用真实新生成像素并在调用前通过计划比较；历史生成图片不得作为本轮产物。只有后者完成新生图、HTML 与视觉验收，才能提供端到端稳定性证据。
