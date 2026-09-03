---
project: Amazon-Keyword-Command-Center-YX
project_cn: 关键词作战总表
document_type: project_memory
version: 1.4
updated_at: 2026-09-03
status: current
language: zh-CN

- 2026-09-03 六模块工作台修订：原计划六模块未被前端完整呈现，本轮补独立页面/脚本、共享蓝色样式/导航/门禁及三份可重建演示数据。41个Node场景、Pages57文件；真实图片、完整标杆/竞对指标、广告结构优化/退出阈值和生产上传→Worker→私有报告链仍不能冒充完成。完整差异见 `docs/acceptance/six-module-workbench.md`。

- 2026-09-03：阶段 8 交付审计补齐真实任务报告对象名：任务运行使用 `report-` 加 48 位十六进制随机串，`run-meta.json.report_path` 记录 task/run/对象路径；演示黄金报告仍固定名仅用于离线 Pages。解析器新增 `reconciliation.header_mapping`，本地 6a 对账为 91 行、五项差值为零；完整 UAT 已复验 Worker 207 项、前端 7 项、20/20 Gate。

- 2026-09-03：阶段 8 前端整改已完成本地验证：登录、工具、报告为独立 HTML/地址；工具页具备 B0+10 位 ASIN、XLSX/CSV/10MB、固定阶段顺序、防重复提交、30 秒/手动刷新和失败原因展示；报告页 fetch 在线渲染并有登录门禁；Pages 构建输出更新为 57 个 allowlist 文件，线上旧站尚待重新发布复验。

- 2026-09-02：GitHub Pages 曾通过旧版登录入口的 HTTPS Smoke Test；本次独立路由改版后的线上内容待重新发布复验。
- 2026-09-02：Provider 本地 HTTP transport 与 `scripts/probe_provider.py` 已完成；最新完整 UAT 统计见本节 2026-09-03 条目。
- 2026-09-02：新西柚 MCP 配置已完成只读 `tools/list` live 验证：HTTP 200、JSON-RPC 结构有效、返回 29 个工具；实际调用 1 次、失败 0、限流 0，未调用业务工具样本，成本/单位/限流语义仍待外部确认。
- 2026-09-02：已完成一次授权的 `get_keyword_info` 只读业务样本：HTTP/业务状态 200，观察到 `cost_credits=1`，业务调用 1 次、失败 0、限流 0；字段和类型已写入 `docs/provider-snapshots/xiyou-tools-list-20260902.md`，缓存/重复、429/5xx、成本单位和缺失值语义仍待外部确认。
- 2026-09-02：追加 5 次授权范围内只读调用，覆盖重复基础指标、ABA 趋势、ASIN 信息和无结果边界；均状态 200、各 1 credit，累计业务调用 6 次、失败 0、限流 0；无结果字段保持 JSON `null`，成本单位、缓存/重复、429/5xx 和版本字段仍未完成真实验证。
- 2026-09-02：响应头只读探针返回 HTTP 200；允许记录的头只有 `content-type`/`content-length`，未观察到成本、限流、`Retry-After` 或版本头。白名单过滤和不记录错误体/Secret 的本地回归已通过，真实 MCP 行为仍需外部确认。
- 2026-09-02：用户新授权后完成 3 轮、5 次真实只读复核：重复 `get_keyword_info` 两次均业务状态 200、各 `cost_credits=1`、`cache_hits=0`，响应摘要相同；未触发 429/5xx，未观察到成本/限流/版本响应头。当前外部 Gate 仅保留成本货币换算、真实 429/5xx 和独立版本字段。
- 2026-09-02：Supabase `reports` Storage 私有读取 Gate 已完成：测试文件两组普通用户认证均为 HTTP 200，A/B 各自对象读取为 HTTP 200，跨店、匿名、无效令牌读取均为 HTTP 400；A 对象补传期间的临时 INSERT policy 已清理，最终仍保持 Worker 写入、用户受控读取。密码全角问号仅在内存中归一化，未改写测试文件或持久化任何凭据。
- 2026-09-01：Supabase `reports` Storage bucket 已在当前项目确认 private，A/B 两份测试 JSON 已上传且未生成公开链接；B 临时用户认证成功但尚未绑定店铺，A 临时用户认证失败，受控浏览器控制台会话已失效。该条为历史中间状态，当前以 2026-09-02 验收记录为准。
- 2026-09-01：外部 Gate 有界审计完成：Supabase Storage 无可见私有桶且仓库无 Storage bucket/object policy；`www.upjk.cn` HTTPS 不可达、HTTP 返回 502，工作区无 Git 仓库或 GitHub workflow。未发布、未改 DNS、未接触生产数据；监督器保持 `BLOCKED_EXTERNAL`。

- 2026-08-22 当前线程曾建立覆盖完整项目目标的平台持续目标；`get_goal` 为空时才调用一次 `create_goal`，已有 active 目标复用。本轮因连续三次相同外部阻塞已标记 `BLOCKED`；恢复后继续由 `PROJECT_TASKS.json` 与 `--claim`/`--complete` 负责唯一任务领取、原子续领和防重复。
- 状态机/持续目标 14 项与项目监督器 32 项合并为 46 项连续执行回归 Gate；任务 ID、执行类型、依赖、验收条件及声明输入共同参与 SHA-256，变化时 stale 重开，未变化且回执有效时跳过；不完整回执 fail closed，运行中输入变化可安全刷新领取并重验。
- 最新完整 UAT 20/20 Gate 通过：Worker 144 项（12 项环境跳过）、前端 5 项、UAT 编排契约 22 项、连续执行/监督器 46 项，Pages 19 文件、文档 15 项，network_calls=0、external_calls=0、Secret=0。监督器最终为 `BLOCKED_EXTERNAL`，本地安全队列为空，平台持续目标已标记 `BLOCKED`，剩余四项均需外部授权或凭据。

- 2026-08-21 本地安全审计收口：`path_guard` 对权限错误和其他 `OSError` fail-closed，避免无法检查的路径绕过 queue/storage/ingestion/Pages 的 Junction/reparse/symlink 边界；新增 3 项回归，完整 UAT Worker 144 项（12 项环境跳过）/前端 5 项、19 Gate 通过，网络/外部调用 0、Secret 0。

- 2026-08-21 UAT 编排最终本地审计：`run_uat.py` 要求 Worker loop、Phase 8、Pages 摘要包含 `network_calls`、`external_calls`、`local_only`，并严格校验字段类型；缺少结构化摘要同时写入 `summary_contract_errors` 和诊断字段，部分摘要、类型错误、超时和启动异常均结构化失败并继续收集全部 19 Gate；`_summary_metrics` 对缺失摘要安全跳过。新增统一 120 秒 Gate 超时和 5 组 ExitStack 临时目录退出清理回归，编排契约 18 项，最新完整 UAT Worker 144 项（12 项环境跳过）/前端 5 项，网络/外部调用 0、Secret 0。
---

- 2026-08-21 report-0.2 追溯契约收口：统一 `normalise_missing_fields()` 供 `shared_traceability()`、`market_merge`、`rule_engine` 使用；共享对账字段和前端展示只接受布尔 `true`，报告页/任务页缺失字段统一过滤、去重、排序并安全降级。新增 7 项回归，完整 UAT Worker 140 项（11 项环境跳过）/前端 5 项，19 Gate 通过，network_calls=0、external_calls=0、Secret 0。

- 2026-08-21 report-0.2 追溯契约收口：`shared_traceability()`、`market_merge`、`rule_engine` 对 `missing_fields` 去除首尾空白并过滤空白/非字符串值；共享对账字段和前端展示均只接受布尔 `true` 为通过；报告页对异常缺失字段数组安全降级。新增 5 项回归，完整 UAT Worker 139 项（11 项环境跳过）/前端 5 项、19 Gate 通过，network_calls=0、external_calls=0、Secret=0。

- 2026-08-21 queue/storage/ingestion/Pages/Supabase 安全审计补强：FileQueue 初始化拒绝被重定向的 state 目录，artifact 与 Pages 目录在创建后再次校验真实目录，保持 Junction/reparse/symlink、恢复失败归档、artifact allowlist/不可覆盖、Supabase URL/header、Secret/网络边界；新增 2 项回归，完整 UAT Worker 136 项（11 项 Windows 链接能力跳过）/前端 5 项、19 Gate 通过，network_calls=0、external_calls=0、Secret=0。

