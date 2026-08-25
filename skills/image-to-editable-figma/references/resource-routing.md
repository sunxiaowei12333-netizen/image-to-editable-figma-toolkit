# 资源类型路由硬门槛

每个新任务在生成素材或编写 HTML 前完整读取本文件。目标是把“复杂视觉原子用图片、简单 UI 用原生节点”变成可复核的资源决策，同时避免把普通按钮、卡片和表单过度位图化。

## 1. 先建立完整清单

计算每张参考图文件的 SHA-256，并在任务版本目录创建 `resource-manifest.json`。单张参考图使用示例中的 `reference`；多张参考图改用由同结构对象组成的非空 `references` 数组。清单覆盖纯场景背景，以及背景上方每个可独立隐藏或替换的前景视觉原子；高视觉权重对象不得因尺寸小、风格扁平或生成困难而遗漏。可编辑文字、标准 UI 图标和普通布局容器不必逐项写入图片清单，但它们仍按主 Skill 的 Text / Instance / Rectangle / Frame 规则交付。

使用以下结构：

```json
{
  "schemaVersion": 3,
  "generationPolicy": {
    "scope": "per-visual-atom",
    "defaultHighQualityCallsPerAtom": 1,
    "pageWideCap": null
  },
  "reference": {
    "path": "/absolute/path/reference.png",
    "sha256": "64位小写十六进制"
  },
  "assets": [
    {
      "id": "summary-frame",
      "kind": "complex-frame",
      "compositionId": "summary-frame",
      "selector": "[data-resource-id='summary-frame']",
      "editableInternals": false,
      "complexitySignals": ["material_edges", "precise_highlight_shadow"],
      "expectedFigmaType": "IMAGE",
      "sourceMethod": "reference-guided-edit",
      "fallbacks": [
        {"method": "targeted-image-edit", "figmaType": "IMAGE"}
      ]
    }
  ]
}
```

每个资源必须在 HTML 的唯一视觉节点上写入同名 `data-resource-id`。图片还必须是直接 `<img data-figma-node-type="IMAGE">`；不得用只负责承载图片的包装节点。

`generationPolicy` 用来消除数量歧义：`1` 次默认调用限制的是同一视觉原子的无效候选和重复尝试，`pageWideCap` 必须为 `null`。先完整判断页面需要多少独立视觉原子，再据此确定时间等级；不得先设整页生成上限再反向把资源改成裁切、抠图或简单几何。

## 2. 取得方法与复用证据

`sourceMethod` 必须使用以下规范值之一：

- `provided-original`：用户提供的独立原始素材；
- `clean-crop`：从参考图无损裁切边界完整的矩形内容；
- `reliable-separation`：从合成图可靠分离非矩形视觉原子；
- `localized-repair`：只修补遮挡或缺失局部，仍输出完整图片原子；
- `reference-guided-edit`：以参考图编辑/重建完整视觉原子；
- `new-generation`：从零生成新的完整图片资源；
- `native-rebuild`：用原生形状、Text 或已批准的 Vector 重建简单元素；
- `library-asset`：使用 Hugeicons 等已要求的库资源。

选择 `clean-crop` 时，资源项必须加入：

```json
"reuseEvidence": {
  "completeVisibleBounds": true,
  "noOcclusion": true,
  "noBakedUiTextOrAdjacentContent": true,
  "effectiveResolutionAtLeast2x": true,
  "inspectionNote": "矩形媒体边界完整，未烘焙卡片描边或状态 UI"
}
```

选择 `reliable-separation` 时，除上述字段外还必须全部为 true：

```json
"hardEdgesOnly": true,
"backgroundClearlySeparable": true,
"noFragileEdgeFeatures": true
```

任一必需布尔值为 false、字段缺失或 `inspectionNote` 为空，都说明当前方法没有足够证据，资源计划预检必须失败并改用清单中更可靠的图片方法。复杂度信号本身不意味着一律生成：如果独立原始素材或裁切/分离证据确实全部成立，仍可复用；但“节省时间、控制生成数量、先做出来看看”不能代替证据。

资源清单写完后、生成素材或编写 HTML 前运行：

```bash
python3 scripts/preflight_resource_plan.py <resource-manifest.json>
```

通过后再执行资源生成。该预检不判断最终视觉质量；资源落盘后仍按主 Skill 完成分辨率、Alpha、材质和 `100%`/`200%` 检查。

