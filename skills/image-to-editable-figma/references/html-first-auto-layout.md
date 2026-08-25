# HTML-first Auto Layout V2

在新任务的 HTML 实现阶段读取本文件。旧任务若根画布没有
`data-figma-layout-version="2"`，保持原结构，不自动迁移。

## 启用方式

1. 将 `assets/semantic-layout.css` 复制到当前任务自己的资源目录，禁止直接链接 Skill 中的共享文件。
2. 在根画布写入 V2 标记，并将纯背景保持为第一个直接子节点：

```html
<main id="canvas"
  class="f-viewport"
  data-figma-layout-version="2"
  data-figma-layout="viewport"
  data-figma-width="fixed"
  data-figma-height="fixed">
  <img class="f-bg-layer"
    data-resource-id="pure-scene-background"
    data-figma-node-type="IMAGE"
    src="assets/background.png"
    alt="背景/纯场景背景">
</main>
```

3. 为每个真实容器选择布局与横纵向尺寸语义：

| 语义 | HTML | Figma 目标 |
| --- | --- | --- |
| `row` | `f-row` | 横向 Auto Layout |
| `column` | `f-column` | 纵向 Auto Layout |
| `wrap` | `f-wrap` | 横向 Auto Layout + Wrap |
| `overlay` | `f-overlay`，叠层子节点使用 `f-absolute` | 普通叠层 Frame |
| `viewport` | `f-viewport` | 根画布、裁切或滚动视口 |

每个带 `data-figma-layout` 的节点同时声明：

```text
data-figma-width="fixed|hug|fill"
data-figma-height="fixed|hug|fill"
```

## 生成规则

- 卡片内容、标题行、统计行、资料信息、进度行和标签组优先使用 `row`、`column` 或 `wrap`。
- 用 `gap` 表达同级间距，用 `padding` 表达容器内边距；不要用子节点 `left/top` 或空白节点模拟。
- 需要精确还原固定稿时，可在 Flex 容器和子节点上保留明确宽高；使用 Flex 不等于强制响应式。
- 背景、人物、装饰底纹、星星、角标、轨道填充和其他真实重叠关系使用 `overlay`/`f-absolute`。
- 图片、图标和不应被压缩的固定元素使用 `f-fixed`；UI 图标同时使用 `f-icon` 并明确 `--figma-icon-size`。
- 可伸缩的中间区域使用 `f-fill` 和 `min-width: 0`；不要让文本或图片依赖浏览器默认 shrink。
- 可见底板继续作为独立 Rectangle 语义节点；Auto Layout 容器保持透明，不用容器 fill 代替底板。
- 页面原有交互绑定在语义元素上，不因布局重构增加透明包装层或改变事件目标。

## 常用结构

```html
<div class="f-row progress-row"
  data-figma-layout="row"
  data-figma-width="fill"
  data-figma-height="hug">
  <span class="f-fixed">已掌握</span>
  <div class="f-overlay f-fill"
    data-figma-layout="overlay"
    data-figma-width="fill"
    data-figma-height="fixed">
    <div class="track"></div>
    <div class="fill f-absolute"></div>
  </div>
  <span class="f-fixed">15 个</span>
</div>
```

标签列表使用 `f-wrap`，每个标签使用 `f-fixed`；不要按截图行数拆成多个无语义行容器。

## Capture 与终检

- Capture 前运行 `scripts/preflight_html.py <html> --manifest <resource-manifest.json> --contract <composition-contract.json>`；V2 的资源路由、布局标记、模板类、尺寸语义和图标固定尺寸不正确时先修 HTML。
- 在同一目标尺寸页面运行 `scripts/check_composition.mjs <URL> <composition-contract.json>`；数量、锚点、边界、锁定比例、层级或必需属性出现 error 时禁止 Capture。脚本通过后仍需对照参考图核对契约本身是否量错。
- Capture 后只处理返回的目标子树。先记录候选容器和子节点的宽高，再将 `row/column/wrap` 规范化为 Auto Layout。
- 装饰底板和叠层子节点在 Auto Layout 中设为绝对定位；不要把轨道填充、插画叠层强行改成流式排列。
- 每个模块规范化后恢复其 Fixed/Hug/Fill 语义，并检查子节点越界、文本换行、图标尺寸和整体截图。
- 最终要求：应为 Auto Layout 的容器中 `layoutMode=NONE` 数量为 0；Auto Layout 子节点越界数量为 0；所有保留的非 Auto Layout Frame 都有明确叠层、裁切、滚动或交互职责。
