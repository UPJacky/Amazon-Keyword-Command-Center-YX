# 西柚 MCP 实测快照（2026-09-02）

本快照只记录非敏感的工具契约与返回结构；不包含 URL 查询令牌、Bearer Token、账号、密码或原始凭据。

## tools/list

- 传输结果：HTTP 200；JSON-RPC `2.0`；`result.tools` 有效。
- 工具数量：29。
- 工具名：`get_asin_ad_change_trends`、`get_asin_bsr_trends`、`get_asin_info`、`get_asin_info_change_trends`、`get_asin_info_trends`、`get_asin_keyword_count_trends`、`get_asin_keyword_rank_hourly`、`get_asin_keyword_rank_trends`、`get_asin_keyword_traffic_trends`、`get_asin_keywords`、`get_asin_keywords_daily`、`get_asin_keywords_monthly`、`get_asin_order_trends`、`get_asin_orders_last_30_days`、`get_asin_traffic`、`get_asin_traffic_trends`、`get_asin_traffic_trends_monthly`、`get_asin_traffic_trends_weekly`、`get_asin_variations`、`get_keyword_aba_trends`、`get_keyword_advertising_replay`、`get_keyword_analysis_monthly`、`get_keyword_asin_analysis`、`get_keyword_info`、`get_multi_asin_keyword_comparison`、`get_multi_asin_keyword_comparison_monthly`、`get_parent_asin_keywords`、`get_parent_asin_keywords_monthly`、`report_missing_xiyou_capability`。

## 最小只读业务样本

- 工具：`get_keyword_info`。
- 参数 schema：必填 `keywords`（字符串数组）和 `country`（字符串）；`intent_summary`、`user_task` 为可选脱敏字段。
- 样本范围：1 个关键词，`country=US`；未执行写入、批量或第二个业务工具。
- 调用结果：HTTP/业务状态 200；响应为 JSON-RPC 对象，包含 `result.content` 与 `result.structuredContent`。
- 响应内容 envelope：`status`（整数）、`cost_credits`（整数）、`data.list`（数组）、`data.total`（整数）。本次实测 `cost_credits=1`。
- 单条数据字段：`searchTerm`（字符串）、`clickConversionRate`（字符串）、`competitiveDifficulty`（整数）、`organicRotation`（字符串）、`abaReport`（对象）、`costPerClick`（对象）。
- `abaReport` 字段：`reportFromDate`/`reportToDate`（YYYY-MM-DD 字符串）、`searchFrequencyRank`（整数）、`weeklySearchVolume`（整数）、`topAsins`（数组）。本次 `topAsins` 返回 3 项。
- `costPerClick` 字段：`value`、`minSuggestedBid`、`maxSuggestedBid`（字符串）。币种/单位未在该次响应或工具 schema 中明确声明，不能推断为美元。

## 已验证与未验证边界

