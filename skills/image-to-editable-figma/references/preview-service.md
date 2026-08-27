# 稳定预览服务

仅在以下情况读取本文件：用户明确授权首次安装稳定预览服务；普通任务需要注册或验证当前预览；服务身份、端口、路由或链接恢复失败；用户要求停止、卸载或清理服务日志。服务正常且命令输出满足主 Skill 的交付条件时，不重复展开本文件。

## 职责边界

稳定预览服务是独立基础设施，只按已注册的任务/版本路由返回磁盘原始字节。它不得参与图片生成、抠图、资源路由、HTML 构建、字体选择、视觉校验、审批判定或 Figma 写入，也不得改写 HTML/CSS/JS、图片或字体。

服务在线不等于用户已经批准导入。服务和管理脚本不得创建 Capture ID、追加 `figmacapture`/`figmaendpoint`、调用浏览器插件、创建 Figma 文件或节点，也不得改变主 Skill 的固定审批文案和版本绑定规则。

## 文件与状态

- 服务端：`scripts/preview-server.mjs`，跨平台 Node 只读 HTTP 服务。
- 管理端：`scripts/preview-service.mjs`，负责安装、状态、注册、验证、启停、卸载和日志清理。
- macOS 保活模板：`assets/launchd-preview-service.plist.template`。
- 默认状态目录：`~/.codex/image-to-editable-figma-preview/`，必须位于 Skill 目录外，Skill 更新不得清除历史路由。
- `config.json` 保存服务名、协议版本、安装实例 ID、固定主机和端口；`routes/` 为每个任务/版本保存一个独立 JSON，使用每路由文件锁、临时文件和原子重命名更新。
- 服务本身只读配置和路由；只有管理命令可以写注册信息。

默认绑定 `127.0.0.1:41972`。端口在首次显式安装时确定，之后不得静默变更。身份接口为：

```text
http://127.0.0.1:41972/.well-known/image-to-editable-figma-preview.json
```

接口只返回服务名、协议版本、安装实例 ID、主机和端口，不返回本地目录。

## 首次显式安装

安装常驻服务属于持久环境修改。只有用户明确同意安装稳定预览服务后，才能执行：

```bash
node scripts/preview-service.mjs install --confirm-persistent-install
```

指定非默认端口只能发生在首次安装：

```bash
node scripts/preview-service.mjs install --port 41972 --confirm-persistent-install
```

macOS 默认写入用户级 LaunchAgent 并启动；`launchd` 只是可选保活包装，Node 服务和路由协议不依赖 macOS。其他平台只完成配置，需由用户选择的平台服务管理器运行 `serve`；不得声称已经获得重启后保活能力。只检查方案、不落盘时使用：

```bash
node scripts/preview-service.mjs install --dry-run
```

若端口已被未知进程占用，安装必须停止：不连接未知服务，不改用随机端口，也不继续交付旧 URL。普通图片任务不得静默运行 `install` 或写入 LaunchAgent。

## 日常任务

在当前版本 Capture HTML 已完成构建、静态预检和依赖闭包检查后执行：

```bash
node scripts/preview-service.mjs status

node scripts/preview-service.mjs register \
  --task-id <task-id> \
  --version <v001> \
  --dir <当前版本绝对目录> \
  --capture <唯一-capture.html>

node scripts/preview-service.mjs verify \
  --task-id <task-id> \
  --version <v001>
```

路由固定为：

```text
/image-to-editable-figma/<task-id>/<version>/<capture-file>
```

不得创建 `/latest`、软链接别名、目录入口或指向整个工作区的路由。同一任务当前版本修改后仍注册原路由和原 Capture 文件名；管理脚本只更新该路由的当前 Capture SHA-256。若同一任务/版本尝试改指向另一个目录或文件，注册必须失败。新任务或用户明确要求新版本时使用新路由。

