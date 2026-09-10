---
project: Amazon-Keyword-Command-Center-YX
document_type: project_status
version: 0.2
updated_at: 2026-09-10
current_phase: Phase 10 / LUNU-04 six-module business completion
status: in_progress
execution_state: RUNNING
current_objective: "按 LUNU-04 执行六模块业务完善：补齐数据链路、判断逻辑、持久证据、页面和新 run 验收；不得把 partial/not_generated 当作完整交付"
next_safe_action: "验证 github-pages：确认 main 发布分支已包含当前 49 文件前端包，并复核正式 HTTPS 根入口、tool 与六模块报告脚本；完成后继续下一个外部 Gate"
stop_reason: ""
last_action_fingerprint: "github-pages:sha256:d3b3f3; publish-main=3e57721; verification=2026-09-10"
verified_gate_snapshot_current: "lunu04-e01-e18-passed; lunu04-e19=blocked_external,terminal_missing; github-pages=main:3e57721,pages_https=200,live_scripts=updated,local_bundle=49,raw_inputs=0,network_calls=0; e19-new-run=f14e96ea-84ad-4d1e-99dc-2cf38ccf24c4/5ab0176b-d357-4389-b1e4-d41e897a7e90; ad_reconciliation=passed,difference=0; rank=partial,91_rows,organic_and_benchmark_missing; negative=partial,28_pending_review,orders_protected; competitors=partial,4_products,product_fields_partly_present,brand_monthly_sales_category_bsr_bullet_points_missing,feature_quotes_missing; listing=partial,4_checks_unknown,self_images=1,competitor_images=3,visual_provider_not_requested; optimization=partial,91_actions,87_trace_fields_missing,91_observation_exit_fields_missing; report_scope=live_provider_data; full_report_complete=false; server_terminal=session_missing; sorftime=enabled_local_adapter_not_live"
local_safe_queue: in_progress
external_blockers_only: false
verified_gate_snapshot: "worker=325;frontend=8;orchestration=25;continuous=63;uat=20/20;pages=57;docs=15;network_calls=0;external_calls=0;secrets=0;lunu04-e01-e18=passed; local_status_fix=passed; sorftime_alias_contract=passed; strongest-run=f08b2d56-e629-4ba1-ae46-fff799a5f715/015f2f09-9afc-4f02-b117-4baf1b727fac; report_sha256=8241c9c4f6c84a044d0e1193b2b53441fb32ab85c89d9225720670ab84b037b7; scope=injected_provider_data; full_report_complete=false; reconciliation=passed,differences=zero; competitors=3,self_images=1,competitor_images=3; service=provider-budgeted-10; frontend_contract=passed; secret_value_hits=0"
---

## LUNU-04 当前最强生产新 run（2026-09-08）

- 新 task/run：`f08b2d56-e629-4ba1-ae46-fff799a5f715` / `015f2f09-9afc-4f02-b117-4baf1b727fac`；未覆盖旧 run。
- 私有报告读取成功，报告 SHA-256：`8241c9c4f6c84a044d0e1193b2b53441fb32ab85c89d9225720670ab84b037b7`；task/run 绑定通过。
- 报告 `schema_version=report-0.2`、`report_scope=injected_provider_data`、`full_report_complete=false`；Provider 状态为 `injected_data`，不能解释为真实市场全量完成。
- 对账 `passed=true`，差值为零；竞对 artifact 有 3 个竞对，但仍缺产品字段；自有图 1 张、竞对图 3 张，图片观察仍不可用。
- 模块状态：竞对 `partial/missing_product_fields`；图片 `partial/image_observations_not_available`；其余缺失字段按契约保持 `partial` 或 `not_generated`，没有默认 ready。

### 当前唯一外部缺口

生产链已经证明认证、上传、Worker、Provider 分支、随机私有报告持久化、前端读取和对账链路可执行；剩余问题是必需的竞品资料与图片观察证据没有在本次 Provider 结果中形成可核查 artifact。不能用空模块、默认 ready 或 `injected_data` 关闭 E20。下一次执行应先确认 Provider 能提供对应 ASIN/图片/类目特征能力，或正式记录范围变更后再验收。

## 新真实端到端复核（2026-09-07）

- 已在 Edge 登录并读取授权店铺；通过工具页只提交 1 次新的真实任务，task=`70092506-dad3-480b-acfb-9b7e428957a4`，run=`62f00837-bbe2-415d-83bc-5b08969b4666`。
- 任务从 `processing/ingestion` 完成到 `completed/report`；输入对象落在 private inputs bucket，任务页可见完成状态和报告入口，未发生重复提交。
- 报告首页通过前端私有 fetch 渲染 91 个搜索词、广告花费 `$5,123.10`、广告订单 `1,578`、整体 CTR `0.7%`，并显示对账差值为 0。
- 自然位模块加载 `91 / 91` 条，但 0 条有自然位、0 条有标杆位次；页面明确展示缺失字段并禁止推算趋势。
- 否定词模块加载 `28 / 28` 条：精准否定 0、词组否定 24、慎否 4、待确认 0；候选保持人工复核，不写入 Amazon。
- 竞对对比与图片/卖点诊断模块均明确显示“真实报告尚未生成”；未以空白页面冒充完成。
- 广告诊断与优化模块加载 `91 / 91` 个动作，但追溯字段待补 87、观察退出待补 91；页面明确禁止执行 Amazon 写入。
- 本次验收结论：登录、RLS 读取、真实上传、Worker 处理、私有报告 fetch、对账差值为零和显式缺口展示均通过；竞品/图片报告仍按 not_generated 展示、自然位和广告优化仍按 partial 展示。按 P8 验收规则项目完成，但不把缺失的 Provider 数据伪造为完整业务数据。

## 历史中间状态（2026-09-01）

## 当前外部复核（2026-09-02）

- GitHub 仓库 `UPJacky/Amazon-Keyword-Command-Center-YX` 已创建为 Public；已提交 21 个 allowlist Pages 文件，并配置 `main` 分支根目录发布。
- 正式 HTTPS 地址 `https://upjacky.github.io/Amazon-Keyword-Command-Center-YX/` 已构建并返回登录入口页面；Pages Gate 已完成，未配置自定义域名或写入任何 Secret。
- Provider 本地接入链路已补齐：`worker/providers/mcp_http_transport.py` 支持 HTTPS、Bearer 令牌、JSON/SSE 响应和 429/5xx 状态交给有界重试；`scripts/probe_provider.py` 只从进程环境读取 `XYDC_MCP_URL`/`XYDC_MCP_TOKEN`，默认缺少配置即零网络，输出只写用户指定的私有证据文件。
- 新西柚 MCP 配置已通过一次只读 live `tools/list`：HTTP 200、JSON-RPC 结构有效、返回 29 个工具，`actual_calls=1`、`failures=0`、`rate_limited=0`；未调用业务工具，成本/单位/限流语义仍待外部 Gate。
- 在已确认工具名后完成一次只读 `get_keyword_info` 样本：HTTP/业务状态 200，返回字段结构有效，`cost_credits=1`、业务调用 1 次、失败 0、限流 0；未执行第二个业务调用，详细字段快照见 `docs/provider-snapshots/xiyou-tools-list-20260902.md`。
- 追加 5 次授权范围内的只读调用：重复基础指标、ABA 趋势、ASIN 信息和两组无结果边界样本均返回状态 200，各 `cost_credits=1`，总业务调用 6 次、失败 0、限流 0；无结果字段保持 JSON `null`，未伪造为 0。
- 新授权复核完成 3 轮、5 次真实只读请求：第 1 轮发现 29 个工具；第 2、3 轮重复 `get_keyword_info` 均 `status=200`、`cost_credits=1`、`cache_hits=0`，响应摘要相同；未触发 429/5xx，响应头未提供独立版本或成本货币信息。
- 用户提供的西柚工具明细列出 28 个数据工具，与实时清单中的 28 个业务工具逐项对齐；实时第 29 项 `report_missing_xiyou_capability` 为能力报告工具，已单独记录。

- `reports` bucket 保持 private；A/B 两个 `master-table.json` 均已落在各自 task/run 目录，未生成永久公开链接。
- 测试文件中的两组普通用户均认证成功（HTTP 200）；A/B 各自读取所属对象成功（HTTP 200），跨店铺、匿名和无效令牌读取均拒绝（HTTP 400）。
- 为补齐 A 对象，曾在测试窗口临时增加同范围 INSERT policy；上传返回 HTTP 200 后已删除该 policy，清理后的再次写入探针返回 RLS 拒绝，最终权限仍为 Worker 写入、用户受控读取。
- 密码只在一次性内存请求中将全角问号归一化为半角问号；没有改写测试文件，没有写入回执、仓库或聊天。

## 早期中间复核（已归档，2026-09-01）

- Supabase 当前项目已确认 `reports` Storage bucket 为 private，并上传 A/B 两份受控测试对象；对象路径与项目测试 task/run 绑定，未生成公开链接。
- B 临时普通用户密码认证返回 HTTP 200；A 临时用户存在于 Auth 列表但认证返回 HTTP 400。B 对象的认证读取、跨店读取、匿名读取和无效令牌读取当前均被拒绝，符合未绑定成员时的 fail-closed 行为；尚不能据此宣称“授权用户可读”。
- 完成授权用户读取需要一次 Supabase 控制台登录，以及为可认证的 A/B 测试用户绑定各自店铺；密码和访问令牌不得写入回执、仓库或聊天。

