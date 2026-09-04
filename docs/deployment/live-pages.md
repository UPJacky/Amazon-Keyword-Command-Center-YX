# Live Pages 本地打包

`scripts/build_pages_live.py` 生成或审计正式模式的静态包，不发布、不访问网络、不调用 Provider、不读 `.env`。此构建 Gate 不代表 Supabase、精确 CORS、RLS、私有报告、上传或 Worker 的线上验收已经通过。

## 输入与边界

Python 调用：`build(output, public_config)`；独立复验：`audit_live_output(output, public_config)`。输出目录必须不存在或为空，不覆盖已有发布物。调用者必须提供且仅提供五个公开字段：

| 字段 | 必须满足 |
| --- | --- |
| `mode` | 字符串 `live` |
| `liveEnabled` | 布尔值 `true`，不接受字符串或数字 |
| `supabaseUrl` | `https://<20位小写字母数字项目ref>.supabase.co`；没有尾斜杠、路径、端口、账号、query 或 fragment |
| `publicKey` | `sb_publishable_` 加 20–128 位字母数字、下划线或连字符；或者该项目的 legacy anon JWT |
| `gatewayUrl` | `supabaseUrl` 原样加 `/functions/v1/kwcc-gateway` |

Legacy JWT 必须是规范 base64url，header 为 `HS256`/`JWT`，签名段解码为 32 字节，payload 的 `iss=supabase`、`role=anon`、`ref` 与 URL 项目相同。只允许这些声明及可选非负整数 `iat`/`exp`，拒绝重复声明、额外字段、service role 和用户会话令牌。本地只检查结构与项目 ref，不验证 JWT 签名、有效期、撤销状态或远端可用性；opaque publishable key 无法离线确认所属项目。调用者需从目标项目提供正确公开 key，真实可用性由外部验收确认。

构建在系统临时目录复用 demo 打包器，再按 `expected_demo_files()` 去掉全部 `data/` 路径，复制白名单子集。目前为 49 个文件，排除 8 个 `data/golden` 演示 JSON，仅保留规则 JSON `rules/defaults/stable.json`。临时 demo 包退出时清理；发布输出不包含演示数据、原始报表、`.env`、私钥或任意额外文件。

仅根目录 `public-config.js` 和 `frontend/public-config.js` 由此打包器生成，可包含校验通过的公开 key 和两个指定 URL。审计要求两文件逐字节等于**调用者再次提供**的配置序列化；不能从待审包读取配置并把它当成批准依据。配置后追加脚本、改用另一个有效 key、修改 URL 或回退 demo 均失败。其他文件沿用 demo Secret 与外部 URL 扫描，同时禁止公开 key 值散落在普通资源中；未更改 demo 的全局扫描规则。

审计检查确切文件清单、意外目录、缺失资源、UTF-8 可读性、HTML 本地引用与断链，并拒绝输出及源路径的 symlink、Windows junction/reparse point。HTML query/fragment 可保留，越界、协议相对外链、绝对路径和脚本协议被拒绝。共享 JS 可能仍含 demo 分支的路径文字；打包器不改写 client.js 或报告逻辑，实际 live 分支不得回退读取 fixture，属于主 Agent 的前端集成验收范围。

## CLI

进程环境必须设置 `KWCC_MODE=live`、`KWCC_LIVE_ENABLED=true`、`KWCC_SUPABASE_URL`、`KWCC_GATEWAY_URL` 和 `KWCC_PUBLIC_KEY`。由调用环境安全注入公开 key；不把实际 key 写进命令历史、文档或日志。脚本不自动加载配置文件或凭据文件。

```powershell
# 在调用环境已注入上述五个变量后：
python scripts/build_pages_live.py --output D:/kwcc-live-release
python scripts/build_pages_live.py --output D:/kwcc-live-release --audit-only
python -m unittest scripts.test_build_pages_live -v
```

除公开 key 仅使用环境变量外，也可用 `--mode`、`--live-enabled`、`--supabase-url`、`--gateway-url` 覆盖对应环境值。CLI 的开关字符串必须精确为 `live` 和 `true`。输出仅打印脱敏 JSON 摘要：`passed`、`published=false`、`local_only=true`、`network_calls=0`、`external_calls=0`；成功还包括确切文件数和不含原始输入/演示数据的标记。失败退出码为 1，参数错误为 2，不打印输入值、key 或异常详情。需要定位打包失败时，在本地对临时包调用审计 API，它只返回规则与文件位置，不返回文件内容。

测试使用合成公开 key/JWT、临时源码快照与临时输出，不改共享 frontend。覆盖项目不匹配、service role、外部 Gateway、配置篡改、Secret 例外范围、fixture/原始报表、遗漏文件、符号链接、断链和 CLI 脱敏；无 Node、npm 或联网安装依赖。实际符号链接测试在操作系统未授予创建权限时明确跳过，另有始终运行的守卫拒绝和不读取目标测试。

## 部署交接

本脚本没有发布入口，不能代替外部发布授权。主 Agent 需在最终 client.js、精确 Origin Gateway 与 live report 合并后重新构建及复验；随后单独完成 HTTPS、Auth、精确 CORS、RLS、私有 Storage/报告与真实用户流程 Gate。只将审计通过的输出目录作为发布候选，禁止直接发布工作区或临时 demo 包。构建和审计期间应保持输入、输出目录不被其他进程改写；本工具不提供面对并发恶意文件系统改写的隔离保证。
