# 最终审计契约

第二阶段，以及包含第二阶段的“第二步+第三步”或完整三阶段路径在最后一次 Figma 写入与独立回读完成后使用。本契约把 P0 门槛和资产来源变成可执行校验，防止待核验、失链或其他库资产被包装成“已完成”。第一阶段不做发布 Style/Component 联动，因此不运行本契约的验证脚本；显式只执行第三阶段时也不运行本契约，改用 [只执行第三阶段审计契约](third-stage-only-contract.md)，因为该路径按要求不建立全量目标库 Style 覆盖。不能用本契约缺失来否定第一阶段或只执行第三阶段的完成，也不能据此宣称第二阶段已完成。

第二阶段的 `mutations.createdLocalComponents`、`createdComponentSets`、`replacedWithLocalInstances` 必须全部为 0，只登记实际使用的目标发布资产。包含第二阶段的连续路径进入第三阶段后，在组件和深度结构写入后重新全量回读，更新三项 mutation 和本地资产来源记录；第二阶段通过的旧 JSON 不能充当第三阶段完成证据。

## 数据来源与报告生成

执行中的数据复用遵循 [执行效率与证据复用](execution-efficiency.md)。最终先完整回读交付范围，包含设计稿、组件整理区、嵌套变体和全部关联实例；刷新台账中的当前节点/区间与来源记录，再用同一份最终数据计算本 JSON、两份覆盖矩阵、资产使用数量和交付报告。所有计数均可追溯到明细，不手工复制中间汇总凑出最终报告。

页面文字、组件整理区文字分别保留范围标记，再汇总完整审计范围；非文字 Fill/Stroke 的 Paint Style 使用量与文字字色矩阵分开，不能相加来满足字色门槛。已删除的历史组件不计入当前资产数量，操作历史另存并明确计数口径。可复用的截图/数字回归须注明适用对象和验证阶段，并确认相关字体、布局、组件定义与覆盖未发生改变。

以下 JSON 字段和验证器门槛保持不变；统一数据来源不替代独立回读和实际质量检查。

## 范围声明

