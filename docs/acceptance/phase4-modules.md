# Phase 4 Module 02/03 本地验收

## Module 02：自然位标杆

入口：`worker/report/modules.py::build_rank_benchmark`。

- 自然位来源是标准化后的 `organic_rank`，广告位来源是 `ad_rank`；不重新解释 Provider 原始字段。
- `None` 表示未上榜/未知，输出 JSON 和前端统一显示为 `—`，不会变成 0。
- 标杆 ASIN 和标杆自然位缺失时保留缺失状态；只有双方排名都存在才计算 `rank_gap`。

## Module 03：否定词候选

入口：`worker/report/modules.py::build_negative_keywords`。

- `exact_negative`：0 单且同时达到 0 单点击与花费边界。
- `phrase_negative`：0 单且已有初步点击证据，但尚未达到直接止损边界。
- `cautious`：有点击但证据不足，不进入直接执行清单。
- `pending_confirmation`：关键广告字段缺失或没有有效点击证据。
- 有订单词不会进入否定词候选；所有输出都带 `write_back: false`，V1 不自动写 Amazon。

本地验证：

```text
python -m unittest worker.tests.test_modules -v
python scripts/build_phase4_modules.py --report data/golden/market-demo-report/master-table.json --output data/golden/market-demo-modules
```

当前演示输出为 91 条标杆记录、28 条否词候选，网络调用为 0。