- 2026-08-21 queue/storage/ingestion/Pages/Supabase 本地安全复核：queue 恢复与失败归档统一拒绝 Junction/reparse point，ingestion 输出 artifact 增加 Junction 检查并在创建目录后复核，Supabase malformed URL 解析异常归一化；定向 70 项通过（13 项 Windows 链接能力跳过），完整 UAT Worker 134 项/前端 5 项、19 Gate 通过，network_calls=0、external_calls=0、Secret=0。

- 2026-08-21 report-0.2 missing_fields 归一化审计：`market_merge` 与 `rule_engine` 对字符串、空值和非字符串 fixture 统一过滤、去重、排序，Provider null 与输入缺失字段不会污染报告级汇总；新增 2 项回归，完整 UAT Worker 134 项（9 项环境跳过）/前端 5 项通过，网络/外部调用 0。
- 2026-08-21 UAT 编排摘要契约边界加固：`run_uat.py` 对结构化 Gate 摘要强制要求 `network_calls`/`external_calls`/`local_only` 三个字段，并拒绝缺失字段、布尔值、负数和非整数调用计数及非布尔值；malformed/partial summary 写入 `summary_contract_errors` 并继续完成全部 19 Gate，不因异常类型导致主编排器早停。新增 3 项编排回归，编排契约 14 项，完整 UAT Worker 134 项（9 项环境跳过）/前端 5 项通过，网络/外部调用 0。

- 2026-08-21 本地安全边界补强：queue/storage/ingestion/Pages 路径检查统一识别符号链接和 Windows Junction/reparse point；artifact allowlist、恢复/失败归档、Supabase URL/header、Pages 源树及 Secret/网络边界复核通过。定向安全回归 73 项（12 项环境跳过），完整 UAT Worker 132 项/前端 5 项、19 Gate 通过，网络/外部调用 0、Secret 0。

- 2026-08-21 report-0.2 本地追溯审计：`run-meta.json` 已纳入安全 artifact allowlist，前端静态契约检查报告页完整追溯展示和任务运行级共享投影；当前 UAT 基线为 Worker 130 项（9 项环境跳过）、前端 5 项，未调用外部服务。

- 2026-08-21 report-0.2 追溯投影复核加固：`shared_traceability()` 对行级 `missing_fields` 只保留非空标准字段名字符串并稳定去重排序；新增 Provider null→行级/报告级/四类 artifact 投影回归与成功 `run-meta.json` 逐值一致性检查。完整 UAT Worker 132 项（9 项环境跳过）、前端 5 项、19 Gate 通过，网络/外部调用 0。

- 2026-08-21 Supabase URL/Header 边界复核：transport 在 URL 解析前拒绝非字符串、空值和 ASCII/C1 控制字符，public key/access token 同步拒绝 ASCII/C1 控制字符；完整 UAT Worker 130 项（9 项环境跳过）、前端 5 项、19 Gate 通过，网络/外部调用 0、Secret 0。

- 2026-08-21 UAT/部署边界审计补强：`build_pages_demo.py`、`phase8_audit.py` 返回统一 JSON 摘要；`run_uat.py` 对 Worker loop、Phase 8、Pages 三个结构化 Gate 拒绝缺失摘要，防止仅凭退出码放行。编排契约当前 11 项，未部署、未取凭据、网络/外部调用 0。

## 当前验证快照

- 2026-09-03：完整 UAT Worker 207 项（12 项环境跳过）、前端 7 项（含 Node 26 场景），20/20 Gate、连续执行 63 项、UAT 编排契约 25 项、迁移 21 项、Pages 57 文件/11 项测试、文档 15 项通过；本地 network_calls=0、external_calls=0、Secret=0。Provider transport、一次性探测入口、响应头白名单观测和真实任务随机报告对象名已通过离线回归。
- Supabase 003 已执行；public schema 的七表和辅助函数匿名 HTTP 均为 401/42501。默认 Data API schema 为 api，客户端显式使用 public。迁移后双用户矩阵已复验：A/B 各自仅见授权店铺、任务和运行记录，跨店读取为 0，越权写入 HTTP 403，匿名读取 HTTP 401；私有 reports Storage 读取矩阵也已通过。
- 默认 demo 与显式 live 分离，Auth/任务/策略读取、私有对象绑定与 Gateway、Provider 预算/缓存和流水线注入的本地链路已通过验证；禁用未配置的上传/策略写入/真实私有报告前端。本地任务已全部收口，当前仅真实 Provider 外部 Gate 未完成。详情见 docs/acceptance/production-adapters-local.md。
- 本轮最终状态 BLOCKED_EXTERNAL：10 项本地任务当前回执有效、无 stale/running/runnable；仅真实 Provider 1 项外部 Gate 未完成。Supabase 双用户 RLS、私有 Storage 与 GitHub Pages 已有正式证据；心跳在终止态暂停，未将项目标记完成。

## 2026-08-21 安全边界审计收口

- `FileQueue.recover_processing()` 领取竞态现在正确解析并隔离冲突 task/run，不再因未初始化标识让连续 Worker 进入异常退避；新增回归覆盖检查后发生 pending 冲突的路径。
- Pages 构建在复制前拒绝源前端、golden artifact 和规则树中的符号链接，避免 `copy2/copytree` 跟随链接读取越过源边界；输出仍执行本地链接、外部 URL、断链和 Secret 审计。
- 本地安全定向回归和完整 UAT 通过：Worker 128 项（9 项环境跳过）、前端 5 项、19 Gate，网络/外部调用 0、Secret 0。

## 2026-08-21 UAT/部署审计编排与临时目录清理加固

- `run_uat.py` 固定执行 19 个本地 Gate；Worker loop、Phase 8 和 Pages 三个结构化边界 Gate 必须提供 JSON 摘要，再累计校验 `network_calls=0`、`external_calls=0`、`local_only=true`；失败、超时和启动异常仍继续收集完整 Gate 清单。
- 五组 UAT 临时输出目录由 `ExitStack` 托管，异常路径也自动清理；新增编排契约覆盖子 Gate 报告外部调用时拒绝。
- 编排契约 11 项；完整 UAT Worker 130 项（9 项环境跳过）、前端 5 项，Pages 19 文件、双入口 Worker、Phase 8、Smoke、迁移、编译和文档契约通过，网络/外部调用 0。

## 2026-08-21 report-0.2 四类 artifact 缺失语义补齐

- `shared_traceability()` 现在将报告级 `missing_fields` 同源投影到 `master-table.json`、`action-results.json`、`report-meta.json` 和成功运行的 `run-meta.json`；报告页展示汇总，任务页继续读取 `report-meta.json` 展示同一语义。
- `market_merge` 显式 Provider `null` 与 `rule_engine` 输入缺失字段的行级语义保持不变；前端/黄金 artifact 契约和数据字典已同步。定向报告 7 项、前端 5 项通过；完整 UAT Worker 128 项、前端 5 项、19 Gate 全部通过，网络/外部调用 0。

## 2026-08-21 本地安全审计补强

- 队列领取和 processing 恢复不再使用可能覆盖目标的 `replace()`，改为硬链接发布后删除源文件；目标冲突进入失败隔离，保留历史记录。
- artifact 的 task/run 中间目录拒绝符号链接，Supabase public key/access token 拒绝全部 HTTP 控制字符；任务页保留 `missing_fields` 缺失语义标记。
- 定向安全边界测试 46 项通过、9 项因 Windows 符号链接能力跳过；完整 UAT Worker 128 项、前端 5 项，19 个 Gate、双入口 loop、Pages、Phase 8、Smoke、迁移、编译均通过，网络/外部调用 0、Secret 0。

# Amazon-Keyword-Command-Center-YX · 项目记忆

## 2026-08-21 report-0.2 共享追溯投影复核

- 四类 artifact 的共享字段由 `worker.report.generate_report.shared_traceability()` 统一派生；`run-meta.json` 仅额外保留 `task_id`、`run_id`、`status`、`current_stage`，避免运行元数据与报告事实源发生漂移。
- `market_merge` 对 Provider 显式 `null` 保留原值并记录标准字段名到 `missing_fields`；`rule_engine` 合并输入/Provider 缺失字段，未知值不得触发防守或高机会动作。
- 数据字典、黄金 artifact、任务运行和前端契约已同步；本轮仅运行本地定向验证，网络/外部调用 0。

