# R12 预算与恢复边界决策记录（2026-09-15）

本记录服务于 `LUNU-05-项目审核验收与逐项修复执行清单-20260911.md` 的 R12。它不是“已完成”证明，也不替代真实 Provider、Supabase、Worker 或线上报告验收。

## 1. 当前已经有本地证据的内容

以下内容已经由当前源码和本地回归证明，不能重复当作未完成任务运行：

1. `worker/providers/cache.py` 提供带 TTL 的磁盘缓存；缓存键包含 Provider/适配器版本、命名空间和完整请求身份，缓存文件不保存认证信息。
2. Xiyou、Sorftime 和视觉适配器在实际生产组合中都使用显式进程级预算；重试也占用预算，费用未知或超过预留时 fail-closed。
3. `worker/runtime/provider_preflight.py` 按任务最坏未缓存调用上界估算下一项任务，不用“只够一次请求”冒充“够完整任务”。
4. `supabase/migrations/011_provider_claim_preview.sql` 的 `kwcc_preview_next_run()` 只返回最小任务投影，不修改队列。
5. `supabase/migrations/012_claim_previewed_run_atomically.sql` 将预览得到的 `task_id/run_id` 与实际 claim 绑定；队列头变化时嵌套 claim 回滚并返回空。
6. 预算不足时 Worker 不领取任务，空队列不执行普通 claim；六任务 fake 场景证明额度耗尽后剩余任务仍为 pending，显式刷新额度后可继续处理。
7. 当前完整本地 UAT 为 21/21；LUNU-05 行为 Gate 为 13/13；本轮 `network_calls=0`、`external_calls=0`、Secret 命中为 0。
8. `ProviderAttemptBudget` 已作为三个 Provider 的共同进程级请求尝试上限；生产 CLI 必须显式提供 `--max-total-provider-attempts`。每个真实传输尝试（包括 5xx/429 后的重试）只预留一个 slot，缓存命中不消耗 slot；回执记录 `actual_calls` 与 `max_attempts`，但不把次数伪装成统一 credit。

## 2. 未闭合边界 A：持久预算状态与选择性重跑

### 2.1 事实

- 当前预算对象的生命周期是 Worker 进程级，计数不会写入 Supabase 的任务/run 记录。
- 当前 `kwcc_rerun_task` 是完整新 run 重跑接口，要求前一个 run 已终态；它没有“只重跑某个 Provider/模块”的 scope 参数。
- 当前安全行为是：领取前预算不足就保持 pending；这避免了“先取走任务、再因预算不足失败”。
- 当前缓存可以跨进程复用成功事实，但缓存命中并不等于预算账本已经持久化，也不等于失败任务能够选择性恢复。

### 2.2 不能直接猜测的部分

不能在没有产品决定和部署契约的情况下任选下面一种行为：

- Worker 重启后把旧预算清零；这会变成用重启绕过额度。
- Worker 重启后永久沿用旧预算；这可能让合法的月度/周期额度无法刷新。
- 预算预留在 claim 前永久扣除；这会把尚未执行的任务算作已消费，并可能造成容量无故损失。
- 预算预留在 claim 失败时自动退回；如果远端实际已收到请求，会低估真实消费。
- 把视觉/竞对/排名中的某一部分标为“选择性重跑”而不冻结输入、规则、Provider 版本和前一 run 关系。

### 2.3 后续实现契约（由 Lunu 或项目负责人确认后执行）

如果要正式关闭这个边界，必须先确定并写入版本化契约：

1. 预算周期身份：例如 `account + provider + budget_period + budget_policy_version`。同一周期重启不可清零；新周期必须显式切换身份。
2. 账本事件：至少记录 `run_id`、Provider、请求哈希、预估调用、实际尝试、已知费用、未知费用、结算状态和原因；不得记录 token、密码、原始响应或带认证 URL。
3. 预留与结算：预留要有唯一键并可幂等；远端费用未知时按保守规则冻结，不自动退款；明确人工/管理员如何在新周期恢复。
4. 选择性重跑：只允许白名单 scope，创建新 `run_id`，引用旧 run 的冻结输入和成功缓存；禁止覆盖旧报告；scope 不允许改变原任务的 ASIN、店铺、核心词和确认版本。
5. 崩溃恢复：Worker 在 claim、Provider 调用、结算、上传、finish 各阶段崩溃后，下一次运行能根据持久事件决定继续、等待、转失败或要求新 run，不能靠重复请求试探。
6. 行为回归：至少覆盖进程重启、同一 run 重复结算、claim 成功后崩溃、未知费用、六任务耗尽、指定单模块重跑、旧报告不可变和新周期显式恢复。