## 历史验证快照（2026-08-31）

- 早期 2026-09-01 外部阻塞探测曾显示临时 Supabase Storage 无可见私有桶；随后在用户授权的浏览器操作中已完成 `reports` 私有桶、A/B 测试对象和 004 迁移配置。该早期探测仍适用于 `www.upjk.cn` HTTPS 不可达、HTTP 返回 502，以及工作区无 Git 仓库或 GitHub workflow；GitHub Pages 与 Provider 未发布、未调用。

- 完整 UAT 20/20 Gate：Worker 197 项（12 项环境跳过）、前端 7 项（含 Node 26 场景）、UAT 编排契约 25 项、连续执行 63 项、迁移 21 项、Pages 21 文件/11 项测试、文档 15 项；本地网络/外部调用 0、Secret 0。
- 已复核 Auth/live 失败关闭、私有报告对象与调用者绑定、Provider 缓存/预算/流水线、双入口 Worker 进程和 Pages 离线配置边界；仍未部署或启用真实 Provider。
- Supabase 003 已执行，七张表与辅助函数在 public schema 的匿名请求均为 401/42501；迁移后的双用户矩阵已通过：A/B 各自仅见 1 个授权店铺、任务和运行记录，跨店铺泄漏为 0，RPC 自己为 true/对方为 false，跨店铺写入 HTTP 403，匿名读取 HTTP 401。其余外部 Gate 保留，不标记项目完成。
- 以下有日期的段落是历史证据；当前计数以本节和顶部 verified_gate_snapshot 为准。
- 最终任务清点：8 项任务均有当前指纹与结构化通过回执，runnable/running/stale 均为空；仅 GitHub Pages、真实 Provider 2 项外部 Gate 仍未完成。完成子 Agent 已关闭，终止态暂停心跳，不标记项目或持续目标完成。

## 2026-08-21 连续执行与防重复状态机

- `RUNNING` 状态必须持续执行具体 `next_safe_action`，一个命令、测试、UAT、文档同步或子 Agent 完成都不能结束执行链。
- 合法终止态限定为 `BLOCKED_EXTERNAL`、`BLOCKED_RISK`、`USER_STOPPED`、`PROJECT_COMPLETE`；每次终止都必须记录 `stop_reason`，外部阻塞不等于项目完成。
- `last_action_fingerprint` 与 `verified_gate_snapshot` 联合跳过输入未变化的已验证动作；心跳只在运行态激活，合法终止态暂停，不再产生完成态空转。
- 连续执行状态机/持续目标 15 项与项目监督器 48 项合并为 63 项独立回归 Gate；UAT 编排契约 22 项，完整 UAT 固定 20 个 Gate。
- 当前线程曾创建覆盖完整项目目标的平台持续目标，并将 `get_goal`/`create_goal` 生命周期要求纳入静态契约；本轮因连续三次相同外部阻塞已标记 `BLOCKED`，单个回复、测试、UAT 或子任务完成不能关闭该目标。
- 项目监督器 v1 已完成并写入当前指纹回执：任务依赖/验收条件纳入指纹，不完整持久回执 fail closed，运行中输入变化可刷新领取并重验；两次实际 `--complete` 均在同一锁内自动领取后继任务。
- 最新完整 UAT 20/20 Gate 通过：Worker 144 项（12 项环境跳过）、前端 5 项、连续执行/监督器 63 项、编排 22 项、Pages 19 文件、文档 15 项；`network_calls=0`、`external_calls=0`、Secret=0。监督器当前继续重验 stale 本地任务，尚未进入外部终止态。

## 2026-08-21 本轮路径守卫 fail-closed 修复

- `path_guard` 对权限错误和其他 `OSError` 采用拒绝优先，防止无法检查的 queue/storage/ingestion/Pages 路径绕过 Junction/reparse/symlink 边界；缺失路径仍允许正常创建。
- 新增 3 项回归；完整 UAT 19/19 Gate、Worker 144 项（12 项 Windows 链接能力跳过）、前端 5 项、双入口 Worker、Phase 8、Pages、Smoke、迁移、compileall 和连续执行全部通过；network_calls=0、external_calls=0、Secret=0。

## 2026-08-21 本轮 UAT 结构化摘要必需字段补强

- `run_uat.py` 对 Worker loop、Phase 8 和 Pages 三个结构化 Gate 强制要求 `network_calls`、`external_calls`、`local_only` 三个字段；缺失字段、类型错误、超时和启动异常均结构化失败并继续收集全部 19 Gate。
- 新增 4 项编排回归，UAT 编排契约 18 项；缺少结构化摘要同时写入 `summary_contract_errors` 和诊断字段，且 `_summary_metrics` 对缺失摘要安全跳过；新增统一 120 秒 Gate 超时和 5 组临时目录退出清理验证。最新完整 UAT 为 Worker 144 项（12 项因当前 Windows 符号链接能力跳过）、前端 5 项，19/19 Gate、双入口 Worker、Phase 8、Pages、compileall 和文档契约通过，network_calls=0、external_calls=0、Secret=0。
---

## 2026-08-21 本轮 report-0.2 追溯契约收口

- `shared_traceability()`、`market_merge` 与 `rule_engine` 统一去除 `missing_fields` 首尾空白并忽略空白/非字符串值；共享对账投影只把布尔 `true` 视为通过，避免字符串型 `"false"` 被误判。
- 前端报告/任务页对缺失字段和对账状态采用严格形状判断，异常字段不会因 `.join()` 或 truthy 转换中断/误显示；新增 7 项回归，完整 UAT 19/19 Gate、Worker 140 项（11 项环境跳过）、前端 5 项、编译和连续执行通过，network_calls=0、external_calls=0、Secret=0。

## 2026-08-21 本轮 queue/storage/ingestion/Pages/Supabase 安全审计

- 加固 FileQueue 初始化：预置 state 目录若为符号链接/Junction/reparse point 会立即拒绝，创建后再次确认是真实目录；artifact 写入和 Pages 输出目录创建后增加同类复核。
- 新增 2 项边界回归；完整 UAT 19/19 Gate、Worker 136 项（11 项因当前 Windows 链接能力跳过）、前端 5 项、双入口 Worker、Phase 8、Pages、Smoke、迁移、compileall、连续执行和文档契约通过；network_calls=0、external_calls=0、Secret=0。

## 2026-08-21 本轮 report-0.2 missing_fields 归一化审计

- `market_merge` 与 `rule_engine` 现在对字符串、空值和非字符串 fixture 统一执行非空字符串过滤、去重和排序，Provider null 与输入缺失字段不会被拆成字符或污染四类 artifact 的报告级汇总。
- 新增 market_merge/rule_engine 回归；定向 report-0.2/market_merge/rule_engine/task-runner 33 项（1 项因 Windows 符号链接能力跳过）、前端 5 项通过；完整 UAT 19/19 Gate、Worker 134 项（9 项因 Windows 符号链接能力跳过）、前端 5 项，网络/外部调用 0，Secret value 0。

## 2026-08-21 本轮 queue/storage/ingestion/Pages/Supabase 安全边界复核

- queue 恢复/失败归档统一拒绝 Junction/reparse point；ingestion 输出 artifact 增加 Junction 检查并在创建目录后复核；Supabase malformed URL 解析异常归一化。
- 定向范围测试 70 项通过（13 项因当前 Windows 链接能力跳过）；完整 UAT 19/19 Gate、Worker 134 项、前端 5 项，network_calls=0、external_calls=0、Secret=0。

## 2026-08-21 本轮 UAT 编排摘要契约边界加固

- `scripts/run_uat.py` 要求结构化 Gate 摘要同时包含 `network_calls`、`external_calls`、`local_only`；拒绝缺失字段、布尔值、负数和非整数计数，以及非布尔 `local_only`。异常只进入结构化 `summary_contract_errors`，不会在汇总阶段抛异常导致早停。malformed/partial summary 会作为失败记录并继续收集后续 Gate。
- 新增 3 项编排回归，UAT 编排契约更新为 14 项；完整 UAT 19/19 Gate、Worker 134 项（9 项因 Windows 符号链接能力跳过）、前端 5 项、双入口 Worker、Phase 8、Pages、Smoke、迁移、编译、连续执行和文档契约通过，网络/外部调用 0、Secret 0。

## 2026-08-21 本轮 Windows 路径重定向边界补强

- queue/storage/ingestion/Pages 的根路径、源树、输入和 artifact 检查统一拒绝符号链接及 Windows Junction/reparse point，避免路径重定向绕过队列状态、存储根目录或 Pages allowlist。
- 定向安全回归 73 项（12 项因当前 Windows 符号链接能力跳过）、完整 UAT 19/19 Gate；Worker 132 项、前端 5 项、双入口 Worker、Phase 8、Pages、Smoke、迁移、compileall、连续执行和文档契约全部通过，网络/外部调用 0、Secret 0。

## 2026-08-21 本轮 report-0.2 本地追溯审计

