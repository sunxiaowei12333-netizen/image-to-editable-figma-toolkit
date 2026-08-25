# Figma Capture 后规范化

仅在 Capture 已完成、目标根节点已确定后使用。只处理本次 Capture 返回的子树；写入前记录目标根节点 ID、父级、子节点顺序、画布尺寸和一张规范化前截图。结构正确且字体指纹一致时不要为了套流程重建节点。

## 字体三阶段指纹与原生 Auto 受控替换

对 Capture 后不符合 DOM 指纹、或用户进入编辑态后发生字形/字宽/换行变化的字体，每种实际 `family/style` 先选一个代表 Text；同一字体存在多种字号、固定宽正文和自动宽标题时，各选择一个布局角色。`lineHeight=AUTO`、面板字体名正确和 `hasMissingFont=false` 都不能单独证明节点已经使用 Figma 原生文字几何。

1. 读取 Capture 前 DOM 的 `family/style/weight`、字符、显式换行、宽高、行数、对齐、字距和父容器边界。
2. 读取导入 Text 的 `fontName`、`fontSize`、`lineHeight`、`letterSpacing`、`textAutoResize`、宽高、`hasMissingFont`，并在任何写入前保存 `getStyledTextSegments()` 的全部 range、fills、字重和其他混排样式。
3. 只有当前 Figma 执行环境可 `loadFontAsync()` 加载所有目标 range 字体时，创建一个不继承导入样式或变量绑定的临时 fresh Text。先加载字体并设置字符和字号，再逐 range 恢复字体、fills 与样式；行高设为 `AUTO`，源设计没有特殊字距时设为 `0`。固定宽正文先固定宽度并使用 `textAutoResize="HEIGHT"`；显式换行或单行自动宽文本使用 `WIDTH_AND_HEIGHT`。读取自然尺寸后在同一调用内删除临时节点。

判定时区分“内容/换行稳定”与“浏览器、Figma 两套引擎的自然盒子差异”：

- 字形类别、笔画形态、实际字重、字符、显式换行和行数必须与 DOM/参考图一致；
- 固定宽正文必须保持既定宽度、换行和可见内容，仅允许高度随 Figma Auto 增长；
- 单行或显式换行的自动宽文本允许使用 Figma Auto 的自然宽高，不要求强行回到浏览器盒子的 `1px` 容差；必须记录差值，并通过父容器、视觉锚点和最终截图保证无裁切、重叠或明显位移；
- fresh Text 与导入 Text 自然尺寸一致时保留导入节点；两者不一致时，即使 `hasMissingFont=false`，也把导入节点视为保留了浏览器旧几何，不在旧节点上反复重设属性。

需要替换时，为每个受影响 Text 新建无绑定的原生 Text，复制字符、语义名、fills、opacity、effects、对齐、约束、父级与子节点索引，逐 range 恢复字体、字号、颜色和强调样式，并设置 `lineHeight=AUTO`、源设计实际字距及正确 `textAutoResize`。父级是 Auto Layout 时保留 `layoutAlign/layoutGrow` 与原索引，让 Hug/Fixed/Fill 吸收新尺寸；父级是普通叠层时，以旧文字盒的中心、左边或设计契约指定锚点重新计算 `x/y`。确认新节点无裁切、无越界并完成截图后再删除旧节点。

禁止在正式混排 Text 上执行 `text.characters = text.characters`、整段重新赋值或整节点 `fontName/fills` 作为编辑态测试；部分 Figma 执行环境会把全部 range 合并成首段样式。普通单一样式 Text 可以用同内容回写验证几何稳定；混排 Text 只审计 range、字体、Auto 行高、边界与截图，或在临时节点上测试并立即删除。若测试误改混排，必须按写入前保存的 range 精确恢复，再重新截图。

Capture 将 `<br>`、内联强调或文本旁的 Shape 拆成多个 Text 时，同时检查字符顺序、重复字符和绝对位置；若出现重叠、遗漏或标点错位，只按已审批 HTML 的源语义拆分/重建对应 fresh Text 和 Shape，不改文案，不借此重新设计布局。

默认 `letterSpacing=0`。只有源设计本身存在非零 tracking 或用户明确要求时才保留/设置相应值；不得用负字距、固定行高、字号变化或缩放补偿把 Figma 原生 Auto Text 强行压回浏览器盒子。无头环境不能可靠加载目标字体时，只读比较已导入 Text 的实际名称、字形、宽高、换行和基线；已有可靠正确证据时不改字、不重排、不替换。

## 确定性节点转换顺序

