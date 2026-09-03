# 连续开发与多 Agent 监督清单

本清单约束主 Agent 和所有子 Agent 的协作行为。它解决的是项目执行流程，不替代业务 Gate，也不授权调用真实外部服务。

UAT 编排固定汇总 20 个本地 Gate，并要求 `network_calls=0`、`external_calls=0`、`local_only=true`；其中连续执行状态机与持续目标 15 项、项目监督器 48 项合并为 63 项独立回归 Gate。单个 Gate 失败、超时或启动异常只记录为失败，不得提前结束后续 Gate。

子 Gate 摘要必须包含 `network_calls`、`external_calls`、`local_only` 三个字段；前两者必须是非负整数，后者必须是布尔值。缺失字段或类型错误记录到 `summary_contract_errors`，仍继续收集后续 Gate。

malformed summary（摘要字段类型错误）不得让主编排器抛异常早停，必须转换为结构化失败并保留后续 Gate 结果。

## 连续执行显式状态机

连续执行由 `PROJECT_TASKS.json` 的持久任务图与 `scripts/project_supervisor.py` 的选择结果驱动，`PROJECT_STATUS.md` 顶部字段用于保存项目级聚合状态和人类可读摘要。状态输入至少包括 `execution_state`、`current_objective`、`next_safe_action`、`stop_reason`、`last_action_fingerprint`、`local_safe_queue` 和 `verified_gate_snapshot`。下文的 `next_action` 是状态机中的通用名称，在当前项目中落盘为 `next_safe_action`，且必须与监督器返回的 `next_task` 一致；“安全”仍以本文和 `AGENTS.md` 的凭据、权限、费用、删除及外部服务边界为准。

| 状态 | 进入条件 | 执行与结束规则 |
| --- | --- | --- |
| `RUNNING` | 存在安全的 `next_action`，或仍需清点本地任务才能确定下一动作 | 必须执行安全动作并继续选择下一动作；只要还有安全的 `next_action`，就不得结束执行链、发送最终收尾或把单个命令、测试、UAT、文档同步、子 Agent 完成当作停止条件 |
| `BLOCKED_EXTERNAL` | 已穷尽安全本地任务，唯一剩余动作需要外部凭据、权限、登录、业务判断或第三方服务确认 | 可以结束当前执行链并暂停心跳；必须记录具体 `stop_reason` 和未完成的外部 Gate，不得标记项目完成 |
| `BLOCKED_RISK` | 已穷尽安全替代方案，下一必要动作涉及重要数据删除、费用、密钥、权限或核心架构变更 | 可以结束当前执行链并暂停心跳，等待用户明确授权或判断 |
| `USER_STOPPED` | 用户明确要求停止或暂停 | 立即停止继续分配动作并暂停心跳，直到用户明确恢复 |
| `PROJECT_COMPLETE` | 项目目标与全部必需验收（包括适用的外部 Gate）均已真正完成，且没有未完成项 | 可以结束执行链并暂停心跳；存在任何外部阻塞时不得进入此状态 |

`BLOCKED_EXTERNAL`、`BLOCKED_RISK`、`USER_STOPPED`、`PROJECT_COMPLETE` 是仅有的合法终止态。`RUNNING` 不是终止态；若 `local_safe_queue: empty` 与 `execution_state: RUNNING` 同时出现，必须重新清点并写出具体 `next_action`，或转入符合事实的合法终止态，不能安静停止。

### 状态转移与防重复

1. 每次动作前读取当前目标、`PROJECT_TASKS.json`、源码/配置/计划输入、用户授权状态、上轮失败，以及 `last_action_fingerprint` 和 `verified_gate_snapshot`，然后运行 `python scripts/project_supervisor.py`。
2. 若监督器返回安全且尚未验证的 `next_task`，保持 `RUNNING`，使用 `--claim` 原子持久化领取状态，执行动作、完成相称的测试和复核，再用 `--complete` 写入当前输入指纹对应的验证回执并在同一锁内领取下一项安全动作。
3. 外部 Gate 不进入普通 `next_task`。只有用户明确授权、依赖有效且本地安全队列清空时，才用显式任务 ID、`--claim-external` 和非敏感授权回执原子领取；成功用 `--complete`，失败或授权撤回用 `--block-external` 原子恢复 `blocked_external`。普通 `--claim` 不得清空外部授权。
4. 任务 ID、执行类型、依赖、验收条件和声明输入共同组成自动指纹；它与有效完成回执一致时跳过重复动作并选择其他 `next_task`，任一变化或回执缺失时旧完成态自动失效并重新开放。本地 `running` 中输入变化时重新 `--claim` 刷新指纹并重验；外部输入变化时先回退再重新授权领取。不得靠重跑同一测试、UAT、审计或文档同步制造推进记录；跳过重复动作本身也不是停止条件。
5. 只有在清点并穷尽全部安全本地动作后，才能根据事实转入 `BLOCKED_EXTERNAL`、`BLOCKED_RISK`、`USER_STOPPED` 或 `PROJECT_COMPLETE`。测试失败、未复核改动或仍可安全诊断/修复时继续保持 `RUNNING`。
6. 外部阻塞只冻结依赖该外部条件的 Gate。其他本地实现、契约、失败路径、测试和文档工作仍作为 `next_action` 继续执行；外部 Gate 未完成不得伪装为 `PROJECT_COMPLETE`。

