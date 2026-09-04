# 005 production jobs 本地审查

状态：**本地迁移草案，未应用**。依赖 001–004 与 Supabase Storage。
本交付只包含本迁移、本文档、`test_production_jobs.py`。不变更任务账本，
不执行远程 SQL、不调用 Provider、不安装依赖；不是生产部署或真实 RLS 验收。

## 接入合同

1. 已登录用户先生成 task/run UUID，将原始文件上传至私有 `inputs`：
   `storeUUID/userUUID/taskUUID/input.xlsx` 或 `input.csv`，路径 UUID 为小写标准形式。
   bucket 上限 10 MiB（10485760 字节）；提交接受 1–10485760 字节。
   上传必须 `upsert=false`。客户端计算小写 64 位十六进制 SHA-256 后提交。
2. `kwcc_submit_task(p_task_id uuid, p_run_id uuid, p_store_id uuid,
   p_self_asin text, p_product_stage text, p_input_file_path text,
   p_input_file_hash text, p_input_size bigint, p_strategy_id uuid default null)`
   返回 `{task_id, run_id, status:'pending'}`，包括精确重放；这是稳定提交确认，
   最新运行状态须另行读取 tasks/task_runs，不能用重放响应覆盖实时状态。
3. Worker 以 service_role 调用 `kwcc_claim_run(p_worker_id text,
   p_lease_seconds int default 300)`。空队列返回 JSON/SQL null；成功返回
   `{task:完整tasks行, run:完整task_runs行, config:strategy.config或null}`。
   Worker ID 允许 1–128 个 ASCII 字母、数字、`_.:-`；租约范围 1–3600 秒。
4. Worker 保存领取返回的 `run.lease_token`，以
   `kwcc_heartbeat_run(p_run_id uuid, p_lease_token uuid,
   p_lease_seconds int default 300)` 续租。返回 bool；false 时停止处理及上传/结束，
   不再次调用 Provider。续租不会缩短当前有效租期。
5. Worker 使用私有 inputs 下载原始字节，在任何 Provider 调用前检查实际长度并
   **重新计算 SHA-256**，与任务中的 hash/size 对照；不可信客户端 hash 仅完成语法校验。
   扩展名和 MIME 都不证明文件内容有效，Worker 仍需解析和对账。
6. 报告由 service_role 使用不可覆盖上传写入已有私有 `reports`，路径必须是
   `taskUUID/runUUID/report-<48位小写十六进制>.json`。文件随机名由 Worker 生成；
   SQL 校验命名格式和对象存在性，不证明随机熵或报告内容正确。
7. `kwcc_finish_run(p_run_id uuid, p_lease_token uuid, p_status text,
   p_report_path text default null, p_rule_version text default null,
   p_config_version text default null, p_provider_snapshot_version text default null,
   p_failure_reason jsonb default null)` 返回 bool。
   只接受 completed/failed；旧租约、空令牌、已终态或租约过期返回 false。
   参数违规抛出固定安全错误码字符串，不把错误参数或原始异常复制进审计。
8. 已登录店铺成员可调用
   `kwcc_rerun_task(p_task_id uuid, p_previous_run_id uuid, p_run_id uuid)`，
   返回 `{task_id,run_id,status:'pending'}`，包括精确重放。允许同店成员重跑，
   不限最初创建者。必须指定同任务的终态前一次 run，任务也须终态且无活动 run。

ASIN 接受 `B0` 加 8 个大写字母/数字；阶段与现有前端一致：
`new/growth/stable/clearance/seasonal_restart`。策略必须属于同一店铺，
且其非空 asin/product_stage 与提交匹配；此接口不接受其他店铺或 store_id=null 的全局策略。
省略策略时，submit 在同一事务从 strategy_configs 选择同 store_id/product_stage 的
配置：匹配 self_asin 的配置优先，其次 asin=null；各组按 created_at DESC、config_id DESC
确定最新版本，不选其他 ASIN 的配置。选中的 config_id 固化到 tasks.strategy_id，
原始可空入参存入 tasks.requested_strategy_id，以区分自动选择与显式指定。
没有匹配配置时 strategy_id=null，claim 返回 config=null，Worker 使用受版本管理的默认规则。
首个运行也将选择冻结到 task_runs.strategy_id。后续 append 新配置不改变既有运行；
显式重跑按相同店铺/阶段/ASIN 优先规则选择最新版本并冻结到新 run，旧 run 保持不变。
此迁移只依赖 001–004，不依赖 006，也不创建 heads 表。006 由主 Agent 独立追加策略版本 RPC。
claim 按 run.strategy_id 读取 strategy.config；策略 append-only 的前提下版本不会漂移。
若受信管理员原地修改该历史行，SQL 不承诺配置内容不可变，Worker 仍须保存生效快照。

## 权限与 Storage