- 复核并加固 `shared_traceability()` 的报告级 `missing_fields` 投影：仅接受非空标准字段名字符串，自动去重排序，异常 Provider fixture 不再导致排序失败或污染四类 artifact；新增 Provider null、非规范 fixture 和成功 `run-meta.json` 逐值一致性回归。
- `run-meta.json` 已纳入 `worker/storage/artifacts.py` 的安全 artifact 白名单；新增 round-trip 回归，运行级报告追溯可由统一 artifact 读写契约复核。
- `frontend/contract_check.py` 现在校验报告页的 schema、币种、对账、输入文件、Provider 和缺失字段展示标记，并检查 task runner 使用 `shared_traceability()` 生成运行元数据。
- 定向 report-0.2/market_merge/rule_engine/task-runner 31 项（1 项因 Windows 符号链接能力跳过）、前端 5 项通过；完整 UAT Worker 132 项（9 项因 Windows 符号链接能力跳过）、前端 5 项，19/19 Gate、双入口 loop、Phase 8、Pages、Smoke、迁移、编译和文档契约通过，网络/外部调用 0，Secret value 0。

## 2026-08-21 本轮 Supabase URL/Header 安全边界复核

- Supabase HTTP transport 在 URL 解析前拒绝非字符串、空值和 ASCII/C1 控制字符；public key/access token 同步拒绝 ASCII/C1 HTTP 控制字符，避免异常类型泄漏和控制字符进入请求边界。
- 定向 queue/storage/ingestion/Supabase/Pages 回归通过；完整 UAT Worker 130 项（9 项环境跳过）、前端 5 项，19 Gate、双入口 loop、Phase 8、Smoke、迁移、编译和文档契约通过；网络/外部调用 0，Secret value 0。

## 2026-08-21 本轮安全边界审计收口

- 修复 `recover_processing()` 在领取竞态冲突分支中未初始化 task/run 标识导致连续 Worker 异常退避的问题；新增竞态回归，失败记录会被隔离且不覆盖历史结果。
- Pages 打包器在 `copy2/copytree` 前拒绝前端、golden artifact、规则源树中的符号链接，避免复制阶段跟随源路径越界；新增源文件链接回归。
- 定向 queue/storage/ingestion/Supabase/Pages 回归通过；完整 UAT Worker 128 项（9 项环境跳过）、前端 5 项、19 个 Gate 全部通过，双入口 loop、Phase 8、Smoke、迁移、编译和文档契约通过；网络/外部调用 0，Secret value 0。

## 2026-08-21 UAT/部署审计编排与临时目录清理加固

- `run_uat.py` 继续固定执行 19 个本地 Gate；现在解析子 Gate 的 JSON 摘要并累计校验 `network_calls=0`、`external_calls=0`、`local_only=true`，不再仅依赖主编排器写死的零值。
- UAT 临时输出目录统一由 `ExitStack` 托管，即使 Gate 执行过程中出现异常也会自动清理；新增编排回归覆盖外部调用被报告时拒绝。
- UAT 编排契约 11 项；完整 UAT Worker 130 项（9 项环境跳过）、前端 5 项，19 个 Gate、双入口 Worker、Phase 8、Pages、Smoke、迁移、编译和文档契约全部通过；网络/外部调用 0，Secret value 0。
- 本轮本地边界审计进一步要求 Worker loop、Phase 8 和 Pages 三个结构化 Gate 必须提供 JSON 摘要；缺失摘要、启动异常和超时均失败但继续收集后续 Gate。编排契约更新为 11 项。
- 复核后当前编排契约测试套件为 13 项；文档计数已同步，结构化 Gate 摘要缺失和摘要字段类型错误均按失败处理。

## 2026-08-21 本地安全审计补强：领取竞态、内部目录链接与 Header 控制字符

- `FileQueue.claim_next()` 与 `recover_processing()` 改为硬链接发布后删除源文件，目标已存在时归档冲突，禁止 `replace()` 覆盖 processing/pending 历史记录；新增领取冲突回归。
- `worker/storage/artifacts.py` 对 task/run 中间目录拒绝符号链接；Supabase public key/access token 现在拒绝全部 HTTP 控制字符；任务页同步包含 `missing_fields` 缺失语义标记。
- 定向边界测试 46 项（9 项因当前 Windows 符号链接能力跳过）通过；完整 UAT Worker 128 项、前端 5 项、19 个 Gate、连续 Worker、Phase 8、Pages、Smoke、迁移、编译全部通过；网络/外部调用 0，Secret value 0。

## 2026-08-21 report-0.2 共享追溯投影复核

- `master-table.json` 继续作为完整报告事实源；`action-results.json`、`report-meta.json` 和成功任务的 `run-meta.json` 现在统一由 `shared_traceability()` 派生共享字段，包含报告级 `missing_fields` 汇总，避免各 artifact 独立拼装造成 schema、输入哈希、币种、对账、缺失语义或版本漂移。
- `market_merge` 显式 Provider `null` 仍保留为 `null` 并写入行级 `missing_fields`；`rule_engine` 会保留这些字段且不会用未知值触发防守/机会动作。
- 新增生成器共享投影、任务 run-meta 字段集合和前端/黄金 artifact 追溯回归；定向 Worker 28 项（1 项因 Windows 符号链接能力跳过）、前端 5 项、连续执行契约、前端契约通过；完整 UAT Worker 128 项、前端 5 项，网络/外部调用 0，Secret value 0。

## 2026-08-21 UAT 编排固定 Gate 与本地调用边界

- `run_uat.py` 现在显式锁定 19 个本地 Gate；即使 Gate 失败、超时或启动异常，也继续执行并汇总完整清单，并校验 `gate_count`、`network_calls=0`、`external_calls=0` 和 `local_only=true`。
- `check_worker_loops.py` 的 loop 子进程超时可由 `KWCC_LOOP_TIMEOUT_SECONDS` 调整（默认 30 秒、最小 1 秒），同时锁定 Python/PowerShell 两个入口、2 个有限周期、2 个心跳、`errors=0`、`stopped=false` 和退出码 0。
- UAT 编排契约当前 9 项；本轮未调用网络、Provider、凭据或部署。

- 本轮报告追溯审计修复 Provider 显式 `null` 未进入行级 `missing_fields` 的缺口；同时加强 action artifact 与任务页共享字段契约，避免缺失值显示与追溯字段不一致。

# 项目状态

- 最新完整 UAT：19 个 Gate 全部通过，Worker 130 项（9 项环境跳过）、前端 5 项；Python/PowerShell loop、Phase 4–8、Pages、Smoke、迁移、编译和文档契约通过，网络/外部调用 0，Secret value 0。

## 2026-08-21 本地安全边界复核

- 加固 worker/queue、worker/storage、输入解析、Supabase HTTP 和 Pages 输出：拒绝队列/存储/Pages 根目录符号链接，队列完成与 artifact 读取拒绝符号链接，输入路径拒绝任一父级符号链接，Supabase 仅接受无凭据/无路径/无查询/无片段/无 CRLF 的 HTTP(S) origin，Pages 审计发现符号链接后不再读取其目标。
- 本轮新增失败归档悬空链接、processing 链接恢复、解析输出目录链接/不可覆盖写、Supabase header 类型和 Pages 输出根目录链接回归；工作区定向 39 项通过（7 项因 Windows 符号链接能力跳过）。完整 UAT Worker 127 项、前端 5 项，连续 Worker、Phase 8、Pages、Smoke、迁移、编译全部通过；网络/外部调用 0，Secret value 0。

## 2026-08-21 UAT 防早停与启动异常回归

- `run_uat.py` 与 `check_worker_loops.py` 将 Gate 子进程启动 `OSError` 归一化为失败结果；超时仍为结构化失败，主 UAT 会继续执行并汇总后续 Gate。
- 新增 UAT 编排契约 9 项，覆盖超时、Gate/loop 启动失败、双入口摘要约束、固定 Gate 数量、子 Gate 外部调用拒绝、临时目录托管和失败后继续收集；完整 UAT Worker 128 项、前端 5 项通过。
- Python 与 PowerShell Worker loop 各完成 2 个有限空队列周期、2 个心跳、`errors=0`、未提前停止；Phase 8、Pages 19 文件、连续执行、迁移、Smoke、编译全部通过；网络/外部调用 0，Secret value 0。

## 2026-08-21 report-0.2 四类 artifact 与前端一致性复核

- 修复报告页缺少 `input_file` 展示的问题；任务页与报告页现在都展示输入文件、币种、对账和版本追溯信息。
- 加强 golden artifact 契约：`action-results.json`、`report-meta.json` 的 `reconciliation_passed` 必须逐项等于 `master-table.json.reconciliation.passed`；任务运行测试继续覆盖成功 `run-meta.json` 的四类 artifact 共享字段。
- 定向报告/任务/前端测试通过；完整 UAT Worker 113 项、前端 5 项通过，网络调用 0、外部调用 0。

## 2026-08-21 report-0.2 运行元数据一致性审查

- 成功任务的 `run-meta.json` 现与 `master-table.json`、`action-results.json`、`report-meta.json` 共享 schema、输入文件、输入 SHA-256、币种、规则/配置/Provider snapshot 版本和对账结果；运行状态字段仍独立保留。
- 新增任务运行追溯回归与前端任务/报告共享字段契约；缺失数值仍以 `null`/`—` 表示，不把未知值伪装为零。
- 报告与前端独立静态检查通过；bundled Python 下 Worker 定向回归和完整 UAT 均已通过，未调用外部服务。

## 2026-08-21 数据字典与报告追溯一致性回归

- `report-meta.json` 已补齐 `currency_code`，并与 `master-table.json`、`action-results.json` 统一校验输入文件、输入 SHA-256、币种、对账结果、规则版本、配置版本和 Provider snapshot 版本。
- 新增生成器、golden artifact 和前端任务页追溯契约；任务页读取 report-meta、报告页读取 master 时展示同一组追溯字段。
- 修复 `run_uat.py` 汇总计数被 Pages 测试覆盖的问题；最新完整 UAT 为 Worker 113 项、前端 5 项，网络调用 0。

