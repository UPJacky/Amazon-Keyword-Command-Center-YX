# V1 数据字典（Phase 2 基线）

规则引擎只写入 `rule_owned` 字段：

```text
action_group
ui_conclusion
ui_color
rule_hits
reason_facts
effective_config_version
```

`ai_explanation`、`ai_next_action_text`、`ai_status` 属于 AI 解释字段，不能覆盖规则字段。

缺失值使用 `null` / `—` 语义，不转换为 0。固定公式：

```text
CTR  = clicks / impressions
CPC  = spend / clicks
CVR  = orders / clicks
ACOS = spend / sales；sales = 0 时为 null
ROAS = sales / spend
```

动作映射唯一来源：`rules/definitions/action_mapping.json`。