## 3. 窄范围强制图片类型

以下 `kind` 默认必须为 `IMAGE`：

- `pure-scene-background`
- `complete-character`
- `person`
- `complex-frame`
- `complex-decoration`
- `standalone-illustration`
- `photo`
- `product-object`
- `material-object`

出现以下任一证据时，完整视觉原子不得标成 `simple-decoration`，而应选择上面最接近的图片类型：

- `irregular_parts`：多个不规则固有部件
- `texture_or_noise`：纹理、纸张纤维、颗粒或噪点
- `material_edges`：木材、金属、玻璃、布料、撕纸等材质边缘
- `precise_highlight_shadow`：精细高光、阴影或立体层次
- `translucency_or_glow`：半透明、玻璃、发光或复杂混合
- `dense_paths`：需要密集路径才能表达
- `recognizable_complete_illustration`：狐狸、花朵、人物、物件等可整体识别和替换的完整插画

对象很小或画风扁平都不能抵消上述证据。`simple-decoration` 仅限没有这些复杂度信号、能用少量基础路径高保真表达的非 UI 装饰。规则按钮、输入框、普通卡片、胶囊、标签和其他 `ui-container` 继续使用 Rectangle / Vector / Text / Auto Layout，不因阴影或渐变自动位图化；若 UI 外壳本身是复杂材质画框，拆为一个 `complex-frame` 图片和独立的内部 UI。

只有两类证据允许把默认图片类型改为 Vector/Group：

1. 用户明确要求编辑该视觉原子的内部结构；
2. 用户提供或当前任务可验证取得了可靠分层的原始矢量源文件。

此时在资源项加入：

```json
"routingException": {
  "type": "user_requires_internal_editing",
  "evidence": "用户当前任务中的明确要求"
}
```

或使用 `verified_layered_vector_source`。时间、生成次数、分辨率失败、透明底失败、对象尺寸小、风格扁平，以及“看起来也能用 SVG 画”都不是例外理由。

## 4. 图片失败不能改变语义类型

资源清单一旦把对象确定为 `IMAGE`，后续只能切换图片取得方法：独立原始素材、干净裁切、可靠透明提取、局部修补、参考图图片编辑或重新生成。每个 `fallbacks[].figmaType` 必须仍为 `IMAGE`。

若所有合规图片方案都失败，保留失败证据并报告阻塞；不得把 `expectedFigmaType` 改成 VECTOR/RECTANGLE，不得用 CSS、内联 SVG 或近似几何静默交付。

## 5. 精确相同参考图的决策复用

新任务仍创建独立目录，不复制或覆盖历史 HTML、CSS、图片和 Figma 节点。若当前对话明确提供了一个已通过用户审批的历史 `resource-manifest.json`，或当前输出根目录存在按精确 SHA-256 建立的可信决策索引，并且参考图 SHA-256 完全相同，可以复用其中的 `kind / complexitySignals / expectedFigmaType` 作为硬证据；素材文件、布局数值和生成结果仍在当前任务独立产生并重新验收。

不得按文件名、视觉相似度或模板猜测自动复用，也不得为寻找候选而扫描任意历史 HTML 和资源目录。相似但哈希不同的设计最多把历史分类作为人工参考，必须按当前画面重新确认。

## 6. Capture 前验证

源版和离线版都运行：

```bash
python3 scripts/preflight_html.py <html> \
  --manifest <resource-manifest.json> \
  --contract <composition-contract.json>
```

必须满足：

- 参考图路径与 SHA-256 一致；
- `generationPolicy` 明确按单个视觉原子限制重复调用，不存在整页生成数量上限；
- `sourceMethod` 使用规范值，裁切/分离路由的 `reuseEvidence` 全部通过；
- 资源 ID 唯一，HTML 中每项恰有预期数量的 `data-resource-id`；
- `IMAGE` 对应直接 `<img>`，DOM 节点类型与 `expectedFigmaType` 一致；
- 默认图片类型和复杂度信号没有被降级；
- 图片资源的所有 fallback 仍返回 `IMAGE`；
- `compositionId` 在构图契约中存在，且契约的 `figmaType` 与资源清单一致；
- 构图契约中显式声明 `resourceId` 的对象没有从资源清单遗漏。

任一项失败都先回到资源规划或 HTML 修正，不进入审批门或 Figma Capture。