- inputs INSERT 的 authenticated permissive policy 只打开该 bucket；另有 restrictive
  INSERT guard 校验 auth.uid 非空、owner_id 本人、路径 userUUID 本人、店铺成员和
  has_store_access。以字符串比较店铺 UUID，避免恶意路径触发 UUID 强转异常。
- bucket API 限制体积、MIME；允许 XLSX、CSV 常见 MIME 及 octet-stream（浏览器可能
  无法辨认 MIME）。最终扩展名仍必须为 input.xlsx/input.csv。SQL 通过 Storage
  生成的 metadata.size 对照提交大小；不把用户自报尺寸视为文件尺寸。
- 本迁移不增加 inputs SELECT 权限；上传响应丢失时通过 submit 检验对象是否已存在。
  不用下载输入或 upsert 来恢复。未成功提交的上传可能留下孤立对象，清理策略另行授权。
- restrictive UPDATE/DELETE guard 拒绝 anon/authenticated 修改或删除 inputs/reports；
  UPDATE 的 USING 和 WITH CHECK 同时阻止改名、覆盖及跨 bucket 移入。
  restrictive INSERT guard 也拒绝普通用户写报告，即使已有其他 permissive policy。
- 004 的 reports_member_read 完整保留；新 guard 不影响 SELECT。没有永久公开链接。
- 003 的 tasks 列级 INSERT 与表级 INSERT 均显式撤销；现有 tasks_member_insert policy
  保留但没有底层 INSERT 权限。任务创建全部走 RPC，不扩张 tasks/task_runs/audit 写权限。
- task_runs 的 authenticated 表级 SELECT 改为安全字段列级 SELECT；lease_token、
  worker_id、lease_until 不向成员开放，报告路径/状态/版本/策略标识仍受 RLS 读取。
- 所有 5 个 SECURITY DEFINER 固定 `search_path=''`，表和外部 schema 函数全限定，
  pg_catalog 内置函数使用 PostgreSQL 隐式安全路径。逐函数 revoke PUBLIC/anon/
  authenticated/service_role，再仅 grant 目标角色。3 个 Worker RPC 另外检查
  `auth.role()='service_role'`；authenticated 没有其 EXECUTE。
- service_role 是受信后台边界，具有 Storage/RLS 绕过能力。本 SQL 不能阻止拿到
  service_role 凭据的代码直接篡改对象；Worker 必须使用不可覆盖上传且不得向前端暴露密钥。

## 幂等、事务和租约

- 首次 submit：校验用户/店铺、参数、策略及现存私有 inputs 对象的精确路径、
  owner_id、metadata.size；持有对象共享锁后，事务创建 tasks、首个 task_runs、audit。
  任一步失败全部回滚。Storage 上传本身在此前独立完成，不与 SQL 事务原子绑定。
- 相同 task UUID 通过事务级 advisory lock 串行化；同 task/run、同创建者以及所有
  提交参数（包括 size 和原始可空 requested_strategy_id）精确相同才重放。返回 pending 确认，
  不新增行或审计；重新换 run ID 不能充当新提交。任何字段冲突拒绝。
  已存在的精确重放仍验证当前成员身份及参数，但不重新查 Storage/策略，避免提交成功后
  对象被受信管理员移除导致重放变成新任务。首次入库的来源校验不会被这一分支绕过。
- task/run 全局主键与活动 run 唯一索引防止并发重复；跨任务复用 run UUID 整笔回滚，
  返回 JOB_ID_CONFLICT。相同前次 run 只能有一个后继，禁止历史链分叉。
- claim 使用 `FOR UPDATE OF t,r SKIP LOCKED` 原子领取，先锁任务、再运行；finish/
  rerun 遵循相同顺序，heartbeat 只锁 run。领取和 task/run 状态变更及 audit 同事务。
- 每次 claim 先把可锁定的过期 processing（包括旧记录无租约）标 failed，写入
  LEASE_EXPIRED 审计；不重置 pending，不自动再次调用 Provider。正在被锁定的过期行
  留待后续 claim 清理。无新任务时仍提交过期清理并返回 null。
- heartbeat/finish 在取锁后用 `clock_timestamp()` 检查租约；finish 在报告对象锁后
  再读取时钟执行令牌、状态、有效期 CAS，等待锁的时间不算续租。finish 成功清空
  lease_until，保留 worker_id/token 用于运行追溯（不会把 token 写进 audit）。
  同一 finish 请求第二次返回 false；调用方可读取运行状态确认第一次是否成功。
- 完成需要精确报告对象存在且 bucket 私有，共享锁将对象记录稳定到事务结束。
  failed 不接受 report_path。任务状态、运行状态/版本、failure_reason 和 audit 原子更新。
- 重跑不修改旧 task_runs/report_path/版本/failure_reason，而是新建 run、记录
  previous_run_id 并将 task 汇总状态改 pending。相同 task/previous/new-run 的请求
  重放返回 pending 确认，不重复 audit；旧链已有后继时换一个新 ID 被拒绝。