`verify` 必须同时确认：服务身份与安装实例一致、路由存在、磁盘 Capture SHA-256 等于注册值、HTTP 200 正文 SHA-256 等于磁盘文件、响应为 `Cache-Control: no-store`。图片和字体依赖继续由既有 `resource-manifest.json`、审批指纹、HTTP 预检、浏览器图片加载和 `document.fonts` 检查负责；不要在服务层复制另一套易漂移的资源清单。

只有 `verify` 成功，且主 Skill 的依赖、画布、字体、截图和审批指纹检查也成功，才能把返回 URL 称为“稳定预览”。最终截图必须来自这个 URL。

## HTTP 安全约束

服务只允许 `GET` 和 `HEAD`，并满足：

- 只监听 `127.0.0.1`，不监听局域网或公网。
- 只提供已注册的单个版本目录，不提供工作区或上级目录。
- 禁止目录列表、写入、上传、删除、重命名和 URL 注册。
- 拒绝 `..`、反斜杠、二次 URL 解码和越界 realpath；软链接解析后超出已注册目录必须返回拒绝。
- 返回正确的 HTML、CSS、JS、JSON、SVG、PNG/JPEG/WebP、WOFF/WOFF2、TTF/OTF MIME。
- 所有响应使用 `Cache-Control: no-store`，不注入会阻断官方 `capture.js` 的 CSP。
- 不修改响应正文；服务内部日志只记录状态和错误，不记录文件正文，单文件达到 `1 MiB` 时最多保留一个轮转文件。LaunchAgent 的 stdout/stderr 不另行累积，使用 `clean-logs` 可显式清空内部日志。

## 异常与恢复

- `status=not-installed`：保留现有 HTML、素材、报告和指纹，说明需要一次明确安装授权；不得临时安装或把临时服务器 URL 称为稳定预览。
- `status=stopped`：已安装时先执行 `start`，再重新 `status → register → verify`。
- `status=unknown-service` 或身份/协议/实例 ID 不匹配：停止交付，报告固定端口冲突；不得误连、换端口或复用旧链接。
- Capture 在注册后变化：重新完成当前版本预检与审批指纹，再次 `register → verify`；原审批按主 Skill 规则失效。
- HTTP 字节与磁盘不一致、路由串稿、路径越界或资源加载失败：停止预览与 Capture，不发送链接，先修复服务或当前版本闭包。
- 恢复失败：保留任务产物并明确阻断“稳定预览”交付；不得降级成一个会随终端结束的临时链接。

## 运维命令

```bash
node scripts/preview-service.mjs status
node scripts/preview-service.mjs start
node scripts/preview-service.mjs stop
node scripts/preview-service.mjs restart
node scripts/preview-service.mjs uninstall
node scripts/preview-service.mjs clean-logs
node scripts/preview-service.mjs self-test
```

`start/stop/restart` 是 macOS LaunchAgent 包装命令；跨平台前台运行使用 `serve`。`uninstall` 会停止并移除保活包装，但必须保留 `config.json`、`routes/`、任务 HTML、图片、字体、报告和审批指纹；卸载后历史 URL 暂时离线，再安装或手动运行同一状态目录可恢复原路由。删除历史路由或任务目录属于单独的破坏性操作，本脚本不提供自动过期或批量清除命令。`clean-logs` 只截断服务日志。

## 回归要求

修改服务或 Skill 中的预览规则后至少运行：

```bash
node --check scripts/preview-server.mjs
node --check scripts/preview-service.mjs
node scripts/preview-service.mjs self-test
```

自测必须覆盖身份接口、GET/HEAD、目录列表禁用、双重解码、软链接越界、并发多任务隔离、同路由锁与拒绝静默改指、磁盘/HTTP 字节一致、服务重启后路由恢复和未知端口进程拒绝。随后用一个独立测试目录对同一 Capture HTML 比较服务前后磁盘/HTTP 字节哈希和浏览器截图；不得用测试服务修改正式任务目录或写入 Figma。
