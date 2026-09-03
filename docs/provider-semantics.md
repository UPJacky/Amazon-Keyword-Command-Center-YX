# Provider 语义与接入契约（待实测冻结）

## 接入纪律

1. Worker 首次接入先调用 MCP `tools/list`，保存实际工具名和 schema；禁止猜工具名。
2. 先做分层 10～30 词小样，再决定是否全量。
3. 统一实现 `estimate()`、`fetch()`、`normalize()`、`cache_key()`、`retry_policy`、`usage_log`。
4. 有效缓存默认复用；只有用户主动刷新才强制更新。
5. 429 使用指数退避，单次任务最多自动重试 2 次，并记录限流次数。

## 当前业务口径草案

| 原始字段/来源 | 标准字段 | 语义 |
|---|---|---|
| `ranks` + `or` 的最小 `totalRank` | `organic_rank` | 自然位；无记录为 `—` |
| `ranks` + `sp/sb/sbv` 的最小 `totalRank` | `ad_rank` | 广告位；无记录为 `—` |
| `topAsins.clickShare` | `top3_click_share` | ABA Top3 点击集中度 |
| `topAsins.conversionShare` | `top3_conversion_share` | ABA Top3 转化集中度 |
| `traffic` | `traffic_estimate` | 西柚流量热度估值，不等于 ABA 点击份额 |
| `trafficRatio` | `traffic_ratio` | 该词占该 ASIN 自身流量比例 |
| `trafficAcquisitionRate` | `traffic_acquisition_rate` | 该 ASIN 吃掉该词的流量比例 |

ABA 趋势使用上一个完整周期；未完整周期不得填 0。Provider 缺失映射到标准 `missing_fields` 数组，不得静默填零。

## 必须在实际接入前确认

- 西柚当前工具名、参数 schema、字段单位、成本与限流响应；
- 搜索量、难度、建议竞价的实际来源与空值语义；
- ABA 周期字段和趋势窗口；
- 缓存 TTL 与强制刷新策略；
- Provider snapshot version 的生成方式。

本地契约已落地于 `worker/providers/base.py`：

```text
estimate()
fetch()
normalize()
cache_key()
retry_policy
usage_log
snapshot()
```

当前 `ProviderContract` 未注入 transport 时会拒绝调用，测试确保不会产生付费请求。

`worker/providers/mcp_client.py` 已提供 transport-neutral 的 `tools/list` 自发现客户端和工具清单留底能力。真实接入前必须把工具名、schema、字段单位和成本写入本文件或其版本化快照。

`worker/providers/mcp_http_transport.py` 与 `scripts/probe_provider.py` 提供了显式、一次性、可审计的真实探测入口：仅从进程环境读取 `XYDC_MCP_URL` / `XYDC_MCP_TOKEN`，默认不执行网络；运行时只输出工具数量和调用计数，工具 schema/样本响应写入用户指定的私有 JSON 路径。探测前必须获得外部授权，输出文件不得提交 Git。

`worker/providers/cache.py` 提供显式 TTL 缓存；缓存命中不调用 Provider，过期也不会静默刷新，必须由任务流程明确决定是否刷新。
