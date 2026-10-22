# 只执行第三阶段审计契约

## 候选版 v2 必需证据

新运行先按 [第三阶段确定执行路径](third-stage-execution.md) 建立文件证据。以下旧计数结构继续保留，但不再单独作为完成依据。审计 JSON 新增：

```json
{
  "schemaVersion": 2,
  "editMode": "in-place",
  "visualPolicy": "text-edge-v1",
  "evidenceManifest": "evidence.json",
  "affectedBeforeNodeIds": ["2:4"],
  "affectedAfterNodeIds": ["3:7"]
}
```

`evidenceManifest` 路径相对审计 JSON。验证器读取实际 PNG、冻结候选与最终状态、原始前后快照，重新计算门禁并与汇总交叉核对。运行身份、文件摘要和快照覆盖不完整时不能完成。空候选允许空 affected 数组，但根边界和当前 editMode 所需图片比较仍必需。

v2 的 `unclassified` 表示仍 pending/blocked 的候选数；不许并入 skippedWithReason。`componentized + alreadyComponentized + skippedWithReason + unclassified = total`。任一未完成候选使状态保持 incomplete。required 候选不能改成 not-applicable/excluded-by-user 消失。没有 v2 证据的旧审计仅为历史记录，本候选验证器拒绝用它宣称完成。

仅用于用户说“帮我整理组件”，或明确说“只执行第三步”“只做组件整理”“不要重新链接组件库，只整理组件”等第三阶段独立路径。“帮我整理组件”本身即授权第三阶段，不要求再附加排除第二阶段的措辞。该路径直接在链接目标范围做组件抽取与深度结构整理；不执行第一、第二阶段，不要求历史第二阶段审计，也不建立全量 Text/Paint Style 或发布按钮覆盖矩阵。

本契约验证四件事：写入范围及共享依赖受保护、重复候选全部归类、组件血缘可追溯、组件化没有非预期改变现有 Style/字体/Paint/几何，且视觉通过固定 text-edge-v1 容差。候选所需的发布 Component 可以按固定目标库真实搜索和复用；不得借此批量重绑 Text/Paint Style 或替换通用按钮。

## 数据来源

在第三阶段任何写入前记录链接目标 ID、父级、位置、前后基线身份与采集时间、根边界、基线截图、候选清单、现有 Component/Instance lineage，以及每个实际候选可见文字区间的 Style ID/key、真实字体/排版、Paint、变量绑定和几何。完成组件/结构写入并清理临时节点后独立回读同一影响范围，再从前后数据生成审计 JSON。

最小依赖只读影响可见结果的相关字段；裁剪外且不影响可见布局的几何差异不计入 `geometryRegressions`。未受本轮组件化影响的节点不要求补做目标库链接；受影响节点必须有前后证据。已声明的组件属性覆盖只有在语义、血缘、最终值和像素均验证后才可计为 `intentionalOverrides`。无法解释的失链、样式变化或缺失证据不得改名为覆盖。

## 范围声明