## 2026-08-21 安全审计与输入边界回归

- `worker/storage/artifacts.py` 的 allowlisted JSON artifact 现为不可覆盖写入，拒绝替换已有历史 artifact，并要求对象型 JSON 载荷。
- 非法队列项归档遇到同名历史失败记录时改用稳定递增后缀，保留两份失败证据，不再覆盖历史记录。
- 解析器拒绝符号链接输入；输入读取的 `OSError` 统一归档为 `INPUT_INVALID` ingestion 失败，避免目录/权限异常泄漏为未结构化 Worker 异常。
- Supabase HTTP transport 拒绝带凭据、查询串或片段的 Base URL，并拒绝 CR/LF header 注入；task/run ID 仍只允许安全字符集。
- 定向安全回归 34 项通过（符号链接测试因当前环境能力跳过）；完整 UAT Worker 113 项、前端 5 项、迁移/Pages/Phase 8/连续 Worker Gate 全部通过，Secret value 0，网络调用 0。

## 2026-08-21 UAT 编排与连续入口进程 Gate

- `scripts/run_uat.py` 新增结构化测试计数、`external_calls=0` 断言字段，并纳入 `scripts/check_worker_loops.py`。
- Python 与 PowerShell Worker loop 均完成 2 轮空队列心跳，退出码 0、错误 0；Phase 4–8 CLI、文档/迁移/动作契约、Smoke、Pages 审计全部通过。
- 当前完整 UAT：Worker 120 项、前端 5 项；Secret value 命中 0、网络调用 0、外部调用 0；未执行部署或真实 Provider。

## 2026-08-21 Provider/规则安全回归

- 修复 `ProviderContract` 对最终一次 429 响应和异常型 429 的 usage 统计：每次实际限流均计入 `rate_limited`，最终失败仍只计一次 `failures`；重试次数和退避仍有界。
- 新增 Provider 429 最终失败、异常 429、5xx 最终失败，以及 MCP `tools/list` 最终 429 回归测试；AI 仍不能生成或修改 `action_group`。
- 定向 Provider/MCP/规则测试 26 项通过；完整 UAT Worker 105 项、前端 3 项通过，网络调用 0，未使用真实 Provider、凭据或外部服务。

## 2026-08-21 业务验收与报告前端追溯回归

- 报告页金额格式改为使用报告 `currency_code` 动态渲染，不再硬编码美元符号；`null`/缺失数值继续展示为 `—`。
- 报告页补充 `report-0.2` schema、币种、输入 SHA-256、Provider snapshot 和对账状态展示；报告周期币种同步来自 artifact，新增保持/谨慎/止损筛选入口，覆盖全部确定性动作映射。
- 任务页补充 schema、币种、输入哈希、Provider snapshot 和对账状态展示；策略页继续只读读取版本化 stable 配置，不写入正式策略。
- 前端回归新增 report-0.2 artifact 追溯字段、缺失值语义和全部 action filter 检查；动态报告字段无效数值统一展示为 `—`，导出 URL 延迟释放以保证下载边界。
- 前端定向契约与 Node.js 语法检查通过；完整 UAT Worker 101 项、前端 1 项通过，网络调用 0，未使用凭据或部署。

## 2026-08-21 本地部署与运行验收复核

- 修正当前 Phase 8 计划中的 UAT 数量为 Worker 101 项、前端 1 项；历史记录中的旧数量保持原样。
- Phase 8 审计现同时要求 `scripts/run_worker_loop.py` 与 Windows `scripts/run_worker_loop.ps1`，避免只验证单一入口。
- 监督契约 13 项、Phase 8 审计、Pages 安全测试 3 项、完整 UAT、编译和 PowerShell 空队列进程验证通过；网络调用 0、Secret value 命中 0。

## 2026-08-21 Worker 队列恢复与进程停止可靠性加固

- `FileQueue.recover_processing()` 遇到同名 `pending` 与遗留 `processing` 记录时，保留 pending 重试候选并将 stale processing 隔离为 `RESULT_CONFLICT`，不再让 Supervisor 在每轮恢复时反复异常退避而表现为卡住。
- `scripts/run_worker_loop.py` 注册 SIGINT/SIGTERM 处理，将停止请求转换为监督器 `stop_event`，并输出 `worker_stop_requested`，保留最终状态可观测性。
- 新增恢复冲突回归；队列/运行时定向测试 23 项通过，完整 UAT Worker 97 项、前端 1 项通过。
- PowerShell 连续进程验证：失败任务 1、成功后续任务 1、空队列轮询 1、processing 0、退出码 0；网络调用 0。

## 2026-08-21 数据与规则质量回归加固

- 解析器不再把 `N/A`、`NULL` 等缺失数值伪装成 0；缺失字段保持 `null`，并记录到行级 `missing_fields`，相关 CTR/CPC/CVR/ACOS/ROAS 保持未知。
- `action-results.json` 补齐 `input_file`、`input_sha256`、`currency_code` 和 `reconciliation_passed`，与 schema/rule/config/provider 版本共同形成完整追溯链。
- `full-demo-report` 与 `market-demo-report` 已按当前生成器重新生成；新增缺失数值、动作结果追溯和 golden artifact 契约回归。
- 定向测试 21 项通过；完整 UAT Worker 97 项、前端 1 项通过；随后使用工作区 bundled Python 执行验证，网络调用 0。

## 2026-08-21 跨轮持续开发生命周期修复

- 根因确认：项目内连续执行协议只能约束单次被唤醒后的执行，最终回复后缺少新的任务唤醒，导致表现为“运行一轮就停”。
- 已确认心跳绑定当前任务并保持 ACTIVE；原每小时周期尚无运行记录且空窗过长，现已调整为每 5 分钟重新唤醒，以项目目标统筹多 Agent、安全本地开发、完整 UAT 和文档同步。
- 多 Agent 协议补充完成后关闭并释放 Agent 槽位，避免已完成 Agent 占满并发额度；心跳不扩大真实 Provider、部署、凭据、费用、权限或删除授权。

## 2026-08-21 数据链路与报告确定性回归加固

- `worker/ingestion/ad_report_parser.py` 增加 Unicode/大小写相同关键词的稳定最终排序键，避免输入排列影响聚合 artifact 顺序。
- `worker/report/generate_report.py` 为 `action-results.json` 补齐 `schema_version`，并增加报告行排序最终 tie-break；当前 `full-demo-report` 与 `market-demo-report` 均已用当前生成器同步为 `report-0.2`。
- `worker/report/modules.py` 对标杆选择、Module 02 行序和 Module 03 候选行序实行稳定排序；未知排名继续保持 `None`，否词 artifact 继续 `write_back=false`。
- 新增 `worker/tests/test_golden_artifacts.py`，覆盖报告 artifact 版本一致性、Module schema、未知排名和禁止写回；新增确定性排列回归。
- 验证：指定范围 26 项、完整 UAT Worker 95 项、前端 1 项、编译和全部本地 Gate 通过；网络调用 0，Secret value 命中 0。

## 2026-08-21 任务执行与失败路径回归加固

- `worker/pipeline/task_runner.py` 现在拒绝同一 `task_id + run_id` 的重复执行，避免覆盖已有成功或失败 artifact；重跑必须创建新的 `run_id`。
- `FileQueue.finish()` 复用安全 ID 校验；结果冲突时新增隔离归档路径，不覆盖已有 completed/failed 结果，也不会让 processing 永久卡住。
- `rerun_contract()` 拒绝 `run_id == previous_run_id`，保持运行 lineage 单向前进。
- 新增重复运行、非法 finish ID、结果冲突隔离、失败后继续后续任务和新 run ID 回归测试。
- 工作区依赖 Python 定向回归 32 项通过；完整 UAT Worker 95 项、前端 1 项及全部本地 Gate 通过；PowerShell 连续进程验证为失败任务 1、成功任务 1、processing 0、退出码 0；网络调用 0。

## 2026-08-21 Phase 8 当前数量同步

- 完整 UAT 实际统计为 Worker 95 项、前端 1 项；同步更新当前计划、记忆和文档契约中的数量。
- 早期 85 项记录保留为历史审计证据，不代表当前测试总数。

## 2026-08-21 Phase 8 发布边界审计加固

- `scripts/phase8_audit.py` 现在把 Phase 8 文档、连续监督契约、前端语法 Gate、Pages 打包脚本和部署文档列为必需资产。
- 审计会在临时目录实际生成 Pages demo，精确核对 19 个 allowlist 文件、HTML 本地引用、Secret-like 内容、外部 URL、符号链接和发布标记；不联网、不发布。
- 修复 Pages 期望清单误包含不存在的 `run-meta.json`，并修正文档本地只读标记检查。
- 定向验证：Phase 8 审计、文档契约、连续监督契约、Pages 安全测试 3 项全部通过；完整 UAT 继续执行。

## 2026-08-21 测试与安全契约子 Agent 回归加固

- 修复迁移契约覆盖缺口：此前 UAT 只检查 `002_indexes.sql` 文件存在，现已逐项校验五个索引定义，并新增回归测试。
- 新增 `scripts/check_frontend_syntax.py`，UAT 现在对 `app.js`、`report.js`、`tasks.js`、`strategy.js` 执行本地 Node.js 语法检查。
- 定向与完整验证：Worker 95 项、前端 1 项、迁移契约 2 项、前端 JS 4 文件、完整 UAT 全部通过；网络调用 0，Secret value 命中 0。
- 直接使用缺少 `openpyxl` 的 Hermes Python 会导致 XLSX 测试级联失败；这是运行时选择问题。统一入口 `scripts/run_uat.py` 已使用工作区依赖 Python，不能把该环境误报当作代码回归。

