# GitHub Pages 发布源审计与定向修复说明

日期：2026-09-15  
项目：Amazon-Keyword-Command-Center-YX  
目的：解释“本地已修复但线上报告页面仍是旧版本”的原因，并给后续执行模型一份不猜测、不重复发布的操作清单。

## 结论先行

当前公开地址：

`https://upjacky.github.io/Amazon-Keyword-Command-Center-YX/`

实际仍在提供 `main` 分支根目录中的旧前端文件，不是刚刚推送的 `master` 分支 checkpoint `b40afef`。

因此：

1. 线上页面地址本身可达，但不能据此证明线上已包含本地 R12 修复。
2. 本地 `master` 的提交成功不等于 GitHub Pages 部署成功。
3. 不能继续重复 `git push origin master`；在发布源不变时重复推送不会改变 Pages 内容。
4. 线上“报告页面无数据/功能旧”的第一根因是发布源与开发分支不一致；报告业务数据缺失仍需另按真实 Provider/Supabase Gate 验收，不能用发布问题掩盖。

## 只读证据

### 1. 远端分支提交不同

| 分支 | 远端提交 | 时间 | 提交标题 |
|---|---|---|---|
| `main` | `45071852e9897bc9ec0c07b62d2bb3710893b064` | 2026-09-14 | `fix: retry transient private report reads` |
| `master` | `b40afefed940f19749bd162dbf923f524b66ebf4` | 2026-09-15 | `fix: close local R12 admission race and evidence gates` |

### 2. 线上文件哈希与 `main` 根目录一致

以下 SHA-256 是对 HTTP 响应正文计算，不包含 Secret：

| 文件 | Pages 线上 | `main` 根目录 | `master` 当前路径 | 判断 |
|---|---|---|---|---|
| `client.js` | `0880b3835be58f6167982f64c1bd4ca6dbe0d04bcf93fb46e149688174d08920`，27002 bytes | 完全一致 | `master/client.js` 为 404；新文件在 `master/frontend/client.js` | 线上来自 main 根目录 |
| `report/negative.js` | `bfae3b317f715007cb92fd2650bd7aeef6c4b4ed419ee555ee8a6c674a505b6d`，8895 bytes | 完全一致 | `master/report/negative.js` 为 404 | 线上来自 main 根目录 |
| `report/optimization.js` | `76b5462902ec6490236d9ac73bdf1b9367335162386e50b40fb8b3e6221f1d76`，14766 bytes | 完全一致 | `master/report/optimization.js` 为 404 | 线上来自 main 根目录 |

补充：`main/frontend/client.js` 也能读取到与 `main/client.js` 相同的旧内容；不能仅凭存在 `frontend/` 目录就假定 Pages 已从该目录发布。公开 URL 的实际文件路径和哈希已经直接证明当前响应对应 `main` 根目录版本。

### 3. 没有仓库内 GitHub Actions 发布配置

本地 `.github/workflows` 不存在。GitHub API 只读检查确认仓库 `has_pages=true`，但匿名 API 的 `/pages` 配置端点返回 404，不能从 API 读取发布源。历史项目状态曾记录 Pages 配置为 `main` 分支根目录；本次哈希比对与该记录一致。

## 这次审计没有证明什么

- 没有证明真实报告数据已经齐全。
- 没有证明 Supabase 010/011/012 已在线执行。
- 没有证明线上 Worker 已重启并运行最新版本。
- 没有证明 CORS、无痕报告门禁和新的三张地址栏截图已经重新验收。
- 没有调用西柚、Sorftime、Doubao，也没有写入 Supabase 或 GitHub Pages 配置。

本地当前证据仍以 `PROJECT_STATUS.md` 顶部为准：R12 本地行为 Gate 13 项、完整 UAT 21/21、网络/真实 Provider 调用 0；LUNU-05 不能因此标记完成。

## 给 Lunu 的唯一推荐修复路径

Lunu 只能在完成以下只读确认后执行一次定向发布，不得盲目双向合并：

### 步骤 A：确认 Pages 发布源

1. 打开仓库 Settings → Pages。
2. 记录当前 Source 的 branch 和 folder，不要修改其他设置。
3. 若界面显示 `main` / `/ (root)`，与本审计一致。
4. 若界面显示其他 branch/folder，先把该结果写入 `docs/acceptance/`，停止后续发布推断。

### 步骤 B：确认要发布的目录

