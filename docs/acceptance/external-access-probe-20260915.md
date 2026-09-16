# LUNU-05 外部访问探针记录（2026-09-15）

本记录只说明访问条件，不是线上六模块通过证明；没有写入任何密码、JWT、API key、私钥、签名 URL 或原始 Provider 响应。

## 本轮结果

| 项目 | 结果 | 结论 |
| --- | --- | --- |
| Supabase 配置文件 | 仅确认 `SUPABASE_URL`、`SUPABASE_ANON_KEY`、`SUPABASE_SERVICE_ROLE_KEY` 标签存在 | Secret 未输出；不证明线上迁移已执行 |
| Supabase HTTPS 只读探针 | 本机 HTTPS 连接返回 `URLError` | 未取得 HTTP/业务结果；不把它记为通过或失败 |
| 浏览器自动化 | 浏览器服务返回 `nodeRepl.fetch request failed` | 本轮不能操作已登录控制台或无痕窗口 |
| 浏览器技能层 | 本轮重新连接 Edge 并进入目标 Supabase 项目 Users 页，确认 2 个测试用户；随后在 SQL Editor 完成只读查询 | 已确认控制台登录态和项目归属；仍不能代替 010/011/012、Worker/Gateway 和登录后报告验收 |
| Supabase SQL Editor 核对 | 业务表/RLS/Storage 可读；010/011/012 已按仓库 SQL 执行并完成 RPC 复核 | 线上结构阻塞已解除；仍需 Worker/Gateway、新六模块 run 和 CORS/报告业务验收 |
| Worker 主机 TCP 22 | `43.139.80.199:22` `TcpTestSucceeded=true` | 仅证明 SSH 端口可达 |
| `ubuntu` 非交互 SSH | 最新探针先返回 `ssh-add -l: Error connecting to agent: No such file or directory`，随后 `BatchMode=yes` 仍为 `Permission denied (publickey,password)`、退出码 255 | 本机没有可用 SSH agent；未取得默认 SSH 代理/密钥的登录授权；未执行远程命令 |
| Supabase CLI | 本机未找到 | 不能从本机直接执行迁移/函数部署 |

## 未执行事项

- 没有尝试密码登录、没有把密码放入命令行或日志。
- 没有读取或打印任何 Secret，也没有将 Secret 写入仓库。
- 没有调用 `kwcc_claim_run`、`kwcc_finish_run`、重跑 RPC，也没有触发 Provider；已在 Supabase SQL Editor 执行计划内的 010、011、012 DDL 并复核结果。
- 没有把 TCP 可达、HTTP 200、旧截图或旧 run 当作 R07–R15 线上业务证据。

## 公开报告门禁只读证据

使用浏览器技能层打开现有报告地址后，页面标题为登录入口，正文提示需要使用 Supabase Auth 登录；页面只加载了 Pages 的 HTML、CSS、公共配置和报告脚本，没有发起报告/网关业务请求。该结果证明“未登录不能看到报告”的门禁路径仍在工作，但不能证明登录后的六模块数据存在，也不能证明 Supabase 010/011/012 已在线执行。

本次只读探针没有输入账号密码、没有借用用户登录标签页、没有读取 Cookie/localStorage/Authorization，也没有点击登录或触发任何 Provider 调用。

## Supabase 控制台只读证据

Edge 会话打开目标项目的 Authentication → Users 页面，页面标题包含目标项目与组织，列表显示 `Total: 2 users`，即两个测试用户已存在。随后在 SQL Editor 通过人工协助执行了只读核对：

```sql
select version, name
from supabase_migrations.schema_migrations
order by version desc
limit 30;
```

Supabase 返回 `ERROR: 42P01: relation "supabase_migrations.schema_migrations" does not exist`。这只能证明该项目当前 SQL Editor 会话中不能访问这个迁移元表，不能推断迁移已执行或未执行。

以下两条结构查询随后也实际执行成功：

```sql
select table_name from information_schema.tables
where table_schema = 'public' order by table_name;
```

结果包含 `audit_events`、`profiles`、`store_memberships`、`stores`、`strategy_configs`、`task_confirmations`、`task_runs`、`tasks`。

```sql
select routine_name from information_schema.routines
where routine_schema = 'public' and routine_name like 'kwcc_%';
```