## 2026-08-21 Phase 8 文档一致性监督回归

- 修正 `PROJECT_MEMORY.md` 当前更新时间为 2026-08-21，并修正 Pages demo 当前输出数量为 19 个文件。
- 在 `PROJECT_PLAN.md` 补充 Phase 8 当前本地 Gate、外部阻塞和下一步定义，明确外部 Gate 不等于项目完成。
- 新增只读检查 `scripts/check_phase8_documentation.py` 并纳入完整 UAT，检查阶段、测试数量、Pages 数量、外部 Gate 和防早停协议一致性。

## 2026-08-21 多 Agent 连续监督协议补齐

- 发现 `PROJECT_PLAN.md` 的旧 Phase 0 开工模板仍含“完成后停止，等待确认”，已改为遵循当前用户指令继续执行，并明确只有外部/危险/无安全下一步时才暂停。
- 新增 `docs/acceptance/continuous-supervision.md`，定义主 Agent 的项目目标监督、子 Agent 交付格式、状态重读和强制续行闭环。
- 新增 `scripts/check_continuous_execution.py`，并纳入 `scripts/run_uat.py`；该检查只读取本地协议文件，网络调用为 0。
- 本次文档监督改动不改变业务规则、数据、权限或外部部署状态。

## 2026-08-21 Phase 8 本地审计完成

- 新增 `docs/acceptance/phase8-local-audit.md`；本地部署前审计通过，外部确认项保持未执行状态。
- `ProviderContract` 429 有界重试回归通过；当时 Worker 测试 85 个，UAT 网络调用 0（历史记录）。
- 新增 `scripts/build_pages_demo.py` 与 `docs/deployment/pages-demo.md`；静态演示站仅打包 allowlist 内容，不执行发布。

## 2026-08-21 Phase 8 Supabase 契约回归加固

- 扩展 `supabase/migration_contract_check.py`：覆盖 profiles/stores/memberships/configs/tasks/runs/audit 全部 RLS 标记、私有报告字段，并拒绝公共报告或 Storage 读取策略。
- 新增 `supabase/test_migration_contract.py`，并纳入 `scripts/run_uat.py`；Phase 8 审计复用同一迁移契约，避免审计与 UAT 使用不同标准。
- 本地验证：当时 Worker 85、前端 1、迁移契约测试 2、完整 UAT、Phase 8 审计和 `compileall worker rules supabase` 全部通过；网络调用 0（历史记录）。
- 仍需外部确认：临时 Supabase 双用户 RLS、GitHub Pages HTTPS/CORS/Auth Redirect、私有 Storage 读取、Provider tools/list/schema/成本/单位/限流。

## 2026-08-21 连续开发防早停协议加固

- 将连续执行要求从“测试通过后继续检查”细化为强制执行器清单：每次命令返回后必须重读计划/状态，完成源码、测试、集成、契约/进程、文档和下一步清点。
- 明确单次 Worker、单个测试或完整 UAT 均不能作为项目完成信号；外部凭据阻塞只冻结对应外部项，不得吞掉本地可执行项。
- 本轮将重新执行完整本地 UAT，并以 UAT 后的状态清点作为收尾依据。

## 2026-08-21 Phase 8 静态 demo 打包验证

- UAT 已验证 Pages demo 打包器输出 19 个文件、无原始输入、无 Secret、未执行发布。
- Pages demo 打包器已补根入口重定向，根地址可进入 `frontend/login.html`。
- 当时本地阶段验证：Worker 85 个、前端 1 个、Phase 4/5/6/7 CLI、Phase 8 审计、Smoke、迁移契约和编译全部通过（历史记录）。

## 2026-08-21 Phase 8 本地部署前审计与 Provider 重试

- `ProviderContract.fetch()` 已实现最多 2 次有界重试、退避、429 计数和最终失败计数；假 transport 回归通过。
- 新增 `scripts/phase8_audit.py`，检查本地部署/安全契约并明确列出需要真实 Supabase、GitHub Pages、Storage、Provider 确认的项目。

## 2026-08-21 Phase 4 Module 02/03 本地实现

- 新增 `worker/report/modules.py`：自然位标杆与否定词候选均为确定性计算，不调用 Provider，不自动写 Amazon。
- 自然位缺失保持 `None`，标杆差距仅在双方排名都存在时计算。
- 否词分为 `exact_negative`、`phrase_negative`、`cautious`、`pending_confirmation`；有订单词不进入否词清单，证据不足不直接否死。
- 新增 2 个 Phase 4 回归测试。
- 新增 `scripts/build_phase4_modules.py`，可从既有报告生成 Module 02/03 JSON；输出明确 `write_back: false`。
- 新增 `worker/competitors/profile.py`、竞对 fixture 和 `scripts/build_competitor_profile.py`；UAT 已纳入竞对档案 CLI，Provider 调用为 0。

## 2026-08-21 Phase 5 竞对档案本地 Gate

- 新增 `docs/acceptance/phase5-competitors.md`；老任务兼容、新任务竞对 artifact、唯一 ASIN、稳定缓存键和图片/核心词留底均有回归证据。
- 当前本地 UAT：Worker 78 个、前端 1 个、Phase 4/5 CLI、Smoke、契约、编译全部通过，网络调用 0。

## 2026-08-21 Phase 6 Provider-neutral checklist

- 新增 `worker/diagnostics/listing_checklist.py`：图片组元数据、Listing checklist 和高市场机会/低 CVR 转化检查引用。
- 图片不下载、观察事实默认为 unknown、Provider 调用为 0；视觉 Provider 接入后只填事实，不改变 checklist 规则。
- 新增 3 个回归测试。
- 新增 `scripts/build_listing_diagnostics.py` 与本地 fixture；UAT 已纳入 checklist/图片组 Provider-neutral CLI。

## 2026-08-21 Phase 6 本地 Gate

- 新增 `docs/acceptance/phase6-checklist.md`；图片事实、checklist 状态、转化检查引用与 Provider 调用边界均有回归证据。
- 当前本地验证：Worker 81 个、前端 1 个、Phase 4/5/6 CLI、Smoke、契约、编译全部通过，网络调用 0。

## 2026-08-21 Phase 7 可追溯优化清单

- 新增 `worker/diagnostics/optimization.py`、`scripts/build_optimization_plan.py` 和 `optimization-plan.json` artifact。
- 每条动作保留数据事实、`rule_hits`、生效配置引用和下一步；`ai_may_change_action=false`。
- 任务流水线和 UAT 已纳入该清单，AI 不参与最终动作。

## 2026-08-21 Phase 7 本地 Gate

- 新增 `docs/acceptance/phase7-optimization.md`；91 条演示动作均可追溯到事实、规则命中和配置引用。
- 当前本地验证：Worker 83 个、前端 1 个、Phase 4/5/6/7 CLI、Smoke、契约、编译全部通过，网络调用 0。
- `task_runner` 成功任务现在同步留底 `rank-benchmark.json` 与 `negative-keywords.json`，Phase 4 模块进入正式本地 artifact 链路。
- 报告页已增加 Module 02/03 本地摘要：显示已上榜数量、否词候选分组和 `写回 Amazon：否`。
- 新增 `docs/acceptance/phase4-modules.md`；`scripts/run_uat.py` 已纳入 Phase 4 CLI 回归。

## 2026-08-21 Phase 3 报告字段与 artifact schema

- 规则输出补齐 `keyword_role`、`product_stage`、`evidence_level`、`next_action_text`、`ai_explanation`、`ai_next_action_text`。
- 报告 schema 升级为 `report-0.2`；前端宽表动态展示广告、市场、排名、证据、下一步和缺失字段。
- 已用当前代码重新生成 `data/golden/market-demo-report/`，91 个关键词、对账通过、Provider snapshot 版本为 `fixture-market-v1`。

## 2026-08-21 连续执行协议实测通过

- 在同一执行链内连续完成：报告 artifact 动态读取、任务页本地任务预览、策略页版本化配置预览、前端契约扩展和全套验证。
- 当前前端本地联调页面：报告读取 `market-demo-report/master-table.json`；任务读取 `report-meta.json`；策略读取 `rules/defaults/stable.json`。
- 验证结果：Worker 70 个、前端 1 个、4 个前端 JS 语法检查、契约检查、Smoke Test、编译检查全部通过；网络调用 0。

## 2026-08-21 Phase 3 Gate 本地复核

- 对账通过，核心广告事实保留；规则/配置/Provider 版本可追溯。
- 五色业务组与灰色数据状态保留独立映射；规则输出含 `rule_hits`、`missing_fields`、`next_action_text`，AI 字段不改动作。
- 报告页宽表通过动态字段渲染，支持横向滚动、筛选和 JSON 导出；本地 golden artifact 已与 `report-0.2` 同步。
- 最终本地验证：Worker 71 个、前端 1 个、契约/迁移/Smoke/编译/JS 语法全部通过，网络调用 0。

## 2026-08-21 连续开发执行协议修复

