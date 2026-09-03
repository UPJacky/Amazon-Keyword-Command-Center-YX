# Amazon Keyword Command Center YX

Amazon 关键词作战系统的本地实现与验证目录。

Codex 持续执行的完整操作步骤见 [CODEX_CONTINUOUS_SETUP.md](CODEX_CONTINUOUS_SETUP.md)。

持续开发由平台级 active 目标保持跨轮生命周期，项目任务由 `PROJECT_TASKS.json` 持久化，并由 `python scripts/project_supervisor.py` 选择下一项；`--claim` 使用并发锁原子领取本地任务，`--complete` 写入验证回执并立即领取后继任务。外部 Gate 只在用户明确授权后通过 `--claim-external` 与非敏感回执显式领取，失败时用 `--block-external` 安全回退。监督器返回 `RUNNING` 时必须继续，输入指纹未变化的已验证任务会被跳过。

## 持续运行 Worker（Windows）

推荐使用 PowerShell 启动器。它会优先使用 `KWCC_PYTHON`，否则尝试工作区 bundled Python，并持续轮询队列：

```powershell
.\scripts\run_worker_loop.ps1 `
  -QueueRoot <queue目录> `
  -StorageRoot <storage目录>
```

默认不会因为空队列退出，每 30 秒输出一条 `worker_heartbeat`。按 `Ctrl+C` 优雅停止。

测试入口可限制轮询次数：

```powershell
.\scripts\run_worker_loop.ps1 `
  -QueueRoot <queue目录> `
  -StorageRoot <storage目录> `
  -MaxCycles 3 `
  -HeartbeatInterval 0
```

`run_worker_once.py` 只处理一个任务后退出，不要用它作为常驻 Worker。

## 本地验收

```powershell
python scripts/run_uat.py
```

UAT 会在当前 Python 缺少 `openpyxl` 时自动切换 bundled Python；也可以设置 `KWCC_PYTHON` 指定解释器。当前 UAT 不调用真实 Supabase、Provider 或 AI 服务。

前端本地联调页面会读取已生成的本地 artifact：报告页读取报告 JSON，任务页读取报告元数据，策略页读取版本化默认配置。它们仍是本地预览，不等同于真实 Auth、Task 或 Config API。

## 当前行为

- 空队列：等待并输出心跳，不退出；
- 任务异常：归档到 `failed`，继续处理后续任务；
- 进程重启：恢复遗留的 `processing` 任务到 `pending`；
- 非法队列 JSON：归档为 `INVALID_QUEUE_PAYLOAD`；
- 连续异常：有界指数退避；
- `Ctrl+C`：优雅停止。
- 队列写入：入队前校验载荷并原子落盘；历史完成/失败结果不会被覆盖。

真实 Auth、Storage、Provider 和受控报告读取仍需配置外部服务后进行受控联调。