## 2026-08-21 UAT 编排与部署审计固定 Gate

- `run_uat.py` 固定执行并汇总 19 个本地 Gate；任何 Gate 失败、超时或启动异常都不会提前停止，报告校验 `gate_count`、`network_calls=0`、`external_calls=0` 和 `local_only=true`。
- `check_worker_loops.py` 实际运行 Python/PowerShell 两个入口各 2 个有限周期，要求 2 个心跳、`errors=0`、`stopped=false`、退出码 0；超时通过 `KWCC_LOOP_TIMEOUT_SECONDS` 有界调整。
- 本轮仅执行本地脚本、契约、进程和文档审计，未调用外部服务、凭据或部署。

## 2026-08-21 报告追溯审计

- Provider 市场快照显式返回 `null` 的字段必须保留为 `null` 并加入行级 `missing_fields`；前端仍统一显示 `—`，不得伪造 0 或货币值。
- 前端契约现在同时核对 action/meta/master 的输入文件、SHA-256、币种、对账、规则/配置/Provider snapshot 版本及完整 rows；任务页/报告页共享字段标记同步加强。
- 本轮仅执行本地代码、契约和 UAT，不调用真实 Provider、Supabase、Storage 或网络。

## 2026-08-21 本地 UAT/进程审计复核

- 新增本地安全边界回归并验证 UAT 编排；完整 UAT Worker 128 项、前端 5 项，UAT 编排契约 9 项，Phase 8 文档契约 13 项，网络/外部调用 0、Secret 0。
- Python 与 PowerShell Worker loop 各完成 2 个有限空队列周期和 2 个心跳，`errors=0`、未提前停止、退出码 0；Pages demo 输出 19 个文件且未发布。

## 2026-08-21 本地安全边界复核

- 本轮仅审查 worker/queue、worker/storage、输入解析、Supabase HTTP、Pages 输出和 Secret/网络静态边界。
- 已拒绝队列/存储/Pages 根目录符号链接，队列完成和 artifact 读取不跟随符号链接，输入路径任一父级符号链接即拒绝；Supabase HTTP 只接受无凭据、无路径、无查询/片段、无 CRLF 的 HTTP(S) origin；Pages 审计遇到符号链接后停止读取其目标。
- 工作区定向安全回归 39 项通过、7 项因 Windows 符号链接能力跳过；完整 UAT Worker 122 项、前端 5 项，网络/外部调用 0、Secret 0。
- 当前完整 UAT 为 Worker 130 项、前端 5 项；本轮边界修复后的连续执行与文档契约均已复核。

## 2026-08-21 UAT 防早停与启动异常回归

- `run_uat.py` 和 `check_worker_loops.py` 对 Gate 子进程启动 `OSError`、超时统一返回结构化失败，不会在前一 Gate 或进程启动异常后中断后续 Gate 收集。
- 新增 UAT 编排契约 5 项；完整 UAT Worker 113 项、前端 5 项，Python/PowerShell loop 各 2 轮、2 心跳、`errors=0`、未提前停止，Phase 8/Pages/连续执行/编译全部通过，网络/外部调用 0（历史记录）。

## 2026-08-21 report-0.2 四类 artifact 与前端一致性复核

- 报告页新增 `input_file` 追溯展示，与任务页共同展示输入文件、币种、对账和版本字段；页面仍只读取本地 master/report-meta artifact。
- golden artifact 契约现在明确要求 action/meta 的 `reconciliation_passed` 与 master 的 `reconciliation.passed` 相等；任务运行契约继续覆盖成功 run-meta 的共享字段。
- 定向报告、任务和前端契约通过；完整 UAT Worker 113 项、前端 5 项通过，网络调用 0、外部调用 0。

## 2026-08-21 report-0.2 运行元数据一致性审查

- `run-meta.json` 现在补齐 report-0.2 的共享追溯字段：schema、输入文件与 SHA-256、币种、对账结果、规则版本、配置版本和 Provider snapshot 版本；`task_id`、`run_id`、状态和阶段仍作为运行级字段保留。
- 任务页读取 `report-meta.json`、报告页读取 `master-table.json` 的前端契约与任务运行回归已补齐；未调用外部服务。
- bundled Python 下 Worker 15 项报告/任务定向回归、完整 UAT Worker 113 项和前端 5 项均已通过；系统 Python 缺少 `openpyxl` 仅是运行时选择问题，未调用外部服务。

## 2026-08-21 数据字典与报告追溯一致性回归

- `report-meta.json` 已补齐 `currency_code`，并与 master/action artifact 共享输入文件、输入 SHA-256、币种、对账、规则、配置和 Provider snapshot 版本；对账状态与 master 一致。
- 新增数据字典说明、生成器回归、golden artifact 回归和前端任务页跨 artifact 契约；`run_uat.py` 仅统计 Worker 与前端测试套件，避免 Pages 测试覆盖汇总。
- 最新完整 UAT 为 Worker 113 项、前端 5 项，Secret value 0、网络调用 0、外部调用 0。

## 2026-08-21 安全审计与输入边界回归

- 本地 allowlisted artifact 写入禁止覆盖已有 JSON，非法队列归档遇到同名失败记录时使用递增后缀，保留历史证据。
- 输入解析拒绝符号链接，并将目录/权限等 `OSError` 归一化为 `INPUT_INVALID` ingestion 失败；Supabase HTTP Base URL 拒绝凭据、查询/片段和 CR/LF header 注入。
- 定向安全回归 34 项通过（符号链接能力受环境限制而跳过）；完整 UAT Worker 113 项、前端 5 项通过，迁移/Pages/Phase 8/连续 Worker Gate 通过，Secret value 0、网络调用 0。

## 2026-08-21 UAT 编排与连续入口进程 Gate

- `scripts/check_worker_loops.py` 实际启动 Python 与 PowerShell 连续 Worker，各执行 2 个有限空队列周期；两者均输出 2 个心跳、退出码 0、错误 0。
- `scripts/run_uat.py` 纳入该进程 Gate，并输出 Worker/前端结构化测试计数；当前完整 UAT 为 Worker 113 项、前端 5 项，Secret value 0、网络调用 0、外部调用 0。

## 2026-08-21 Provider/规则安全回归

- `ProviderContract` 现在在响应型和异常型 429 的每次实际尝试发生时统一累计 `usage.rate_limited`，包括达到最大重试次数后的最终失败；5xx 仍按有界 `RetryPolicy` 重试并只记录最终失败。
- MCP `tools/list` 继续复用 Provider 统一重试、实际调用和失败统计；新增最终 429 回归。规则引擎保持确定性，AI 字段只读且不能覆盖 `action_group`。
- 定向 Provider/MCP/规则测试 26 项、完整 UAT Worker 105 项和前端 3 项通过，网络调用 0。

## 2026-08-21 业务验收与报告前端追溯回归

- `frontend/report.js` 按 report-0.2 的 `currency_code` 动态格式化金额，并展示 schema、币种、输入 SHA-256、Provider snapshot 和对账状态；缺失值仍保持 `—`。
- 报告周期币种同步来自 artifact；筛选入口覆盖 `scale_up`、`defend_rank`、`hold_steady`、谨慎观察、优化、`stop_loss`/`reduce_or_pause` 和 `data_missing`；任务页展示同一 report-meta 的追溯字段。
- 前端契约增加 report-0.2 顶层/行级追溯字段、缺失值语义、全部筛选标记和动态币种标记检查；无效数值展示为 `—`，导出对象 URL 延迟释放；完整 UAT Worker 105 项、前端 3 项通过，网络调用 0。

## 2026-08-21 本地部署与运行验收复核

- 当前 Phase 8 计划数量已与实际 UAT 对齐：Worker 101 项、前端 1 项；旧数量仅保留在历史记录。
- `phase8_audit.py` 同时检查 Python `run_worker_loop.py` 与 Windows `run_worker_loop.ps1`；监督契约 13 项、完整 UAT、Pages 安全审计和 PowerShell 空队列进程验证通过，网络调用 0。

## 2026-08-21 Worker 队列恢复与进程停止可靠性加固

- 启动恢复遇到 pending/processing 同名冲突时，保留 pending 作为重试候选，隔离遗留 processing 为 `RESULT_CONFLICT`，避免连续 Supervisor 永久重复恢复异常。
- 连续 Python 入口注册 SIGINT/SIGTERM，停止请求会设置 `stop_event` 并输出可观测事件；不改变外部调用边界。
- 队列/运行时定向测试 23 项、完整 UAT Worker 97 项和前端 1 项通过；PowerShell 失败后续任务进程验证通过，网络调用 0。