在同一目标子树按以下顺序转换；开始前读取本任务的 `composition-contract.json`，后续用其中的 `figmaType`、数量、锚点和边界作为逐项验收依据。每次重建都保留父级子节点索引、绝对位置、尺寸、旋转、透明度、混合模式、fills、strokes、effects、圆角和约束。处于 Auto Layout 中的绝对叠层还要恢复 `layoutPositioning="ABSOLUTE"`，重挂父级时显式换算相对坐标。

1. 根 Frame 的正确场景 `IMAGE` fill：新建同尺寸叶子 Rectangle，复制 IMAGE fill，命名为背景语义并插入为第一个/最底层子节点，再清空根 fill。
2. 无子节点、无容器职责且带 `IMAGE` fill 的 Frame：在同一父级和索引重建为叶子 Rectangle 图片层。
3. 无子节点、无职责的纯视觉 Frame：规则矩形重建为 Rectangle，圆形/椭圆重建为 Ellipse；不规则轮廓才使用 Vector。
4. 契约 `figmaType="LINE"` 或 HTML 标记 `data-figma-node-type="LINE"` 的直线：按 DOM 起终点、描边、透明度和端点样式重建为 Figma Line；不得保留为零高度 Frame、窄 Rectangle 或文字下划线伪装。
5. 契约 `figmaType="VECTOR"` 的高视觉权重不规则形状：优先沿用显式 SVG/path 几何，以 `vectorPaths` 或 SVG 导入重建，并删除仅用于导入的包装层。气泡尾巴、凹口和切角必须核对方向、连接位置、描边层数和与底板的遮挡关系；不得把 Capture 生成的矩形伪元素或 `clip-path` 外框直接交付。
6. 需要保留的真实容器若自身承担 fill/stroke/effect：将可见外观提取为容器内最底层的 Shape，容器自身保持透明，只负责 Auto Layout、叠层、裁切、滚动、响应式或交互。
7. UI 图标 Frame/SVG：按 HTML 的库名称和几何建立或复用正确主组件，以 Instance 替换；普通 Vector 只存在于图标主组件内部。
8. 仅包裹一个 Text 的 Frame：只有确认其没有 padding、gap、对齐、裁切、响应式、交互或定位职责时才解包；保留可见外观或职责时不得为了减少 Frame 强拆。

若转换改变了可见像素，立即撤销该项或根据记录恢复布局属性；不得用新的视觉偏差换取节点类型计数通过。容器仅为消除 Auto Layout 越界而做不可见宽度调整时，也要确认不会移动、拉伸或裁切任何可见子节点。

## 批次与验收

推荐把写操作压缩为三个有依赖顺序的批次：图片/Shape 与容器外观、可安全重排的字体、图标/解包与最终清理。每个批次返回创建、替换和删除的节点 ID；发生错误先读取部分修改状态，不盲目重放整批。

正常路径保留三张综合证据：HTML 最终截图、Capture 后规范化前截图、Figma 最终截图。只有转换可能影响可见像素、最终差异明显或结构审计失败时才增加局部截图；字体临时候选不建候选页、不留测试节点。

最终必须同时满足：

- 根节点尺寸等于标准画布；背景为首个/最底层叶子 Rectangle 图片层，根节点无 image fill；
- 带 IMAGE fill 的无职责 Frame、无职责叶子 Frame、纯样式 Frame 均为 `0`；
- 规则矩形底板为 Rectangle，UI 图标为可追溯的 Instance；
- 构图契约中的每项对象数量与 `figmaType` 完全匹配；LINE 不得退化为 Frame/Rectangle，气泡尾巴等 VECTOR 的方向、位置和轮廓不变量保持一致；
- Figma 节点边界与已通过的 HTML 构图报告处于契约容差内，中心/边角锚点和锁定比例没有因规范化改变；
- 每个保留 Frame 都能说明布局、叠层、裁切、滚动、响应式、交互或根画布职责；
- Auto Layout 直接子节点越界为 `0`；
- 代表 Text 的字形、实际字重、字符和行数/换行与 DOM 一致；固定宽正文保持宽度与换行，自动宽/显式换行 Text 使用 Figma 原生 Auto 自然宽高并保持视觉锚点、无裁切或重叠；所有可安全重排的 range 均为真实字体、`lineHeight=AUTO` 和源设计实际字距，不能安全加载的已验证本机字体保持只读；
- 最终截图与已验收 HTML 在背景覆盖、前景 Alpha、文本、图标、按钮、卡片和层级上无可见退化。
