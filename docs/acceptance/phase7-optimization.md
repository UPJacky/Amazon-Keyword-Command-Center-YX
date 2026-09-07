# Phase 7 广告诊断与优化清单

入口：`worker/diagnostics/optimization.py`、`scripts/build_optimization_plan.py`。

每条动作都保留：

```text
data_facts → rule_hits → config_refs → action_type / next_action_text
```

支持的动作类型包括：加投候选、核心防守、新词测试、观察退出检查、Listing 诊断、竞价调整、结构清理、止损复核、数据补齐和下一轮复盘。

约束：

- 不改变规则引擎已经写入的 `action_group`；
- `ai_may_change_action=false`；
- 不自动修改 Amazon 广告；
- 配置引用保留 `config_version` 及相关边界对象；
- 成功任务生成 `optimization-plan.json`（当前 schema `optimization-plan-0.2`）。
- 产物逐条保留源文件提供的 campaign、ad group、target、match type 等广告实体上下文；实体明细不完整时，`entity_diagnoses[].judgement` 必须为 `not_judged`，不得从关键词聚合推断实体级动作。
- 每条实体诊断同时保留事实、判断、建议动作和退出条件；缺失退出条件使用 `pending`，不填造阈值。

当前演示报告生成 91 条可追溯动作，Provider/AI 调用为 0。
