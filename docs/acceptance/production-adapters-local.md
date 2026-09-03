# 真实接入前的本地适配链路

本记录证明可注入的本地接入链路，不代表外部服务已经配置或上线。默认仍为离线 demo；所有本地测试使用 fake transport。

## 2026-09-03 验证证据

- `python scripts/run_uat.py`：20/20 Gate 通过，Worker 206 项（12 项环境跳过）、前端 7 项、连续执行 63 项、编排 25 项、迁移 21 项、Pages 31 文件/11 项测试、文档 15 项。
- 本地 Pages 构建输出包含根登录、独立 `tool/` 和 `report/`；工具输入边界、刷新和失败原因、报告 fetch/门禁/宽表格契约通过；网络与外部调用均为 0。

## 2026-08-31 验证证据

- `python scripts/run_uat.py`：20/20 Gate 通过，Worker 197 项（12 项环境跳过）、前端 7 项（包含 Node 26 场景）、连续执行 63 项、编排 25 项、迁移 21 项、Pages 21 文件/11 项测试（4 项环境跳过）、文档 15 项。
- Python/PowerShell 连续 Worker 各运行 2 个周期、2 次心跳，errors=0；Smoke 与 Phase 4～7 CLI 通过；六个前端 JS 语法通过。
- 本地 UAT network_calls=0、external_calls=0、Secret=0。真实 Supabase 的独立证据见 supabase-live-evidence-20260831.md，不能混称本地零网络测试。

## Supabase 与私有报告

- REST 表接口明确发送 `Accept-Profile: public` 和 `Content-Profile: public`，不依赖项目默认 schema。Auth 和 Storage 不发送这些 profile headers。
- `SupabaseHttpTransport.read_report()` 继续只返回元数据；`read_report_content()` 才是私有内容读取。
- 内容读取必须显式配置两个 transport、HTTPS origin、公开 key、当前用户 token 和受信的私有桶名。先 Auth，再经同一用户的 RLS 查询 task/run，最后读取绑定对象。
- 只接受 `task_id/run_id/<filename>.json` 相对路径，禁止 URL、编码穿越、跨 run、公共链接、角色提升和跟随重定向。缺少 transport 时不发任何请求；异常体与凭据不写入错误。
- `PrivateReportGatewayTransport` 将既有 Gateway 的 `reports.read_private` 接到上述链路。每次都使用本次调用者 token；未实现的配置写入、原子任务领取明确拒绝，不能假装成功。
- 真实私有桶及 Storage RLS 仍须外部验证，不能用本地 fake 测试替代。

## Provider 小样与主流水线

- `ProviderBatchOrchestrator` 默认 disabled。真实调用必须显式注入单次尝试 transport、正常化器、已确认的工具请求、账户/数据集 namespace、版本及 `CallBudget`。
- 完整 JSON 请求、provider、namespace 和语义版本共同决定缓存键；同批重复不重复返回行。显式刷新保留失败前的最后成功缓存，不缓存错误。
- 硬预算按每一次实际 transport 尝试消耗，包括 429、5xx 和异常重试，消耗后不退款。共享预算只保证单进程，多进程部署不能冒充全局预算；transport 禁止隐藏重试。
- 缓存拒绝链接/reparse point、危险键名、非法 TTL/时间戳；完整 JSON 原子发布。
- `McpHttpTransport` 只通过 `last_response_metadata` 暴露受控响应头白名单（Content-Type、成本、Retry-After、限流和版本相关头）；控制字符、超长值和未白名单字段会被丢弃，Authorization、原始错误体和请求/响应 Secret 不进入证据。`scripts/probe_provider.py` 会把该白名单写入 `response_metadata_after_tools_list`/`response_metadata_after_sample`，便于未来外部 Gate 复核。
- `as_enricher(request_builder)` 可直接注入 `run_task(..., provider_enricher=...)`。只有输入解析、对账、规则配置和竞品校验通过后才调用；拷贝输入和配置，Provider 不得修改规则。
- 输出必须包含 market_rows、版本和整数 usage，写入私有 `provider-usage.json`。异常安全归一为 provider 阶段失败，不持久化原始异常。
- 端到端本地验证覆盖首次运行调用、第二运行缓存命中、版本追溯、非法输入零调用以及失败不生成正式报告。

## 前端与部署边界

- 默认 demo 与显式 live 分离；live 配置只允许公开 key，真实会话不能由 demo 标记替代。
- 独立复核发现并修复后退缓存泄露旧视图：pagehide 立即锁定并暂停页面，persisted pageshow 强制重新加载，新的客户端只读取当前会话；初始 Auth 延迟响应不得重新展示离开页面的数据。离线 VM 覆盖退出、换用户、过期和延迟响应四场景；尚未声称真实浏览器 BFCache 验证通过。
- 上传后端、策略写入权限尚未配置时必须说明未执行，不能把本地文件路径当上传成功或显示“已保存”。
- Pages demo 打包器生成固定离线 public-config，不复制现场 live 配置；新增客户端脚本仍只按 allowlist 打包。
- 正式发布需要独立确认精确 HTTPS origin、Auth redirect、CORS、私有存储与 Provider schema/成本，不能从 demo 打包成功推导上线完成。