新审计必须包含 [当前可见范围](visible-scope.md#验收与计数) 定义的 `scope`。本契约的完整回读、覆盖分母和质量计数均受该范围约束。排除的隐藏/裁剪外节点既不算异常，也不算 exception 或已处理；可见内容及必要布局依赖仍须验证。验证器兼容无 scope 的历史记录，不能据此省略新记录的范围声明或重写旧失败结果。

## JSON 结构

生成 UTF-8 JSON，至少包含：

```json
{
  "status": "complete",
  "scope": {
    "mode": "current-visible",
    "processingRootIds": ["3:4"],
    "dependencyCheckPassed": true,
    "excludedContentPreserved": true
  },
  "p0Passed": true,
  "targetLibrary": {
    "name": "目标发布库名称",
    "fileKey": "目标库文件 key",
    "libraryKey": "目标发布 library key"
  },
  "typography": {
    "totalSpans": 0,
    "targetDirect": 0,
    "targetInherited": 0,
    "exceptions": 0,
    "verificationPending": 0,
    "linkRegressed": 0,
    "otherStyle": 0,
    "unmapped": 0,
    "unclassified": 0,
    "unresolvedUnlinked": 0
  },
  "color": {
    "totalSpans": 0,
    "targetDirect": 0,
    "targetInherited": 0,
    "exceptions": 0,
    "otherStyle": 0,
    "exactUnlinked": 0,
    "unclassified": 0,
    "unresolvedUnlinked": 0
  },
  "mutations": {
    "createdLocalComponents": 0,
    "createdComponentSets": 0,
    "replacedWithLocalInstances": 0
  },
  "assetSources": []
}
```

`status` 只能是 `complete` 或 `incomplete`。文字和字色分别满足：

`targetDirect + targetInherited + exceptions = totalSpans`

例外必须已在明细中给出节点/区间和已证实差异；未知值不能靠增加 `exceptions` 清零。以下任一字段非 0 时，`p0Passed` 必须为 `false`，状态必须为 `incomplete`：

- 排版：`verificationPending`、`linkRegressed`、`otherStyle`、`unmapped`、`unclassified`、`unresolvedUnlinked`。
- 字色：`otherStyle`、`exactUnlinked`、`unclassified`、`unresolvedUnlinked`。

`p0Passed=false` 时整体仍为 incomplete。按 run-contract.md 继续独立候选时，增加 scopedContinuation：mode=independent-candidates、blockedNodeIds、candidateReceipts。每份原始执行证据对应 candidateId、evidencePath、完整 affectedNodeIds（含布局/样式依赖）、dependencyCheckPassed/propertiesPassed/lineagePassed/visualPassed/rollbackReady 及三项实际 mutation 数量。受影响集合不得与阻塞集合相交，回执计数必须等于总 mutations。验证器只校验记录结构和一致性，不替代原始工具证据；不得手填布尔值冒充执行。没有此证据时 mutations 必须为 0。

## 默认无等价排版例外

主 Skill 已将“目标库确认无严格等价 Text Style”设为用户预先接受的排版例外。完成限定 library key 的真实搜索和完整排版属性比较后，这类区间直接从 `unmapped` 转入 `typography.exceptions`，无需再次询问用户，也不阻止 `p0Passed=true` 或进入已授权的第三阶段。例外明细仍须包含节点/区间、原排版属性、候选发布 key、逐项差异和最终保持的实际属性。

字体不可加载的区间只有在原节点无需编辑或重排、目标稿稳定渲染、边界和截图均通过时，才能计入 `typography.exceptions`；第三阶段需要编辑该文字的组件候选须单独跳过。尚未完成搜索/比较、真实属性不明、本次写入失链、已有等价 Style 可写、文字重叠/裁切，或缺失字体导致渲染不稳定时，仍分别计入原有阻塞字段，不能改名为例外。

## 文字黑灰色归一化审计

按固定 Profile 的“文字黑灰色归一化”执行后，成功绑定的区间计入 `color.targetDirect` 或 `color.targetInherited`，并在明细记录原 RGBA、目标 RGBA、目标 Paint Style key、颜色分类（`black-to-333333` 或 `nearest-neutral-gray`）和截图验证。无法安全覆盖而回退原 Paint 的区间可以计入 `color.exceptions`，但必须记录实例可写性、混合区间或实际背景可辨认性证据；不能留在 `exactUnlinked` 或 `unclassified` 后宣称完成。

## 默认排版值的审计依据

按 [默认排版值的确认](typography-layout-repair.md#默认排版值的确认) 解决 API `MIXED`/缺失时，未知字距直接采用本 Skill 预先授权的 0，无需另取面板或本次用户确认，也不单独计入 `verificationPending` 或例外。复用已有数据，不为补齐字距原始值追加扫描；未单独读取时如实记录 `not-read`。其他属性已验证、正式链接/画面检查均通过的区间，计入 `targetDirect` 或 `targetInherited`，不要求 API 字距必须先返回数值 0，也不要求仅因未知字距补做探针。存在其他独立探针触发条件时，仍须完成对应验证。

在区间明细附 `spacingResolution`，记录适用 `nodeId`/区间与发布 key、API 原始值、采用的行高/字距、证据来源及规则引用或原话/截图、探针复用依据、正式 key 和几何/截图检查结果。证据来源可为 `editor-panel`、`user-confirmed-defaults` 或 `skill-default-zero-letter-spacing`；最后一项引用主 Skill 的“默认未知字距按 0px 处理”，仅用于未知字距，不为未知行高等其他属性提供证据。采用值与 API 返回值分开保存，不能声称读取结果已是 0；默认规则或用户确认不自动证明链接已写入，正式节点的 key 缺失或排版发生真实冲突时仍不能清零阻塞项。

## 资产来源台账

`assetSources` 对实际使用的目标发布 Text Style、Paint Style、Component，以及本次新建的局部 Component/Component Set 分组记录：

```json
{
  "assetType": "TEXT_STYLE",
  "assetName": "PingFang SC/Body1_CN_Regular",
  "sourceType": "target-library",
  "libraryName": "目标发布库名称",
  "libraryKey": "目标发布 library key",
  "assetKey": "发布资产 key",
  "remote": true,
  "usageCount": 3,
  "nodeIds": ["1:2"]
}
```

- `assetType` 只能是 `TEXT_STYLE`、`PAINT_STYLE`、`COMPONENT` 或 `COMPONENT_SET`。
- `sourceType=target-library` 时，库名称和 library key 必须与 `targetLibrary` 完全一致，`assetKey` 非空且 `remote=true`。
- `sourceType=local-copy` 时，`libraryName`、`libraryKey` 为 `null`，`remote=false`；组件名称必须以 `本页局部/` 开头，`description` 必须包含“不属于发布库”。
- Text Style 的 `usageCount` 合计必须等于排版 `targetDirect + targetInherited`；Paint Style 同理。目标发布组件和局部组件的每条记录都要列出实际实例/母组件节点 ID。
- 本次创建局部组件或组件集时，必须存在对应的 `local-copy` 来源记录；没有使用某类资产时可以不写该类记录。

## 执行门禁

运行：

```bash
python3 scripts/validate_final_audit.py /absolute/path/to/final-audit.json
```

- 退出码 0：契约有效且可以宣称完成。
- 退出码 2：契约有效，但任务仍为未完成；输出具体阻塞项。
- 退出码 1：字段缺失、计数矛盾、来源伪装或其他审计错误。

该脚本只验证机器可读审计与门槛关系；它不能代替 Figma 属性回读、编辑器面板、截图、像素比较或写入范围保护与目标前后边界验证。
