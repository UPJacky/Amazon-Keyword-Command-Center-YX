# 项目监督器 v1 验收协议

本文定义 `PROJECT_TASKS.json` 的持久任务图、动作领取、验证回执和连续执行规则。它解决“做完一个动作就停止”和“输入未变化却反复执行同一动作”两个问题，不扩大真实 Provider、外部部署、凭据、费用、权限或重要数据删除的授权范围。

## 台账结构

根对象只要求以下字段：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `schema_version` | integer | 当前固定为 `1` |
| `tasks` | array | 非空任务数组；数组顺序是依赖同时满足时的稳定领取顺序 |

每个任务必须且只能用以下核心字段表达监督状态：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `id` | string | 非空且全局唯一；领取和依赖都使用该稳定 ID |
| `title` | string | 非空的人类可读标题 |
| `status` | string | 仅允许 `pending`、`running`、`completed`、`blocked_external`、`blocked_risk` |
| `execution` | string | 仅允许 `local`、`external` |
| `depends_on` | array[string] | 只能引用已存在任务；禁止自依赖和依赖环 |
| `fingerprint_inputs` | array[object] | 非空；每项为本地相对 `path` 或稳定 `literal`，监督器据此自动计算当前指纹 |
| `input_fingerprint` | string | 当前动作输入的 `sha256:<64 lowercase hex>` 指纹 |
| `verified_fingerprint` | string | 最近有效验证所覆盖的输入指纹；尚未验证时为空字符串 |
| `acceptance` | array[string] | 非空且可验证的完成条件 |
| `verification` | array[object] | 验证回执；未验证任务为空数组，完成任务必须非空 |

未知 `schema_version`、重复 ID、未知状态、未知执行类型、悬空依赖、自依赖、依赖环或多个 `running` 任务均应 fail closed，不得猜测下一动作。

## 指纹与验证回执

监督器从 `fingerprint_inputs` 自动计算当前 SHA-256，而不是信任台账中的静态字符串。`kind=path` 只能引用台账目录内存在的相对文件或目录；目录按稳定路径顺序递归读取并忽略 `.git`、`__pycache__`、`.pytest_cache`。`kind=literal` 用于授权状态、费用边界或其他没有本地文件的稳定输入。绝对路径、`..` 越界、缺失路径、空目录、未知输入类型和非规范 SHA-256 均 fail closed。

任务 ID、`execution`、`depends_on` 和 `acceptance` 由监督器强制纳入指纹；声明输入还必须覆盖会改变任务行为或验收结论的源码、配置、计划、授权状态和依赖版本。纯时间戳、完成态文字和重复通知不计入输入。监督器在每次选择时重算 `current_fingerprint`，因此任务依赖、验收条件或本地文件内容变化都会自动让旧完成回执失效。

任务只有同时满足下列条件才是有效完成：

```text
status == completed
and current_fingerprint == input_fingerprint
and input_fingerprint == verified_fingerprint
and verification is not empty
```

若持久状态写着 `completed`，但双指纹不相等或 `verification` 为空，监督器必须将其计算状态视为 `pending`。这就是 `stale`：它不是额外的持久状态值，而是失效完成项自动重新成为候选的计算结果。有效完成项必须被跳过，不能通过重复运行同一测试或审计制造进度。

每条验证回执至少应包含 `kind`、`source` 或执行命令、`result` 和可核对的 `summary`。回执必须对应当前 `input_fingerprint`；失败、被跳过或仅依赖旧快照的动作不能写成通过回执。

## 依赖与动作领取

依赖任务只有在“有效完成”时才算满足。任务领取按以下顺序执行：

1. 严格校验台账和依赖图，并把失效的 `completed` 计算为 stale/`pending`。
2. 若恰有一个 `running` 任务，返回聚合状态 `RUNNING` 并继续该任务；不得另领第二项。
3. 否则按 `tasks` 数组顺序查找依赖已满足的 `local + pending` 任务。
4. 领取前自动重算 `fingerprint_inputs`；`--claim` 在跨平台并发锁内原子持久化当前 `input_fingerprint` 与 `status=running` 后才开始动作，避免同一动作被重复领取。
5. `execution=external` 的任务永远不得由普通 `--claim` 自动选择。用户明确授权且全部安全本地任务完成后，只能通过显式任务 ID、结构化非敏感授权回执和 `--claim-external` 在锁内领取。
6. 若没有可运行本地任务，才计算项目聚合终止态；不得把“某个动作完成”直接当成终止条件。

监督器严格拒绝多个 `running` 任务，也拒绝依赖尚未有效完成却已标记为 `running` 的任务。未授权的外部任务保持 `blocked_external`；它们不是本地失败，也不能伪装成已完成。

## 外部 Gate 授权生命周期

外部任务使用显式生命周期，不参与自动选择：

```powershell
python scripts/project_supervisor.py --claim-external <task-id> --authorization-json '<authorization-receipts>'
python scripts/project_supervisor.py --complete <task-id> --verification-json '<verification-json-array>'
python scripts/project_supervisor.py --block-external <task-id> --reason-json '<block-event-receipts>'
```

`--claim-external` 只有在任务为 `execution=external`、依赖全部有效、没有任何 `running`、没有待执行安全本地任务，且显式任务 ID 位于当前 `blocked_external` 集合时才允许执行。stale 的外部完成项也必须重新取得授权后显式领取。授权数组必须至少包含一条 `kind=authorization`、`result=passed` 回执；只能记录授权范围、临时环境、费用边界等非敏感摘要，字段严格限于 `kind/source/result/summary`。JWT、密码、私钥或带值的 Secret/Token/API Key 会被拒绝写入台账。

