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

## 锚点与比例

`anchor.horizontal` 支持 `left / center / right`，`anchor.vertical` 支持 `top / center / bottom`。未显式填写 `offsetX/offsetY` 时，检查脚本会根据 `bounds` 推导目标偏移；因此人物可以故意超出底边，只要其负的 bottom offset 与契约一致。

`aspectPolicy` 支持：

- `intrinsic`：图片显示宽高比必须与 `naturalWidth/naturalHeight` 一致；
- `locked`：按 `expectedAspectRatio` 或 `bounds.width/bounds.height` 检查；
- `flexible`：不做比例检查，只适用于明确可拉伸的纯色/渐变几何。

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
  --output /absolute/path/to/composition-report.json
```

脚本使用隔离的临时 Chrome profile，通过真实 DOM 检查 canvas 尺寸、元素数量、可见性、边界、锚点、比例、`z-index` 和必需属性，不依赖 Playwright。`errors` 非空时禁止 Capture。脚本通过后仍要对照参考图确认契约没有量错，尤其检查 alpha 可见边界、遮挡和形状轮廓。

所有任务都在 HTML、离线版、构图报告和最终截图完成后进入主 Skill 定义的“HTML 审批门”。收到明确确认当前文件指纹并授权导入 Figma 的审批前不得创建 Capture ID、新建或写入 Figma；用户提出修改时更新当前 HTML、重新运行本检查并重新请求审批。

## Figma 终检

Capture 后沿用同一契约：

- `IMAGE` → 叶子 Rectangle + IMAGE fill；
- `RECTANGLE` → Rectangle；`ELLIPSE` → Ellipse；
- `VECTOR` → Vector；`LINE` → Line；
- `TEXT` → Text；`INSTANCE` → 可追溯组件 Instance；
- `FRAME/GROUP` 只在契约明确需要相应职责时保留。

逐项核对数量、节点类型、边界和锚点。规范化不得改变已通过的 HTML 构图；最终截图还要人工核对尾巴方向、描边层数、遮挡和透明主体内部完整性。