动作去重键应同时覆盖动作标识、相关输入指纹和验证快照。源码、配置、计划、测试计数、失败状态、行为契约或用户授权任一发生变化时，原验证证据才失效，并按影响范围重新执行相应验证；仅完成态文字、时间戳或去重标记变化，不触发整套 Gate。

## 主 Agent 职责

- 以当前项目目标作为总目标，维护唯一任务计划和当前阶段状态。
- 将可拆分的本地工作分配给代码、测试、安全、流程/文档或部署审计子 Agent。
- 验证子 Agent 的改动和测试结果，不接受“已完成”作为未经复核的事实。
- 每个子任务结束后重新读取计划与状态，清点剩余本地工作并分配下一项安全任务。
- 汇总所有 Gate、未完成项和唯一外部阻塞，不把子任务完成写成项目完成。
- 子 Agent 交付被复核后立即关闭并释放 Agent 槽位，保证下一轮仍可并行分配工作。

## 子 Agent 交付格式

每个子 Agent 必须报告：

1. 修改了哪些文件；
2. 执行了哪些本地验证及结果；
3. 是否影响其他模块或文档；
4. 尚未完成的本地工作；
5. 需要凭据、权限、业务判断或外部服务确认的阻塞。

子 Agent 不得调用未经授权的真实 Provider、Supabase、Storage 或部署服务，不得删除重要数据，不得把网络不可用伪装成测试通过。

## 强制续行闭环

每次工具命令或子 Agent 返回后，按以下顺序继续：

```text
状态重读
→ 本地任务清点：读取 PROJECT_TASKS.json 并运行项目监督器
→ next_task 领取与自动输入指纹检查
→ 改动核验
→ 定向测试
→ 必要的完整 UAT / 集成（输入与验证快照未变化时复用已有证据）
→ 契约或进程级验证
→ 写入任务验证回执并同步文档与状态
→ 再次运行项目监督器并立即领取下一项安全工作
```

以下情况均不能直接收尾：单次 Worker 成功、单个测试通过、完整 UAT 通过、文档改完、某个子 Agent 报告完成。当前阶段所有本地 Gate 已检查且没有任何无需用户输入即可执行的下一步时，还必须写明事实并转入一个合法终止态；`RUNNING` 下不得暂停。

## 跨轮持续唤醒

平台级持续目标是跨轮生命周期所有者。用户要求持续推进整个项目时，主 Agent 先用 `get_goal` 检查；结果为空才调用一次 `create_goal`，已有 active 目标时复用，禁止为每个子步骤重复创建目标。持续目标绑定完整项目完成条件，单个回复、测试、UAT、文档同步或子 Agent 完成不能关闭它。

心跳自动化由上述状态机控制，只在 `RUNNING` 时保持激活，用于跨轮继续当前目标。被唤醒后先确认持续目标，再运行项目监督器：返回 `RUNNING` 时继续其唯一 `next_task`，返回合法终止态时暂停；输入与验证回执未变化时跳过已有证据覆盖的重复动作，不机械重跑完整 UAT、审计或文档同步。

心跳不授权真实 Provider、Supabase、Storage 或外部发布，也不授权费用、密钥、权限或重要数据删除。进入 `BLOCKED_EXTERNAL`、`BLOCKED_RISK`、`USER_STOPPED` 或 `PROJECT_COMPLETE` 后必须暂停心跳，禁止终止态空转；仅在用户恢复、阻塞解除或出现新的安全本地任务并将状态切回 `RUNNING` 后恢复。

## 当前 Phase 8 外部阻塞

本地验证保持网络调用为 0。尚未授权且不能虚构为通过的项目包括：临时 Supabase 双用户 RLS、GitHub Pages HTTPS/CORS/Auth Redirect、私有 Storage 读取，以及真实 Provider `tools/list`/成本/字段单位/429 验证。它们只冻结对应外部 Gate，不冻结本地文档、契约、失败路径和测试工作。

## 监督验证入口

```powershell
python scripts/check_continuous_execution.py
python scripts/project_supervisor.py
python scripts/run_uat.py
```

监督检查只读取本地文件并检查协议契约；不会调用网络或外部服务。
