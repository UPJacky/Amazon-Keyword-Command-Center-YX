# Sorftime 原生产品详情能力证据（2026-09-09）

本文件只记录脱敏的字段完整性，不包含 endpoint、查询参数、密钥、原始响应或产品敏感值。

## 验证范围

- 使用项目本机提供的原生 Sorftime MCP 配置。
- 最多 5 次真实只读调用：4 个已知 US ASIN 的 `product_detail`，以及 1 次 `similar_product_feature`。
- 调用结果由项目内 `worker/providers/sorftime_transport.py` 和 `worker/providers/sorftime_adapter.py` 解析；没有写入生产任务、没有生成公开链接、没有修改 Amazon 数据。

## 结果摘要

| 能力 | 结果 | 证据口径 |
|---|---|---|
| 原生 MCP 连接 | 通过 | 5 次请求均完成 JSON-RPC/SSE 解析，没有暴露凭据 |
| 产品详情 | 4/4 成功 | 每个 ASIN 均返回标题、品牌、主图、价格、评分、评论数、月销量、类目和变体数 |
| 图片留底 | 部分通过 | 当前响应可稳定提取主图 URL；完整 Photo 数组仍需以真实 schema 再确认 |
| BSR | 未完成 | 当前归一化结果仍记录 `missing_fields=["bsr"]`，不能填 0 或推算 |
| 类目特征 | 通过 | `led lights` 返回 20 条特征，已进入统一类目特征归一化器 |
| 生产持久化 | 未完成 | 本次只读能力验证没有跑 Supabase Worker，也不能替代 E19 真实新 run |

## 对 E19 的结论

这次证据证明 Sorftime 能提供竞对产品基础字段和类目特征，线上竞对模块的 `missing_product_fields` 不是“Provider 没有任何产品能力”。但它不能直接关闭 E19：必须让生产 Worker 使用同一原生适配器完成一个新的 task/run，并在私有 bundle 中持久化 `competitors.json`、`category-features.json` 及其来源追溯。

生产重跑还必须处理两项缺口：

1. 将 BSR 按原生响应真实字段映射；未知时保持 `null` 并记录缺失原因。
2. 若要进入图片诊断，必须持久化稳定 `image_id`、主图/副图 URL 和对应的观察证据；只有主图不能冒充完整图组或视觉判断。

不得用本文件的能力样本替代真实 task/run，也不得把 `injected_data`、partial 或 demo 报告标为完整交付。
