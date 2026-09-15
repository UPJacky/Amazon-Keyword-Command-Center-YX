# LUNU-05 当前短交接（2026-09-15，R12 本地补强后）

> 当前最新完整 UAT 已更新为 Worker 372、LUNU-05 行为 Gate 13、Supabase 静态 71；下方若仍出现 110/115 项，仅是较早回执的历史描述，不作为当前统计。

- 总目标：完成 LUNU-05 R01-R15 与第 6 节逐项业务验收。当前仍未完成，不能用旧 E20 回执或通用 UAT 代替业务验收。
- 监督器：`lunu05-business-remediation` 为 `RUNNING`。本轮继续做本地证据链和安全边界回归；真实 Provider、Supabase、部署和线上截图仍是独立 Gate。

## 本地已完成

- 任务输入契约已严格校验：B0 开头 10 位 ASIN、大写两位站点、产品阶段、相对安全的 `.xlsx/.csv` 路径、SHA-256 和 1–10 MiB 文件大小。
- 业务确认绑定已补齐 task/store/ASIN/input hash/object/hash 的服务端契约与静态迁移检查。
- 西柚/Sorftime 字段别名、图片 gallery、来源追踪、缓存键、有限重试、预算用量和 Provider-only 市场行已补齐；没有用广告数据伪造自然数据。
- 视觉证据现在要求可定位区域、来源引用、可读性和置信度；`unknown/low/unreadable` 不得进入 judged/ready。
- 否词、竞对、自然位、份额、实体优化、观察窗口/退出条件和防守 ACOS 已补业务规则与 fail-closed 反例。
- 报告持久化已包含主模块、补充模块、`rules-snapshot.json`、`run-meta.json`、`provider-usage.json`、证据 manifest 和 canonical hash；缺字段仍显示 `partial`。
- 前端 live 报告读取现在校验证据 manifest 的 task/run、注册文件、manifest 自哈希和所读模块哈希；篡改的新 bundle 在渲染前返回 `REPORT_INVALID`，旧 `ad_only` 兼容包仍按旧语义处理。
- 确认对象在生产证据中只保存 `confirmation_sha256`；视觉证据只保存图片输入哈希，不保存图片 URL；西柚、Sorftime、Doubao 回执只保存请求/响应哈希、状态、尝试次数和结果，不保存正文或认证信息。
- 生产 Sorftime 组合已启用任务级预检：先按未缓存的自有 ASIN、去重竞品和主关键词类目特征估算调用量；预算不足时整任务不发起 Sorftime 请求，全缓存时估算为 0 并允许零调用复用缓存。
- 生产 Xiyou 组合已启用任务级预检：市场关键词与可选竞品快照按整任务估算调用量；预算不足时在任何 Xiyou 传输前 fail-closed，全缓存时估算为 0 并允许零调用复用缓存。
- 新增 `supabase/migrations/011_provider_claim_preview.sql` 与生产 `kwcc_preview_next_run`：claim 前只读返回最小任务投影；`worker/runtime/provider_preflight.py` 统一估算 Xiyou/Sorftime/视觉最坏未缓存调用上界，预算不足不 claim，空队列不调用 claim。
- 新增 `supabase/migrations/012_claim_previewed_run_atomically.sql` 与生产 `kwcc_claim_previewed_run`：预览成功后按 task/run 身份原子领取，队列变化时回滚嵌套 claim 并返回空，防止预算估算错配任务。
- 新增六任务预算耗尽/恢复 fake Gate：预算耗尽后剩余 pending 任务不丢失，显式刷新预算后可继续领取；`scripts/test_lunu05_business_gate.py` 现为 13 项行为 Gate 全部通过，完整 UAT 为 21/21（Worker 372、Supabase 静态 71）。
- R12 两个尚未闭合边界已经单独形成决策记录：`docs/acceptance/r12-budget-decision-20260915.md`。其中明确了持久预算/选择性重跑必须先确定周期、预留、结算和崩溃恢复契约；Xiyou、Sorftime、Doubao 不得在没有 Provider 计费映射时硬加成统一 credit。

## 最近验证结果

- artifact registry 回归已单独通过：`python -m unittest scripts.test_lunu05_business_gate worker.tests.test_artifacts -v`，17 项通过（3 项平台不支持 symlink 的测试跳过）。前端 manifest/模块篡改回归：`node --test frontend/tests/client.test.js`，47 项通过。
- 生产边界、视觉回执、西柚、Sorftime、LUNU-05 Gate 定向回归共 110 项通过；确认 hash、图片输入 hash、原始 payload 拒绝、Sorftime/Xiyou 预算不足整任务不调用和全缓存零调用均有断言；同时修复了 LUNU-05 Gate 对 `ProductionWorker.__new__` 的跨测试污染。
- 最近一次完整 UAT（已包含前端 manifest、Provider 回执 hash、Sorftime/Xiyou 任务预检、011/012 迁移静态合同和原子预览领取）通过 21/21：Worker 372（跳过 12 个环境能力项）、前端 8、编排 25、连续 63、Supabase 静态 71、Pages 57 文件/46 构建测试、文档 15；network_calls=0、external_calls=0、Secret 命中=0。
- 本地 fake 工厂结果明确保留 `report_scope=injected_provider_data` 且 `full_report_complete=false`，所以该测试只证明接线和持久化，不冒充真实 Provider 完整数据。

## 尚未通过的真实 Gate

- Pages 发布源已查明：公开关键脚本与远端 `main` 根目录旧版本一致；新 checkpoint `b40afef` 已在 `master`，但没有进入线上。不要重复推送 `master`；先按 `docs/acceptance/github-pages-publish-source-audit-20260915.md` 在 Pages 设置中确认 Source，再走唯一一条定向发布路径。

- 没有新一轮真实六模块 Provider 生产任务的完整数据证据；视觉图片观察、市场/类目特征、买家清单、文字证据和优化退出条件仍需真实新 run 验证。
- 没有重新执行真实 Supabase 010 确认 RPC/迁移、双用户 RLS、私有 Storage 读取和未登录拒绝的线上矩阵。
- 没有重新验证部署后的 Worker 重启、GitHub Pages 精确 Origin/CORS 和带地址栏的新报告截图。
- R12 已完成 Sorftime/Xiyou 任务级未缓存调用估算、领取前最小预览、预算不足整任务 fail-closed、缓存命中后的零调用放行、六任务耗尽后的显式刷新恢复模拟和预览身份原子领取；仍未接入预算耗尽后的持久化恢复/选择性重跑和跨 Provider 信用总上限。
- fake transport、旧报告、旧截图和本地 demo 均不能作为上述真实 Gate 的替代。

## 后续顺序

1. 重读监督器并领取最新输入指纹。
2. 核对完整 UAT 回执已写入状态，并执行 `git diff --check`。
3. 预览/claim 并发竞态已闭合；不要重复跑同一回归。R12 的持久恢复/选择性重跑和跨 Provider credit 需按决策记录先得到契约确认，再实现或在验收中登记为未通过边界。
4. 按 R07-R15 拆分真实外部 Gate；真实调用只使用环境注入凭据，不把 Secret 写入回执或聊天。线上 Gate 未通过前不得关闭 `lunu05-business-remediation`。
