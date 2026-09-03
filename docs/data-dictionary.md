# V1 数据字典入口

唯一枚举与动作映射见：

- `rules/data_dictionary.md`
- `rules/definitions/action_mapping.json`

确定性公式：

```text
CTR  = clicks / impressions
CPC  = spend / clicks
CVR  = orders / clicks
ACOS = spend / sales；sales = 0 时显示 —
ROAS = sales / spend
```

Unknown、未上榜、Provider 未返回和证据不足必须与确认的零值区分。所有规则字段由规则引擎写入，AI 只能写解释字段。

## 报告行字段（report-0.2）

- `evidence_level`、`action_group`、`ui_conclusion`、`ui_color`、`rule_hits`、`next_action_text`：由确定性规则引擎写入。
- `product_stage`：来自生效配置，当前由用户指定，不由 AI 推断。
- `ai_explanation`、`ai_next_action_text`：AI 解释字段；未请求时为 `null`，不得改写动作或阈值。
- `missing_fields`：Provider 或输入缺失字段列表；必须由报告追溯层的统一归一化函数生成，成为去除首尾空白、去重、排序后的标准字段名字符串数组，空白字符串和非字符串值忽略。缺失值保持 `null` / `—`，不得填 0。`market_merge`、`rule_engine`、四类 artifact 和 report/tasks 前端必须遵循同一语义。
- `report-0.2` 还保留 CTR、CPC、CVR、ACOS、ROAS、搜索量、难度、建议竞价、自然位和广告位等宽表字段。

解析器约束：输入报表中的空字符串、`-`、`N/A`、`NULL` 等缺失数值保持为 `null`，并写入该关键词的 `missing_fields`；Provider 快照显式返回 `null` 时同样必须把对应字段加入 `missing_fields`，且规则结果不得覆盖已有缺失字段；只有确认存在的数值才参与展示和派生比率。`action-results.json` 必须同时保留 `input_file`、`input_sha256`、`currency_code`、`reconciliation_passed`、`rule_version`、`config_version` 和 `provider_snapshot_version`，确保动作结果可追溯。

## 报告 artifact 追溯一致性

同一报告目录中的 `master-table.json`、`action-results.json`、`report-meta.json` 和成功运行的 `run-meta.json` 必须共享相同的 `schema_version`、`input_file`、`input_sha256`、`currency_code`、`rule_version`、`config_version`、`provider_snapshot_version` 和报告级 `missing_fields` 汇总。该汇总只接受行级标准字段名，不能因空值、重复值或非标准 fixture 形态改变排序或生成失败。`action-results.json`、`report-meta.json` 与 `run-meta.json` 的 `reconciliation_passed` 必须等于 `master-table.json.reconciliation.passed`。这些共享字段由生成器的同一 `shared_traceability()` 投影派生，避免不同 artifact 各自拼装后发生漂移；四类文件均受本地 artifact allowlist 保护，禁止覆盖历史产物。`run-meta.json` 还保留 `task_id`、`run_id`、`status` 和 `current_stage` 等运行字段，但这些运行字段不应覆盖报告追溯字段。任务页读取 `report-meta.json`，报告页读取 `master-table.json`，两页都必须展示输入文件、币种、对账、缺失值语义和版本追溯信息；运行级审计可用 `run-meta.json` 独立复核同一链路。
