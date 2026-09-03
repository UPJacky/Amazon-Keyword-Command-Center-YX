# Phase 2 本地 Smoke Test

执行：

```text
python scripts/smoke_test.py
```

验收链路：

```text
FileQueue pending
→ claim processing
→ XLSX parser
→ reconciliation gate
→ deterministic rule engine
→ report JSON artifacts
→ completed queue
```

该 Smoke Test 不连接 Supabase、不调用西柚、不调用 AI、不读取 Secret。真实外部接入前必须保留本测试作为本地回归门。

连续 Worker 验证入口：

```text
python scripts/run_worker_loop.py --queue-root <queue> --storage-root <storage> --max-cycles 3
```

Windows 推荐使用项目启动器，它会优先选择 `KWCC_PYTHON`，其次选择工作区 bundled Python，避免系统 Python 缺少 `openpyxl`：

```powershell
.\scripts\run_worker_loop.ps1 -QueueRoot <queue> -StorageRoot <storage>
```

如需每轮都看到存活消息，可加 `-HeartbeatInterval 0`；默认值为 30 秒。

生产监督器不传 `--max-cycles`，进程会持续轮询；默认每 30 秒输出一条 `worker_heartbeat` 到 stderr。启动时会把上次异常中断遗留在 `processing` 的任务恢复到 `pending`，空队列按轮询间隔等待，异常使用有上限的指数退避，收到 Ctrl+C 后优雅退出。

单个任务发生未预期异常时，Worker 会将该任务归档到 `failed` 并继续轮询，不会把任务永久留在 `processing`。

队列文件不是合法 UTF-8 JSON 时，会归档为 `INVALID_QUEUE_PAYLOAD`，不会阻塞后续合法任务。

队列边界还包括：入队前拒绝缺少必需字段的载荷；入队与归档使用原子 JSON 写入，避免 Worker 读到半个文件；完成/失败结果若已存在则拒绝覆盖历史运行。

Phase 4 本地模块可从已生成报告运行：

```text
python scripts/build_phase4_modules.py --report data/golden/market-demo-report/master-table.json --output <module-output>
```

该命令只生成自然位标杆和否定词候选 JSON，不调用 Provider，也不会写回 Amazon。
