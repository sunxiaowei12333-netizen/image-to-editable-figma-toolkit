# 构图保真契约

新任务在生成资源或编码前读取本文件。目标是把“主面板居中、人物在角落、不能多出主体、形状尾巴方向正确”等视觉判断变成 Capture 前可检查的契约，而不是用固定坐标替代设计判断。

## 建立契约

在任务版本目录创建 `composition-contract.json`。只记录会显著影响构图、主体身份或 Figma 语义的对象：

- 主面板、主卡片、弹窗和核心内容区；
- 人物、IP、商品、头像、画框和其他不能增减的主体；
- 角落锚定、中心锚定或明显相互遮挡的前景；
- 气泡尾巴、凹口、切角、填空线等高视觉权重形状；
- 需要在 Figma 中得到特定节点类型的元素。

普通正文段落和低权重小装饰不必逐项写入。一个最小契约示例：

```json
{
  "canvas": {"selector": "#canvas", "width": 1024, "height": 640},
  "defaults": {
    "canvasTolerancePx": 1,
    "boundsTolerancePx": 4,
    "anchorTolerancePx": 4,
    "aspectRatioTolerance": 0.01
  },
  "elements": [
    {
      "id": "primary-paper",
      "selector": "[data-composition-id='primary-paper']",
      "count": 1,
      "bounds": {"x": 87, "y": 62, "width": 850, "height": 514},
      "anchor": {"horizontal": "center", "vertical": "center"},
      "aspectPolicy": "intrinsic",
      "figmaType": "IMAGE"
    },
    {
      "id": "left-character",
      "selector": "[data-composition-id='left-character']",
      "count": 1,
      "bounds": {"x": 13, "y": 387, "width": 181, "height": 325},
      "anchor": {"horizontal": "left", "vertical": "bottom"},
      "aspectPolicy": "intrinsic",
      "figmaType": "IMAGE"
    },
    {
      "id": "right-character",
      "selector": "[data-composition-id='right-character']",
      "count": 1,
      "bounds": {"x": 819, "y": 477, "width": 201, "height": 160},
      "anchor": {"horizontal": "right", "vertical": "bottom"},
      "aspectPolicy": "intrinsic",
      "figmaType": "IMAGE"
    },
    {
      "id": "question-tail",
      "selector": "[data-composition-id='question-tail']",
      "count": 1,
      "figmaType": "VECTOR",
      "attributes": {
        "data-figma-node-type": "VECTOR",
        "data-shape-tail": "right"
      },
      "shapeInvariants": ["right-facing tail", "two-layer border", "tail joins bubble midpoint"]
    }
  ]
}
```

`bounds` 均为目标画布内、相对 `canvas` 左上角的 CSS px。透明图片先按 alpha 可见边界量取目标，再反算 `<img>` 外框；契约中的 DOM `bounds` 应填写最终反算后的实际外框，另外在资源清单保留 alpha 可见边界。

普通 `delivery` 对当前参考图量取一次可见目标边界，生成后将实测 alpha 边界换算为 DOM `bounds`，并以最终画布 `100%` 综合预览判断是否存在可见变形、错位或裁断；机器数值越界但正常尺寸不可辨认时直接继续。只有用户明确要求 `rule-regression` 或 `fresh-generation-stability` 时，才对每个生成原子保存可见完整边界裁切并独立量取两次；两次 `x/y/width/height` 必须一致，才冻结资源清单的 `targetVisibleBounds`。实验生图计划把它保存为不可追改的 `referenceBounds`，同时保存裁切证据 SHA-256。稳定性实验还必须先通过元数据计划比较，不能在不同边界、画布或提示词下比较生成结果。

## 原图目标与实际主体分别记录

`delivery-generation-plan.json` 中的 `referenceBounds` 是首次分析冻结的原图可见目标。构图契约的 DOM `bounds` 只是含透明留白的图片外框；两者必须分开保存。不能修改目标宽高来迁就生成图，也不能以 DOM 符合反算结果声称原图比例通过。

