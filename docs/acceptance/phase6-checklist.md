# Phase 6 Provider-neutral Listing Checklist

当前已实现的是视觉 Provider 接入前的安全数据底座：

- 图片组只保存 URL、编号、位置和空的 `observations`，不下载图片。
- checklist 初始状态为 `unknown`，识别事实与最终评价分离。
- 高市场机会且低 CVR 的关键词会引用 `hero_value_prop`、`benefit_proof` 检查项，但不会自动改动作。
- `provider_calls=0`；视觉 Provider 接入后必须只补充事实，并保留规则/人工复核边界。

验证命令：

```text
python -m unittest worker.tests.test_listing_checklist -v
python scripts/build_listing_diagnostics.py --input data/golden/listing-diagnostics-input-demo.json --output <output>/listing-diagnostics.json
```
