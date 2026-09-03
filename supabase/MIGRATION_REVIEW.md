# 001_initial_schema 静态审查

## 已覆盖

- 任务与运行分离：`tasks.task_id`、`task_runs.run_id`、`previous_run_id`；
- `created_by`、`store_id`、`role` 预留；
- 任务、运行、策略、审计表启用 RLS；
- 普通用户读取范围通过店铺成员关系限制；
- 任务插入要求创建者为当前登录用户。

## 执行前必须复核

- 在临时 Supabase 项目执行迁移并验证 SQL 语法；
- 为 `stores`、`store_memberships`、`tasks`、`task_runs` 的常用查询补充索引；
- 复核管理员写策略 / 授权的策略，当前迁移只提供读取与任务插入基础策略；
- 验证 `security definer` 函数的 owner、search_path 和权限；
- 验证 Storage 私有桶策略，禁止以公共读替代登录后受控读取；
- 迁移执行前确认不会覆盖已有生产表。

当前结论：可作为 V1 草案，尚未执行到真实 Supabase。

已补充 `migrations/002_indexes.sql`，执行前仍需在临时项目验证索引和 RLS 查询计划。

`migrations/003_authenticated_only.sql` 用于已经执行过基线迁移的项目：它撤销 `PUBLIC`、`anon` 与旧 `authenticated` 对七张业务表的权限，仅向 `authenticated` 恢复读取和 `tasks` 列级插入所需的最小权限，并将八个客户端策略显式限定为 `to authenticated`。客户端只能创建 `pending/ingestion` 任务，不能写入完成态、失败原因或完成时间。`audit_events.store_id is null` 仅允许事件对应用户本人读取；匿名角色、其他登录用户和 `user_id is null` 的全局事件均不可见。迁移还收紧 `has_store_access(uuid)` 的默认 `PUBLIC` 执行权限和 `security definer` 的 `search_path`。

真实项目验收必须同时检查：未携带用户 JWT 的 Data API 请求返回权限错误；两个普通用户仍只能读取各自店铺、任务和运行；跨店铺读取为空、越权写入被拒；重复执行 `003` 不改变权限结果。

## 静态契约检查

执行 `python supabase/migration_contract_check.py` 可检查所有业务表 RLS、任务/运行读取策略、私有报告读取字段、公共报告/Storage 策略禁用边界、`002_indexes.sql` 中五个查询索引，以及 `003_authenticated_only.sql` 的匿名撤权、最小授权和 authenticated-only 策略。`supabase/test_migration_contract.py` 将该检查作为回归测试，`scripts/run_uat.py` 与 Phase 8 审计均会执行。该检查不执行 SQL，也不能替代临时 Supabase 项目中的真实 RLS 验证。