## 2026-08-21 数据与规则质量回归加固

- 报表解析器对空字符串、短横线、`N/A`、`NULL` 等缺失数值保持 `null` 语义，并在行级 `missing_fields` 留痕；派生比率不会用缺失值计算。
- `action-results.json` 现在保留输入文件/哈希、币种、对账结果以及规则、配置、Provider 快照版本，动作结果可独立追溯。
- 当前 golden report 已重生成，定向数据与规则回归 21 项通过；完整 UAT Worker 97 项、前端 1 项通过；不调用网络、Provider 或 AI。

## 2026-08-21 Phase 8 发布边界审计加固

- 本地 Phase 8 审计现在实际构建临时 Pages demo，并核对精确 19 文件 allowlist、HTML 引用边界、Secret-like 内容、外部 URL、符号链接和发布标记。
- 审计同时要求 Phase 8 文档、连续监督契约、UAT、前端语法检查和部署文档存在；不联网、不发布、不使用凭据。

> 本文件是 Codex / Claude Code / Worker / 豆包 / 其他 Agent 进入项目时必须先读取的长期项目记忆。
>
> 核心原则：**规则做判断，参数定边界，数据做证据，AI 做解释。**

> v1.4 修订重点：吸收 Claude Code 计划审核意见，补齐 `action_group → ui_conclusion → UI颜色` 映射、加投/防守语义拆分、五色结论+灰色数据状态统一术语、规则黄金样例、Provider 待验证假设、规则回滚与可复现定义；同时冻结当前部署决策：**前期不做 ICP 备案，先按未备案路线运行，后期备案完成后只迁移前端托管/域名，不重写数据层、规则引擎与 Worker。**

## 1. 项目定位

项目中文名：**关键词作战总表**。

项目不是单纯的关键词词库、广告报表或排名查询工具，而是一个以“搜索词表现 + 自然排名变化”为核心驱动的 Amazon 关键词运营决策系统。

核心闭环：

```text
广告真实表现
+ 市场机会数据
+ 自然排名
+ 产品阶段 / 利润边界
        ↓
确定性规则引擎
        ↓
投放结论 / 运营动作
        ↓
AI 解释原因与下一步
        ↓
后续复盘：广告动作 → 自然位 → 自然单 → 整体利润
```

项目目标不是“把 ACOS 做得越低越好”，而是判断：

- 哪些词值得加投；
- 哪些词必须防守；
- 哪些词保持即可；
- 哪些词需要谨慎试投；
- 哪些词应先优化 Listing / 价格 / 广告结构；
- 哪些词证据已经充分，应停止投放或止损；
- 哪些词数据不足，暂时不能强判。

---

## 2. 指令优先级

出现冲突时按以下优先级执行：

```text
用户最新明确指令
>
PROJECT_MEMORY.md（本文件）
>
PROJECT_PLAN.md
>
已确认的规则定义 / 当前生效配置
>
DESIGN-airtable.md（仅 UI 视觉与交互）
>
分阶段验收与优化指南 / 原实施计划
>
旧版教程、历史 Prompt、历史示例值
```

旧文档中的数值如 20%、30%、45%、20 点击、$50、难度 85、Top3 60%/80% 等，**只能作为默认模板示例**，不得视为固定规则。

---

## 3. 四角色架构

继续保持四角色：

```text
┌─────────────────────────────┐
│ 前台 Web                     │
│ 登录 / 任务 / 策略 / 报告    │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ 中转台                       │
│ Auth / Task / Config / RLS   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Worker                       │
│ Parse / Provider / Rule / AI │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ 文件柜                       │
│ Raw / JSON / Report / Cache  │
└─────────────────────────────┘
```

强约束：

- 前台与 Worker 不直接耦合；
- Worker 只通过任务与配置数据工作；
- Provider Key、万能钥匙、OSS Secret 只存在服务端；
- 前端只允许公开型 Key；
- V1 不为了“架构先进”拆微服务。

### 3.1 当前部署路线（已拍板）

当前决定：**前期不做 ICP 备案，后期再迁移到备案域名。**

因此 V1 前期默认按“未备案路线”施工：

```text
前台：GitHub Pages（默认 Pages 地址优先；如后续需要，可再绑定未备案自定义域名）
中转台：Supabase / 等效 Auth + Task + Config + RLS
Worker：现有云服务器，仅跑后台任务，不通过大陆服务器 80/443 对外提供网页
文件柜：保持私有；报告必须通过登录后的受控读取链路访问
```

未备案阶段禁止为了“看起来像正式站点”而把前台直接放到大陆服务器常用 Web 端口。

如果最终文件柜使用 OSS 私有桶，Phase 0 / Phase 8 必须确认一条**不依赖已备案域名**的受控报告读取链路；可以采用现有中转层、Supabase 私有 Storage / 签名能力或其他已审计方案，但不得把整桶改为公共读，也不得把长期公共链接当正式鉴权。

备案完成后的迁移原则：

```text
只替换：前端托管位置 / 自定义域名 / HTTPS / CORS Origin / Auth Redirect URL / 备案页脚
尽量不动：Task schema / Rule Engine / Config / Provider / Worker / Golden Tests / 报告数据模型
```

后期迁移视为独立 Deployment Migration，不得借备案之名重写核心业务。

---

## 4. 项目最重要的业务约束

### 4.1 规则与参数必须分开

规则回答：**怎么算。**

参数回答：**边界是多少。**

禁止：

```python
if clicks >= 20:
    stop_loss()
```

必须类似：

```python
if clicks >= config.stop_loss.zero_order_clicks:
    stop_loss_review()
```

所有数值条件必须从 `current_effective_config` 读取。

### 4.2 可配置业务规则 vs 不可配置数据定义

系统必须把“业务阈值”和“数据定义”分成两层。

**允许在策略中心配置的，是业务边界，例如：**

- 目标 / 容忍 / 盈亏平衡 ACOS；
- 0 单点击 / 花费止损阈值；
- 自然位防守区间；
- 高 / 低搜索量分位；
- 高 / 低难度线；
- Top3 集中度阈值；
- 趋势窗口与趋势变化阈值；
- CPC / 建议竞价比例；
- 证据等级边界；
- 五色展示顺序与组内主排序字段。

**禁止用户修改的，是数据定义与系统不变量，例如：**

```text
ASIN 格式定义
CTR  = clicks / impressions
CPC  = spend / clicks
CVR  = orders / clicks
ACOS = spend / sales
ROAS = sales / spend
销售额 = 0 时 ACOS = —
未上榜 / Provider 未返回 = —，不是 0
搜索词聚合 = 原始量 SUM 后重新计算比率
原报表自带比率不得求和或平均
```

这些定义只能通过代码版本 / schema 版本变更，不能进入普通策略配置。

### 4.3 AI 不负责最终动作

AI 可以：

- 解释规则结果；
- 把原因写成人话；
- 生成检查清单；
- 标明缺失数据；
- 提议新增规则供人工确认。

AI 不可以：

- 修改 `action_group`；
- 自己猜产品阶段；
- 自己修改 ACOS / CTR / CVR / CPC 门槛；
- 把缺失值当 0；
- 因为 ABA 上升就直接加投；
- 因为 ACOS 高就直接止损；
- 在规则未覆盖时强行下结论。

**结论写保护机制：**

- `action_group`、`ui_conclusion`、`rule_hits`、`effective_config_version` 只能由规则引擎写入；
- AI 输入为这些字段的只读副本；
- AI 输出 schema 中不得包含动作字段；
- AI 只允许写 `ai_explanation`、`ai_next_action_text`、`ai_status` 等解释字段；
- 存储层 / JSON 生成器再次过滤 AI 输出，发现动作字段直接丢弃并记审计日志；
- AI 超时、429、格式错误或不可用时，报告照常生成，直接展示规则引擎的 `rule_hits` / `reason_facts`，AI 状态标记为不可用，**不得阻塞任务完成**。

### 4.4 确定性

同一份：

- 原始数据；
- `rule_version`；
- `config_version`；

重复运行两次，最终动作必须完全一致。

若不一致，视为规则系统缺陷，不得让 AI “解释掉”。

### 4.5 Unknown 不等于 0

