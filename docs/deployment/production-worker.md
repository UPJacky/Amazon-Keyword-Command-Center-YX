# Production Worker（本地实现，未发布）

本入口通过 Supabase RPC 领取租约，从私有 inputs 下载广告报表，在临时目录内调用已有 `run_task`，将单一 JSON bundle 上传私有 reports，读回验证 SHA-256 后才调用 finish。默认不读取凭据、不请求网络。可选的西柚关键词指标模式见 `xiyou-live-enrichment.md`；它仍不是完整六模块报告。

## 启动与权限

Python 需要现有 Worker 依赖；处理 XLSX 需要 `openpyxl`。从项目根目录运行默认零网络进程验证：

```powershell
python -B scripts/run_production_worker.py --max-cycles 2 --poll-interval 0.01
```

默认 CLI 是无网络常驻轮询；`--max-cycles` 限制轮数。SIGINT/Ctrl+C 和 SIGTERM 设置停止事件；空闲等待可立即结束，正在执行的 Provider 回调返回后停止后续上传/finish。Python 不强行终止已开始的第三方回调，注入方必须配置其超时。

只有服务器服务环境可提供 `SUPABASE_URL` 和 `SUPABASE_SERVICE_ROLE_KEY`。不读取 `.env`、用户目录、浏览器会话、MCP 配置或凭据文件，不接受命令行 key。不要把 service key 放入前端或报告。显式授权后的命令为：

```powershell
python -B scripts/run_production_worker.py --confirm-live --ad-only --worker-id server-worker-1
```

本轮未执行此 live 命令。CLI 要求明确选择 `--ad-only`，或按 `xiyou-live-enrichment.md` 同时提供 `--xiyou-keywords` 与调用/credit硬上限；两者互斥，两种模式均不能声称全报告完成。缺少确认时在读取环境变量前拒绝。服务端也可显式构建 `ProductionWorker(transport=..., provider_enricher=...)` 或按任务注入 `provider_factory`。回调只在输入/配置及 pipeline 对账门禁后执行；由注入方负责 Provider 授权、超时、预算和字段来源，不会自动发现工具。

## RPC 与对象合同

所有 RPC 均 POST `/rest/v1/rpc/<name>`，JSON 请求/响应，显式 `Accept-Profile/Content-Profile: public`：

| RPC | 参数与结果 |
| --- | --- |
| `kwcc_claim_run` | `p_worker_id`, `p_lease_seconds=300`；返回 `null` 或 `{task, run, config}`；`config` 是 run.strategy_id 冻结选择的策略 JSON 或 `null`，runtime 直接使用返回值、不另查最新策略 |
| `kwcc_heartbeat_run` | `p_run_id`, `p_lease_token`, `p_lease_seconds`；只接受 JSON 布尔 `true` |
| `kwcc_finish_run` | `p_run_id`, `p_lease_token`, `p_status`, `p_report_path`, `p_rule_version`, `p_config_version`, `p_provider_snapshot_version`, `p_failure_reason`；只接受 JSON 布尔 `true` |

task/run/store/created_by/lease_token 必须为非零、小写标准 UUID，run 若包含 task_id 必须匹配 task。`self_asin` 必须为 10 位大写字母数字。任务输入对象键严格为 `storeUUID/userUUID/taskUUID/input.xlsx` 或 `input.csv`，不含 bucket 前缀；拒绝 URL、本地路径、跨任务/跨用户/跨店路径、编码字符、查询参数和路径穿越。

下载只访问 `GET /storage/v1/object/authenticated/inputs/<object-key>`。必须提供 64 位 SHA-256 `input_file_hash`，与实际下载字节比对；实际文件必须非空且不超过 10 MiB。RPC 草案中的 `input_size` 可缺失或 null；提供时必须是正整数且与实际字节数一致。同时兼容 `input_file_size`、`input_file_size_bytes`；多个字段存在时全部校验。即使声明大小缺失，流式下载仍受 10 MiB 硬限约束。

失败 RPC 回执严格为 `{code, stage, retryable:false}`，不发送 message 或原始异常，匹配 005 RPC 白名单。对账、配置和 Provider 失败保留已知代码；上传/读回失败映射 `REPORT_UPLOAD_FAILED`，读回哈希不一致本地诊断为 `REPORT_HASH_MISMATCH`，未知异常映射 `UNEXPECTED_TASK_ERROR`。CLI 本地诊断仅含固定安全文字，无上游响应体、请求头或凭据。

## 生效配置与 bundle

配置顺序：`load_default_config()` 完整稳定期底座 → `rules/strategy_templates.json` 中对应阶段模板 → RPC 返回的策略 config → `task_config_override`。阶段映射为 new/new_product_growth、growth/balanced_growth、stable/stable_profit、clearance/clearance、seasonal_restart/seasonal_restart。策略或任务覆盖中的 product_stage 若与任务不一致则拒绝。通过已有 `validate_config` 验证后，剔除传入 config_version，使用已有 `config_version()` 生成内容版本；不修改任何规则文件，不推断新的业务阈值。

主报告所有字段原样保留，要求 `schema_version="report-0.2"`、`rows` 为数组、对账通过和 input_sha256 与任务哈希匹配，然后添加：

