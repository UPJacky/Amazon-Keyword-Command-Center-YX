# Phase 5 竞对档案本地验收

入口：`worker/competitors/profile.py`、`scripts/build_competitor_profile.py`。

- 竞对集合要求 3～5 个唯一 ASIN；自己的 ASIN 不能重复进入竞对集合。
- 档案保留品牌、标题、图片 URL、核心关键词、缺失字段和 snapshot version。
- 缓存键对竞对顺序、关键词大小写和 marketplace 大小写不敏感，保证同一输入可复用。
- 老任务仍可不提供 `competitor_profile`；新任务提供有效档案时在 run artifact 中生成 `competitors.json`。
- 无 Provider transport 时 `provider_calls=0`；本地模块不会发起网络请求。

验证命令：

```text
python -m unittest worker.tests.test_competitor_profile worker.tests.test_task_runner -v
python scripts/build_competitor_profile.py --input data/golden/competitor-input-demo.json --output <output>/competitors.json
```
