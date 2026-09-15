# LUNU-05 外部访问探针记录（2026-09-15）

本记录只说明访问条件，不是线上六模块通过证明；没有写入任何密码、JWT、API key、私钥、签名 URL 或原始 Provider 响应。

## 本轮结果

| 项目 | 结果 | 结论 |
| --- | --- | --- |
| Supabase 配置文件 | 仅确认 `SUPABASE_URL`、`SUPABASE_ANON_KEY`、`SUPABASE_SERVICE_ROLE_KEY` 标签存在 | Secret 未输出；不证明线上迁移已执行 |
| Supabase HTTPS 只读探针 | 本机 HTTPS 连接返回 `URLError` | 未取得 HTTP/业务结果；不把它记为通过或失败 |
| 浏览器自动化 | 浏览器服务返回 `nodeRepl.fetch request failed` | 本轮不能操作已登录控制台或无痕窗口 |
| 浏览器技能层 | 本轮曾连接 Edge 并进入目标 Supabase 项目 Users 页，确认 2 个测试用户；清理卡住的 SQL 编辑器会话后当前仅剩 Chrome 可见 | 已确认控制台登录态和项目归属；仍不能代替 010/011/012、Worker/Gateway 和登录后报告验收 |
| Worker 主机 TCP 22 | `43.139.80.199:22` `TcpTestSucceeded=true` | 仅证明 SSH 端口可达 |
| `ubuntu` 非交互 SSH | `BatchMode=yes`，退出码 255，分类为 `permission_denied` | 未取得默认 SSH 代理/密钥的登录授权；未执行远程命令 |
| Supabase CLI | 本机未找到 | 不能从本机直接执行迁移/函数部署 |

## 未执行事项

- 没有尝试密码登录、没有把密码放入命令行或日志。
- 没有读取或打印任何 Secret，也没有将 Secret 写入仓库。
- 没有运行 `kwcc_claim_run`、`kwcc_finish_run`、重跑 RPC、迁移或部署命令。
- 没有把 TCP 可达、HTTP 200、旧截图或旧 run 当作 R07–R15 线上业务证据。

## 公开报告门禁只读证据

使用浏览器技能层打开现有报告地址后，页面标题为登录入口，正文提示需要使用 Supabase Auth 登录；页面只加载了 Pages 的 HTML、CSS、公共配置和报告脚本，没有发起报告/网关业务请求。该结果证明“未登录不能看到报告”的门禁路径仍在工作，但不能证明登录后的六模块数据存在，也不能证明 Supabase 010/011/012 已在线执行。

本次只读探针没有输入账号密码、没有借用用户登录标签页、没有读取 Cookie/localStorage/Authorization，也没有点击登录或触发任何 Provider 调用。

## Supabase 控制台只读证据

Edge 会话曾打开目标项目的 Authentication → Users 页面，页面标题包含目标项目与组织，列表显示 `Total: 2 users`，即两个测试用户已存在。随后进入 SQL Editor 仅用于准备迁移历史查询；由于 CodeMirror 隐藏编辑器的 CDP 输入被截断，查询未执行，未发生数据库写入。会话已清理；当前 BrowserSkill 列表暂时只剩 Chrome，Edge 需要重新连接后才能继续控制台操作。

## 恢复后唯一入口

1. 在可用的 Edge/Tencent 控制台会话中完成 `ubuntu` SSH 登录，或让本机 SSH agent 提供该服务器的已授权密钥；只需告诉执行环境“登录已完成”，不要在聊天发送 Secret。
2. 登录后先只读确认 `/home/ubuntu/keyword-war-room`、当前提交、服务状态和环境变量名；随后再按 `r12-budget-decision-20260915.md` 的顺序执行线上 Gate。
3. Supabase 管理会话可用后，在受控项目按顺序应用并核对 010、011、012；不使用 service role 伪造普通用户 RLS 证据。

当前监督器仍应保持 `RUNNING`；以上访问故障只阻塞对应外部 Gate，不得将 LUNU-05 标为 `PROJECT_COMPLETE`。