生成前，在既有资源准备中为独立前景裁切原图局部输入，保留完整轮廓和必要上下文。使用清理/去字/补全遮挡的提示词，明确保留外轮廓、标题牌等固有结构和主色；不要重新设计。把输入路径、SHA、裁切范围保存在冻结计划旁的 `generation-inputs.json`，与原资源 ID 对应。实验稳定性比较仍必须固定同一输入，不混用局部输入与整页输入宣称同条件。

提示词中的画布尺寸并非模型的硬几何约束。输出画布比例不符不直接判失败；检查其中真正可见的主体：

```bash
python3 scripts/measure_alpha_bbox.py <asset.png> \
  --plan <delivery-generation-plan.json> --asset-id <resource-id> \
  > <resource-id-geometry.json>
```

该命令从冻结计划读取目标及锁定轴，拒绝命令行覆盖；同时保存计划/图片 SHA、等比布局解、像素偏差、百分比和有效倍率，不自动给视觉通过。不要通过提高 Alpha 阈值忽略真实边缘。复用既有联系表与最终整页预览：

- 约 3% 以内通常较小；3%–5% 或超过 4px 提醒关注；超过 5% 优先排查。这些仅为注意力提示。
- 矮条多约 3px 即使超过 5%，正常尺寸不显著仍可 warning；大面板少约 20px 即使不到 5%，明显改变留白仍须修正。不得把这些样例固化为通用豁免。
- 不得拉伸人物、角花、金属边来凑数值；整体比例、锚点、内容容纳和重叠关系必须正常。

## 受控纠正

仅普通 `delivery`：图片素材在最终正常尺寸下出现明显比例、整体颜色错误，或严重 Alpha 失败，且无法通过安全布局或同一文件的可靠局部处理解决、已有明确纠正方向时，默认只对失败视觉原子追加一次图片生成/重型编辑，无需再次询问用户。每个原子的首次生成与所有类型的纠正合计最多两次；换失败原因、色键、通道或任务版本不重置次数，其他合格资源不重做。