结果包含 `kwcc_append_strategy`、`kwcc_claim_run`、`kwcc_finish_run`、`kwcc_heartbeat_run`、`kwcc_rerun_task`、`kwcc_rollback_strategy`、`kwcc_save_strategy`、`kwcc_save_task_confirmation`、`kwcc_submit_task`、`kwcc_submit_task_with_business_inputs`、`kwcc_validate_strategy`，但没有 `kwcc_preview_next_run` 或 `kwcc_claim_previewed_run`。另外，`pg_get_functiondef` 特征核对显示 `kwcc_claim_run` 不包含 010 引入的 `business_confirmation` 返回字段特征；`kwcc_save_task_confirmation` 包含确认绑定特征，但该特征已存在于 009，不能单独证明 010 已提交。因此当前线上证据应判定为：基础业务表/RLS/旧 RPC 存在，010 的 claim 消费改造未证实且很可能未部署，011/012 RPC 明确缺失。

没有调用业务 claim/finish RPC、没有插入业务数据、没有触发 Provider。010、011、012 是按仓库文件在 SQL Editor 执行的函数定义/授权变更，不是业务数据写入。

010 执行后复核 `kwcc_claim_run` 的函数体特征，结果为 `claim_v010=true`；011 执行后新建 SQL Editor 查询到 `kwcc_preview_next_run`；012 执行后查询到 `kwcc_claim_previewed_run` 与 `kwcc_preview_next_run` 两行。执行结果页显示成功，012 为 `Success. No rows returned`。

迁移元表 `supabase_migrations.schema_migrations` 在该项目 SQL Editor 中不存在，故本次无法依赖迁移历史表确认版本；以上三项必须以函数/授权和后续 Worker 行为复验。后续如使用 Supabase CLI，应先核对本地迁移账本与线上状态，避免仅因函数已存在就重复声称迁移记录完整。

当前 Edge 会话仅用于控制台核对，结束后应清理。

## 2026-09-16 腾讯云 Edge 控制台复核

- 已在 Edge 中完成腾讯云 Lighthouse 目标实例 `UpJacky-Ubantu` 的登录态确认，实例状态为 Running，目标地址仍为 `43.139.80.199`；本记录不保存登录凭据。
- 已打开实例的“执行命令”弹窗，填写了一条只读诊断命令，用于检查执行身份、部署目录和 Git HEAD；执行记录上传保持关闭，未涉及 COS。
- 弹窗中的 CodeMirror 命令编辑器能够显示命令，底部“执行命令”按钮也显示为可用；语义点击、编辑器 `Ctrl+Enter` 和一次 Tab→Enter 键盘路径均未产生新的执行记录，弹窗仍保持打开。随后已停止该 BrowserSkill 会话。
- 自动化提交失败期间没有执行远程命令；后续一次只读诊断已真实执行。整个过程没有重启 Worker/Gateway、没有读取环境变量或 Secret，也没有改变服务器文件。自动化失败结果本身不是远程命令失败证据；Worker/Gateway 状态仍需依靠后续只读诊断确认。
- CUA Edge 备用通道同时返回 `nodeRepl.fetch request failed`，所以不能用第二个浏览器控制通道补交同一命令。本条不再重复点击；恢复入口是用户在同一个已登录 Edge 弹窗中手动点击一次“执行命令”，或提供已授权的 SSH agent/密钥入口。
- 后续在保留登录态的 Edge 实例中，第一条只读诊断已真实执行并生成新记录：输出确认执行身份为 `root`、部署目录存在（`DEPLOY_OK`）；Git HEAD 查询返回 ExitCode 128，且该条命令主动将 stderr 丢弃，因此只能确认 Git 查询未成功，不能据此判断目录是否为 Git 工作树。该命令未重启、未写文件、未读取环境变量或 Secret。
- 第二条服务/进程/端口只读诊断已填入 CodeMirror，但自动点击再次没有提交；当前已交给人工协助面板等待一次真实鼠标点击，不再重复自动点击。

## 恢复后唯一入口

1. 在可用的 Edge/Tencent 控制台会话中完成 `ubuntu` SSH 登录，或让本机 SSH agent 提供该服务器的已授权密钥；只需告诉执行环境“登录已完成”，不要在聊天发送 Secret。
2. 登录后先只读确认 `/home/ubuntu/keyword-war-room`、当前提交、服务状态和环境变量名；随后核对 Worker/Gateway 是否已加载 010/011/012 对应的 claim/previewed RPC。
3. 在 Worker/Gateway 确认后重启并做精确 CORS/健康检查，再创建全新的六模块 run；不得用现有旧 run 或旧截图替代。
4. Supabase 普通用户 RLS/私有 Storage 仍需用两个测试用户完成矩阵验证；不得使用 service role 伪造普通用户 RLS 证据。

当前监督器仍应保持 `RUNNING`；以上访问故障只阻塞对应外部 Gate，不得将 LUNU-05 标为 `PROJECT_COMPLETE`。
