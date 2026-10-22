# 猿辅导学生端 App 基础规范 Profile

本 Profile 是本 Skill 每次执行必读的固定目标库配置。调用本 Skill 即使用「【规范和组件】猿辅导学生端App」，无需用户重复指定或确认。第一阶段只使用本文已缓存的静态视觉值、字体表、按钮尺寸说明和圆角映射，不导入、搜索或验证发布资产；第二阶段开始才验证本 Profile 的发布 key 能否导入及资产类型是否一致。此 Profile 的文字发布资产映射与排版属性最后批量验证于 2026-09-15。

## 定位信息

- 组件库文件 key：`A0R5sjaWBJXXWYqt9055ug`
- 发布库名称：`【规范和组件】猿辅导学生端App`
- 发布 library key：`lk-206cbab5e277f8e22a1cf0d35a9f8d1217709e893ce3b790473c157cfd1e271cef4e1ecc526073f2c3bfacfaef5de329ec86c4e863e5261e9807ae2611c86cfc`
- 颜色规范节点：[`171130:773`](https://www.figma.com/design/A0R5sjaWBJXXWYqt9055ug/?node-id=171130-773)
- 字体字号规范节点：[`105676:7192`](https://www.figma.com/design/A0R5sjaWBJXXWYqt9055ug/?node-id=105676-7192)
- 按钮规范节点：[`95903:225`](https://www.figma.com/design/A0R5sjaWBJXXWYqt9055ug/?node-id=95903-225)

以上三个链接是固定规范入口，不依赖用户再次提供。搜索必须用发布 library key 限定，不能混用 `UI仓库.fig` 或跟课端库中的同名资产。

## Paint Style

静态色板包含用户于 2026-09-18 提供的规范截图中的 24 项：品牌色 1 项、辅助色 5 项、衍生色 9 项、中性色（含白色）9 项。新增项的名称、色值和用途来自截图；`未缓存` 表示尚未读取真实发布 key，不是不存在发布资产。第一阶段可直接使用这些静态值；第二阶段需要联动时，再限定目标 library key 搜索并核验，不能把名称或截图当作发布身份验证。渐变端点来自截图，方向、色标位置和透明度尚未完整缓存。

| 用途 | Style 名称 | 发布 key | 真实值 |
| --- | --- | --- | --- |
| 品牌强调、主按钮、主要图标 | 品牌及辅助色/Color_Orange_01 | `62ffa13327093d6abb4bba304013a720d4f38d73` | `#FF7400` |
| 金刚位图标 | Color_Yellow_01 | 未缓存 | `#FFB122` |
| 金刚位图标 | Color_Yellow_02 | 未缓存 | `#F8E966` |
| 金刚位图标 | Color_Blue_01 | 未缓存 | `#48A5FF` |
| 金刚位图标、成功状态 | Color_Green_01 | 未缓存 | `#25CA7B` |
| 失败、警告、提醒 | Color_Red_01 | 未缓存 | `#FF3939` |
| 橙色模块背景 | 衍生色/Color_Orange_02 | `18236d0f9c19158716a80d74a9182d3487de2460` | `#FFD5B3` |
| 浅橙模块/页面背景、错误选项背景 | 衍生色/Color_Orange_03 | `bad5594b4eb89f7bcda5e5adb45d19f60826ed75` | `#FFF3EB` |
| 模块背景、选项选中背景 | Color_Yellow_03 | 未缓存 | `#FFFAEA` |
| 模块背景、正确选项背景 | Color_Green_02 | 未缓存 | `#F0F9EF` |
| 模块背景 | Color_Blue_02 | 未缓存 | `#EBF7FF` |
| 主按钮正常渐变 | 衍生色/Color_OrangeGradient_01 | `5375579d935354388f41c4373807b47df40fc6a8` | `#FF9714 → #FF7400`（仅端点） |
| 主按钮点击渐变 | 衍生色/Color_OrangeGradient_02 | `95c0f49721a610a5e08829084de00e6e3554e11f` | `#EB8B12 → #EB6B00`（仅端点） |
| 新消息、气泡提示 | Color_RedGradient_01 | 未缓存 | `#FF3939 → #FF7400`（仅端点） |
| 预告标签 | Color_GreenGradient_01 | 未缓存 | `#25CA7B → #00BC63`（仅端点） |
| 标题 | 中性色/Color_Gray_01 | `e5c1cd8b5f6d42cf678d2c399f3357a4dd52b84d` | `#222222` |
| 正文 | 中性色/Color_Gray_02 | `7f487ea07b47df1c08a4ee889c51c40405dc1364` | `#333333` |
| 深说明文字 | 中性色/Color_Gray_03 | `c9005216bba343cd95fe72a1accfe54ffe66e4b0` | `#666666` |
| 说明文字 | 中性色/Color_Gray_04 | `7accb2297453f8ea000989263292725fa313acab` | `#999999` |
| 弱说明文字 | 中性色/Color_Gray_05 | `20e84095a632d79124a8cc01ad4b13475da2fec7` | `#CCCCCC` |
| 边框 | 中性色/Color_Gray_06 | `87a3bb3d788b84ef4bc01de5dd7e1cf27954d7e7` | `#E5E5E5` |
| 模块背景 | 中性色/Color_Gray_07 | `742bf7e27bbf43ae79dae8819033773a1b0691bf` | `#F4F4F4` |
| 页面背景、分割线 | 中性色/Color_Gray_08 | `0b7a7fcf0594ac92457df5e975783a18386cafbd` | `#F8F8F8` |
| 白色背景、反白图标、按钮文字 | 中性色/Color_White | `fdfafa90674c65562dbf200fcbcfe2966f82cd16` | `#FFFFFF` |

### 第一阶段接近颜色归一化

用户已授权第一阶段把接近规范色的实际颜色调整为最近的规范色，不再要求原色与规范色完全相等，也不为每个近似色再次询问。只在目标稿的 `processingRootIds` 内处理可见文字区间及界面 Fill/Stroke；复用正常 Paint 预检，不读取实时组件库。

1. **先用途，后色差。** 根据实际内容、位置和状态区分品牌强调、功能提示、文字、边框、模块/页面背景等，筛选上表中用途相容的候选；功能色不能跨成功/失败语义替换，边框/背景灰不能用于文字。多种色相都适用的图标或模块背景，再由色差决定。已有规范色且用途相容时保持；黑灰文字优先执行下一节的专用规则。
2. **最近色的默认判定。** 对可见、不透明、正常混合模式的 `SOLID`，将 sRGB 转为 CIELAB（D65），用 CIEDE2000 色差 `ΔE00` 排序，选择用途相容候选中差值最小者。默认 `ΔE00 <= 10` 视为接近；这是本 Skill 的执行阈值，不是截图中的组件库标准。超过阈值、用途无法可靠判断或存在同色差且语义不同的候选时，保留并记录原因，不能因为总能找到一个最近色就强行替换。用户明确指定颜色或阈值时以用户要求为准。
3. **保留 Paint 结构。** 混合文字逐区间处理；不合并多层 Paint，不清除透明度或改变混合模式。半透明色、图片填充、插画素材、特殊装饰叠加色保留。渐变当前仅缓存端点，第一阶段不凭端点推断方向/位置/透明度，也不把渐变压成纯色；保留并列为第二阶段候选。以后只有完整参数已获确认时，才能在相同用途及渐变结构内逐色标比较、保留位置/方向/透明度并替换接近的色值。
4. **记录并验收。** 写入前记录节点/文字区间、用途、原 Paint、目标色名/色值、色差和影响区域；第一阶段只修改实际 Paint，不绑定发布 Style。写入后回读实际 Paint 并验证截图：已记录区域内的颜色变化属于本规则授权修正，区域外及文字几何、换行、尺寸、图标路径不应变化；状态辨识或文字可读性受损时回退对应修改并记录。
5. **保持阶段边界。** 第一阶段处理后的实际 Paint 可在第二阶段按完全等价原则绑定真实发布 Style。若跳过第一阶段，不补做本节的彩色文字或非文字近似色修正；第二阶段仍只保留主 Skill 已单独授权的黑灰文字归一化。

### 文字黑灰色归一化

这是用户预先授权的固定文字字色规则，只作用于主 Skill 的 `processingRootIds` 内可见 Text/文字区间，不处理页面外围标注。按区间读取 Paint；一个 Text 包含混合字色时逐区间判断，不能把整个节点压成单色。

1. 只自动处理 `SOLID`、可见、总透明度为 1、正常混合模式的中性文字 Paint。将 sRGB 通道换算为 0–255 后，`max(R,G,B) - min(R,G,B) <= 8` 才视为中性色；半透明、渐变、图片、彩色/带色偏 Paint 保留原样并走普通语义匹配或颜色例外。
2. **黑色/近黑文字**：满足中性色条件且 `max(R,G,B) <= 51`（`0x33`）时，不选择 `#222222`，统一使用正文色 `中性色/Color_Gray_02`：`#333333`，发布 key `7f487ea07b47df1c08a4ee889c51c40405dc1364`。
3. **其他灰色文字**：满足中性色条件、亮度高于近黑范围且不是白色/反白文字时，在文字用途候选 `Color_Gray_02 #333333`、`Color_Gray_03 #666666`、`Color_Gray_04 #999999`、`Color_Gray_05 #CCCCCC` 中按 CIELAB `L*` 差值选择最近项；等距时选更深的一项以保持可读性。不得把边框/背景用途的 `Gray_06`、`Gray_07`、`Gray_08` 当作文字最近灰色。
4. 第一阶段只按上表写入目标实际 Paint，不绑定 Style；第二阶段导入并绑定对应发布 Paint Style。若用户显式跳过第一阶段，第二阶段可在同一次受控写入中先归一化实际 Paint、再绑定发布 key，这不代表补做了完整第一阶段。
5. 写入后逐区间回读实际 RGBA、`fillStyleId` 对应发布 key 和旧颜色变量绑定，并比较文字所在页面截图。正常的文字颜色差异属于本规则授权变化，文字区域之外仍须保持基线一致。远程实例无法覆盖、写入会破坏混合区间、或目标灰色在实际背景上不可辨认时，回退该区间、登记有证据的颜色例外并继续其他节点，不暂停整轮任务。

第一阶段按上述接近颜色规则修正实际 Paint；黑灰文字的专用规则优先。第二阶段绑定 Style 时仍须实际 Paint 与发布资产完全等价；透明白、透明橙、图片、非等价渐变和装饰叠加色保留原 Paint。

## Text Style

### PingFang SC

| Style 名称 | 字号/字重 | 发布 key |
| --- | --- | --- |
| PingFang SC/H1_CN_Semibold | 32 Semibold | `9725fea8a63d3f7d51c4985199dc3e564b499eef` |
| PingFang SC/H2_CN_Medium | 28 Medium | `efec0569e073cfcd7b3fb37ca886f47a84134d95` |
| PingFang SC/H4_CN_Medium | 24 Medium | `083298b7917468e23bed6ba1cd636743d6c121b8` |
| PingFang SC/H6_CN_Semibold | 20 Semibold | `3a5498d7872952cdf6d89d6fc3bd13e169dd173f` |
| PingFang SC/H6_CN_Medium | 20 Medium | `7768fb72eea65f503812ad4136d6c49a5097e7e6` |
| PingFang SC/H7_CN_Medium | 18 Medium | `f8f0e34fd6f61cbf48bfc2c9962cb86698e770d3` |
| PingFang SC/Body1_CN_Semibold | 16 Semibold | `8d97bb75e55d72e2395fb64d922e823310d91d11` |
| PingFang SC/Body1_CN_Medium | 16 Medium | `4cab994078eaf15b2ca8365a5fffc267c5a395f8` |
| PingFang SC/Body1_CN_Regular | 16 Regular | `e4c71926086c04760e25f1eb4cc5bed0a54339e9` |
| PingFang SC/Body2_CN_Semibold | 14 Semibold | `94f6785b1ca3720073d6be36479b35641d61d043` |
| PingFang SC/Body2_CN_Medium | 14 Medium | `e402fd596bff3fd56c469679f3064050d7b2faba` |
| PingFang SC/Body2_CN_Regular | 14 Regular | `cdb42a74a4d618efdccf66baabba2c37dc8c1ef3` |
| PingFang SC/Caption1_CN_Medium | 13 Medium | `7846d774bbcd065725a787bc8d85627e04fc70e9` |
| PingFang SC/Caption1_CN_Regular | 13 Regular | `2f384eb3a5818231b2f323072bc39382b529cb4d` |
| PingFang SC/Caption2_CN_Semibold | 12 Semibold | `9db669438d710a6f894adaab2a36c0cace6e0999` |
| PingFang SC/Caption2_CN_Medium | 12 Medium | `56f4d6e147e7bc03b6440866fa9cc6f2980b9c4e` |
| PingFang SC/Caption2_CN_Regular | 12 Regular | `115710d4d9ed2a5fa083c2ef8393bdcb94d1c574` |

### D-DIN 数字

| Style 名称 | 字号/字重 | 发布 key |
| --- | --- | --- |
| D-DIN/H8_N_Bold | 48 Bold | `755bb42aa31c33a1dcef1e4cef1cdab2aac3bfc5` |
| D-DIN/H10_N_Bold | 36 Bold | `427dc069ac08091c379ff4ed6da01ca620d45f1b` |
| D-DIN/H2_N_Bold | 28 Bold | `00af7017b8c57ebd3db06a5acb909f6bef79dc89` |
| D-DIN/H4_N_Bold | 24 Bold | `2a85d3c56c8436354ea976b7fe7e1b2de6c022e3` |
| D-DIN/H6_N_Bold | 20 Bold | `ef5a371256c83feb7efbcd999b98a86aab16d4c1` |
| D-DIN/18_DIN_Semibold | 18 Bold | `154319af802db02a4f5e89534f21833e0ff533c5` |
| D-DIN/Body1_N_Bold | 16 Bold | `838564456d08769b18e7594e067b92501b789dd5` |
| D-DIN/Body2_N_Bold | 14 Bold | `7db53559814da4c9dd421a5e7f1c04f2ced434de` |

已验证字体：`PingFang SC Regular/Medium/Semibold`、`D-DIN DIN-Bold`，实际使用时仍核验当前环境。宋体按[宋体必须使用思源宋体](typography-layout-repair.md#宋体必须使用思源宋体)使用真实可加载的思源宋体，优先核验 `Source Han Serif CN`，保留原字重及字号、行高、字距和对齐；禁止改用 PingFang。所需思源宋体字重不可用时报告具体阻塞，不用其他字重凑成功。

2026-09-15 批量只读验证结果：当时缓存的 16 个 PingFang SC 与 7 个 D-DIN 发布 key 均可导入，类型/名称/字体/字号与表中映射一致，行高为 `Auto`，字距为 `0%`。第二阶段若业务稿仍引用旧 Style 版本并返回 `MIXED`，先按原发布 key 导入当前样式，再批量重新绑定；不要把旧版本 `MIXED` 当作当前库仍异常，也不要为消除它单独强写节点字距。当前导入结果与本段不符时，使本段缓存失效并按“固定目标库资产重新发现”处理。

2026-10-20 A-r2 候选复测补充：新增上表 `Caption1_CN_Medium` 与 `H8_N_Bold` 的实际导入验证，分别为 PingFang SC Medium 13px 和 D-DIN DIN-Bold 48px，均为 Auto 行高、0% 字距。检索还返回名称为 `PingFang SC/Caption1_CN_Semibold` 的 key `5e9688a0a6998af8a78b059ca8f10c5950591f74`，但该次实际 `fontName.style` 是 **Medium**；不能把它匹配给 Semibold 文本，也不改写发布库来修正名称。

本表是已验证映射的缓存，不是目标库资产全集。缓存命中可用于正向复用；缓存未命中不能证明不存在等价样式。把未匹配的实际排版组合集中按目标 library key 检索，再比较真实字体、字号、行高、字距等参数，才可登记无等价例外。每次核验保留查询和候选真实值，不能仅凭名称、旧表缺项或空缓存跳过。

## Button Component

按钮规范页存在部分组件集合错误，读取 `componentPropertyDefinitions` 或 `variantProperties` 可能失败。第一阶段只把 24/28/32/40/48px 作为已有按钮的静态尺寸参考，并按缓存的颜色/圆角规则调整现有结构；无法从本文确定的状态外观保持不变，列入第二阶段候选。第二阶段快速路径优先使用已验证的集合 key 或明确子组件 key，不重复读取已知损坏字段。

| 组件集合 | 发布 key |
| --- | --- |
| 48_PrimaryButton | `d7cc11cb1298af0615ea7766df6dbe563ed6dd29` |
| 40_PrimaryButton | `19e01ce6607416a2597f6f92570b9203965a78ac` |
| 32_PrimaryButton | `b1a27a27e22964b6601640c6bc5b6992e2a77644` |
| 28_PrimaryButton | `fa24b3ddaa864eaed8ee98d5c53589e8463ae752` |
| 48_SecondaryButton | `c40a7ad50a28e0680a03c6fa6f48f4705c6a39e5` |
| 40_SecondaryButton | `6040270b68b55e0c60c1ab819ce800ab8d6f9eed` |
| 32_SecondaryButton | `7ae9185e3e7e1ee29a97285c28b0310c84b0e3b2` |
| 28_SecondaryButton | `fc1872f79bb3bf9a5bd0e1828eb67c53d61a917a` |
| 40_StrokeButton | `777659da706097c0ed672e24a3514bfe0c357152` |
| 32_StrokeButton | `c4574b1c39c7e4b93e215907e6f4338ca50fd1df` |
| 24_StrokeButton | `7c4e7ed3cf7027e3ab9287062382ffc69c6bce53` |
| 32_TextIconButton/Primary | `910e6c37ef8ab155b08c41642eed06b9fb570ec0` |
| 32_TextIconButton/Secondary | `a8098f567cfa37eb28fcf8ab4284721294f8af02` |
| 32_IconTextButton | `6aa304637bfdf8054eccbe8a2ccd18413dc845ba` |

本次流程已验证的直接变体：

| 状态 | 子组件名称 | 发布 key |
| --- | --- | --- |
| 32px 主按钮正常态 | Type=Primary,Size=32,State=Normal | `6da7c0a86e80a114a48ea657d10ad3ed3b4ffb93` |
| 48px 主按钮禁用态、无图标 | Type=Primary,Size=48,State=Disabled,icon=off | `5ac817be23271fec815ccbb8f1e973a3956bbf86` |

这些组件没有可用的 TEXT component property；实例文字节点也没有 `componentPropertyReferences.characters`。需要改文案时，加载实例中文字的实际字体后直接修改 unmanaged Text。禁用态真实视觉是浅橙色，不是灰色；用户已明确要求“以组件库为准”时可直接使用，否则替换前先说明视觉差异。

按钮选择补充规则：候选先按语义和高度差匹配，实例宽度独立设置为最接近的 4 的倍数。当前已验证的 `32_PrimaryButton` 没有 Disabled 变体；当原按钮高度更接近 32px 时，不得为了获得 Disabled 状态跳到 48px，可使用 32px Normal 实例并通过实例透明度等可审计 fallback 表现禁用态，同时在图层名和交付中说明。

## 圆角映射

用户当前允许值：全圆角、8、12、16、20、24。

使用离散映射，不用连续区间：

| 原值 | 目标值 |
| --- | --- |
| 0 | 0，不处理 |
| 8 | 8 |
| 10 | 12 |
| 12 | 12 |
| 14 | 16 |
| 16 | 16 |
| 18 | 20 |
| 20 | 20 |
| 24、25 | 24 |
| 圆形、胶囊、半径大于短边一半 | 全圆角 |

遇到表中没有的值，按实际视觉和最近允许值判断，并在结果中记录；不要修改 0 圆角节点。

## 分阶段快速路径调用预算

在 Figma 无异常时，按当前授权阶段控制范围：

第一阶段目标是一次轻量预检、一次在链接目标原位批量处理基础视觉、一次独立回读与目标前后截图。不得在这一阶段增加发布库搜索、Style key 探测、组件候选全量盘点或深度结构审计。

第二阶段在同一目标稿上用一次紧凑预检覆盖发布资产可用性与全量文字/字色台账，按 key 去重批量导入本次目标资产，在一次写入中完成互不依赖的 Text/Paint 联动；只有按钮候选依赖前一步结果时才拆分按钮写入。最后只做一次独立全量回读、一次视觉校验和一次审计脚本；没有按钮时跳过按钮写入，未发生错误或证据失效时不追加逐节点回读、面板复核和重复截图。

第三阶段只对实际重复候选搜索等价发布组件；每个组件族完成一次代表验证后再批量替换，随后执行深度结构整理和最终全量审计。没有重复候选或结构候选时跳过对应写入，不创建空组件区。

这些是组织目标，不是固定调用次数承诺。不要为了合并调用而混合高风险写入；出现错误时仍遵守 `figma-use` 的恢复流程。