- 将“测试通过”明确降级为子步骤完成，不再作为当前阶段自动收尾条件。
- 新增连续执行收尾协议：每个子步骤后必须继续检查代码缺口、回归/UAT、进程级验证、文档同步和下一项安全工作。
- 真实外部服务需要凭据时，仍须先完成所有不依赖凭据的本地模拟、失败路径、契约和文档工作。

## 2026-08-21 任务 API 契约输入边界

- `create_task_contract` / `rerun_contract` 现在校验必填字段和安全 ID，拒绝路径穿越型或空标识。
- 新增 1 个任务契约回归；报告页本地 artifact 联调已接入，完整 UAT 通过：Worker 70 个、前端 1 个、网络调用 0。

## 2026-08-21 前端演示退出会话清理

- 所有指向登录页的演示退出链接现在都会清除 `kwcc_demo_session`，避免退出后旧演示会话继续生效。
- 前端静态契约检查已锁定退出清理逻辑；完整 UAT 通过，Worker 69 个、前端 1 个。

## 2026-08-21 配置与私有报告标识边界统一

- `task_runner` 在规则阶段前显式校验用户策略配置；非法配置返回 `CONFIG_INVALID`，不生成正式报告或规则快照。
- `SupabaseGateway.read_report` 与 HTTP transport 使用同一安全 ID 字符集，拒绝将查询表达式注入任务/运行标识。
- 新增 2 个回归测试；完整 UAT 通过：Worker 68 个、前端 1 个、网络调用 0。

## 2026-08-21 报告入口安全契约统一

- `build_report` 直接调用也会校验策略配置，不能绕过参数边界。
- `SupabaseGateway.read_report` 现在必须显式携带 access token，并继续校验安全 task/run 标识。
- 新增 1 个回归测试；完整 UAT 通过：Worker 69 个、前端 1 个、网络调用 0。

## 2026-08-21 队列原子写入与历史结果保护

- `worker/queue/file_queue.py` 入队前复用完整载荷校验，缺少 `input_path` / `input_file_path` 的任务不会写入 `pending`。
- 入队、非法归档和完成/失败归档统一采用临时文件替换，避免连续 Worker 读取半写入 JSON。
- `finish()` 检测目标结果已存在时拒绝覆盖，保护历史运行记录。
- 新增 2 个队列回归测试；完整 UAT：Worker 66 个、前端 1 个、契约检查和 Smoke Test 全部通过。
- PowerShell 启动器进程级验证：连续处理 2 个任务，`completed=2`、`failed=0`、`processing=0`；网络调用 0。

## 2026-08-21 任务追溯 artifact 补齐

- `worker/pipeline/task_runner.py` 成功运行现在额外写入 `input-meta.json` 与 `rules-snapshot.json`。
- `input-meta.json` 固化输入文件名、SHA-256、解析器版本、币种和对账结果。
- `rules-snapshot.json` 固化规则版本、配置版本、Provider snapshot 版本和完整生效配置；对账失败不会生成规则快照。
- 定向回归与完整 UAT 通过：Worker 64 个、前端 1 个、网络调用 0、Secret value 命中 0。

## 2026-08-21 队列载荷与幂等边界加固

- `worker/queue/file_queue.py` 现在校验 JSON 对象、`task_id` / `run_id`、`input_path`（兼容 `input_file_path`）以及队列文件名一致性。
- 非法载荷会归档到 `failed/INVALID_QUEUE_PAYLOAD`，不会遗留在 `processing` 阻塞连续 Worker。
- 同一 `task_id + run_id` 在 pending、processing、completed、failed 任一状态存在时禁止重复入队，避免覆盖历史运行结果。
- `worker/queue/runner.py` 兼容任务契约中的 `input_file_path`。
- 回归新增 4 项；完整 UAT：Worker 64 个、前端 1 个、契约检查和 Smoke Test 全部通过；`network_calls=0`、Secret value 命中 0。

## 当前结论

项目当前已具备本地 Phase 2 实现：报表解析、规则引擎、报告生成、文件队列、持续 Worker 入口和静态前端骨架均已落地；真实 Supabase/Auth/Storage/Provider 接入仍未配置。

本状态以当前源码、测试和 UAT 结果为准；历史审计记录保留在本文件下方，不再代表当前实现状态。

## 已完成的 Phase 0 只读审计

- 已读取：`AGENTS.md`、`MEMORY.md`、`PROJECT_MEMORY.md`、`PROJECT_PLAN.md`。
- 已检查根目录文件、子目录、隐藏目录、实现文件和配置文件。
- 已核对 `DESIGN-airtable.md` 存在；根目录与 `Page/DESIGN-airtable.md` SHA-256 相同。
- 已核验演示报表 `商品推广_搜索词_报告_LED演示.xlsx`：
  - Sheet：`SP搜索词报告`；
  - 数据行：118；
  - 去重搜索词：91；
  - 展示：1,230,627；点击：9,045；花费：5,123.10；销售额：20,982.29；订单：1,578；
  - `led light`：4 行、展示 15,216、点击 131、花费 82.96、销售额 408.42、订单 30。
- 已发现历史文档中的公共读报告方案，与当前 `PROJECT_MEMORY.md` / `PROJECT_PLAN.md` 的私有受控读取要求冲突；历史方案不得执行。

## Phase 1 当前进展

- 已创建 `worker/ingestion/ad_report_parser.py`：支持 XLSX / CSV / TSV、动态表头、动态列识别、数值清洗、搜索词聚合、比率重算、单币种校验、重复解析一致性和 JSON 输出。
- 已创建 `scripts/parse_ad_report.py` CLI。
- 已固化 golden fixture 到 `data/fixtures/`，并记录 SHA-256、来源和基线元数据。
- 已创建 `data/golden/demo-report/reconciliation.json` 与 `ad-aggregated.json`。
- 已创建 6 个自动化测试，当前全部通过。
- 已加入 3 份样例输入回归：原始 XLSX、动态列 CSV、无币种/零销售额 TSV；三者均通过解析与对账。
- 已固定 3 个演示表抽样词：`led light`、`led strip lights for home`、`room accessories`。
- 当前演示报表对账：展示、点击、订单差值为 0；花费、销售额差值为 0.00；重复解析一致；币种为 USD。

当前仍需用户确认：3 个抽样词的人工核对结果，以及 Phase 1 Gate 是否通过。正式任务编排层尚未接入，因此“对账失败后不调用 Provider/不进入规则引擎”的上层停机链路将在后续任务模型中实现；当前 CLI 已以非零退出码表示失败。

## 技术栈基线

| 项目 | 当前事实 |
|---|---|
| 前端 | 未发现实现 |
| Worker | 未发现实现 |
| 中转台 / 数据库 | 未发现 schema、迁移或连接配置 |
| Provider | 未发现接入代码；西柚、AI、视觉 Provider 均待验证 |
| 报表解析 | 未发现解析器；只有可作为 golden fixture 的 XLSX |
| 规则引擎 | 未发现实现；规则目前存在于文档中 |
| 报告生成 | 未发现实现 |
| 测试 | 未发现测试代码或测试配置 |
| 部署 | 未发现 Git 仓库、前端构建或部署配置 |
| 版本管理 | 当前目录无 `.git` |

## 已完成能力与缺失能力

### 已具备

- 项目长期记忆和分阶段计划；
- 业务规则草案、数据定义、动作映射、排序和安全要求；
- `DESIGN-airtable.md` 设计基准；
- 一份结构清晰、可复核的 Amazon 搜索词 XLSX 样例；
- 样例报表总量和 `led light` 聚合基线。

### 尚未具备

- 动态表头 / 动态列识别解析器；
- 搜索词确定性聚合和 `reconciliation.json`；
- CSV 支持、单币种校验、解析器版本留底；
- Provider tools/list 自发现、标准化、缓存、限流、调用记录；
- 配置 schema、配置覆盖、config_version、rule_version；
- 规则引擎、映射表、黄金规则测试和确定性测试；
- 前端登录、任务、策略、报告和权限；
- 私有报告读取链路、RLS / 等效访问控制、审计；
- GitHub Pages / Worker / 中转台部署资产。

## 硬编码阈值与规则风险

- 运行时代码中未发现硬编码，因为目前没有运行时代码。
- 历史规则文档含 20%、30%、45%、20 点击、$50、难度等示例值；按 `PROJECT_MEMORY.md` 约束只能作为模板示例，不能直接实现为固定阈值。
- 旧实施教程描述“报告对象公共读 + 随机文件名 + 永久公开链接”；这与当前私有报告、登录后受控读取、不得长期公共链接的要求冲突，应标记为历史方案。
- 旧材料还包含“先做完整工人”和“永久公开报告”等偏实现指令；在当前指令优先级下，必须服从最新用户指令与 v1.4 记忆/计划。

## action_group / ui_conclusion / 颜色映射差异草案

当前没有实现映射，因此差异不是“代码错误”，而是“实现缺失”。Phase 2 应按版本化定义落地：

| action_group | ui_conclusion | UI |
|---|---|---|
| scale_up | add | green |
| defend_rank | defend | green |
| hold_steady | keep | cyan |
| cautious_test / continue_observation | cautious | yellow |
| optimize_listing / optimize_bid / optimize_structure | optimize | orange |
| stop_loss / reduce_or_pause | stop_loss | red |
| data_missing | data_missing | gray |

必须保持 `add` 与 `defend` 底层独立；不能合并成 `add_defend`。

## Provider 未决假设与验证方法