在上述契约没有确定前，当前实现保持“pending + 显式恢复”的保守行为，不应把该边界标为 ready，也不应自行新增重置额度按钮。

## 3. 未闭合边界 B：跨 Provider 信用上限

### 3.1 事实

当前三个 Provider 的计量单位不同：

- Xiyou 返回/预算使用 `calls` 与可能的 `cost_credits`；未知费用按保守预留处理。
- Sorftime 当前可统计请求次数，但项目没有公开、可验证的跨服务 credit 换算规则。
- Doubao 视觉适配器统计请求次数和输出 token；输出 token 不是 Sorftime 或 Xiyou credit。

因此不能把三者的整数直接相加后称为“总 credit”，也不能拿本地估算值宣称账户账单已经对账。

### 3.2 可安全采用的两层上限

在 Provider 给出正式计费映射前，生产配置只能同时保留：

1. 每 Provider 自己的调用/credit/token 硬上限；
2. 一个名称明确为 `total_provider_attempts` 的跨 Provider 请求尝试上限。它只表示请求次数，不表示统一费用；每一次请求尝试（含可计费失败和重试）只计一次。

只有当 Provider 文档或账户回执明确给出单位、周期、失败计费和重试计费规则后，才能另行设计 `total_provider_credits`，并在报告中区分 `estimated`、`reserved`、`actual`、`reported`。

当前本地代码已经落实上述“次数上限”这一安全层：claim 前按任务最坏调用数和 `RetryPolicy` 计算 `total_provider_attempts`，claim 后由同一个 `ProviderAttemptBudget` 约束 Xiyou、Sorftime、Doubao；达到上限时在发起下一次 Provider 请求前失败并保留可诊断错误码 `TOTAL_PROVIDER_ATTEMPTS_EXHAUSTED`。该层仍是单 Worker 进程边界，不解决跨进程、跨周期或账户级账本问题。

## 4. 线上 Gate 不能被本地记录替代

本地记录完成后，按以下顺序执行线上验收：

1. 在受控 Supabase 项目应用 010、011、012 迁移；核对函数 ACL、服务角色限定、RLS、私有 Storage 和幂等/回滚行为。
2. 发布与本指纹一致的 Worker、前端和数据库版本；Worker 使用环境注入 Secret，日志只输出安全错误码和哈希摘要。
3. 用已授权测试账号提交一个全新 run，固定自有 ASIN、2–5 家竞品、核心词、确认版本和预算；不覆盖历史 run。
4. 验证六模块报告中实际采集数、合法无结果、partial/failed 原因和 Provider usage。不能只看 HTTP 200 或 `full_report_complete`。
5. 用已登录窗口访问报告，再用无痕/未登录窗口访问同一个地址；后者必须跳回登录或明确拒绝，不能读取私有对象。
6. 检查报告对象名是不可猜测的随机名；截取 1440px 桌面和 390px 手机截图，截图不得包含 Secret、密码、签名 URL 或原始 Provider 响应。
7. 将每个 Gate 的 task/run、release manifest、SQL 版本、模块状态、关键字段路径、HTTP/业务码和截图路径写入新的验收回执。

## 5. 交给 Lunu 时的硬性禁止项

- 不要为了通过 UAT 把 `full_report_complete`、`real_provider_verified` 或模块 `ready` 直接改成 true。
- 不要用重启清零预算，不要把 Xiyou/Sorftime/Doubao 单位硬加成统一 credit。
- 不要把本地 fake、旧 run、旧截图、公开 HTML 壳页面当作线上六模块完整报告。
- 不要把原始请求/响应、密码、JWT、API key、私钥或含认证信息的 URL 写入 Git、日志、聊天或任务回执。