以下状态必须严格区分：

```text
0 = 确认值为零
— / 未返回 = Provider 没有数据或未上榜
数据缺失 = 本次任务无法获取
证据不足 = 有数据但不足以下强判断
```

不得用 0 代替未知。

---

## 5. 数据优先级

判断优先级固定：

```text
P0  Amazon 广告搜索词报表：自己的真实账户表现
P1  产品阶段 / 利润边界 / 当前策略
P2  自然排名与排名变化
P3  市场机会：搜索量、难度、ABA、Top3、建议竞价
P4  AI 解释
```

外部市场数据只用于辅助机会判断，不能覆盖自己的真实广告表现。

---

## 6. 广告报表解析规则

广告报表解析属于**确定性代码**，禁止让大模型肉眼汇总。

### 6.1 动态表头

不能假设第一行一定是表头。

在前若干行中寻找同时包含“搜索词”和“展示/曝光”语义的行。

### 6.2 动态认列

按列名语义匹配，不按固定列号。

至少识别：

- 客户搜索词；
- 展示；
- 点击；
- 花费；
- 销售额；
- 订单。

### 6.3 数值清洗

统一处理：

- `$`；
- `,`；
- `%`；
- 空格；
- 空值；
- Excel 数值 / 文本混合。

### 6.4 搜索词聚合

同一搜索词可能来自多个 Campaign / Ad Group / Match Type / Target。

必须按“客户搜索词”聚合以下原始量：

```text
展示 SUM
点击 SUM
花费 SUM
销售额 SUM
订单 SUM
```

再重新计算：

```text
CTR  = 点击 / 展示
CPC  = 花费 / 点击
CVR  = 订单 / 点击
ACOS = 花费 / 销售额
ROAS = 销售额 / 花费
```

禁止对报表自带比率求和或平均。

销售额为 0 时：

```text
ACOS = —
```

不是 0，也不是 Infinity。

### 6.5 自动对账与正式公式

每次解析必须生成 `reconciliation.json`，至少包括：

- 原始行数；
- 有效行数；
- 去重搜索词数；
- 原始表合计；
- 聚合表合计；
- 每个指标的差值；
- 比率重算抽检结果；
- 重复解析一致性结果；
- `passed` / `failed`。

正式对账定义：

```text
SUM(raw.impressions) == SUM(aggregated.impressions)
SUM(raw.clicks)      == SUM(aggregated.clicks)
SUM(raw.orders)      == SUM(aggregated.orders)
ABS(SUM(raw.spend) - SUM(aggregated.spend)) <= 0.01
ABS(SUM(raw.sales) - SUM(aggregated.sales)) <= 0.01
```

其中：

- 展示、点击、订单是整数，要求严格一致；
- 花费、销售额以货币最小精度对账，计算容差 `0.01`，报告 UI 可格式化显示为 `0.00`；
- CTR / CPC / CVR / ACOS / ROAS 必须由聚合后的原始量重新计算；
- 比率内部计算至少保留 `1e-6` 精度，展示层再按 UI 规则格式化；
- 同一文件、同一解析器版本连续解析两次，规范化后的聚合结果必须逐字段一致。

强约束：

> 任意关键原始量对账失败，任务立即停止，不调用付费 Provider，不进入规则引擎，不生成正式报告。

### 6.6 当前演示报表回归基线

文件：`商品推广_搜索词_报告_LED演示(1).xlsx`

当前样例实际结构：

- Sheet：`SP搜索词报告`；
- 数据范围：`A1:T119`；
- 原始数据行：118；
- 去重“客户搜索词”：91；
- 有重复搜索词：16 个；
- 单个搜索词最多出现：4 行。

原始量总计：

| 指标 | 基线值 |
|---|---:|
| 展示量 | 1,230,627 |
| 点击量 | 9,045 |
| 花费 | 5,123.10 |
| 7天总销售额 | 20,982.29 |
| 7天总订单数 | 1,578 |

可作为单词聚合测试的搜索词：`led light`

- 原始出现 4 行；
- 展示 15,216；
- 点击 131；
- 花费 82.96；
- 销售额 408.42；
- 订单 30；
- 重算 CTR ≈ 0.8609%；
- 重算 CVR ≈ 22.9008%；
- 重算 ACOS ≈ 20.3124%。

这些基线用于回归测试，不是业务阈值。

正式落地要求：

- 将该文件复制 / 固化到 `data/fixtures/`；
- 标记为 `fixture_type: golden`；
- 记录来源、是否脱敏、文件 SHA-256、解析器版本；
- golden 文件不得被业务代码修改；
- Phase 1 人工抽样词必须固定进测试用例，避免每次“随机抽 3 个”造成验收漂移。

---

## 7. 西柚 / ABA 字段语义

Worker 先 `tools/list` 自发现远程 MCP 工具，不硬编码猜接口名。

字段语义：

- `or`：自然位；
- `sp` / `sb` / `sbv`：广告位；
- `sor` / `oor`：推荐等其他位置；
- `totalRank`：页面绝对位次。

自然排名：

> 在 `ranks` 中位置码为 `or` 的记录取最小 `totalRank`。

广告排名：

> 在 `sp/sb/sbv` 中取最小 `totalRank`。

无对应排名记录：

```text
显示 —
```

不是 0，不是错误。

注意语义：

- `traffic` = 西柚流量热度估值，不等于 ABA 点击份额；
- ABA `topAsins` 才是前三 ASIN + `clickShare` / `conversionShare`；
- `trafficRatio` = 该词占这个 ASIN 自身流量的比例；
- `trafficAcquisitionRate` = 该 ASIN 吃掉该词多少流量；
- ABA 数据存在滞后，使用上一个完整周期；
- 低流量词断档显示 `—`。

Provider 纪律：

- 先小样；
- 429 识别为限流；
- 指数退避；
- 单次最大自动重试 2 次；
- 有缓存不重复付费抓取；
- 每任务记录调用量。

Provider 唯一事实来源必须落到 `docs/provider-semantics.md`，至少定义：

- Provider / MCP 实际工具名与 schema（来自 `tools/list`，不靠猜）；
- 每个字段原始名称、标准化名称、单位、空值语义；
- 搜索量、难度、建议竞价、Top3、ABA 趋势、自然位、广告位的来源；
- 自然位来源固定为西柚关键词-ASIN分析：`ranks` 中 `or` 的最小 `totalRank`；
- 广告位来源固定为 `sp/sb/sbv` 的最小 `totalRank`；
- ABA 使用上一个完整周期，不把最近未完整周期当 0；
- 缓存 TTL / 强制刷新策略；
- 429 重试策略与最大自动重试次数；
- Provider 字段缺失时的 `missing_fields` 映射。

缓存 TTL 本身属于工程配置，可在 Phase 0/2 根据实际成本和更新频率确定；未经确认不得散落写死在多处代码中。

---

## 8. 当前产品阶段规则

系统至少支持：

- 新品期；
- 上升期；
- 稳定期；
- 清货期；
- 季节性老品重启。

在自动阶段判定尚未正式验收前：

> **产品阶段必须由用户手动指定。**

阶段原则：

### 新品期

允许较高的阶段容忍 ACOS，重点是买流量、拿第一批转化、建立相关性、推动自然位。

### 上升期

要求 ACOS 随数据成熟逐步下降，广告从“买数据”转向“放大有效词”。

### 稳定期

重点是利润与自然位平衡，使用当前配置中的目标 ACOS、容忍 ACOS、盈亏平衡 ACOS。

### 清货期

重点转为库存周转与低成本清货，不把冲排名作为主要目标。

### 季节性老品重启

不直接继承上一季动作，重新验证搜索量、CPC、CVR、竞争格局、自然位和趋势。

---

## 9. 关键枚举与数据字典约束

最终枚举值以版本化的 `docs/data-dictionary.md` / rule definitions 为唯一事实来源。V1 至少包含：

```text
evidence_level:
  no_ads | insufficient | preliminary | sufficient

market_opportunity:
  unknown | low | medium | high

organic_defense_level:
  unknown | none | watch | defend | core_defend

acos_pressure:
  unknown | healthy | watch | high | over_break_even

ai_status:
  not_requested | success | degraded | unavailable

action_group:
  scale_up | defend_rank | hold_steady | cautious_test | continue_observation | optimize_listing | optimize_bid | optimize_structure | stop_loss | reduce_or_pause | data_missing

ui_conclusion:
  add | defend | keep | cautious | optimize | stop_loss | data_missing

ui_color:
  green | cyan | yellow | orange | red | gray
```

