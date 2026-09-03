# Codex 持续执行设置指南

## 重要说明

Codex 的单个对话轮次不是无限后台进程；跨轮连续开发必须由“平台级持续目标 + 持久任务图 + 项目监督器 + 仅运行态心跳”共同实现。只修改提示词不能保证持续执行，也不能防止重复动作。

本项目先用 `get_goal` 检查线程是否已有 active 持续目标；用户要求持续推进而目标为空时，调用 `create_goal` 一次，把完成条件绑定到整个项目而不是当前动作。`PROJECT_TASKS.json` 保存任务、依赖、输入指纹和验证回执，`scripts/project_supervisor.py` 选择下一项安全任务。`--claim` 在并发锁内原子领取，`--complete` 原子完成当前任务并立即领取后继任务；心跳只在监督器返回 `RUNNING` 时激活，合法终止态暂停，避免空转消耗 token。

## 第一步：打开项目任务

在 Codex 桌面端：

1. 可以继续当前项目任务，也可以创建新任务；项目进度以工作区任务图和状态文件为准，不依赖聊天记忆。
2. 工作目录选择：

   `D:\codex2\Amazon-Keyword-Command-Center-YX`

3. 确认工作目录不是其他项目。

## 第二步：粘贴首条指令

把下面整段作为新任务的第一条消息发送：

```text
你现在负责持续推进当前项目，工作目录是：
D:\codex2\Amazon-Keyword-Command-Center-YX

请先读取 AGENTS.md、MEMORY.md、PROJECT_MEMORY.md、PROJECT_PLAN.md、PROJECT_STATUS.md、PROJECT_TASKS.json 和 README.md，并运行 python scripts/project_supervisor.py。

执行策略：
1. 先检查平台持续目标；若 get_goal 为空，使用 create_goal 创建覆盖完整项目目标的持续目标，已有 active 目标时复用；
2. 监督器返回 RUNNING 时，先运行 python scripts/project_supervisor.py --claim，再执行 next_task；完成后使用 --complete 写入验证回执并原子领取下一项，不要完成一个小步骤后主动结束；
3. 自动完成文件读取、代码修改、测试、失败定位、修复、重跑和状态更新；
4. 测试失败先自行诊断和修复，不要直接等待我下新指令；
5. 只有真实异常且经过定位和安全重试仍无法解决，或需要我提供业务判断、凭据、权限、外部服务确认，或涉及危险操作时才暂停；
6. 没有阻塞时，不要只汇报“已完成”；必须继续领取监督器的下一项安全工作；
7. 不调用真实外部 Provider，不发送消息，不花费费用，不删除重要数据，除非我明确授权；
8. 输入指纹与验证回执未变化的已完成任务必须跳过，不能重复测试或审计来伪装推进；
9. 只有 BLOCKED_EXTERNAL、BLOCKED_RISK、USER_STOPPED、PROJECT_COMPLETE 才能结束执行链。

现在开始执行，不要先向我询问是否继续。
```

## 第三步：确认是否成功

新任务开始后，应看到 Codex：

- 建立或复用一个覆盖完整项目目标的 active 持续目标；
- 读取本目录文件；
- 执行命令或检查代码；
- 完成一个动作后重新运行监督器并领取下一步；
- 指纹未变化的已验证动作被跳过，不会机械重跑；
- 只有遇到真实阻塞才请求你协助。

如果它立即只回复一段总结并结束，检查以下五项：

1. 工作目录是否确实是本目录；
2. `get_goal` 是否返回 active 持续目标；为空时是否已调用一次 `create_goal`；
3. `PROJECT_STATUS.md` 是否为 `RUNNING` 且具有具体 `next_safe_action`；
4. `python scripts/project_supervisor.py` 是否返回 `RUNNING` 和具体 `next_task`；
5. 心跳是否只在 `RUNNING` 时激活。

## 项目监督器

每次开始和最终回复前读取状态：

```powershell
python scripts/project_supervisor.py
```

返回 `RUNNING` 后原子领取：

```powershell
python scripts/project_supervisor.py --claim
```

完成当前任务时传入 JSON 数组形式的验证回执：

```powershell
python scripts/project_supervisor.py --complete <task-id> --verification-json '<verification-json-array>'
```

`--complete` 会在同一个并发锁内写入完成回执并立即领取下一项安全本地任务，因此两个动作之间不会出现可被另一轮重复领取的空档。任务 ID、执行类型、依赖、验收条件和声明输入共同参与指纹；输入或任务契约变化会使已完成任务 stale 重开。若本地 `running` 期间输入变化，完成会被拒绝；再次执行 `--claim` 刷新领取指纹并重验即可继续。外部 Gate 不由普通领取自动选择；明确授权后使用 `--claim-external <task-id> --authorization-json '<非敏感回执>'`，失败时使用 `--block-external <task-id> --reason-json '<事件回执>'`，成功仍使用 `--complete`。监督器本身不调用外部服务。返回 `RUNNING` 时必须继续执行当前任务；返回合法终止态时才允许暂停。

## Worker 常驻运行

如果你要运行的是项目 Worker，而不是让 Codex 自动改代码，在 PowerShell 中执行：

```powershell
Set-Location 'D:\codex2\Amazon-Keyword-Command-Center-YX'
.\scripts\run_worker_loop.ps1 `
  -QueueRoot 'D:\codex2\Amazon-Keyword-Command-Center-YX\runtime\queue' `
  -StorageRoot 'D:\codex2\Amazon-Keyword-Command-Center-YX\runtime\storage'
```

这个进程会持续轮询、处理任务并输出 `worker_heartbeat`。按 `Ctrl+C` 才会停止。

测试启动器是否工作：

```powershell
.\scripts\run_worker_loop.ps1 `
  -QueueRoot 'D:\codex2\Amazon-Keyword-Command-Center-YX\runtime\queue' `
  -StorageRoot 'D:\codex2\Amazon-Keyword-Command-Center-YX\runtime\storage' `
  -MaxCycles 3 `
  -HeartbeatInterval 0
```

## 不要使用的方式

- 不要靠反复发送“继续”代替任务图和监督器；
- 不要把 `scripts/run_worker_once.py` 当成常驻入口；
- 不要只修改 `AGENTS.md` 而不维护任务状态、指纹和验证回执；
- 不要在合法终止态保留周期心跳空转；
- 不要在没有凭据和授权时强行进行真实 Supabase/Provider 联调。