外部任务领取后以 `status=running` 保存授权回执。普通 `--claim` 不得刷新或清空外部授权；若输入在外部执行期间变化，先用 `--block-external` 安全回退，再取得当前输入的新授权。外部 Gate 成功时复用 `--complete` 写入真实验收回执；失败、授权撤回或三次有界尝试仍无法完成时，用 `--block-external` 和至少一条 `kind=external_block`、`result=passed` 的事件回执原子回到 `blocked_external`。这里的 `passed` 表示“阻塞事件记录成功”，不表示外部 Gate 通过。回退转换会在同一锁内继续领取任何新出现的安全本地任务。

## 完成后立即续领

主 Agent 完成一个动作后必须在同一执行链中依次执行：

```text
执行验收
→ 写入 verification 回执
→ verified_fingerprint = input_fingerprint
→ status = completed
→ 原子持久化 PROJECT_TASKS.json
→ 重新运行监督选择
→ 立即领取 next_task
```

可执行入口为：

```powershell
python scripts/project_supervisor.py --claim
python scripts/project_supervisor.py --complete <task-id> --verification-json '<verification-json-array>'
```

`--claim`、`--claim-external`、`--block-external` 与 `--complete` 都在独立锁文件上持有跨平台非阻塞并发锁，并以同目录临时文件加原子替换写回台账。持久化或命令传入的每条回执都必须包含非空 `kind`、`source`、`result=passed`、`summary`，不完整回执 fail closed。运行期间本地任务输入发生变化时拒绝完成；再次执行 `--claim` 会刷新当前本地 `running` 任务的领取指纹并清空旧证据，重新验证后即可继续。普通 `--claim` 不刷新外部任务，避免丢失显式授权。完成当前任务与领取后继任务在同一次锁定转换中完成，进程之间不存在“已完成但下一项尚未领取”的重复领取窗口。

单个命令、测试、UAT、文档同步或子 Agent 返回都只关闭对应步骤。监督器返回 `RUNNING` 时，主 Agent 不得发送最终收尾；必须继续当前 `running` 任务或领取返回的 `next_task`。只有监督器给出合法聚合终止态才允许结束当前执行链。

若动作失败但仍可安全诊断、修复或重试，任务保持 `running`，继续本地处理。只有外部依赖或危险操作真实阻断且本地替代工作已穷尽时，才转入相应阻塞态。

## 合法聚合终止态

任务使用小写 `status`，项目级执行状态使用以下大写状态：

| 聚合状态 | 是否终止 | 条件 |
| --- | --- | --- |
| `RUNNING` | 否 | 存在一个运行任务，或存在依赖满足的安全本地候选 |
| `BLOCKED_EXTERNAL` | 是 | 没有本地运行项、pending 候选或 stale 候选，剩余任务仅为 `blocked_external` |
| `BLOCKED_RISK` | 是 | 安全替代工作已穷尽，下一必要动作涉及费用、密钥、权限、重要数据删除或核心架构判断 |
| `USER_STOPPED` | 是 | 用户明确要求停止或暂停 |
| `PROJECT_COMPLETE` | 是 | 所有任务均有效完成，且不存在任何阻塞或未完成项 |

`BLOCKED_EXTERNAL` 不等于项目完成。存在任何可运行本地任务、未复核改动、stale 完成项或可安全修复的失败时，聚合状态必须保持 `RUNNING`。

## Heartbeat 生命周期与去重

Heartbeat 仅在项目聚合状态 `RUNNING` 时允许激活，用于跨轮继续同一个 `running` 任务或领取下一项。进入 `BLOCKED_EXTERNAL`、`BLOCKED_RISK`、`USER_STOPPED` 或 `PROJECT_COMPLETE` 后必须暂停 heartbeat，不能靠重复读取、重复 UAT、重复审计或重复通知空转消耗 token。

每次 heartbeat 唤醒后先比较任务输入指纹和有效验证回执：

- 指纹一致且回执有效的 `completed` 任务直接跳过；
- 指纹变化或回执缺失的 `completed` 任务按 stale 重新开放；
- 已存在 `running` 任务时继续它，不重新领取；
- 完成当前任务后立即选择下一项，不能等待用户再次发送“继续”；
- 只有合法聚合终止态才停止跨轮执行。

## 当前图的预期选择结果

当前任务图先完成根任务 `supabase-rls-hardening` 和 `supervisor-external-gates`，再重新验证依赖它们的 `phase8-local-gate`；这样修改 `supabase/` 或监督器源码时不会让正在运行的根任务因依赖 stale 而失效。稳定完成态下，这些本地任务与 `supervisor-v1` 的当前指纹、领取指纹、验证指纹和回执必须全部有效；监督器不得重复运行它们，并应返回 `BLOCKED_EXTERNAL`，列出尚未完成的外部 Gate。已获用户授权的具体外部 Gate 再用 `--claim-external` 显式进入 `RUNNING`。

若任一本地任务的源码、依赖或验收条件变化，监督器必须先返回 `RUNNING` 并选择依赖顺序中的首个 stale 任务。完成该任务的当前输入验证后，`--complete` 自动领取后继任务；全部本地 stale 项重新验证完成后才恢复上述外部阻塞态。四项外部 Gate 在授权未变化时始终不能被自动调用。