- 工具目录对账（用户提供的西柚工具明细，2026-09-03）：目录列出 28 个数据工具，名称与实时 `tools/list` 返回的 28 个业务数据工具逐项一致；实时清单额外的 `report_missing_xiyou_capability` 是能力报告工具，不在数据工具目录中。该对账解决了“官方页面 28 / MCP 实时 29”的差异，但用户提供的目录描述仍不能替代每个工具 schema 的实时字段验证。
- 已验证：工具发现、`get_keyword_info` 参数形状、JSON-RPC 响应结构、字段类型、报告日期窗口和单次成本字段。
- 补充实测：在追加授权的 3 次只读调用中，重复调用 `get_keyword_info`、调用两周 `get_keyword_aba_trends`、调用一个 `get_asin_info`；三次均返回状态 200、各报告 `cost_credits=1`，合计业务调用 3 次、失败 0、限流 0。
- `get_keyword_aba_trends` 返回 `data.dateRangeNotice` 与 `data.entities`；实体含 `country`、`searchTerm`、`trends`，趋势项含 `reportFromDate`、`reportToDate`、`searchFrequencyRank`、`weeklySearchVolume`、`topAsins`。
- `get_asin_info` 返回 `data.entities`；实体含 `amazonUrl`、`asin`、`bigPicUrl`、`country`、`currency`、`price`、`ratings`、`smallPicUrl`、`stars`、`title`。
- 重复调用的 Provider usage 显示 `cache_hits=0`；这只证明本次直接 MCP 调用未命中 Provider 侧缓存，不替代应用层缓存/重复抑制的本地契约测试。完整 UAT 仍保持通过。
- 边界实测：对无结果关键词执行一次 `get_keyword_info` 和一次一周 `get_keyword_aba_trends`；两次状态 200、各 `cost_credits=1`。基础指标中的 `abaReport`、`competitiveDifficulty`、`costPerClick` 返回 JSON `null`，趋势项中的 `searchFrequencyRank`、`weeklySearchVolume` 返回 JSON `null`，确认缺失值保持 `null` 而非伪造为 0。
- 响应头探针：对同一 MCP 端点执行一次脱敏只读请求，HTTP 200；允许记录的响应头只有 `content-type` 和 `content-length`，未观察到 `X-Cost-Credits`、限流头、`Retry-After` 或独立 API 版本头。该结果只描述当前 MCP 端点，不把 OpenAPI 文档的行为外推到 MCP。
- 新一轮三轮授权只读复核：第 1 轮 `tools/list` 实际调用 1 次；第 2、3 轮使用完全相同的 `get_keyword_info` 参数，各包含 `tools/list` 与业务调用，均返回业务 `status=200`、`cost_credits=1`、失败 0、限流 0。两次业务响应 SHA-256 相同，但两轮 usage 均为 `cache_hits=0`，因此当前 MCP 未呈现 Provider 侧缓存/去重；本轮共 5 次实际请求，未触发 429/5xx。
- 本轮正常响应头仍只观察到 `content-type: application/json`，没有独立版本头、成本头、限流头或 `Retry-After`；成本 credit 的账户货币换算不能由正常响应推断。
- 2026-09-03 MCP `initialize` 响应提供独立字段 `result.serverInfo.version="v1"`，协议版本为 `2025-03-26`，服务名为 `xiyou-insight`；该字段已解决“响应头缺失版本”的观测缺口。
- 2026-09-03 精确重复实测：两次完全相同的 `get_keyword_info` 业务请求的 `result` 摘要完全相同，但两次均返回 `cost_credits=1`、`cache_hits=0`；当前 Provider 未呈现重复请求免费缓存/去重，应用层本地缓存和批内重复抑制仍由项目自身负责。
- 2026-09-03 有界限流实测：仅对 `tools/list` 发起 45 次受控只读请求，36 次 HTTP 200、9 次 HTTP 429、0 次传输异常；429 响应带 `Retry-After=5` 或 `6`。未继续加压，也未用畸形请求制造错误。
- 文档范围：西柚 OpenAPI v2 文档描述了 `X-Cost-Credits`、429 时的 `Retry-After`、请求节奏和有界 5xx 重试；这些是 OpenAPI v2 的文档证据，不是当前 MCP 端点的实时响应证据。
- 2026-09-03 官方文档复核：OpenAPI v2 指定 `X-Auth-Version: 2.0`，说明 `X-Cost-Credits`、429 的 `Retry-After`、默认 40 次/分钟节奏及最多 3 次 5xx/网络错误退避重试；官方 MCP 展示页列出 28 个数据工具，而实时 `tools/list` 返回 29 个（多出的能力报告工具也已记录），两者工具清单与协议不能混用。官方页面未提供可确认的 MCP 缓存/去重规则。
- 2026-09-03 官方 OpenAPI v2 额度/扣费说明补充：服务端按实际接口和返回结果计算本次 Credit，不同接口或参数规模可能消耗不同额度，并通过 `X-Cost-Credits` 返回；接口错误通常不产生业务扣费。该条只作为 OpenAPI v2 的失败扣费参考，不能证明当前 MCP 在错误、重试或限流时的实际扣费行为，也没有提供 Credit 到人民币/美元的换算。
- 2026-09-03 官方 MCP 展示页额度说明：所有注册用户免费接入，注册即得每月 `20,000 Credit`；VIP 每月 `40,000 Credit`。用户从同一官方页面补充确认周限额为 `7,000 Credit`。这确认了免费额度、VIP 月额度与周限额，但页面未说明 credit 到人民币/美元的付费换算，也不能替代 MCP 端点的 429/5xx 和独立版本实测。来源：<https://platform.xydc.com/mcp>。
- 2026-09-03 官方 MCP 页面公开工具计费规则（从页面公开前端配置核对，28 个数据工具全部有规则）：`get_asin_traffic`/`get_asin_info` 每个 ASIN 1；`get_asin_keywords`/`get_asin_keywords_monthly` 每返回 20 个关键词 1，不足按 1；`get_asin_info_trends`、`get_asin_info_change_trends`、`get_asin_traffic_trends`、`get_asin_ad_change_trends`、`get_asin_bsr_trends` 每 10 天 1；`get_asin_traffic_trends_weekly` 每 4 周 1；`get_asin_traffic_trends_monthly` 每 1 月 1；`get_asin_orders_last_30_days` 每 5 个 ASIN 1；`get_asin_order_trends` 每 6 个月 1；`get_asin_variations` 固定 5；`get_keyword_info` 每 10 个关键词 1；`get_keyword_asin_analysis`/`get_keyword_analysis_monthly` 每返回 20 个 ASIN 1；`get_keyword_aba_trends` 为关键词数 × 周数、每 20 组 1；`get_asin_keyword_traffic_trends`/`get_asin_keyword_rank_trends` 每 5 天 1；`get_asin_keyword_rank_hourly` 每 1 天固定 3；`get_asin_keywords_daily` 每返回 20 个关键词 1、无结果不消耗；`get_parent_asin_keywords`/`get_parent_asin_keywords_monthly`/`get_multi_asin_keyword_comparison`/`get_multi_asin_keyword_comparison_monthly` 每返回 20 个关键词 5、无结果不消耗；`get_asin_keyword_count_trends` 每 10 个实际返回的 ASIN 日期点 1；`get_keyword_advertising_replay` 每关键词 1 天固定 15。页面 FAQ 同时说明 Free 每月 20,000、每自然周 7,000，周额度周一 00:00 重置；成功返回有效数据才扣 Credit，明显参数错误和鉴权失败不扣。
- 尚未实测：安全只读范围内未触发 HTTP 5xx；用户已向西柚确认，西柚明确回复没有提供 sandbox、mock 或 5xx 测试接口。因此不能用压力或破坏性请求强行制造 5xx；项目以本地 fake transport 的 5xx 有界重试回归作为实现证据，并明确不宣称真实 MCP 5xx 已通过。成本 credit 的货币换算/账户计费规则仍未公开，且不应从免费额度推断付费价格。429、重复/缓存和独立版本字段已有上述实测证据。
