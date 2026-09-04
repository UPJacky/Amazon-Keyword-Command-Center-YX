# 精确 Origin 网关与正式发布边界

当前实现目录为 `supabase/functions/kwcc-gateway/`。它是现有 Supabase 项目的附加 Edge Function，Worker 仍在云服务器运行，数据库与报告桶保持现有 RLS。

## 为什么此前的阻塞描述不完整

`frontend/client.js` 使用 Authorization Bearer 和 `credentials: 'omit'`。Supabase 托管 API 的 `Access-Control-Allow-Origin: *` 不等于匿名能读取数据，也不能单凭这个响应头断言登录被浏览器阻止。官方示例就使用 wildcard；本项目仍保留计划中更严格的“精确 Origin”要求，由网关实现。

- Supabase 官方 CORS 文档：https://supabase.com/docs/guides/functions/cors
- Supabase 用户令牌说明：https://supabase.com/docs/guides/functions/auth-headers
- MDN wildcard 与 cookies 请求限制：https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSNotSupportingCredentials

浏览器 Origin 是 `https://upjacky.github.io`，不含项目路径；Auth Site URL 则可以是 `https://upjacky.github.io/Amazon-Keyword-Command-Center-YX/`。同一 Github 用户下的其他仓库页面也共享这个 Origin；CORS 不能按仓库路径隔离。

## 网关边界

- 只接受精确 Origin，拒绝空 Origin、`null`、相似域名；预检和所有实际响应都包含 `Vary: Origin`、`Cache-Control: no-store`。
- 登录只允许 password grant；读用户、退出、业务表读取、私有输入上传、两项任务 RPC、两项策略版本 RPC、绑定路径的私有报告读取为显式白名单。
- 普通请求携带当前用户 JWT，交由 Supabase Auth/RLS 验证。解码 JWT 只用于提前拒绝错误角色，绝不当作认证成功证据。
- 不读取服务密钥，不转发 Cookie、不跟随重定向、不透传上游错误体，不允许 Worker 租约/完成 RPC 或 Auth 管理接口。策略写入继续由数据库检查本店管理员角色。
- 上传仅允许 10 MiB 内的 `.xlsx/.csv`，路径包含店铺/当前用户/任务 ID，不允许覆盖。Worker 必须重新计算实际下载字节的 SHA-256 后才执行分析。
- 精确 CORS 只约束浏览器访问应用网关。原 Supabase 地址仍有托管 wildcard；原地址的数据保护仍由 Auth/RLS 执行。

## 本地验证

```text
node --test supabase/functions/kwcc-gateway/gateway.test.mjs
```

测试使用 fake upstream，不调用真实 Supabase。覆盖预检、域名、匿名/错误角色、用户令牌保留、私有路径、上传归属与大小、RPC白名单、响应净化。

## 待部署步骤

先审阅 `supabase/PRODUCTION_JOBS_REVIEW.md` 并在测试项目应用 005/006 迁移，随后部署函数。CLI 需要用户正常登录的 Supabase 管理会话；service role 不是管理平台部署凭据。

```text
supabase functions deploy kwcc-gateway --project-ref fcowaovsbxxtxljjhllp --no-verify-jwt
```

`--no-verify-jwt` 仅取消平台对整个函数的统一入口校验，以便登录及 OPTIONS 到达函数；函数内受保护路由仍要求用户 JWT，所有业务请求继续由上游 Auth/RLS 验证。必须按此代码整体部署，不能使用空白函数替换。

默认 `KWCC_ALLOWED_ORIGIN` 已为当前 Pages Origin；`SUPABASE_URL` 由运行环境提供。函数不需注入服务密钥。正式前端通过 `gatewayUrl = Supabase origin + '/functions/v1/kwcc-gateway'` 使用这个入口。

发布后应从正式 Pages 浏览器验证：允许 Origin 预检 204/精确响应头，其他 Origin 拒绝，匿名任务/报告 401，A/B 各自报告可读且互相拒绝。再发布独立 live 包；不能用默认 demo 包或示例用户报告冒充生产端到端完成。

2026-09-03 本轮尝试两个已连接 Edge 浏览器的 Supabase 控制台，都仅显示空白应用壳，未得到函数列表；已关闭对应 Agent Window。未新增远端函数、未修改权限，此记录不代表管理会话有效。

后续打开登录入口一度显示组织页，但项目入口仍空白；再次确认最终停在明确的登录表单。已通过 BrowserSkill 请求人工登录，45秒窗口未完成并关闭会话。当前不重复盲刷：恢复控制台登录或提供已登录管理CLI是部署前置条件，不需要在聊天发送密码/Secret。
