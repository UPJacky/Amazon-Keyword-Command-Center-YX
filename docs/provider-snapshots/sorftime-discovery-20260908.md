# Sorftime 原生 MCP 工具发现

2026-09-08 使用用户提供的本机 sorftime-MCP.txt 配置，POST JSON-RPC tools/list。

- 主机：mcp.sorftime.com，HTTPS，查询参数 key 认证；密钥未抄录。
- HTTP 200，Content-Type text/event-stream，共 97 个工具。
- SSE 先按行选择 data: JSON 再解析；不能直接对包含 event: 的整个响应做 JSON 解析。
- 此轮只验证工具发现，没有执行 tools/call 或业务采集，不能据此声称产品、类目或图片数据已成功返回。

本阶段相关工具（从本次实际返回投影）：

| 工具 | 用途 | 必填字段 | 参数 |
|---|---|---|---|
| product_detail | Amazon 产品详情 | asin | asin, amz_site |
| similar_product_feature | Amazon 子类目产品特征 | product_name | product_name, amz_site |
| product_reviews | 近一年评论，最多 100 条 | asin | asin, review_type, amz_site |
| keyword_detail | 热门关键词详情 | keyword | keyword, keyword_support_site |

以上名称和参数来自当前原生 MCP，不能套用 LinkFox 网关的 marketplace/includeTrend 参数。业务调用前还需读取相应参数完整 schema；图组、Listing 文本、单位和缺失语义必须以真实响应为准。

下一步：持久化不含凭据的完整目标 schema，接入原生 SSE transport，再以真实任务 ASIN 做有界详情与类目样本；图片模型仍需单独集成。现有 production-adapters-local 已领取，阶段尚未完成。