- 西柚：尚无实际 tools/list、schema、字段单位、限流、成本和缓存证据。Phase 0/Provider 接入时先做 tools/list，自发现工具，不猜工具名；再用 10～30 个关键词分层小样验证。
- AI（当前倾向豆包）：尚无模型、超时、成本和降级配置。需验证响应 schema 不含动作字段，失败时报告仍能生成。
- 视觉 Provider：尚未确定模型、隐私边界和成本；留到 Phase 6 前验证。
- 备用 Provider：尚未确定；不得在未确认成本与字段语义前接入。

## DESIGN 依赖检查

- `DESIGN-airtable.md` 存在，根目录与 `Page/` 镜像一致。
- 文档明确白色画布、深色主按钮、留白、表格工作区、宽表横向滚动、响应式断点等视觉基准。
- 文档是 Airtable 营销 / 设计系统提取，不包含本项目业务结论颜色和报告字段定义；五色业务结论 + 灰色数据状态仍以 `PROJECT_MEMORY.md` / `PROJECT_PLAN.md` 为准。
- 开发前应记录设计文件哈希，并形成与报告 UI 的适配说明。

## 未备案部署路线检查

- 当前计划路线一致：前台优先 GitHub Pages；Worker 只在服务器后台运行；服务器不通过大陆 80/443 对外提供前台网页。
- 报告必须保持私有，通过登录后的受控读取链路访问。
- 当前尚无 GitHub Pages、Supabase、Worker、Storage 或 CORS 配置可验证，因此部署路线“设计已冻结、实现未开始”。
- 后期备案只迁移托管、域名、HTTPS、CORS、Auth Redirect 和页脚，不重写任务、规则、Provider、Worker 和报告数据模型。

## Phase 1 前置阻断项

1. 尚无解析器、测试框架或正式 fixture 目录。
2. 样例文件实际名称为 `商品推广_搜索词_报告_LED演示.xlsx`，与记忆中带 `(1)` 的文件名不一致；内容基线一致，但需在 Phase 1 固化实际文件名与 SHA-256。
3. 尚未确定 CSV 结构、币种识别和多币种拒绝行为的实现位置。
4. 尚无 `reconciliation.json` 生成与失败即停止机制。
5. 尚无 3 份真实 / 样例报表，无法满足 Phase 1 Gate。
6. 尚无版本控制；建议在首次代码实现前建立 Git，并明确不纳入密钥和原始敏感文件。

## 复用 / 重建判断

当前没有可复用的运行时代码，不能称为增量改造。建议按“从零搭建轻量 V1 数据底座”，但复用现有文档规则、设计基准和 XLSX golden fixture；不要在 Phase 0 直接搭建完整前端或 Provider。

## 下一步

## Phase 2 / 前端基础当前进展

- 已建立 `worker/config/config_merge.py`：全局 → 店铺 → 阶段 → ASIN → 任务覆盖，生成稳定 `config_version`。
- 已建立 `worker/tasks/task_model.py`：区分 `task_id`、`run_id`、`previous_run_id`，支持可复现键。
- 已建立 `worker/rule_engine/engine.py`：输入完整性、证据等级、强止损、自然位防守、谨慎测试、优化、加投/保持的最小确定性判断；AI 不参与动作。
- 已建立 `rules/definitions/action_mapping.json`、`rules/defaults/stable.json`、`rules/data_dictionary.md`。
- 已生成前端页面骨架：
  - `frontend/index.html`：登录页；
  - `frontend/workspace.html`：登录后工作台 / 任务 / 策略摘要；
  - `frontend/report.html`：Module 01 报告页；
  - `frontend/styles.css`、`frontend/app.js`：样式和本地演示交互。
- 前端当前为静态演示，不宣称已完成真实 Supabase Auth、上传、任务队列或权限控制；未包含 Secret。
- 当前测试总数：14 个，全部通过；前端静态入口和 Secret 扫描通过。

下一步：继续把策略中心配置、规则快照、报告数据接入页面，再接真实 Auth / Task / Storage；Provider 仍需先完成语义验证和小样纪律。

## 本轮继续执行结果

- 已建立 `worker/report/generate_report.py`，串联：报表解析 → 对账门禁 → 配置 → 规则引擎 → 稳定排序 → 报告 JSON。
- 已生成 `data/golden/full-demo-report/`，包含 `master-table.json`、`action-results.json`、`report-meta.json`；91 个关键词、对账通过、规则/配置版本留底。
- 已补充 `docs/architecture.md`、`docs/data-dictionary.md`、`docs/provider-semantics.md`。
- 前端新增页面：`frontend/login.html`、`frontend/tasks.html`、`frontend/strategy.html`，并保留 `index.html`、`workspace.html`、`report.html`。
- 前端静态检查通过：6 个 HTML 页面，无 Secret。
- Python 测试总数仍为 15 个，全部通过。
- 当前演示样例在没有市场 Provider 快照时主要落在 `hold_steady` / `continue_observation`，这是数据缺失下的保守结果，不应视为 Provider 已接入。

## Auth / Task / Storage 接入准备

- 已新增 `supabase/migrations/001_initial_schema.sql`：profiles、stores、store_memberships、strategy_configs、tasks、task_runs、audit_events，以及基础 RLS 草案。
- 已新增 `worker/api/task_contract.py`：任务状态转换、失败原因结构、创建任务和重跑契约。
- 已新增 `worker/storage/artifacts.py`：task/run 分目录、artifact 白名单、ID 校验、路径穿越防护和 JSON 读写。
- 前端新增任务创建、上传占位、产品阶段和策略试算交互；仍是演示模式，未连接真实 Auth / Storage。
- SQL 只完成本地静态检查，尚未在 Supabase 项目执行迁移；执行前必须人工复核 RLS 与部署环境。
- 自动化测试总数：19 个，全部通过。

## 本轮任务执行入口

- 已新增 `worker/pipeline/task_runner.py`：执行解析、对账门禁、报告生成和 artifact 留底。
- 输入不存在或解析失败：任务在 ingestion 阶段失败，不生成正式报告。
- 对账失败：任务在 reconciliation 阶段失败，明确跳过 Provider 和规则阶段。
- 成功运行：生成 `ad-aggregated.json`、`reconciliation.json`、`master-table.json`、`action-results.json`、`report-meta.json`、`run-meta.json`。
- 自动化测试总数更新为 21 个，全部通过。
- 新增静态审查记录：`supabase/MIGRATION_REVIEW.md`、`frontend/FRONTEND_CONTRACT.md`。

## 本轮 Worker 队列

- 已新增 `worker/queue/file_queue.py` 作为本地队列适配器：`pending → processing → completed/failed`。
- 任务文件名使用 `task_id__run_id.json`，ID 经过安全校验，重复任务和路径穿越会被拒绝。
- 队列适配器不改变 `task_runner`、规则引擎或报告格式；未来可替换为 Supabase 查询适配器。
- 自动化测试总数更新为 23 个，全部通过。
- 本轮 Agent 未留下额外代码改动；真实 Supabase Gateway 和前端契约测试仍保留为后续小任务。

## Gateway 与前端契约

- 已新增 `worker/adapters/supabase_gateway.py`：Auth、Task、Config、私有 Report 读取接口；未配置 transport 时明确抛错，不发网络请求。
- 已新增 `frontend/contract_check.py` 和 `frontend/test_frontend_contract.py`：检查 6 个页面、本地资源引用和 Secret-like 内容。
- Worker 测试总数：25 个，全部通过；前端契约测试：1 个，通过。
- 当前 Gateway 仍是 transport-neutral 契约，真实 Supabase SDK / HTTP 适配尚未启用。

## Provider 接入前契约

- 已新增 `worker/providers/base.py`：Provider transport、retry policy、usage log、cache key、normalize、snapshot。
- 已新增 `worker/providers/config_validation.py`：策略配置必需区块、ACOS 边界和止损参数校验。
- 未注入 transport 时 Provider 明确拒绝调用，不产生外部请求。
- Worker 测试总数更新为 28 个，全部通过。

## Worker CLI 与 MCP tools/list 契约

- 已新增 `scripts/run_worker_once.py` 和 `worker/queue/runner.py`：单次领取并执行本地队列任务，无任务时安静退出。
- 已新增 `worker/providers/mcp_protocol.py`：构造 `tools/list` JSON-RPC 请求、解析工具 schema、识别 MCP 错误；不发网络。
- 已新增 `supabase/migrations/002_indexes.sql`：成员、任务、运行和审计查询索引。
- Worker 测试总数更新为 31 个，全部通过。

## MCP 客户端与运行环境模板

- 已新增 `worker/providers/mcp_client.py`：注入式 MCP 客户端，支持 `tools/list` 自发现、工具 schema 快照留底和明确的 transport 缺失错误。
- 已新增 `.env.example`，仅列出变量名，不包含任何真实值。
- 已完成全项目 Secret value 扫描，通过；前端契约测试仍通过。
- Worker 测试总数更新为 32 个，全部通过。

## Provider 标准化与缓存

- 已新增 `worker/providers/xiyou_normalizer.py`：自然位取 `or` 最小位次，广告位取 `sp/sb/sbv` 最小位次；未返回保持 `null`，不填 0；Top3、流量和缺失字段统一标准化。
- 已新增 `worker/providers/cache.py`：显式 TTL、缓存命中、过期行为和安全 cache key。
- Provider 回归测试总数更新为 36 个，全部通过。
- 真实西柚字段单位、工具 schema、成本和限流仍未验证；当前标准化层只依据项目记忆中的待验证语义草案。

## 市场快照合并与规则联调