- `task_id`、`run_id`：对应当前领取的任务与运行。
- `self_asin`、`store_id`、`product_stage`、`marketplace`：仅在任务实际提供非空字符串时加入；不推断 marketplace。
- `modules`：以已有 artifact 完整文件名为键，内容为该 JSON 对象。固定包含 `rank-benchmark.json`、`negative-keywords.json`、`optimization-plan.json`；只有 pipeline 实际生成时才包含 `competitors.json`。可显式注入与任务 self_asin 匹配的 competitor_profile；不凭 ASIN 列表虚构竞品数据。未生成 Listing artifact 就不添加对应键。
- `provider_evidence`：默认 `{status:"not_requested", real_provider_verified:false}`；普通注入按有无 market_rows 标记 `injected_data` 或 `no_market_data`。只有显式标记 `real_provider_verified:true` 的真实 Provider 适配器才会进入 `real_provider_data`，注入本身不证明真实 Provider 来源。
- `report_scope`：默认 `ad_only`；普通注入为 `injected_provider_data`；真实 Provider 适配器为 `live_provider_data`。`full_report_complete` 只有在主表非空、真实 Provider 已验证且五个必需业务 artifact（rank、negative、competitors、listing、optimization）全部声明 `module_status.status=ready` 时才为 `true`，不再硬编码。缺失排名、市场或模块数据继续保留原有 null/missing_fields/unknown，不填 0 或伪造成功状态。

直接使用 pipeline 随机生成的 `report-<48hex>.json` 文件名。上传对象键为 `taskUUID/runUUID/report-<48hex>.json`，不含 reports 前缀，与前端私有报告读取及 RPC 合同一致。bundle 在内存组装，不覆盖 pipeline 的历史 artifact。

处理顺序严格为：领取 → 首次续租 → 校验配置/下载输入 → 校验字节大小与哈希 → TemporaryDirectory 内运行 pipeline/读取产物 → 清理临时文件 → POST `/storage/v1/object/reports/<key>`，`x-upsert:false` → GET `/storage/v1/object/authenticated/reports/<key>` → 比对上传/读回哈希 → 最终续租 → finish(completed)。现有 XLSX 解析器未显式 close 的工作簿循环由 runtime 在退出临时目录前执行垃圾回收释放，避免 Windows 文件句柄占用；没有修改 parser。

`completed` 只表示广告任务 bundle 已验证持久化且数据库接受 finish，并非全报告、真实 Provider 或全部外部 Gate 完成。前端可直接读取 `bundle.modules["rank-benchmark.json"]` 等，不需要额外对象请求。

## 租约、网络与恢复语义

独立 daemon 心跳线程覆盖慢 Provider/下载/上传期间，默认每 100 秒续租 300 秒。参数 `--lease-seconds` 接受 3–3600 秒，`--heartbeat-interval` 必须为正且不超过租约三分之一；生产建议 HTTP timeout 远小于心跳间隔。本地 monotonic deadline 从请求开始计时，拒绝已经过期的迟到回执。心跳 false、异常或本地过期都视为失租，不再 finish 成功。最终续租和 finish 与后台心跳串行，避免完成后再续租。

transport 仅允许配置的 `https://<project>.supabase.co` origin、三类 RPC 和指定私有 Storage 路由；拒绝自定义 origin/HTTP/URL 凭据/端口/额外路径。使用 urllib、关闭代理继承、拒绝所有重定向，单请求一次尝试，无隐藏重试。连接/读取 timeout 默认 20 秒（最大 60），流式分块检查时间和字节数；RPC 响应限 1 MiB，输入限 10 MiB，报告限 64 MiB。下载超长或 Content-Length 不一致失败。两次轮询是新的显式 claim，并非对上传或 finish 重试。

上传成功但读回失败会提交失败状态，可能留下未引用的私有对象，不自动删除或覆盖。finish 超时/异常/false 时不重复 finish，返回 pending 供服务端状态核对；不得自动创建新 run 或重试可能收费的 Provider。当前 005 草案的租约回收将过期运行标记 failed，并不自动重新排队。SIGINT 留下的运行遵循同一过期恢复流程。

私有 bucket 与 worker-only service-role RPC 授权由 SQL/部署侧保证；当前 005 草案的 completed finish 还验证 reports bucket 为 private 且对象存在。runtime 不修改权限或发布 SQL。

## 本地验证与待办

```powershell
python -B -m unittest worker.tests.test_production_runtime worker.tests.test_task_runner worker.tests.test_provider_pipeline worker.tests.test_config_merge -v
```

测试使用 fake transport，覆盖输入 hash/跨任务路径/可选大小/10 MiB、上传失败、读回错误、失租与独立 Provider 心跳、回执严格布尔与失败白名单、完成顺序、阶段配置、随机文件名、前端 bundle 合同、临时清理、SIGINT handler 和有界 CLI 子进程。CSV 和 91 行 XLSX 均真实调用已有 pipeline。真实网络、外部 Provider 和发布均未执行。

2026-09-03 联合回归：生产 runtime、现有 task runner、Provider pipeline、config merge 共 52 项，51 passed / 1 环境 skip；含实际 91 行 XLSX 和 CLI 有界子进程。最终 005 SQL 已只读复核：`config` 来自 `run.strategy_id`，`input_size` 为 bigint，lease_token 为 UUID，失败 reason 白名单与 runtime 映射一致。前端 `read/readModule` 的 report-0.2、task/run 绑定和 `*.json` 模块键也已只读核对。本轮没有改账本、SQL、pipeline 或前端。

Pending：在已授权测试项目执行 005/006 后实测 claim/download/upload/readback/finish 私有链；西柚模式仍只补关键词基础指标，Listing/自然标杆/缺失竞品与图片指标继续保持未完成。

仓库现有 `.gitignore` 的 `runtime/` 规则会忽略 `worker/runtime/production.py` 和 `worker/runtime/__init__.py`。本轮写入范围不含 `.gitignore`，没有更改忽略规则或暂存文件；主 Agent 提交时需对这两个新源码文件显式 `git add -f`，避免漏交付。