新审计必须包含 [当前可见范围](visible-scope.md#验收与计数) 定义的 `scope`。本契约的完整回读、覆盖分母和质量计数均受该范围约束。排除的隐藏/裁剪外节点既不算异常，也不算 exception 或已处理；可见内容及必要布局依赖仍须验证。v2 验证器要求显式 scope；无范围声明的历史记录不能直接作为新运行的通过证据。

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
  "mode": "third-stage-only",
  "editMode": "in-place",
  "targetProtection": {
    "targetNodeIds": ["3:4"],
    "scopeRespected": true,
    "sharedDependenciesUnchanged": true,
    "canvasBoundaryPassed": true
  },
  "candidateCoverage": {
    "total": 0,
    "componentized": 0,
    "alreadyComponentized": 0,
    "skippedWithReason": 0,
    "unclassified": 0
  },
  "mutations": {
    "createdLocalComponents": 0,
    "createdComponentSets": 0,
    "replacedWithLocalInstances": 0
  },
  "stylePreservation": {
    "affectedTextSpans": 0,
    "unchanged": 0,
    "intentionalOverrides": 0,
    "unexpectedChanges": 0,
    "missingBeforeAfterEvidence": 0
  },
  "lineage": {
    "instancesChecked": 0,
    "missingMainComponent": 0,
    "orphanLocalInstances": 0,
    "wrongMainComponent": 0,
    "temporaryNodes": 0
  },
  "visualValidation": {
    "acceptedMinorTextDifferences": 0,
    "rootsCompared": 0,
    "unexpectedPixelDifferences": 0,
    "geometryRegressions": 0
  },
  "assetSources": []
}
```

`status` 只能是 `complete` 或 `incomplete`，`mode` 必须为 `third-stage-only`。所有计数字段必须是非负整数，并满足：

- `candidateCoverage.componentized + alreadyComponentized + skippedWithReason + unclassified = total`
- `candidateCoverage.unclassified = 0`
- `stylePreservation.unchanged + intentionalOverrides = affectedTextSpans`
- `stylePreservation.unexpectedChanges = 0`
- `stylePreservation.missingBeforeAfterEvidence = 0`
- `lineage.missingMainComponent`、`orphanLocalInstances`、`wrongMainComponent`、`temporaryNodes` 全部为 0
- `visualValidation.unexpectedPixelDifferences` 和 `geometryRegressions` 全部为 0
- 原位模式的 `targetProtection.scopeRespected`、`sharedDependenciesUnchanged`、`canvasBoundaryPassed` 全部为 `true`，targetNodeIds 与 scope.processingRootIds、证据根 ID 一致

如果 `candidateCoverage.total > 0` 且存在稳定重复候选，必须由候选明细证明它们已经组件化、原本已组件化或有具体跳过原因；不能通过虚增 `skippedWithReason` 清零。若确实没有候选，`total=0` 可以通过，但仍须完成写入范围保护、边界和像素验证。

新审计与 evidence.json 必须使用相同 `editMode`。默认 `in-place`：每个 rootMappings 的 sourceId/copyId 为同一目标根 ID，before/after 快照的 baselineId 相同且非空，capturedAt 递增，根包含 parentId/index/x/y，每根只有 final 前后图片比较。

只有用户明确要求副本时设 `safe-copy`，改用 `sourceProtection: {sourceNodeIds: [...], copyNodeIds: [...], mappingComplete: true, sourceUnchanged: true, canvasBoundaryPassed: true}`，根 ID 不同且三种图片比较齐备。scope.processingRootIds 对应副本根。省略 editMode 仅兼容历史 safe-copy 证据，不作为新运行默认值。

## 资产来源

`assetSources` 只登记本轮实际复用的目标发布 Component，以及本轮新建的局部 Component/Component Set。不得把目标稿中既有 Text/Paint Style 登记为本轮完成的组件库联动。

每条记录至少包含：

```json
{
  "assetType": "COMPONENT",
  "assetName": "本页局部/指标卡",
  "sourceType": "local-copy",
  "libraryName": null,
  "libraryKey": null,
  "assetKey": null,
  "remote": false,
  "usageCount": 3,
  "nodeIds": ["3:4"],
  "description": "来源：当前目标稿；不属于发布库"
}
```

- `assetType` 只能是 `COMPONENT` 或 `COMPONENT_SET`。
- `sourceType=target-library` 时，`libraryName`、`libraryKey`、`assetKey` 均非空，且 `remote=true`。
- `local-copy` 是保留的本地资产来源枚举，不代表需要复制整稿；原位编辑同样使用它。
- `sourceType=local-copy` 时，`libraryName`、`libraryKey`、`assetKey` 为 `null`，`remote=false`；名称以 `本页局部/` 开头，`description` 包含“不属于发布库”。
- `createdLocalComponents + createdComponentSets > 0` 时，必须存在对应数量的 `local-copy` 来源记录；验证器检查记录数量不得少于创建的局部母资产数量。

## 执行门禁

运行：

```bash
python3 scripts/validate_component_audit.py /absolute/path/to/component-audit.json
```

- 退出码 0：契约有效且可以宣称第三阶段完成。
- 退出码 2：契约有效，但第三阶段仍未完成；输出具体阻塞项。
- 退出码 1：字段缺失、计数矛盾、来源伪装或其他审计错误。

该脚本只验证机器可读审计与门槛关系；它不能代替 Figma 属性回读、截图、像素比较、组件候选判断或写入范围与共享依赖保护验证。

轻微字形差异按 [字体与视觉容差](font-visual-policy.md) 保存真实文字 PNG、根内位置及前后文字快照；evidence.json 设置 visualPolicy="text-edge-v1"。acceptedMinorTextDifferences 为已接受的差异像素总数，不得用它抵消文字区域之外或明显排版变化；unexpectedPixelDifferences 仍必须为 0。

## 共享维护的附加证据

本轮有共享维护目标的组件族，审计同时引用组件建模参考规定的 `shared-sync.json`，列出基础组件、各变体嵌套关系、共享/覆盖职责、独立测试与恢复结果。现有 v2 验证器不自动判断这份行为证据，必须人工核对真实调用；不以脚本通过代替同步验收。用户只授权单族小样本时，只报告该样本验证结果，不生成全页完成结论，也不因此扩展其他组件、样式或面板配置。
