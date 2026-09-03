# V1 架构基线

```text
frontend static pages
        ↓ Auth / Task / Config API（待接入）
中转台：Auth + Task + Config + RLS（待实现）
        ↓
Worker：ingestion → provider snapshot → rule engine → report
        ↓
私有文件柜：raw / JSON / report / cache
```

当前已实现：报表解析、配置合并、task/run 模型、确定性规则引擎、报告 JSON 组装、文件队列、持续 Worker 轮询和静态页面骨架。当前未实现：真实 Auth、数据库任务接入、Provider 网络调用和受控报告读取。

前端不得持有 Provider Secret；Worker 不直接被前端调用；报告不使用永久公共链接。
