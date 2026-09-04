# Amazon-Keyword-Command-Center-YX 项目记忆

## 最新执行纠正（2026-09-03，优先于下方历史快照）

## 当前真实链路收口（2026-09-04）

- GitHub Pages 线上根入口、`tool/`、`report/` 均返回 200；B 测试账号的真实任务已由远程 Worker 完成，报告从 Supabase 私有 Storage fetch 后在线渲染。报告对象名为 `report-` 加 48 位随机十六进制，未使用 ASIN 或日期。
- 线上复验已覆盖：精确 Origin Gateway、Auth 200、RLS 自有可见/跨店为 0/越权写入 403、私有报告自有读取 200/跨用户拒绝、未登录报告地址回登录页、未登录 API 返回 401 `AUTH_REQUIRED`、页头退出登录和六个独立模块入口。
- 当前唯一阻塞是正式带浏览器地址栏的登录页/工具页/报告页截图。BrowserSkill 只能保存网页视口，因此已保存的四张图片仅作为视口证据，不能冒充带地址栏截图。西柚没有测试接口，5xx 按用户确认使用本地模拟验收。

历史执行纠正：正式链路此前并非只差 CORS，已发布的 b42009a 是演示包；后续已补齐 005/006、精确 Origin 网关、私有上传/报告前端、生产 Worker 和独立 live 打包。原 001–004 的 RLS/Storage 证据不覆盖新增迁移，当前以本节 2026-09-04 线上复验为准。

- 2026-09-03 六模块整改：按用户参考图改为蓝色工作台，新增五个独立报告HTML/JS及共享导航。原计划本就要求六模块，旧状态“只差截图”不完整；数据/规则缺口详见 `docs/acceptance/six-module-workbench.md`。本轮完成的是演示前端交付，不是生产链路完成；不能把placeholder图片或unknown checklist当成视觉分析成功。

- 2026-09-03：阶段 8 交付审计补齐真实任务报告随机对象名（48 位十六进制）、run-meta 相对路径追溯和解析器表头映射；演示黄金目录仍保留 `master-table.json` 作为离线 Pages fixture。6a 对账 91 行、五项差值零；完整 UAT Worker 207 项、前端 7 项、20/20 Gate 通过，network_calls=0、external_calls=0、Secret=0。

## 当前验证快照

- 2026-09-03：阶段 8 前端整改已完成本地验证：新增独立 `tool/` 与 `report/` 地址、工具输入边界/刷新/失败原因交互、报告 fetch 门禁与宽表格；Pages 57 文件包已发布到远端 `main` 提交 `b42009a`，HTTPS 路由复验通过；Supabase 托管 API 的精确 CORS 仍待解决。

