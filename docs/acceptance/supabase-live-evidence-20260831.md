# Supabase 外部验证记录（2026-08-31）

范围：用户已授权的临时项目，迁移、普通用户 RLS 与私有 Storage 边界验证；不包含真实 Provider 或生产发布。

## 2026-09-02 私有 Storage Gate 完成

- `reports` bucket 仍为 private；A/B 两个 `master-table.json` 已位于各自 task/run 目录，未生成永久公开链接。
- 测试文件中的两组普通用户均认证成功（HTTP 200）；各自读取所属对象成功（HTTP 200），跨店铺、匿名和无效令牌读取均被拒绝（HTTP 400）。
- 为补齐缺失的 A 对象，测试窗口内临时增加了同范围 INSERT policy；上传成功后立即删除。清理后的重复写入探针返回 RLS 拒绝，确认没有留下普通用户写权限。
- 密码全角问号仅在一次性内存请求中归一化为半角问号；没有改写本地凭据文件，没有记录密码、service role key、私钥或访问令牌。

本次 `private-storage` 外部 Gate 已通过监督器写入结构化回执；剩余 GitHub Pages 与真实 Provider 为独立外部 Gate。

## 2026-09-01 私有 Storage 配置与受控验证

- 当前项目的 `reports` bucket 已通过 Supabase 控制台确认 `public=false`；A/B 两份受控 `master-table.json` 已上传到各自 task/run 目录，未创建公开 URL。
- B 临时普通用户可通过当前项目 Auth 登录；A 临时用户仍返回认证失败。由于 B 尚未绑定测试店铺，B 读取自有对象、跨店对象、匿名读取和无效令牌读取均被拒绝；这证明了拒绝路径，但不替代“已授权用户可读”证据。
- 继续完成该 Gate 需要在当前 Supabase 控制台登录后，为两个可认证的普通测试用户绑定各自店铺，并重新运行一次内存态的自有/跨店/匿名/无效令牌矩阵；不得把密码、service role key、私钥或访问令牌写入仓库或聊天。

## 已取得证据

- 通过已登录浏览器新建 SQL 查询，事务执行 `003_authenticated_only.sql`，未覆盖原未保存查询。
- 查询结果：migration=`003_authenticated_only`，anon_select=false，authenticated_select=true。
- Data API 默认 schema 为 `api`。不带 profile 的业务表请求返回 PGRST205，不应当作 RLS 证据。
- 带 `Accept-Profile: public` 的 profiles、stores、store_memberships、strategy_configs、tasks、task_runs、audit_events 全部返回 HTTP 401、SQLSTATE 42501。
- 带 `Content-Profile: public` 的 has_store_access RPC 同样返回 HTTP 401、42501。
- 上述 HTTP 仅使用前端公开 key，未持久化认证凭据，未使用 service role 绕过 RLS。
- 续验使用两个普通邮箱密码用户：A/B 均成功认证；每个用户仅读取到自己的 1 个店铺、1 个任务和 1 个运行记录，跨店铺泄漏为 0；各自 `has_store_access` 对自己的店铺为 true、对方为 false；跨店铺任务写入均为 HTTP 403，匿名店铺读取为 HTTP 401。
- 续验期间密码和访问令牌仅存在于浏览器/一次性内存请求中，临时验证页与本地 HTTP 服务已清理。

## 本次 Gate 结论

- 003 后双用户读取、跨店铺写入和凭据不暴露验收已通过；`supabase-rls` 外部任务已由监督器写入结构化完成回执。
- GitHub Pages HTTPS/CORS/Auth Redirect、私有 Storage 读取和真实 Provider 调用仍是独立外部 Gate，未因本次 Supabase 通过而视为完成。

## 续做条件

若继续项目，按监督器列出的下一个外部 Gate 取得相应授权后再执行；不得把 Supabase 的通过结果外推到其他外部服务。