- 租约无法中止已经发出的 HTTP 请求，也无法保证外部 Provider 的 exactly-once。
  Worker 不得在租约失效后继续发起工作；人工重跑前应确认可能发生的外部调用。

## 安全失败载荷

失败必须只含 3 个键，示例：

```json
{"code":"INPUT_HASH_MISMATCH","stage":"ingestion","retryable":false}
```

code 白名单：INPUT_INVALID、INPUT_HASH_MISMATCH、INPUT_SIZE_MISMATCH、
INPUT_DOWNLOAD_FAILED、RECONCILIATION_FAILED、CONFIG_INVALID、
COMPETITOR_PROFILE_INVALID、PROVIDER_ENRICHMENT_FAILED、REPORT_GENERATION_FAILED、
REPORT_UPLOAD_FAILED、UNEXPECTED_TASK_ERROR。LEASE_EXPIRED 仅由 claim 内部产生。
stage 白名单：task、worker、ingestion、reconciliation、config、competitors、provider、
report、storage。code/stage 必须为字符串，retryable 必须为 JSON false。
未知 code/stage、空值、额外键、嵌套 JSON、message、URL、原始异常均拒绝。
Worker 需剥离本地 failure_reason.message，映射到上述有限 code/stage；用户可见文字由前端
按 code 提供。本迁移不会把本地异常消息原样发布。版本参数可为 null；非空仅接受
1–128 字符的 ASCII 字母、数字、`_.:-`，不得放入凭据或原始 Provider 响应。

## 本地验证与未完成 Gate

运行：`python -B -m unittest discover -s supabase -p test_production_jobs.py -v`。
测试为**静态合同**：函数签名/权限、DDL 事务/重放、原列级权限撤销、Storage guard、
路径正反例、对象来源和尺寸检查、幂等比较、租约 CAS、报告绑定、失败白名单、历史链。
不会创建数据库、不伪装并发/RLS/Storage 运行证据。默认与 bundled Python 均未安装
pglast/pg_query/sqlparse，PATH 无 psql；可选 pglast 测试明确 skip，未安装或联网。
没有 PostgreSQL 语法解析、函数执行、数据库事务、真实双 Worker 竞态的已通过声明。

2026-09-03 集成复核：上述命令共 28 项，27 项静态合同通过、1 项可选 parser 跳过；
原 `python -B -m unittest discover -s supabase -p test_migration_contract.py -q`
21 项通过，原测试文件未修改。无网络调用、无安装、无迁移应用。

应用前须另获授权，在可丢弃的本地/测试 PostgreSQL + Supabase Storage 环境验证：

1. 确认 001–004 完整、Storage owner_id 为 text、metadata.size 来自实际上传；
   复核现存函数所有者、角色继承和自定义 ACL/policy。执行 005 两次验证幂等。
2. 检查遗留每 task 多个 pending/processing、同 previous_run_id 多个后继；唯一索引
   遇到冲突会让整笔迁移失败，必须人工决定历史治理，不能删数据凑通过。
   旧任务 input_size 留 null；不自动补值，旧任务禁止经本 rerun RPC 重跑。
3. A/B 店铺成员、非成员、匿名：合法上传/提交成功，跨店/跨 owner/错误 UUID 路径、
   10MiB+1 上传、零长度提交、缺失对象、错误 size、格式错误 hash、跨店策略均拒绝。
   两次同输入提交只生成一组 task/run/audit，逐字段变化冲突，失败不留半成品。
   验证省略策略时 ASIN 专属优先于更晚的店铺默认，组内最新优先，其他产品/阶段排除；
   无匹配返回 null；append 新版本后精确重放仍绑定原 config_id，新重跑选择最新匹配版本。
4. service_role Worker 执行两个独立会话并发 claim，同 run 最多被领取一次；
   heartbeat 与过期清理、finish 的锁等待交错；错 token/null token/过期全部拒绝。
   claim 过期清理不会重入 pending；审计失败使整个事务回滚。
5. 报告不存在、public bucket、其他 task/run、固定 master-table.json、非48hex 拒绝；
   正确 private 对象可完成。普通用户报告 INSERT/UPDATE/DELETE 继续拒绝，旧读策略通过。
6. 多次并发重跑、旧 previous 分叉、非终态、跨任务 previous、重复/冲突 run ID；
   旧运行的报告/版本/失败原因保持不变；重复 finish 返回 false 后读取状态可确认结果。
7. 完整生产前端→上传→RPC→Worker 下载重 hash→Provider→私有报告→finish→前端读取的
   接入/UAT 仍由主 Agent 的 production-job-pipeline 阶段处理，不由本静态测试替代。

当前范围内交付为这三个本地文件；外部应用与真实 PostgreSQL/Storage 验收仍未执行。