- 2026-09-03：GitHub Pages 新版独立路由 HTTPS Smoke Test 已通过；浏览器演示登录可渲染报告，登出后直达报告地址回到登录入口。截图为视口证据，不冒充无痕/生产验收。
- 2026-09-02：Provider 本地安全 transport、一次性探测入口和受控响应头观测已补齐；最新完整 UAT 统计见本节 2026-09-03 条目。
- 2026-09-02：从本地新 MCP 配置完成一次只读 `tools/list` live 验证：HTTP 200、JSON-RPC 有效、返回 29 个工具，1 次调用、0 失败、0 限流；未执行业务工具样本，Provider schema/成本/单位/限流仍待外部 Gate。
- 2026-09-02：在已确认工具名后完成一次只读 `get_keyword_info` 样本：HTTP/业务状态 200，返回字段结构有效，观察到 `cost_credits=1`，业务调用 1 次、失败 0、限流 0；缓存/重复、429/5xx、成本单位和缺失值语义仍未实测。
- 2026-09-02：追加 5 次授权范围内只读调用（重复基础指标、ABA 趋势、ASIN 信息、两组无结果边界）；均状态 200、各 1 credit，累计业务调用 6 次、失败 0、限流 0；无结果字段保持 JSON `null`，详细快照见 `docs/provider-snapshots/xiyou-tools-list-20260902.md`。
- 2026-09-02：用户新授权后完成 3 轮、5 次真实只读请求：重复 `get_keyword_info` 两次均状态 200、各 1 credit、`cache_hits=0`，响应摘要相同；没有触发 429/5xx，未观察到成本/限流/版本响应头。快照已更新，剩余真实 Gate 为成本货币换算、429/5xx 和独立版本字段。
- 2026-09-04：完整本地 UAT 20/20 Gate，Worker 269 项（12 项环境跳过）、前端 7 项（含 Node 93 场景）、连续执行 63 项、UAT 编排契约 25 项、Pages demo 57 文件/live候选49文件、文档 15 项通过；本地 network_calls=0、external_calls=0、Secret=0。新增上传、策略版本、精确Origin网关、生产Worker和西柚有界关键词指标均为本地证据，尚未部署。
- 真实 Supabase 已执行 003；显式 public schema 下七张表与 has_store_access 的匿名请求全部返回 401/42501。后置双用户复验已在临时项目通过：A/B 各自仅见授权店铺、任务和运行记录，跨店铺读取为 0，越权写入 HTTP 403，匿名读取 HTTP 401；私有 reports Storage 的 A/B 自有读取、跨店/匿名/无效令牌拒绝矩阵也已通过；凭据未持久化。
- 前端显式 live Auth/任务/策略读取、私有报告对象读取与 Gateway、Provider 缓存预算与流水线注入已实现并通过 fake 集成；上传、策略写入和真实私有报告前端仍明确禁用，不能假报上线。临时 Supabase 项目的历史 003/RLS/Storage 证据仍保留，但新版六模块尚未重新发布或做生产链复验；西柚无 5xx 测试接口，按用户确认以本地 fake transport 验收。
- 本轮最终监督器：BLOCKED_EXTERNAL，本地任务无可执行项；Supabase RLS 与私有 Storage 已完成当前项目复验，GitHub Pages 严格精确 CORS 仍是唯一外部阻塞。`supabase-live-evidence-20260831.md` 已追加当前项目证据；不把平台 wildcard 冒充精确 Origin 配置。

## 历史执行记录

- 2026-08-22 当前线程曾建立覆盖完整项目目标的平台持续目标；`get_goal` 为空时才调用一次 `create_goal`，已有 active 目标复用。本轮因连续三次相同外部阻塞已标记 `BLOCKED`；恢复后继续由 `PROJECT_TASKS.json` 与 `--claim`/`--complete` 负责唯一任务领取、原子续领和防重复。
- 状态机/持续目标 14 项与项目监督器 32 项合并为 46 项连续执行回归 Gate；任务 ID、执行类型、依赖、验收条件及声明输入共同参与 SHA-256，变化时 stale 重开，未变化且回执有效时跳过；不完整回执 fail closed，运行中输入变化可安全刷新领取并重验。
- 最新完整 UAT 20/20 Gate 通过：Worker 144 项（12 项环境跳过）、前端 5 项、UAT 编排契约 22 项、连续执行/监督器 46 项、Pages 19 文件、文档 15 项，network_calls=0、external_calls=0、Secret=0。监督器最终为 `BLOCKED_EXTERNAL`，本地安全队列为空，平台持续目标已标记 `BLOCKED`，剩余四项均需外部授权或凭据。

- 2026-08-21 本地安全审计收口：`path_guard` 对权限错误和其他 `OSError` fail-closed，避免无法检查的路径绕过 queue/storage/ingestion/Pages 的 Junction/reparse/symlink 边界；新增 3 项回归，完整 UAT Worker 144 项（12 项环境跳过）/前端 5 项、19 Gate 通过，网络/外部调用 0、Secret 0。

- 2026-08-21 UAT 编排最终本地审计：`run_uat.py` 要求 Worker loop、Phase 8、Pages 摘要包含 `network_calls`、`external_calls`、`local_only`，并严格校验字段类型；缺少结构化摘要同时写入 `summary_contract_errors` 和诊断字段，部分摘要、类型错误、超时和启动异常均结构化失败并继续收集全部 19 Gate；`_summary_metrics` 对缺失摘要安全跳过。新增统一 120 秒 Gate 超时和 5 组 ExitStack 临时目录退出清理回归，编排契约 18 项，最新完整 UAT Worker 144 项（12 项环境跳过）/前端 5 项，网络/外部调用 0、Secret 0。

