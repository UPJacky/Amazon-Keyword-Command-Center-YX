# 西柚关键词指标生产接入（本地实现，未启用）

`worker/providers/xiyou_live_enrichment.py` 只接入已有真实样本确认过的 `get_keyword_info` 合同。它不会读取环境变量、自动发现工具、重试或调用网络；生产组合根必须显式注入 `McpHttpTransport`、站点、ASIN、关键词上限和共享预算。

每次任务最多选择前 10 个去重关键词并发出一次请求。调用前同时预留 1 次调用和 1 credit；返回的 `cost_credits` 必须是非负整数。未知费用、超出预留、传输异常、HTTP/MCP/业务错误会锁住共享预算，防止无法对账时继续花费。预算是单进程边界，不能冒充分布式账户配额。

当前只把已确认的 `competitiveDifficulty` 直接保存为 `competitive_difficulty`，不猜测单位或把它缩放成 0–1。ABA 周搜索量/日期等已确认字段放在 `provider_observations` 追溯对象中；因当前正式报告字典尚无这些原始字段，不强塞成别的列。CPC 字符串缺少已确认币种，不转为 `suggested_bid`。自然/广告排名、Top3 份额、流量、机会分等保持 `null` 并进入 `missing_fields`。因此该接入仍然是部分市场数据，`full_report_complete=false`。

本地测试使用 fake transport 和既有广告 XLSX，禁止真实 socket；覆盖去重、最多10词、空结果/null、跨关键词/站点/ASIN、数据类型、费用与调用预算、并发共享预算、无重试、pipeline 对账和广告事实不被覆盖：

```text
python -m unittest worker.tests.test_xiyou_live_enrichment -v
```

需要含 `openpyxl` 的项目运行时。服务器私有环境使用现有 `XYDC_MCP_URL`/`XYDC_MCP_TOKEN`；不把 token 放在参数、日志或报告。外部迁移和服务部署完成后，显式启动示例（数值仅是操作者本次批准的硬上限，不是默认值）：

```text
python scripts/run_production_worker.py --confirm-live --xiyou-keywords 10 --max-provider-calls 10 --max-provider-credits 10
```

`--xiyou-keywords` 与 `--ad-only` 互斥，两个预算都必填且必须为正整数；未显式启用时 Worker 继续生成 `ad_only` 报告。真实调用、账户总额度、其他西柚工具、完整自然位/竞品/图片模块是独立外部或业务 Gate，不能由本 fake 测试关闭。