1. 在本地 `master` 当前 checkpoint 中确认真正可发布的前端目录和入口：
   - `frontend/index.html`
   - `frontend/tool/index.html`
   - `frontend/report/index.html`
   - `frontend/report/rank.html`
   - `frontend/report/negative.html`
   - `frontend/report/competitors.html`
   - `frontend/report/listing.html`
   - `frontend/report/optimization.html`
2. 使用项目已有的 Pages 构建/审计脚本生成 allowlist 输出，不要手工复制整仓库。
3. 输出必须继续满足：没有 `.env`、JWT、密码、私钥、Provider token、原始广告报表和本地 demo 数据；只允许前端静态文件和必要的公共配置。
4. 构建后运行 Pages 静态审计和 `python -B scripts/run_uat.py` 中对应 Pages Gate；不能只看构建命令退出码。

### 步骤 C：发布方式二选一，只执行用户已确认的那一种

#### 方案 1：保持 Pages 为 `main` 根目录（推荐短期）

适用条件：Settings → Pages 明确显示 `main` / root，且项目仍希望使用当前公开地址。

1. 从 `master` 的已审查 checkpoint `b40afef` 构建一个干净的 Pages 输出目录。
2. 只把 allowlist 输出同步到 `main` 根目录对应的发布位置。
3. 该同步必须形成单独、可回滚的发布提交，提交信息包含源 checkpoint：`publish: pages from b40afef`。
4. 推送 `main` 一次。
5. 等待部署后，用 HTTP GET 重新计算以下文件哈希；必须与发布输出一致：
   - `client.js`
   - `report/rank.js`
   - `report/negative.js`
   - `report/competitors.js`
   - `report/listing.js`
   - `report/optimization.js`
   - `tool/tool.js`
6. 线上哈希未变化时，不得再次推送；记录为 Pages 部署/CDN 延迟或发布失败，转到外部 Gate。

#### 方案 2：把 Pages Source 改为 `master` 的正确目录

适用条件：用户明确选择让 Pages 直接跟踪 `master`，且 Settings 页面确认该目录可作为 Pages 根目录。

1. 先在 GitHub Pages 设置中确认 `master` 和正确 folder；不要凭仓库文件名猜测。
2. 修改 Source 后等待一次部署。
3. 重新检查全部入口、静态资源相对路径、报告页登录门禁和 API Origin。
4. 如果 `master` 的发布目录不是根目录，不要把整个仓库根目录改成 Pages；应使用项目已有构建输出或在仓库内新增明确的 Actions workflow，但该架构变更必须单独评审。

## 发布后必须重新验收

1. 登录页、工具页、报告首页和六个独立报告地址均 HTTP 200。
2. 登录后报告页通过 Supabase 私有 fetch 在线渲染，不是裸贴 Storage URL。
3. 未登录直接打开 `report/*.html?task=...&run=...` 必须跳回登录或明确拒绝，并在无痕窗口截图。
4. 工具页继续验证 ASIN、文件类型/大小、提交防重复、任务刷新、失败原因、退出登录。
5. 线上版本中必须能看到本地新代码携带的版本/契约变化；不能只验证壳页面 200。
6. 真实新任务仍需单独验证真实六模块数据：自然位、否词、竞对、图片卖点、广告诊断优化；`partial`/`not_generated` 必须按真实字段决定，不能用演示数据填充。
7. 乙线未登录直接调用接口必须被拒；取得带地址栏截图后才关闭该 Gate。

## 回滚规则

- 只能回滚到已知的发布提交或已知的 Pages 输出，不得使用 `git reset --hard` 或覆盖用户工作树。
- 发布提交必须保留源 checkpoint、构建摘要、哈希表和验收结果。
- 回滚只影响前端发布，不删除 Supabase 数据、任务、run、报告或 Provider 缓存。
- 任何涉及 Pages Source、分支保护、密钥、权限、数据库迁移和线上 Worker 的操作，都要单独记录，不要混在普通前端提交中。

## 当前状态

- 本地修复 checkpoint：`b40afef`，已推送到 `origin/master`。
- 当前公开 Pages：仍为旧 `main` 根目录版本，线上新版本未确认生效。
- 本地可继续做：Pages 发布目录审计、构建输出核验、发布后静态哈希对账、外部 Gate 清单整理。
- 真实外部阻塞：Pages Source 的 UI 确认/发布、Supabase 线上迁移/RLS/Storage、Worker 重启、真实六模块新 run、CORS/无痕截图。
- 禁止结论：不能把“master 已推送”“HTTP 200”或“旧页面能打开”写成“LUNU-05 完成”。