- 2026-08-21 report-0.2 追溯契约收口：统一 `normalise_missing_fields()` 供 `shared_traceability()`、`market_merge`、`rule_engine` 使用；共享对账与前端状态只把布尔 `true` 视为通过，报告页/任务页缺失字段统一过滤、去重、排序并安全显示 `—`。新增 7 项回归，完整 UAT Worker 140 项（11 项环境跳过）/前端 5 项，19 Gate、编译、连续执行通过，网络/外部调用 0、Secret 0。

- 2026-08-21 queue/storage/ingestion/Pages/Supabase 安全审计补强：FileQueue 初始化拒绝被重定向的 state 目录，artifact 与 Pages 目录在创建后再次校验真实目录，保持 Junction/reparse/symlink、恢复失败归档、artifact allowlist/不可覆盖、Supabase URL/header、Secret/网络边界；新增 2 项回归，完整 UAT Worker 136 项（11 项 Windows 链接能力跳过）/前端 5 项、19 Gate 通过，network_calls=0、external_calls=0、Secret 0。

- 2026-08-21 queue/storage/ingestion/Pages/Supabase 本地安全复核：queue 恢复/失败归档统一识别 Junction/reparse point，ingestion 输出 artifact 拒绝 Junction 并在建目录后再次复核，Supabase malformed URL 解析错误归一化；定向 70 项通过（13 项 Windows 链接能力跳过），完整 UAT Worker 134 项（9 项环境跳过）/前端 5 项、19 Gate 通过，network_calls=0、external_calls=0、Secret 0。

- 2026-08-21 report-0.2 missing_fields 归一化审计：`market_merge` 与 `rule_engine` 对异常 fixture 统一过滤非空字符串、去重排序，字符串不会被拆成字符；新增 2 项回归，完整 UAT Worker 134 项（9 项环境跳过）/前端 5 项，网络/外部调用 0。
- 2026-08-21 UAT 编排摘要契约边界加固：`run_uat.py` 要求结构化 Gate 摘要包含 `network_calls`、`external_calls`、`local_only`，并拒绝缺失字段、布尔/负数/非整数调用计数和非布尔 `local_only`；malformed/partial summary 仍继续收集全部 Gate。新增 3 项回归，编排契约 14 项，完整 UAT Worker 134 项（9 项环境跳过）/前端 5 项，网络/外部调用 0。

- 2026-08-21 本地安全边界补强：queue/storage/ingestion/Pages 的路径检查统一拒绝符号链接及 Windows Junction/reparse point，避免目录重定向绕过根目录与 allowlist；定向安全回归 73 项（12 项因当前 Windows 符号链接能力跳过）、完整 UAT Worker 132 项/前端 5 项、19 Gate 通过，网络/外部调用 0、Secret 0。

- 2026-08-21 report-0.2 本地追溯审计：将 `run-meta.json` 纳入安全 artifact 白名单；前端契约补齐报告页追溯展示标记及任务运行级 `shared_traceability()` 静态边界；完整 UAT 当前基线为 Worker 130 项、前端 5 项。

- 2026-08-21 report-0.2 追溯投影复核加固：`shared_traceability()` 对行级 `missing_fields` 只保留非空标准字段名字符串并稳定去重排序；新增 Provider null→行级/报告级/四类 artifact 投影回归与成功 `run-meta.json` 逐值一致性检查。完整 UAT Worker 132 项（9 项环境跳过）、前端 5 项、19 Gate 通过，网络/外部调用 0。

- 2026-08-21 Supabase URL/Header 边界复核：transport 在 URL 解析前拒绝非字符串、空值和 ASCII/C1 控制字符，public key/access token 同步拒绝 ASCII/C1 控制字符；完整 UAT Worker 130 项（9 项环境跳过）、前端 5 项、19 Gate 通过，网络/外部调用 0、Secret 0。