严重 Alpha 失败指：主体不透明区域被误删而透底、出现非真实镂空或结构缺口，或正常尺寸下可见的烘焙底色、明显色边/光晕；须由原始生成文件与蒙版、深浅底或实际页面对照确认，不能仅凭脚本数值或 Alpha 外框判定。局部问题能可靠修复时先修同一文件；仅放大可见且不伤结构的轻微差异不重生。确认是色键冲突时，重新按[实际提取色域](alpha-extraction.md#生成前选色)检查受保护颜色，更换安全色键后生成并提取；没有可说明的安全替代或纠正方向时保留失败证据并停止，不盲试。原始生成图本身缺失主体、分辨率不足等其他失败仍按原异常规则处理，不借此扩大重试范围。

纠正前保存失败证据和原因，在当前任务下一版本冻结 `correction-plan.json`：原计划路径及 SHA、资源 ID、未改变的原图 `referenceBounds`、实际输入路径及 SHA、纠正提示词及 SHA、已有/本次调用序号、开始结束时间。Alpha 纠正还记录失败类型、原始生成图与蒙版/合成证据路径及 SHA、同文件修复不可行的依据、旧/新色键及按实际提取色域完成的冲突检查；只在 Alpha 失败时补这些字段，不增加正常路径的独立检查轮次。只纠正已确认的问题；不改路由、不覆盖原图目标、不批量产生候选。输入仍使用原图局部参考，保持安全色键和有效像素要求。

纠正后重做该资源 Alpha/比例与受影响最终检查。仍明显不符就交付诊断并停止，不产生第三次调用。修正文字颜色等 HTML 内容同样使旧审批失效。`rule-regression` 不生图；`fresh-generation-stability` 仍保持一次调用，不能用纠正结果冒充首次稳定性。

## 锚点与比例

`anchor.horizontal` 支持 `left / center / right`，`anchor.vertical` 支持 `top / center / bottom`。未显式填写 `offsetX/offsetY` 时，检查脚本会根据 `bounds` 推导目标偏移；因此人物可以故意超出底边，只要其负的 bottom offset 与契约一致。

`aspectPolicy` 支持：

- `intrinsic`：图片显示宽高比必须与 `naturalWidth/naturalHeight` 一致；
- `locked`：按 `expectedAspectRatio` 或 `bounds.width/bounds.height` 检查；
- `cover`：只用于允许裁切纯场景边缘的背景 `<img>`；元素边界仍必须精确等于画布，脚本验证 `object-fit: cover`，不要求素材原始宽高比与画布完全一致；
- `flexible`：不做比例检查，只适用于明确可拉伸的纯色/渐变几何，不能用于人物、IP、奖章、画框或背景图片。

参考图和目标画布比例不同时：

1. 先锁定目标画布；
2. 保持人物、IP、完整画框和主面板自身比例；
3. 保持中心、边角或相对容器锚点；
4. 只延展/裁切纯场景背景，或调整空白和模块间距；
5. 不拉伸整个参考图，不复制主体填空，不把人物移入不对应的角落。

## 主体数量与形状不变量

同类人物、头像、商品或卡片用一个 selector 加精确 `count`。数量不一致直接失败。生成结果中出现额外人物、重复脸、邻近画框、原截图背景或相邻 UI，不得通过遮罩隐藏后继续。

气泡、牌板、标签等轮廓除 `bounds` 外，还要在 `shapeInvariants` 记录方向、连接点、凹口/切角、描边层数和轮廓比例。机器可检查的部分写进 `attributes`；仍需视觉判断的部分用最终综合截图核对。最终需要 Vector/Line 编辑的几何必须用显式 SVG/path/line 表达，不能只存在于伪元素或 `clip-path`。

## 运行时检查

源 HTML 在唯一 HTTP URL、目标尺寸加载并通过静态预检后运行：

```bash
node scripts/check_composition.mjs \
  http://127.0.0.1:<port>/<unique-path>.html \
  /absolute/path/to/composition-contract.json \
  --mode delivery \
  --output /absolute/path/to/composition-report.json
```

脚本使用隔离的临时 Chrome profile，通过真实 DOM 检查 canvas 尺寸、元素数量、可见性、边界、锚点、比例、`z-index`、必需属性、字体、颜色和资源隔离，不依赖 Playwright。普通交付使用 `--mode delivery`：数量、可见性、层级、必需属性、资源/字体加载和颜色不匹配仍进入 `errors` 并禁止 Capture；纯边界、锚点和比例数值越界进入 `warnings`，由同一次 `100%` 最终截图确认是否存在可见问题。实验模式省略该参数并保持 strict。脚本通过后仍要对照参考图确认契约没有量错，尤其检查 alpha 可见边界、遮挡和形状轮廓。

所有任务都在 HTML、离线版、构图报告和最终截图完成后进入主 Skill 定义的“HTML 审批门”。收到明确确认当前文件指纹并授权导入 Figma 的审批前不得创建 Capture ID、新建或写入 Figma；用户提出修改时更新当前 HTML、重新运行本检查并重新请求审批。

## Figma 终检

Capture 后沿用同一契约：

- `IMAGE` → 叶子 Rectangle + IMAGE fill；
- `RECTANGLE` → Rectangle；`ELLIPSE` → Ellipse；
- `VECTOR` → Vector；`LINE` → Line；
- `TEXT` → Text；`INSTANCE` → 可追溯组件 Instance；
- `FRAME/GROUP` 只在契约明确需要相应职责时保留。

逐项核对数量、节点类型、边界和锚点。规范化不得改变已通过的 HTML 构图；最终截图还要人工核对尾巴方向、描边层数、遮挡和透明主体内部完整性。