`missing_fields` 必须是标准字段名数组，禁止自由文本替代；至少可覆盖：

```text
search_volume
competitive_difficulty
suggested_bid
aba_trend
top3_asins
top3_click_share
organic_rank
ad_rank
traffic_ratio
traffic_acquisition_rate
```

枚举新增、删除、改名必须升级 schema / rule 版本并有迁移说明。

---

## 10. 正式业务判断框架

### 10.1 先看产品阶段，再看 ACOS

ACOS 不能脱离阶段和利润判断。

系统必须读取：

- 目标 ACOS；
- 容忍 ACOS；
- 盈亏平衡 ACOS；
- 加码 ACOS 上限；
- 优化 ACOS 起点；
- 允许战略亏损线。

这些参数全部可配置。

### 10.2 广告证据必须分级

分级名称可保持：

- 无投放；
- 样本不足；
- 初步信号；
- 证据充分。

边界来自配置，而不是代码常量。

规则方向：

- 未达到初步信号：继续观察 / 小幅优化；
- 达到初步信号但未充分：优先诊断；
- 有订单时，订单证据优先于纯点击信号；
- 达到当前 0 单止损证据且仍 0 单：进入强制止损复核。

### 10.3 自然排名进入防守区时提高战略价值

自然位进入当前配置的核心防守区（例如模板可配置 Top3 / Top5 / Top10）时，进入“加投 / 保持 / 防守”复核。

但防守必须同时满足：

- ACOS 未突破当前可承受范围；
- 利润底线可承受；
- 预算可承受；
- CPC 不无限抬高。

如果自然位已经靠前、CPC 接近建议竞价上限、ACOS 无继续改善空间，优先动作：

> **守住不加价。**

自然位防守不能突破硬性成本边界。

### 10.4 市场机会用于决定“值得不值得继续投入”

市场机会至少结合：

- 搜索量；
- 难度；
- Top3 点击集中度；
- ABA 趋势。

所有分位、集中度、趋势变化率和观察周期均可配置。

重要：

- 市场高机会 + 广告表现暂差：优先诊断，不轻易判死；
- 市场低机会 + 证据充分且表现差：更倾向缩减 / 止损；
- 无广告证据 + 市场机会可接受：小预算测试；
- ABA 趋势不能单独触发加投。

### 10.5 0 单止损必须有“证据阈值”

0 单不能一刀切。

必须同时看：

- 点击证据；
- 花费证据；
- 相关性；
- Listing 承接；
- 市场机会；
- 当前产品阶段。

达到当前配置的强止损条件才进入“停止投放 / 止损”。

### 10.6 多投放对象内耗单独诊断

同一搜索词可能同时来自：

- Auto；
- Broad；
- Phrase；
- Exact；
- 多个 Campaign / Ad Group。

系统需要识别可能的：

- 自相竞价；
- Broad 抢 Exact；
- CPC 被自己抬高；
- 订单数据分散。

这类问题不能只按 ACOS 判定。

---

## 11. 正式展示结论、动作映射与排序规则

### 11.1 统一术语：五色作战结论 + 灰色数据状态

正式业务结论仍使用**五种颜色**：

1. 绿色：加投 / 防守；
2. 青色：保持；
3. 黄色：谨慎投放；
4. 橙色：优化；
5. 红色：停止投放 / 止损。

**灰色“数据待补”不是第六种业务结论，而是数据状态。**

“加投”和“防守”虽然同为绿色，但在底层必须是两个不同 `ui_conclusion`，因为：

- `add` = 主动扩大有效流量；
- `defend` = 为已有自然位 / 核心位置做防守；
- 两者成本边界、触发条件、后续动作不同；
- 前端可以同色显示，但规则、审计、测试、导出不得合并为一个枚举。

### 11.2 action_group → ui_conclusion → UI 颜色映射

以下为 V1 默认映射，Phase 0 核对现有实现，Phase 2 开工前冻结并版本化到 rule definitions：

| action_group | ui_conclusion | UI | 业务含义 |
|---|---|---|---|
| `scale_up` | `add` | 绿色 | 有增量机会，允许主动加投 |
| `defend_rank` | `defend` | 绿色 | 核心自然位 / 关键词需要守位 |
| `hold_steady` | `keep` | 青色 | 当前表现稳定，保持策略 |
| `cautious_test` | `cautious` | 黄色 | 小预算、小幅度验证 |
| `continue_observation` | `cautious` | 黄色 | 证据不足，继续观察 |
| `optimize_listing` | `optimize` | 橙色 | 先修 Listing / 转化承接 |
| `optimize_bid` | `optimize` | 橙色 | 出价 / CPC / 成本需要优化 |
| `optimize_structure` | `optimize` | 橙色 | Campaign / Match Type / 内耗结构优化 |
| `stop_loss` | `stop_loss` | 红色 | 已满足强止损条件 |
| `reduce_or_pause` | `stop_loss` | 红色 | 缩量 / 暂停 / 进入止损执行清单 |
| `data_missing` | `data_missing` | 灰色状态 | 关键数据不足，禁止强判 |

映射关系必须通过版本化定义加载，禁止散落在前端、Prompt、SQL 和 Worker 多处各写一份。

### 11.3 主表默认排序

当前正式展示组顺序：

```text
绿色（add / defend）
→ 青色（keep）
→ 黄色（cautious）
→ 橙色（optimize）
→ 红色（stop_loss）
→ 灰色状态（data_missing）
```

绿色组内部 `add` 与 `defend` **不再额外写死谁先谁后**，默认一起按市场搜索量从高到低排列。

同一展示组默认按：

```text
市场搜索量 DESC
→ 广告花费 DESC
→ keyword 规范化字符序 ASC
```

目的：先看到需要守住排名和具备投入价值的核心机会词，再看稳定词、观察词、优化词，最后集中处理止损词。

### 11.4 排序可配置，但稳定 tie-break 不可缺失

“展示组顺序 + 组内搜索量降序”是当前默认业务策略，可在策略中心调整；稳定性兜底必须存在。

默认完整键链：

```text
ui_color_group_order ASC
→ market_search_volume DESC（缺失值最后）
→ ad_spend DESC
→ normalized_keyword ASC
```

`normalized_keyword` 的确定性规范：

1. Unicode 统一做 NFC 归一化；
2. 排序比较使用 Unicode code point / 明确定义的 deterministic comparator；
3. 不依赖操作系统 locale；
4. 英文字母大小写比较规则在代码中固定并有测试；
5. 原始 `keyword` 仍原样保存，规范化值只用于稳定排序 / 去重辅助，不覆盖用户原词。

前两层属于可配置业务排序；后两层属于稳定性兜底。缺失市场搜索量放最后，不得把 `—` 当 0。

### 11.5 规则行为黄金样例（Phase 2 入场券）

以下样例只描述**关系**，不写死任何业务阈值；所有边界来自 `current_effective_config`：

| Case | 关键输入事实 | 期望 action_group / 结论 |
|---|---|---|
| G01 | 核心必需字段缺失，无法形成证据 | `data_missing → data_missing` |
| G02 | 广告证据充分、0 单且越过强止损边界 | `stop_loss → stop_loss` |
| G03 | 自然位进入核心防守区、成本健康、利润可承受 | `defend_rank → defend` |
| G04 | 自然位需防守，但成本已越过不可突破底线 | 不得 `defend`；按止损/优化规则分流 |
| G05 | 证据充分、表现健康、市场机会高、存在扩量空间 | `scale_up → add` |
| G06 | 表现健康但无明确扩量或防守信号 | `hold_steady → keep` |
| G07 | 证据不足、市场机会可接受 | `cautious_test` 或 `continue_observation → cautious` |
| G08 | 市场机会高、广告差，但未达到硬止损，承接存在问题 | `optimize_listing/optimize_bid → optimize` |
| G09 | 多 Campaign / Match Type 出现明显内耗 | `optimize_structure → optimize` |
| G10 | 市场机会低、广告证据充分且持续低效，触发当前止损规则 | `reduce_or_pause/stop_loss → stop_loss` |
| G11 | 无广告历史但市场机会满足当前测试条件 | `cautious_test → cautious` |
| G12 | AI 文案建议“加投”，但规则结果为止损 | 规则结果保持 `stop_loss`，AI 输出不得改动作 |