- 2026-08-21 UAT/部署边界本地审计：Pages CLI 与 Phase 8 输出统一为 JSON 摘要，并要求 Worker loop、Phase 8、Pages 三个结构化 Gate 摘要缺失即失败；新增缺失摘要回归，编排契约当前 11 项。未部署、未取凭据、网络/外部调用仍为 0。

- 2026-08-21 安全审计收口：修复 queue `recover_processing()` 领取竞态冲突分支的未初始化标识，新增失败隔离回归；Pages 打包在复制前拒绝源文件/源树符号链接，避免 `copy2/copytree` 跟随越界。完整 UAT Worker 128 项（9 项环境跳过）、前端 5 项、19 Gate 通过，网络/外部调用 0、Secret 0。

- 2026-08-21 report-0.2 四类 artifact 缺失语义补齐：`shared_traceability()` 将报告级 `missing_fields` 同源投影到 master/action/meta/run-meta；报告页展示汇总，任务页继续读取 report-meta，market_merge/rule_engine 行级语义保持不变。定向报告 7 项、前端 5 项、完整 UAT Worker 128 项/前端 5 项、19 Gate 全部通过，网络/外部调用 0。

- 2026-08-21 UAT/部署审计编排加固：`run_uat.py` 固定执行 19 个 Gate，解析子 Gate JSON 摘要并累计拒绝非零 `network_calls`/`external_calls` 或 `local_only=false`；五组临时输出目录改由 `ExitStack` 托管，异常路径也自动清理；编排契约 9 项、完整 UAT Worker 128 项/前端 5 项通过，未调用外部服务。

- 2026-08-21 本地安全审计补强：队列领取与 processing 恢复改为不覆盖目标的硬链接发布，artifact task/run 中间目录拒绝符号链接，Supabase header 拒绝全部 HTTP 控制字符；新增回归后定向 46 项（9 项环境跳过）、完整 UAT Worker 128 项/前端 5 项通过，网络/外部调用 0、Secret 0。

- 2026-08-21 report-0.2 共享追溯投影复核：`shared_traceability()` 统一生成 action/meta/run-meta 的 schema、输入文件与 SHA-256、币种、对账、规则/配置/Provider 版本；新增生成器与任务运行字段集合回归。market_merge/rule_engine 的 Provider null→`missing_fields` 语义、前端/黄金 artifact 契约定向通过，未调用外部服务。

- 2026-08-21 UAT 编排边界加固：`run_uat.py` 固定汇总 19 个本地 Gate，失败/超时/启动异常仍继续收集，并强制校验 Gate 数量及 `network_calls=0`、`external_calls=0`、`local_only=true`；`check_worker_loops.py` 支持有界本地超时配置。UAT 编排契约 8 项通过（后续新增子 Gate 外部调用与临时目录清理回归已在顶部记录）。

- 2026-08-21 报告追溯审计：Provider 市场快照显式返回 `null` 的字段现在同步写入行级 `missing_fields`；前端契约补齐 action artifact 的输入文件/哈希/币种/规则/配置/Provider 版本、对账和 rows 一致性检查，未调用外部服务。

- 2026-08-21 本地安全边界复核：队列/存储/Pages 根目录拒绝符号链接，失败归档和 processing 恢复不跟随悬空/processing 符号链接，解析输出拒绝符号链接并禁止覆盖历史 JSON，输入路径拒绝父级符号链接，Supabase HTTP origin/header 类型拒绝不安全值，Pages 审计不读取符号链接目标。工作区定向 39 项（7 项环境跳过）、完整 UAT Worker 127 项/前端 5 项通过，网络/外部调用 0、Secret 0。
- 当前完整 UAT 为 Worker 130 项、前端 5 项；本轮边界修复后的连续执行与文档契约均已复核。

- 2026-08-21 UAT 防早停回归：`run_uat.py` 与 `check_worker_loops.py` 将子进程启动异常和超时转换为结构化失败，继续收集后续 Gate；新增编排契约 5 项。完整 UAT Worker 113 项、前端 5 项，双入口各 2 轮/2 心跳，网络和外部调用 0。

- 2026-08-21 report-0.2 四类 artifact 与前端一致性复核：报告页补齐 `input_file` 展示；golden artifact 契约逐项锁定 action/meta 对账结果等于 master 对账结果；任务运行回归覆盖成功 run-meta。完整 UAT Worker 113 项、前端 5 项通过，网络/外部调用 0。

