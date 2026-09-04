# 阶段 8 · 交作业本地证据

日期：2026-09-03。本文只记录可在本地重跑的证据；线上发布、真实浏览器和无痕窗口证据不以本地模拟冒充。

## 6a 透视与对账

验收输入：`data/fixtures/商品推广_搜索词_报告_LED演示.xlsx`；离线基准：`data/golden/market-demo-report/master-table.json`。

| 步骤 | 结果 |
|---|---|
| 1. 核对认列 | 通过。解析器在前 30 行按表头别名识别 `客户搜索词/展示量/点击量/花费/销售额/订单`，并把原文字段与列序号写入 `reconciliation.header_mapping`。 |
| 2. 总量对账 | 通过。展示 `1,230,627`、点击 `9,045`、花费 `5,123.10`、销售额 `20,982.29`、订单 `1,578`；五项差值分别为 `0/0/0.00/0.00/0`。 |
| 3. 行数对账 | 通过。原始有效行 `118`，重复行 `27`，去重搜索词 `91`，报告行 `91`。 |
| 4. 抽样对账 | 通过。最大花费词 `led lights` 聚合为展示 `320,422`、点击 `3,418`、花费 `1,833.22`、销售额 `7,998`、订单 `612`；单行长尾词 `100 ft led strip lights` 为 `1,632/18/11.19/14.16/1`。 |
| 5. 比率抽查 | 通过。`led lights` 的 CTR=`3418/320422`、CVR=`612/3418`、ACOS=`1833.22/7998`、ROAS=`7998/1833.22`，报告值与重算值一致；比例来自聚合原始量而非求和/平均。 |

解析器还写入 `repeat_parse_consistent=true`，91 行全部执行比率重算；对账不通过时任务在 reconciliation 阶段停止，不进入 Provider、规则和正式报告。

## 6b 抽词追溯

抽样词为 `led lights` 和 `100 ft led strip lights`。两行均能从报告行追溯到输入聚合量、`input_sha256`、`rule_version`、`config_version`、`provider_snapshot_version`、`action_group` 和 `evidence_level`；缺失值保持 `null/—`，当前两个样本无缺失字段。字段不确定时不以 0 代替，Provider 明确返回 null 会进入 `missing_fields`。

## 报告对象与页面保护

- 真实任务运行报告现在使用 `report-` 加 48 位十六进制随机串，例如 `report-<随机串>.json`，并在 `run-meta.json.report_path` 固化为 `task_id/run_id/随机文件名`。同一运行目录不会生成可猜的 `master-table.json`；演示黄金目录保留固定名仅用于离线 Pages 示例。
- 报告页通过 `fetch()` 读取 JSON 后在线渲染表格，不把文件柜 URL 裸贴到页面；私有读取链路先用当前登录用户查任务元数据，再用同一用户令牌读取对象。
- `frontend/tool/index.html`、`frontend/report/index.html` 与根登录入口是独立 HTML 地址；Pages 构建审计固定核对 57 个文件、无断链、无网络调用。
- 页面源码已有未登录门禁：`app.js` 检查会话标记，缺失时跳转到登录入口；乙线 API 继续由 Auth/RLS 拒绝匿名调用。

## 线上浏览器复核（2026-09-03）

- BrowserSkill 已连接 Edge，并在隔离 Agent Window 中直接访问线上 `/report/`；清除演示会话后，页面自动跳转到 `/index.html` 登录页，报告表格内容不可见。
- 在同一隔离会话完成演示登录后，`/tool/` 正常显示 ASIN、`.xlsx/.csv`、10 MB、阶段 3 固定顺序、手动刷新和失败原因列；`/report/` 正常显示 `fetch 在线获取并渲染`、91 个搜索词、`对账 通过 · 差值 0`。
- 线上 `index.html`、`tool/index.html`、`tool/tool.js`、`report/index.html`、`report.js`、`styles.css` 均返回 200，且与当时已审计发布目录哈希一致；远端演示包 `main` 为 `b42009a`。
- BrowserSkill 截图只输出网页视口，不包含浏览器地址栏；因此三张带地址栏截图仍保留为人工交付项，不能用视口截图冒充。匿名乙线 API 拒绝截图也仍需在可控的真实接口环境中补齐。

## 阶段 8 清单

| 项目 | 本地结果 |
|---|---|
| 独立登录、工具、报告页面 | 通过；`index.html`、`tool/index.html`、`report/index.html` 均独立存在。 |
| ASIN、上传格式/大小、阶段顺序、重复提交、刷新、失败原因、退出 | 通过静态契约和前端回归；工具页限定 B0 开头 10 位 ASIN、`.xlsx/.csv`、10 MB，阶段顺序固定，提交中禁用按钮，任务列表支持手动与 30 秒刷新，失败原因和退出入口可见。 |
| 宽表格与移动端横向滚动 | 通过；固定最小列宽、表头居中、内容左对齐、横向滚动和窄屏样式已写入共享 CSS。 |
| 本地 Git 存档与密钥纪律 | 通过；已有基线提交，工作树干净，`.env`、密钥文件、私钥、原始上传文件和运行目录均被忽略且不在索引。 |
| 对账、抽词、随机报告对象名 | 通过；见上方 6a/6b 和对象名证据。 |
| 本地 5xx | 通过；按用户确认“西柚无测试接口”，使用本地 5xx 模拟作为验收证据，未伪造西柚真实 5xx。 |
| 线上 Pages 精确地址/重发布 | 演示包通过；远端 `main=b42009a`，根入口、`/tool/`、`/report/` 均 HTTPS 200。生产live包尚未发布，不以演示证据替代。 |
| 未登录窗口打开报告页 | 通过；BrowserSkill 隔离 Agent Window 清除演示会话后直接打开 `/report/`，自动跳回 `/index.html`，报告内容不可见。 |
| 三张带地址栏截图、乙线匿名 API 拒绝截图 | 部分完成；已生成登录/工具/报告网页视口截图，但接口只提供视口不含地址栏；带地址栏截图和乙线真实接口拒绝截图仍需人工补齐。 |

## 重跑命令

```text
python scripts/check_phase8_documentation.py
python scripts/phase8_audit.py
python scripts/run_uat.py
```

上述命令均为本地验证；UAT 的网络调用和外部调用必须保持为 0。