这些样例必须转成自动化 golden rule cases；任何规则版本升级都输出旧结论/新结论/变化原因。


---

## 12. 策略中心：所有数值可视化配置

策略中心是核心基础设施，不是附属页面。

入口：

```text
[策略设置]
```

建议分区：

```text
产品阶段
ACOS / 利润
广告证据
止损规则
转化诊断
市场机会
自然排名防守
排序规则
高级设置
```

### 12.1 必须可配置的主要参数

#### 产品阶段

- 新品期时间窗口；
- 上升期时间窗口；
- 稳定期条件；
- 清货期条件；
- 季节性重启观察窗口。

#### ACOS / 利润

- 目标 ACOS；
- 容忍 ACOS；
- 盈亏平衡 ACOS；
- 加码 ACOS 上限；
- 优化 ACOS 起点；
- 战略亏损容忍线。

#### 广告证据

- 样本不足点击上限；
- 初步信号点击阈值；
- 证据充分点击阈值；
- 初步订单阈值；
- 充分订单阈值；
- 0 单止损点击；
- 0 单止损花费。

#### 转化诊断

- CTR 低值；
- CVR 低值；
- CPC 过高判断比例；
- CPC / 建议竞价上限比例。

#### 市场机会

- 高搜索量分位；
- 低搜索量分位；
- 低难度线；
- 高难度线；
- Top3 开放阈值；
- Top3 集中阈值；
- 趋势下滑阈值；
- 趋势观察周期。

#### 自然排名

- Top3 / Top5 / Top10 等防守区间；
- 最大可接受防守 ACOS；
- 最大可接受防守 CPC；
- 排名变化观察周期。

#### 排序

- 五色结论顺序；
- 组内排序字段；
- 订单权重；
- ACOS 权重；
- 搜索量权重；
- 自然排名权重；
- 市场机会权重；
- 花费风险权重。

### 12.2 控件类型

- 百分比：数字输入框 + `%`；
- 点击 / 订单 / 排名：整数输入；
- 花费 / CPC：金额输入 + 币种；
- 时间窗口：数字 + 天/周，或下拉；
- 规则启停：Toggle；
- 排序顺序：拖拽 / 上下移动；
- 策略模板：下拉 + 复制。

### 12.3 配置覆盖优先级

```text
本次任务临时覆盖
>
ASIN 专属配置
>
产品阶段配置
>
店铺配置
>
全局默认配置
```

最终合并为：

```text
current_effective_config
```

Worker、规则引擎、AI 全部只读这一份最终配置。

### 12.4 设置窗口必须有的按钮

至少：

```text
[保存]
[取消]
[恢复默认]
[复制当前策略]
[另存为模板]
[应用到本 ASIN]
[应用到多个 ASIN]
[查看修改记录]
[试算影响]
```

### 12.5 即时试算

修改参数时不立即覆盖正式配置。

先显示：

- 哪些动作组数量变化；
- 哪些关键词结论发生变化；
- 哪些关键词从加投变优化 / 从优化变止损；
- 影响的预计花费范围（若数据支持）。

用户确认保存后才生成新的 `config_version`。

---

## 13. 规则冲突优先级

冲突时建议按：

```text
硬性止损 / 利润底线
>
关键数据完整性
>
广告证据等级
>
产品阶段
>
自然位防守价值
>
市场机会
>
优化 / 诊断
>
加投 / 保持
>
小预算测试 / 继续观察
>
低优先级
```

补充：

- 自然位防守不能突破硬性成本边界；
- 市场高机会不能覆盖真实的强止损证据；
- 数据缺失时禁止强行判定；
- 证据不足时禁止激进扩量或激进否定。

---

## 14. 豆包 / AI 最终解释格式

AI 只接收规则引擎已经产出的：

- 动作；
- 触发规则；
- 关键指标；
- 市场补充；
- 缺失字段。

推荐输出结构：

```text
【动作】+【最关键广告证据】+【市场/自然位补充】+【下一步】
```

AI 不得重新计算并推翻动作。

---

## 15. 报告模块

当前目标报告可分六个模块：

1. 关键词作战总表；
2. 自然位标杆；
3. 否定词清单；
4. 竞对对比；
5. 图片与卖点诊断；
6. 广告诊断与优化方案。

V1 最优先保证：

> **Module 01 关键词作战总表完全可信、可配置、可复现。**

---

## 16. UI 设计记忆

正式前端必须读取 `DESIGN-airtable.md`。

当前设计基准：

- 白色画布；
- 深墨色主文字 / 主按钮；
- 大量留白；
- 主要 CTA 使用接近黑色；
- 大卡片可用 coral / forest / dark 等签名色块；
- 不使用 SaaS 常见的渐变、aurora、mesh 背景；
- 主要圆角约 10–12px；
- 表格是桌面端核心工作界面；
- 宽表固定列宽 + 横向滚动；
- 窄屏允许左右滑，不把列挤成竖条；
- 视觉强调优先用字号 / 色块，不滥用粗体。

主表必须支持五色业务结论筛选，并能单独筛选灰色“数据待补”状态。

---

## 16.1 Phase 0 待验证假设

以下在 v1.4 中不再视为“永久已知事实”，Phase 0 必须逐项验证并写进 `PROJECT_STATUS.md` / decisions：

- 西柚 MCP 的当前工具名、schema、字段语义、限流与成本；
- 西柚是否作为 V1 唯一市场/排名 Provider，是否需要备用或手动兜底；
- AI 解释 Provider（当前倾向豆包）具体模型、超时、成本与降级；
- Phase 6 视觉 Provider 的具体模型与隐私边界；
- `DESIGN-airtable.md` 是否存在、版本是否与当前五色+灰色术语一致；
- 现有项目真实代码位置、技术栈和可复用率；
- 未备案阶段最终报告的私有读取链路。

## 16.2 可复现与规则回滚

“可复现”定义为：在同一 `input_hash + provider_snapshot_version + rule_version + config_version` 下，**所有 `rule_owned` 业务字段与排序结果一致**。

不要求 `generated_at`、日志时间、trace id、AI 自然语言措辞等非规则字段字节级一致。

规则必须支持版本回滚：

- 新规则发布生成新的 `rule_version`；
- 旧版本不可覆盖删除；
- 发现规则缺陷时可将 active rule pointer 回退到已验证版本；
- 回滚后新运行使用回退版本，历史 run 保留原 `rule_version`；
- 规则回滚与配置回滚分开记录，不得混为同一次变更。

---

## 17. 安全与文件访问

正式生产方案：

- 原始广告报表私有；
- 生成报告默认私有；
- 报告通过登录鉴权后的受控读取 / 短时访问能力呈现；
- 不把“公共读 + 随机文件名”作为正式生产安全方案；
- 教程中的对象公共读仅可作为早期连通性测试思路，不作为最终验收；
- RLS / 等效权限必须开启；
- `.env`、密钥库、Provider Secret 不进 Git；
- CORS 只允许当前明确前端 Origin；未备案阶段允许 GitHub Pages Origin，后期迁移备案域名时同步替换；
- 删除、权限、密钥、核心安全方案变更必须明确授权。

---

## 18. 付费接口纪律

任何 Provider 新接入或规则大改：

```text
先 10～30 个关键词小样
→ 验收
→ 再全量
```

每次任务执行前记录：

- 关键词数量；
- 预计 Provider 调用量；
- 缓存命中；
- 新增调用量；
- 最终实际调用量；
- 失败 / 429 次数。

禁止无限重试。

---

## 19. 任务幂等、数据生命周期与审计

### 19.1 任务 / 重跑语义

- `task_id` 表示一次用户提交；上传文件发生变化 = 新任务；
- 每次实际执行生成独立 `run_id`；
- “重新分析”不覆盖历史运行，创建新 `run_id`，通过 `previous_run_id` 关联上一轮；
- 同一 `task_id + input_hash + rule_version + config_version + provider_snapshot_version` 的规则结果必须可复现；
- 已存在有效 Provider 缓存时默认复用，不因重跑重复付费；
- 重跑不得产生相互覆盖、来源无法追溯的 JSON / 报告文件。

### 19.2 V1 币种规则

V1 一个任务只允许一个币种。