- 2026-08-21 report-0.2 运行元数据审查：`run-meta.json` 补齐与 master/action/meta 一致的输入文件、输入哈希、币种、对账和规则/配置/Provider snapshot 版本字段；新增任务运行和前端共享追溯回归。Worker 113 项、前端 5 项通过，未调用外部服务。

- 2026-08-21 安全输出边界回归：队列 pending 符号链接不再被读取，队列与通用 artifact 使用独占原子发布，报告 master/action/meta 产物禁止覆盖历史文件；定向安全回归 34 项、完整 UAT Worker 113 项/前端 5 项通过，网络调用 0。

- 2026-08-21 数据字典与报告追溯一致性回归：`report-meta.json` 补齐 `currency_code`，master/action/meta 的输入哈希、币种、对账、规则、配置和 Provider 版本一致性已由契约覆盖；修复 UAT 汇总计数被 Pages 测试覆盖的问题。完整 UAT Worker 113 项、前端 5 项，网络调用 0。

- 2026-08-21 安全审计与输入边界回归：artifact 历史 JSON 禁止覆盖、非法队列失败归档避免同名覆盖、输入符号链接拒绝并结构化为 `INPUT_INVALID`，Supabase URL/header 边界加固；定向 31 项、完整 UAT Worker 110 项/前端 4 项通过，Secret value 0、网络调用 0。

- 2026-08-21 UAT 编排回归：新增 `scripts/check_worker_loops.py`，实际运行 Python 与 PowerShell 连续 Worker 各 2 轮并验证心跳/退出码；`run_uat.py` 纳入该 Gate 并输出结构化测试计数。完整 UAT Worker 110 项、前端 4 项通过，Secret value 0、网络调用 0、外部调用 0。

- 2026-08-21 Provider/规则安全回归：修复最终响应/异常型 429 未计入 `usage.rate_limited` 的缺口；补齐 5xx 有界失败和 MCP `tools/list` 最终 429 测试。定向 26 项、完整 UAT Worker 105 项、前端 3 项通过，网络调用 0，AI 不可改变动作。
- 2026-08-21 前端业务验收回归：报告页周期币种绑定 report-0.2 artifact，补齐 stop_loss/reduce_or_pause 筛选、无效数值缺失语义和导出 URL 安全释放；前端 3 项、完整 UAT Worker 105 项通过，网络调用 0。

- 2026-08-21 本地部署验收复核：修正 `PROJECT_PLAN.md` 当前 Phase 8 的 Worker 数量为 101；Phase 8 审计同时检查 Python/PowerShell 连续 Worker 入口；监督契约 13 项、完整 UAT 和 PowerShell 空队列进程验证通过，网络调用 0。

- 2026-08-21 Worker 可靠性回归：恢复时 pending/processing 同名冲突改为隔离 stale processing，不再反复退避卡住；连续 Python 入口支持 SIGINT/SIGTERM stop_event 和 `worker_stop_requested`；定向 23 项、完整 UAT Worker 97 项通过，PowerShell 失败后续任务验证 `processing=0`，网络调用 0。

- 2026-08-21 数据与规则质量回归：解析器保留缺失数值为 `null` 并记录 `missing_fields`，动作结果 artifact 补齐输入哈希/币种/对账追溯字段；golden artifact 已同步，定向回归 21 项、完整 UAT Worker 97 项通过。

- 2026-08-21 Provider-neutral 配置边界回归：MCP `tools/list` 复用统一 429/5xx 有界重试和 usage 记录；缺失 transport 记录失败但 `actual_calls=0`；`RetryPolicy` 和配置阈值校验补齐非法参数/缺失路径。定向 20 项、完整 UAT Worker 101 项、前端 1 项通过，网络调用 0。

## 当前状态

- 2026-08-21 Phase 8 发布边界审计已加固：`phase8_audit.py` 实际构建临时 Pages 包并精确核对 19 个 allowlist 文件，同时纳入文档、连续监督、前端语法和部署边界资产检查；全程网络调用为 0、未发布。

