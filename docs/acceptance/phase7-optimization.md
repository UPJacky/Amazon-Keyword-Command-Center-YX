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
- 成功任务生成 `optimization-plan.json`。

当前演示报告生成 91 条可追溯动作，Provider/AI 调用为 0。
