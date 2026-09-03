# 本地 UAT 回归入口

执行：

```text
python scripts/run_uat.py
```

`run_uat.py` 会检测 `openpyxl`。当前解释器缺少 XLSX 依赖时，会自动使用工作区依赖运行时；也可以通过 `KWCC_PYTHON` 指定 Python 路径。

覆盖：

- Worker 解析、对账、规则、报告、队列、Provider 契约测试；
- 前端页面契约检查；
- 本地端到端 Smoke Test；
- Supabase migration 文件存在性；
- Secret value 扫描；
- 网络调用计数必须为 0。
- Phase 4/5/6/7 本地 CLI 与 Phase 8 部署前静态审计。
- Python 与 PowerShell 连续 Worker 入口的本地有限轮询进程验证：至少 2 个心跳、退出码 0、`network_calls=0`。
- 每个 UAT 子命令都有有界超时；loop Gate 还必须核对恰好 2 个有限周期、`errors=0`、未提前停止和至少 2 个心跳，不能仅凭一次退出码为 0 判定连续执行通过。
- UAT 必须执行固定的 20 个本地 Gate，其中 `scripts.test_continuous_execution` 15 项与 `scripts.test_project_supervisor` 48 项合并为 63 项独立 Gate；报告显式校验 Gate 数量、`network_calls=0`、`external_calls=0` 和 `local_only=true`。Worker loop 默认 30 秒超时，可通过 `KWCC_LOOP_TIMEOUT_SECONDS` 仅在本地测试中调整，最小仍为 1 秒。
- UAT 编排契约回归覆盖 25 项：Gate 超时、Gate/loop 启动失败均被结构化为失败并继续收集后续 Gate，首个 Gate 失败后仍遍历完整 Gate 清单；结构化边界 Gate 缺少 JSON 摘要、缺少必需字段或摘要字段类型错误时，同时写入 `summary_contract_errors` 与诊断字段并拒绝放行，不会提前退出；`_summary_metrics` 对缺失摘要安全跳过；所有 Gate 使用统一 120 秒有界超时，5 组临时目录在 Gate 收集结束后均由 ExitStack 退出清理；当前文档快照必须唯一且计数一致，不能靠历史通过记录放行。
- 连续开发与多 Agent 监督协议静态契约检查：`python scripts/check_continuous_execution.py`。
- 前端随包 JavaScript 语法检查：`python scripts/check_frontend_syntax.py`；该 Gate 使用本地 Node.js `--check`，不执行页面、不联网。
- Supabase 迁移契约同时检查 `001_initial_schema.sql` 的 RLS/私有报告边界和 `002_indexes.sql` 的五个查询索引定义。
- continuous-supervision：主 Agent 持续监督子 Agent，外部阻塞只冻结对应 Gate。
- 监督规则详见 [`continuous-supervision.md`](continuous-supervision.md)。

该项对应 `continuous-supervision` 本地契约：主 Agent 的持续监督只冻结对应外部 Gate，不会因单个测试或一次命令成功提前结束。

该 UAT 不替代真实 Supabase、Storage、Provider 和部署验收，但是真实接入前必须通过。

UAT 会继续执行并收集后续 Gate 的结果，即使前一个 Gate 失败；只有所有 Gate、测试计数、进程契约和安全边界均通过，才返回成功。

Phase 8 静态审计会把本地可验证项与外部确认项分开输出；外部确认项不会被伪装成已通过。