- 当前项目为 Amazon 关键词作战系统，已完成本地 Phase 2 链路和前端骨架。
- Worker、规则引擎、报告生成、文件队列和本地 UAT 已有实现；真实 Supabase/Auth/Storage/Provider 尚未配置。
- 当前队列入口同时支持单次执行 `scripts/run_worker_once.py` 与连续轮询 `scripts/run_worker_loop.py`。
- 单任务未预期异常会归档到 `failed`，不会阻塞后续任务；异常细节保存在失败结果中。
- Worker 启动时会自动恢复遗留的 `processing` 任务到 `pending`，适用于当前单 Worker 本地队列。
- Supervisor 遇到连续异常时使用有界指数退避，并继续轮询；测试模式可验证退避上限。
- 非法 JSON 队列项会归档到 `failed`，随后继续领取后续合法任务。
- 队列载荷现在还校验 JSON 对象结构、输入路径和文件名/ID 一致性；同一 `task_id + run_id` 不允许跨状态重复入队。
- 任务成功运行会额外留底 `input-meta.json` 与 `rules-snapshot.json`，追溯输入哈希、解析器、规则/配置/Provider 版本和完整生效配置。
- 常驻入口默认每 30 秒输出 `worker_heartbeat`，可配置为每轮输出以确认空队列时进程仍在运行。
- 最新本地 UAT：Worker 105 项、前端 3 项、Phase 4/5/6/7 CLI、Phase 8 审计、动作映射/迁移契约和 Smoke Test 全部通过，网络调用为 0。
- PowerShell 常驻启动器已完成真实多任务验证：连续处理 2 个任务且无失败。
- 本地队列入队前校验完整载荷，队列记录原子落盘，完成/失败结果禁止覆盖已有历史文件。
- 任务进入规则阶段前会校验完整策略配置；私有报告 Gateway 与 HTTP 层统一拒绝不安全的 task/run 标识。
- `build_report` 直接入口同样校验策略配置；Gateway 私有报告读取必须显式携带 access token。
- 任务创建/重跑契约现在在 API 边界校验必填字段和安全 ID；报告页已读取本地 market-demo artifact，支持筛选与 JSON 导出。
- 任务页已读取本地报告元数据展示演示任务，策略页已读取版本化 stable 配置展示本地预览；连续执行协议已在同一执行链中实测通过。
- Phase 3 报告 schema 已升级为 `report-0.2`，golden market 报告已按当前字段重新生成，避免前端读取过期 artifact。
- Phase 3 本地 Gate 已复核：宽表、筛选、导出、缺失值语义、五色/灰色映射、版本追溯和 AI 只读字段均有当前实现与回归证据；Worker 测试 71 项。
- Phase 4 Module 02/03 已开始本地实现：自然位标杆与否词候选模块已落地，否词只生成候选，不自动写 Amazon。
- Phase 4 模块已有 `scripts/build_phase4_modules.py` 本地编排入口，可重复生成 rank benchmark 与 negative keyword artifacts。
- Phase 5 已落地本地竞对档案契约：3～5 个唯一 ASIN、图片 URL/核心词留底、稳定缓存键和 `provider_calls=0`；竞对 CLI 已纳入 UAT。
- Phase 5 竞对档案本地验收文档已建立；真实 Provider 候选和竞品数据核对仍需外部服务确认，不影响本地契约 Gate。
- Phase 6 已开始 Provider-neutral 实现：Listing checklist、图片组元数据和高机会低 CVR 检查引用已落地，未下载图片或调用视觉 Provider。
- Phase 6 checklist 验收文档与本地 CLI 已完成；视觉事实采集仍需未来外部 Provider/人工复核，不阻塞当前本地契约。
- Phase 7 已落地确定性优化清单：动作可追溯到数据事实、rule_hits 和配置引用，任务 artifact 为 `optimization-plan.json`，AI 不可改动作。
- Phase 7 本地验收文档已建立，演示报告生成 91 条动作，当前仍不调用 AI/Provider。
- Phase 8 已补齐本地部署前静态审计；Provider 429 已实现有界重试和 usage 计数。真实外部部署/权限/Provider schema 仍未执行。
- 连续开发防早停协议已加固：每次工具命令后必须重读计划/状态并完成源码、测试、集成、契约/进程、文档和下一步清点；单次命令或完整 UAT 均不能直接结束执行链。
- 多 Agent 监督协议已落地：主 Agent 以项目目标统筹任务计划、核验子 Agent 交付并持续分配安全本地工作；监督契约入口为 `scripts/check_continuous_execution.py`，已纳入完整 UAT。
- 2026-08-21 当前任务心跳自动化已从每小时缩短为每 5 分钟，解决最终回复后的长时间空窗；子 Agent 完成并复核后必须关闭释放槽位，避免下一轮因并发额度耗尽而早停。