- 已新增 `worker/providers/market_merge.py`：市场/排名快照只补充标准字段，不覆盖广告展示、点击、花费、订单、销售额等真实表现。
- 已新增 `data/golden/provider-snapshot-demo.json`，作为本地 Provider snapshot fixture。
- `worker/report/generate_report.py` 已支持传入市场快照；联调结果：`led light → defend_rank/defend`，`room accessories → optimize_bid/optimize`。
- 已生成 `data/golden/market-demo-report/`，保存带市场快照的完整报告输出。
- Worker 测试总数更新为 39 个，全部通过。

## 策略试算

- 已新增 `worker/rule_engine/preview.py`：临时配置重算、动作数量变化、逐词 before/after 差异。
- 试算结果明确标记 `persisted: false`，不会写正式配置或覆盖历史运行。
- 边界测试已覆盖：修改 0 单止损点击阈值会改变动作，但不改变原始广告事实。
- Worker 测试总数更新为 40 个，全部通过。

## Supabase HTTP 接入适配

- 已新增 `worker/adapters/supabase_http.py`：Auth、REST tasks、pending claim、私有 report 查询的请求构造。
- 采用显式注入 `request_fn`；未注入时不会创建或发送 HTTP 请求。
- 测试覆盖 Auth header、REST path、payload 和未配置保护。
- Worker 测试总数更新为 42 个，全部通过。

## Phase 2 本地 Smoke Test

- 已新增 `scripts/smoke_test.py` 和 `docs/acceptance/phase2-smoke.md`。
- 完整链路已通过：队列提交 → Worker 领取 → XLSX 解析 → 对账门禁 → 规则 → 报告 artifact → completed 归档。
- Smoke Test 明确 `network_calls=0`，不连接 Supabase、Provider 或 AI。
- Worker 测试总数更新为 43 个，全部通过。

## 当前未完成但已明确边界

- Supabase Auth / RLS / Task 表 / Storage 尚未接入；
- Worker 任务轮询已通过 `scripts/run_worker_loop.py` 接入；真实报告受控读取尚未接入；
- 西柚 MCP 尚未调用，实际 tools/schema/成本/限流仍待验证；
- 页面中的演示按钮尚未连接真实 API。

## 2026-08-21 本地 UAT 结果

- 已执行 `scripts/run_uat.py`，整体结果 `passed: true`。
- Worker 测试 43 个、前端契约测试 1 个，全部通过。
- 前端页面、静态资源引用、迁移文件检查通过。
- 本地端到端 Smoke Test 通过，报告 artifact 已生成，`network_calls=0`。
- Secret value 扫描命中数为 0；未使用任何真实 Supabase、Provider 或 AI 凭据。
- 因此当前可继续进入本地联调/实现；真实外部服务验证仍以配置凭据后的受控小样本为边界，不影响本地 UAT 结论。

## 2026-08-21 UAT 运行时修复

- 发现系统默认 Python 未安装 `openpyxl`，导致 XLSX 测试在错误运行时下失败；不是解析逻辑回归。
- `scripts/run_uat.py` 已增加运行时选择：支持 `KWCC_PYTHON`，否则在缺少 `openpyxl` 时自动切换工作区依赖 Python。
- 修复后重新执行完整 UAT：43 个 Worker 测试、1 个前端测试、契约检查和 Smoke Test 全部通过。

## 2026-08-21 前端演示会话边界

- `frontend/app.js` 已对后台页面增加演示会话保护：无 `kwcc_demo_session` 时重定向至 `login.html`。
- 保护范围覆盖工作台、任务、策略和报告页面；登录页不会被保护逻辑拦截。
- 页面仍明确标注为演示模式，不等同于 Supabase Auth；真实登录接入后应替换为受控 Auth 会话校验。
- 变更后完整 UAT 通过，网络调用仍为 0。

## 2026-08-21 前端会话契约回归

- `frontend/contract_check.py` 已增加会话保护回归检查：必须存在演示会话标记、登录重定向代码，以及四个后台页面的保护标记。
- 该检查只验证静态边界，不把演示 localStorage 会话当作生产认证。
- 变更后完整 UAT 通过。

## 2026-08-21 Supabase HTTP 输入边界

- `worker/adapters/supabase_http.py` 已校验 Base URL 必须为绝对 HTTP(S) 地址。
- 私有报告查询的 `task_id/run_id` 只接受安全 ID 字符集，拒绝将查询表达式注入 REST filter。
- `SupabaseGateway` 对 worker、task、run 必填边界增加校验；未配置 transport 仍不会发网络请求。
- Worker 测试更新为 45 个，前端测试 1 个；完整 UAT 通过。

## 2026-08-21 私有请求令牌边界

- `auth_user` 与私有 `read_report` 请求现在必须显式携带 access token。
- 测试区分两层失败语义：缺少 token 直接拒绝；携带 token 但未配置 transport 时抛出未配置错误且不发网络。
- Worker 测试更新为 46 个，前端测试 1 个；完整 UAT 通过。

## 2026-08-21 Supabase 迁移契约检查

- 新增 `supabase/migration_contract_check.py`，静态检查任务/运行表 RLS、成员读取策略、私有报告字段和店铺访问函数未被意外移除。
- `scripts/run_uat.py` 已纳入该检查；检查不执行 SQL，不替代临时 Supabase 项目中的真实 RLS 验证。
- 完整 UAT 通过，网络调用仍为 0。

## 2026-08-21 策略配置数值边界

- `worker/providers/config_validation.py` 已拒绝 bool、NaN、正负无穷等非业务数值作为 ACOS/止损阈值。
- 新增回归测试，Worker 测试更新为 47 个；前端测试 1 个，完整 UAT 通过。

## 2026-08-21 规则动作映射契约

- 新增 `rules/action_mapping_contract_check.py`，检查所有规则动作都有稳定的 `ui_conclusion/ui_color` 映射，并锁定六色展示顺序。
- 规则回归覆盖 Unknown 市场数据、缺失自然排名、零销售额 ACOS 为未知，以及 add/defend 语义分离。
- Worker 测试更新为 50 个；前端测试 1 个，完整 UAT 通过。

## 2026-08-21 报告版本追溯

- `build_report`、`run_task` 已支持 `provider_snapshot_version`，并写入 `master-table.json`、`action-results.json`、`report-meta.json`、`run-meta.json`。
- 报告生成回归验证同输入行顺序稳定、原始 SHA-256/规则版本/配置版本保留，Provider 版本可追溯。
- Worker 测试更新为 51 个；前端测试 1 个，完整 UAT 通过。

## 2026-08-21 连续 Worker 入口

- 新增 `worker/queue/supervisor.py` 与 `scripts/run_worker_loop.py`，补齐持续轮询入口；`run_worker_once.py` 仍保留为单次执行器。
- 连续入口支持多任务处理、空队列等待、异常有界指数退避、`stop_event`/Ctrl+C 优雅停止和有限循环测试模式。
- Worker 回归测试更新为 59 个；前端测试 1 个，完整 UAT 通过。
- Supervisor 连续异常时使用有界指数退避，避免异常状态下退出或高速空转。
- 非法 JSON 队列项会归档为 `failed/INVALID_QUEUE_PAYLOAD`，不会阻塞后续合法任务。
- 常驻入口默认每 30 秒输出 `worker_heartbeat`，可通过 `--heartbeat-interval` / `-HeartbeatInterval` 调整。
- 已完成真实进程级验证：PowerShell 启动器连续处理 2 个任务，`completed=2`、`failed=0`，空队列后按测试轮数正常结束。
- 单任务未预期异常会归档为 `failed` 并继续轮询，避免任务永久停留在 `processing`。
- Worker 启动时会恢复上次异常中断遗留在 `processing` 的任务到 `pending`，避免重启后卡单。

## 2026-08-21 Worker 监督异常语义回归

- 连续 Worker 回归已覆盖：重复异常有界退避、失败/成功结果分开计数、processing 恢复、心跳、空队列等待和优雅停止。
- 监督器不会把失败任务误记为完成；异常不会无限快速重试。
- Worker 测试更新为 60 个；前端测试 1 个，完整 UAT 通过。

## 2026-08-21 Worker 退避上限边界修复

- 修复 `worker/queue/supervisor.py`：首次异常/空队列等待以及成功后的退避重置统一受 `max_backoff` 限制。
- 新增回归测试覆盖 `poll_interval > max_backoff` 与 `max_backoff=0`，避免第一次等待绕过上限。
- 运行时与队列测试 9 项通过；完整 UAT 通过，Worker 测试 85 项，前端 1 项，网络调用 0。
- PowerShell 启动器进程级空队列验证通过：2 个有限轮询周期均输出心跳，退出码 0。

## 2026-08-21 Provider-neutral 配置与降级边界回归加固

- `McpProvider.tools/list` 复用统一 Provider 重试路径，429/5xx 受有界退避策略约束，并记录 `actual_calls`、`rate_limited` 与失败计数。
- 缺失 transport 明确记录本地失败但不计外部调用；`RetryPolicy` 拒绝负重试、非有限或负退避和非法 HTTP 状态。
- 配置校验补齐非对象配置、版本字段、证据阈值顺序、市场机会阈值、自然位边界和低 CVR 边界；规则动作与 AI 解释字段边界保持只读。
- 定向 Provider/MCP/config/rule 测试 20 项通过；完整 UAT Worker 101 项、前端 1 项通过，编译、Smoke、Phase 8 审计通过，网络调用 0。
