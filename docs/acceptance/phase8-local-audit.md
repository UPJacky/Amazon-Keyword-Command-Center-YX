# Phase 8 本地部署前审计

执行：

```text
python scripts/check_phase8_documentation.py
python scripts/phase8_audit.py
python scripts/run_uat.py
```

本地已验证：

- 必需 Worker、前端、迁移和规则文件存在；
- tasks/task_runs RLS 与私有 `report_path` 静态契约存在；
- `003_authenticated_only.sql` 撤销七张业务表的匿名权限、恢复 authenticated 最小权限，并将客户端策略限定为登录角色；
- 前端演示会话保护存在；
- 未配置大陆服务器网页端口或公共报告桶；
- 连续 Worker 入口存在；
- Phase 8 计划、状态、记忆、UAT 数量和外部 Gate 定义一致；
- `phase8_audit.py` 会实际构建临时 Pages 包，并精确核对 57 个 allowlist 文件（含根目录登录入口、独立 `tool/` 和 `report/` 路由）、固定离线 public-config、无外部调用和无断链；
- Worker 连续入口同时检查 `run_worker_loop.py` 与 Windows 包装器 `run_worker_loop.ps1` 存在；两者均只调用本地 Worker，不负责发布或外部联调；
- `scripts/check_worker_loops.py` 会实际运行 Python 与 PowerShell 两个入口各 2 个有限轮询周期，检查结构化周期摘要（`cycles=2`、`errors=0`、未提前停止）、至少 2 个心跳和退出码，不联网。
- UAT 编排固定执行 20 个本地 Gate（含状态机/持续目标 15 项与项目监督器 48 项，共 63 项连续执行回归），并校验 Gate 数量、`network_calls=0`、`external_calls=0` 和 `local_only=true`；任何 Gate 失败、超时或启动异常均结构化汇总，不提前停止。
- `check_worker_loops.py`、`phase8_audit.py` 和 Pages 打包 Gate 必须返回可解析 JSON 摘要；摘要缺失、启动异常或超时均判定失败，且 UAT 仍继续收集后续 Gate。
- UAT 汇总拒绝布尔值、负数或非整数的 `network_calls`/`external_calls`，以及非布尔 `local_only`；这些摘要契约错误会记录为失败，不会让编排器异常中止。
- 结构化 Gate 摘要还必须同时包含 `network_calls`、`external_calls` 和 `local_only` 三个必需字段；部分摘要按契约失败处理，不得依赖默认值放行。
- malformed summary（摘要字段类型错误）必须进入结构化失败记录，并继续执行和汇总后续 Gate。
- 该类错误统一写入 `summary_contract_errors`，并继续收集剩余 Gate。
- UAT 的五组临时输出目录由受管上下文创建，正常和异常路径均自动清理。
- UAT 网络调用为 0，Secret value 命中为 0。

尚未执行且不能伪装为通过：

- 临时 Supabase 项目 003 迁移后的双用户 RLS 复验（003 与匿名拒绝已验证，见 supabase-live-evidence-20260831.md）；
- GitHub Pages HTTPS、精确 CORS 和 Auth Redirect 验证；
- 真实私有 Storage 读取验证；
- Provider `tools/list`、成本、字段单位和真实 429 验证。