## 连续执行约定

- Codex 默认持续推进用户当前目标，不因完成一个小步骤、一次测试通过或一次命令结束而主动停止。
- 当前线程已建立持续目标；最终回复前必须确认不存在仍可执行的本地子步骤，不能因单次 UAT 通过提前收尾。
- 没有阻塞时，自动执行下一项安全工作：读取相关文件、实现、测试、修复、重跑和更新状态。
- 只有真实异常、需要用户确认/凭据/权限、危险操作，或无安全可执行进展时才暂停。

## 核心边界

- 规则负责判断，参数负责边界，数据负责证据，AI 负责解释。
- 未配置真实凭据时，不发起外部网络调用。
- 详细业务规则与文件索引见 `PROJECT_MEMORY.md`；阶段计划见 `PROJECT_PLAN.md`；状态见 `PROJECT_STATUS.md`。
- 根目录运行入口与持续执行说明见 `README.md`。

## 当前下一步

- 当前阶段为 `Phase 8 / local-deployment-audit`；本地部署前安全项已持续推进。真实 Supabase/Auth/Storage/Provider 联调仍需用户提供凭据和外部服务确认。
- GitHub Pages demo 已有 allowlist 打包器和 UAT 验证，但没有执行外部发布；正式站点仍需真实 Auth/Storage/CORS 验收。
- 2026-08-21 防早停协议回归：完整本地 UAT 重新通过，Worker 101 项、前端 1 项、网络调用 0；当前唯一未完成项是需要外部凭据/服务确认的部署与 Provider 联调。
- 2026-08-21 Phase 8 迁移契约回归加固：静态检查覆盖全部业务表 RLS、私有报告字段和公共报告/Storage 禁止边界；新增 1 项迁移契约测试并纳入 UAT，Phase 8 审计复用同一检查。
- 2026-08-21 测试与安全契约回归加固：迁移契约现逐项检查 `002_indexes.sql` 五个索引定义；新增 `scripts/check_frontend_syntax.py` 并纳入 UAT，对四个随包 JavaScript 文件执行本地 Node.js 语法检查。工作区依赖 Python 下 Worker 84、前端 1、迁移契约 2 和完整 UAT 全部通过，网络调用 0。
- 2026-08-21 运行时监督退避边界修复：`worker/queue/supervisor.py` 让首次等待和成功后重置也受 `max_backoff` 限制；新增回归测试覆盖 `poll_interval > max_backoff` 与 `max_backoff=0`，Worker 测试 85 项、完整 UAT 通过。
- 2026-08-21 任务执行与失败路径回归加固：同一 `task_id + run_id` 的直接重复执行现在返回 `DUPLICATE_TASK_RUN` 且不覆盖历史 artifact；`FileQueue.finish()` 拒绝非法 ID，结果冲突通过 `RESULT_CONFLICT` 隔离归档；重跑契约要求新 `run_id`。Worker 测试 93 项、PowerShell 连续失败后续任务验证通过，网络调用 0。
- 2026-08-21 数据链路与报告确定性回归加固：解析器、报告排序和 Module 02/03 artifact 增加稳定 tie-break；`action-results.json` 补齐 `report-0.2` schema；`full-demo-report` 与 `market-demo-report` 已按当前生成器同步；新增 golden artifact 契约测试。Worker 测试 95 项、指定范围 26 项、完整 UAT 通过，网络调用 0。