- 报表若能识别币种，则写入 `currency_code`；
- 同一任务发现多币种，立即报错并停止，不做自动汇率换算；
- 不允许把 USD / EUR / GBP 等金额直接相加；
- 多币种 / 汇率属于后续版本能力。

### 19.3 数据保留默认策略

默认建议值属于运维策略，可由管理员调整：

- 原始上传报表：90 天；
- Provider 原始缓存：30～90 天，按 Provider 更新频率单独配置；
- 规则 / 配置快照、动作结果、正式报告：默认长期保留；
- 审计日志：至少 180 天。

任何自动删除必须可配置、可审计；核心证据删除前必须明确授权。

### 19.4 最低权限与审计

V1 不提前做复杂 RBAC，但必须预留 `created_by`、`store_id`、`role`。普通 User 只能访问被授权店铺，不能修改全局 / 店铺级策略；Admin 可管理策略与授权。

至少记录：

```text
login_success / login_failure
file_uploaded
task_created / task_started / task_failed / task_completed / task_rerun
config_previewed / config_changed / config_rolled_back
provider_refreshed / provider_rate_limited
report_viewed / report_exported
file_deleted / permission_changed
```

每条至少包含时间、用户、store_id、task_id/run_id（适用时）、动作、结果、必要版本号。

---

## 20. 项目施工纪律

- 先审计，后修改；
- 发现数据错，先定位数据源 / 字段 / 聚合问题，再改工具；
- 同一操作失败 2 次，停止盲目重试，给出错误证据；
- 常规读写、代码修改、本项目进程重启不需要每一步都问确认；
- 花钱、删除、权限/密钥/核心架构变更必须先确认；
- 只动本项目进程，禁止 `pm2 restart all` / `reload all`；
- 每一阶段必须有 Gate；
- 未通过 Gate 不跨阶段掩盖问题。

---

## 21. Codex 每次开工的读取顺序

```text
1. PROJECT_MEMORY.md
2. PROJECT_PLAN.md
3. PROJECT_STATUS.md（如存在）
4. 当前任务相关 rules / schema / tests
5. 涉及 UI 时再读 DESIGN-airtable.md
6. 只读取与当前阶段相关的源码
```

禁止每次为了一个小改动扫描整个项目。

---

## 22. 当前最核心验收句

项目任何新实现都必须能回答：

> 这个结论是由哪条规则触发、使用了哪个配置版本、依据哪些原始数据、缺了哪些数据、为什么重复运行不会变？

答不出来，就还不是可上线的关键词决策系统。

---

## 23. 运行时与本地 UAT 索引（2026-08-21）

- 多 Agent 连续监督协议：主 Agent 负责项目目标、计划、子 Agent 分工、Gate 核验和下一步分配；子 Agent 必须返回改动、验证、未完成项和外部阻塞。规范见 `docs/acceptance/continuous-supervision.md`。
- `scripts/check_continuous_execution.py` 是本地静态监督契约，已纳入 `scripts/run_uat.py`；它不调用网络，单次命令或子 Agent 完成不得被当作项目完成。
- 当前任务已激活每 5 分钟心跳自动化，用于最终回复后的跨轮重新唤醒；每次唤醒仍需执行状态重读、多 Agent 分工、Gate 核验和文档同步。完成的子 Agent 必须关闭释放并发槽位。

- 本地 UAT 统一入口：`scripts/run_uat.py`；验收说明：`docs/acceptance/uat-local.md`。
- XLSX 解析依赖 `openpyxl`。UAT 会在当前 Python 缺少该依赖时自动切换工作区依赖运行时；如需固定解释器可设置 `KWCC_PYTHON`。
- 最近一次 UAT：105 个 Worker 测试、3 个前端测试、前端/动作/迁移契约、Smoke、Phase 4/5/6/7 CLI、Phase 8 审计和 Pages demo 全部通过；网络调用为 0，Secret value 命中为 0。
- 任务执行失败路径：同一 `task_id + run_id` 不得重复生成或覆盖 artifact；队列结果冲突必须隔离归档为 `RESULT_CONFLICT` 并释放 processing；重跑必须使用不同的 `run_id`。
- 真实 Supabase/Auth/Storage 与 Provider 仍未配置凭据，禁止在本地 UAT 中虚构或发起外部调用。
- 前端演示边界：`frontend/app.js` 仅以 `kwcc_demo_session` 保护静态后台页面并重定向登录；这不是生产鉴权，真实接入时必须替换为 Supabase Auth 会话校验。
- 前端契约回归入口同时检查会话标记、登录重定向和后台页面保护标记，避免静态页面改动移除该边界。
- Supabase HTTP 适配器必须校验绝对 HTTP(S) Base URL 与安全 task/run ID；Gateway 的 worker/task/run 必填字段不能静默放行。
- Supabase HTTP 的 `auth_user` 与私有报告读取必须带 access token；缺 token 与 transport 未配置是两种不同失败语义。
- 迁移静态契约入口：`supabase/migration_contract_check.py`；它只防止核心 RLS/私有报告字段被意外删除，不替代真实 Supabase RLS 验证。
- 策略配置数值必须是有限的真实 int/float；Python bool、NaN、无穷值均视为无效阈值。
- 动作映射静态检查入口：`rules/action_mapping_contract_check.py`；规则回归必须保持 Unknown 不等于 0、缺失自然位不触发防守、零销售额 ACOS 为未知，且 add/defend 底层动作独立。
- 报告必须留痕原始输入 SHA-256、规则版本、配置版本和 Provider snapshot 版本；当前四类报告/run artifact 均支持 `provider_snapshot_version`。
- Worker 入口：`scripts/run_worker_once.py` 只处理一个任务；连续处理使用 `scripts/run_worker_loop.py`，默认持续轮询，测试可用 `--max-cycles`，异常必须有界退避且可优雅停止。
- Worker 监督器异常语义已锁定：失败结果单独计数，未捕获异常计入 errors，processing 任务启动前恢复，退避有 max_backoff 上限。
- Windows 推荐使用 `scripts/run_worker_loop.ps1`，自动选择 `KWCC_PYTHON` 或工作区 bundled Python。
- 连续开发防早停协议：单次 Worker、单个测试或完整 UAT 只关闭对应子步骤；命令返回后必须重读计划/状态并清点本地源码、测试、集成、契约/进程、文档和下一步，只有无安全本地工作或明确外部阻塞时才允许收尾。
- Phase 8 迁移契约回归加固：`supabase/migration_contract_check.py` 现在覆盖全部业务表 RLS、私有报告字段和公共报告/Storage 禁止边界；`supabase/test_migration_contract.py` 已纳入 `scripts/run_uat.py`，Phase 8 审计复用同一检查标准。
- 测试与安全契约回归加固：`supabase/migration_contract_check.py` 同时逐项校验 `002_indexes.sql` 五个查询索引；`scripts/check_frontend_syntax.py` 对四个随包 JavaScript 文件执行本地 Node.js 语法检查并已纳入 UAT。直接使用缺少 `openpyxl` 的解释器运行 Worker 测试会产生环境级级联失败，统一入口应使用 `scripts/run_uat.py` 的运行时选择。
- 运行时监督退避边界回归：`worker/queue/supervisor.py` 的首次等待和成功后退避重置均不超过 `max_backoff`；新增 `max_backoff=0` 回归，避免声明上限被第一次轮询等待绕过。
- 数据链路与报告确定性回归：解析器、报告排序和 Module 02/03 输出均增加稳定 tie-break；`action-results.json` 补齐 `report-0.2`；两个报告 golden 目录已用当前生成器同步，新增 `worker/tests/test_golden_artifacts.py`。指定范围 26 项、完整 UAT Worker 95 项通过，网络调用 0。

## 2026-08-21 Provider-neutral 配置与降级边界回归加固

- MCP `tools/list` 统一走 ProviderContract 的有界重试与 usage 统计，429/5xx 不绕过 retry policy；缺失 transport 不产生网络调用并记录本地 failure。
- `RetryPolicy` 现在拒绝非法重试和退避参数；配置验证覆盖非对象配置、版本类型、证据阈值顺序、市场机会、自然防守和诊断 CVR 边界。
- 规则引擎继续独立于 Provider/AI，动作由确定性规则生成，AI 字段仅解释且 `ai_may_change_action=false`；无 Provider 时保留明确降级路径。
- 定向回归 20 项、完整 UAT Worker 105 项、前端 3 项通过；网络调用 0，未使用凭据、费用或真实 Provider。
