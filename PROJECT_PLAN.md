---
project: Amazon-Keyword-Command-Center-YX
project_cn: 关键词作战总表
document_type: implementation_plan
version: 1.4
updated_at: 2026-09-10
status: current
language: zh-CN

## 当前阶段 8 交付审计（2026-09-03）

本轮恢复执行后的优先纠正：已发布 b42009a 为演示包；真实接入不只差 CORS。`live-release-readiness` 与 `production-live-deployment` 已完成，005/006 迁移、精确 Origin 网关、私有上传、任务/run、租约 Worker、策略版本和 live 报告读取均有复验记录；历史测试/截图不替代新生产链证据。

- 真实任务报告对象名采用 `report-<48位十六进制随机串>.json`，运行元数据记录 `task_id/run_id/report_path`；固定 `master-table.json` 仅保留在离线演示黄金目录。
- 解析器输出 `reconciliation.header_mapping`，供 6a 第一步核对实际表头与列序号；演示输入 118 行聚合为 91 个搜索词，展示/点击/花费/销售额/订单差值均为零，比例从聚合原始量重算。
- 阶段 8 交付证据见 `docs/acceptance/phase8-delivery-audit.md`；线上重发布、真实无痕报告门禁和三张带地址栏截图均已登记，报告页截图来自带 `task/run` 的真实在线报告地址。

> 当前基线见 Phase 8 的“当前执行状态（2026-08-31）”；此前有日期的执行段落保留为历史证据。

## 当前 Provider 外部 Gate 进度（2026-09-02）

- 新 MCP 配置已通过一次只读 `tools/list`：HTTP 200，响应为有效 JSON-RPC，返回 29 个工具；随后完成 6 次正常/边界只读业务样本，均 HTTP 200、失败 0、限流 0，观察到每次 `cost_credits=1`，无结果字段保持 `null`。
- 在用户新授权的 3 轮复核中追加 5 次实际请求：重复 `get_keyword_info` 两次均为业务 `status=200`、`cost_credits=1`、`cache_hits=0`，响应摘要相同；因此未观察到 Provider 侧缓存/去重，但没有触发 429/5xx。
- `scripts/probe_provider.py` 已支持直接脚本启动；`McpHttpTransport` 现在只通过 `last_response_metadata` 暴露成本、Retry-After、限流和版本相关响应头白名单，控制字符/超长/未白名单字段会被丢弃，不记录 Authorization 或原始错误体。
- 当前 MCP 响应头探针只观察到 `content-type` 和 `content-length`，没有实时确认成本单位、429/5xx 行为或独立版本字段；缓存/重复已观察为本轮直接请求 `cache_hits=0`，仍不能把该结果当作账户级计费或所有请求场景的完整证明。

## 当前本地路径守卫 fail-closed 修复（2026-08-21）

- `worker/security/path_guard.py` 在 `stat/lstat` 遇到权限或其他 `OSError` 时拒绝路径，不再把无法检查的路径当作安全普通目录；缺失路径仍保持可创建语义。
- 新增 3 项回归，完整 UAT Worker 144 项（12 项环境跳过）、前端 5 项、19/19 Gate 通过；未调用网络、真实 Provider、凭据、部署或费用。

## 当前 UAT 结构化摘要必需字段补强（2026-08-21）

- `run_uat.py` 对 Worker loop、Phase 8 和 Pages 三个结构化 Gate 强制要求 `network_calls`、`external_calls`、`local_only` 三个字段；缺失字段、类型错误、超时和启动异常均结构化失败并继续收集全部 19 Gate。
- 新增 4 项编排回归，当前 UAT 编排契约 18 项；缺少结构化摘要同时写入 `summary_contract_errors` 和诊断字段，且 `_summary_metrics` 对缺失摘要安全跳过；新增统一 120 秒 Gate 超时和 5 组临时目录退出清理验证。最新完整 UAT Worker 144 项（12 项环境跳过）、前端 5 项、Pages 19 文件、双入口 Worker、Phase 8、compileall 和文档契约通过，network_calls=0、external_calls=0、Secret=0。
---

> 2026-09-07 Phase 9 纠正：项目按 `LUNU-01-报告缺数排查与修复方案.md`、`LUNU-02-报告工作台设计方案.md` 与 `PROJECT_TASKS.json` 的 P0-P8 重新开启。此前 Phase 8 完成仅保留为安全发布和 ad-only 对账 Gate，不再代表六模块业务完整。

## 当前 report-0.2 追溯契约收口（2026-08-21）

- 直接修复报告、规则、市场合并和前端边界：`missing_fields` 去除首尾空白并过滤空白/非字符串值；`shared_traceability()` 与前端对账判断拒绝把字符串 `"false"` 当作通过；前端对异常缺失字段形状安全降级为 `—`。
- 新增 7 项回归；统一 `normalise_missing_fields()` 供报告、市场合并、规则引擎使用，前端 report/tasks 对缺失字段过滤、去重、排序；完整 UAT 19/19 Gate，Worker 140 项（11 项环境跳过）、前端 5 项，Python/PowerShell loop、Phase 8、Pages、Smoke、迁移、编译和文档契约通过；本轮禁止并未调用外部服务。

## 当前 queue/storage/ingestion/Pages/Supabase 安全审计（2026-08-21）

- FileQueue state 目录、artifact task/run 目录和 Pages 输出目录均在创建前后拒绝符号链接/Junction/reparse point，保持恢复/失败归档、artifact allowlist/不可覆盖、URL/header 与本地 Secret/网络边界不变。
- 新增 2 项边界回归；完整 UAT 19/19 Gate，Worker 136 项（11 项 Windows 链接能力跳过）、前端 5 项；本轮未调用网络、真实 Provider、凭据、部署或费用。

## 当前 report-0.2 missing_fields 归一化审计（2026-08-21）

- `market_merge` 与 `rule_engine` 对异常 fixture 的 `missing_fields` 统一过滤非空字符串、去重排序，字符串不会被拆成字符，确保行级、报告级和四类 artifact 语义一致。
- 新增 2 项回归；完整 UAT Worker 134 项（9 项环境跳过）、前端 5 项，定向报告/市场合并/规则引擎/任务运行 33 项（1 项环境跳过），本轮未调用网络、真实 Provider、凭据或部署。

## 当前本地安全边界复核（2026-08-21）

- queue 恢复/失败归档、ingestion 输出和 Supabase URL 解析边界已补齐；不触发外部网络、Provider、部署、凭据或费用。
- 定向范围测试 70 项通过（13 项环境跳过）；完整 UAT 19/19 Gate，Worker 134 项、前端 5 项，network_calls=0、external_calls=0、Secret=0。

## 当前 UAT 编排摘要契约边界加固（2026-08-21）

- `run_uat.py` 对结构化子 Gate 摘要强制要求 `network_calls`、`external_calls`、`local_only` 三个字段，并执行类型与范围校验；缺失/异常摘要写入 `summary_contract_errors`，malformed/partial summary 保持为结构化失败并继续收集 19 Gate 而不早停。
- 新增 3 项编排回归，当前 UAT 编排契约 14 项；完整 UAT Worker 134 项（9 项环境跳过）、前端 5 项、Pages 19 文件、双入口 Worker、Phase 8、编译和文档契约通过，网络/外部调用 0。

## 当前本地安全边界补强（2026-08-21）

- queue/storage/ingestion/Pages 的根路径、源树和 artifact 路径检查同时拒绝符号链接及 Windows Junction/reparse point；恢复、失败归档和 artifact 发布继续保持不可覆盖。
- 定向安全回归 73 项（12 项因当前 Windows 符号链接能力跳过），完整 UAT 19/19 Gate、Worker 132 项、前端 5 项、compileall、双入口 Worker、Pages、Phase 8、Smoke 和文档契约通过；网络/外部调用 0、Secret 0。

## 当前 report-0.2 本地追溯审计（2026-08-21）

- `run-meta.json` 已纳入安全 artifact 白名单，可通过统一 `write_json/read_json` 复核运行级追溯；前端契约覆盖报告页展示字段、任务页 report-meta 字段及 task runner 的共享投影边界。
- `shared_traceability()` 对报告级 `missing_fields` 执行标准字符串过滤、去重和排序，避免异常 fixture 破坏四类 artifact 一致性；当前完整 UAT 基线为 Worker 132 项（9 项环境跳过）、前端 5 项；本轮不调用网络、真实 Provider、凭据或部署。

## 当前安全审计收口（2026-08-21）

- queue 失败归档/processing 恢复的领取竞态已覆盖：冲突不覆盖历史记录，且不会因未初始化 task/run 标识让连续 Worker 早停或反复异常退避。
- Pages 打包源树在复制前拒绝符号链接，结合输出审计确保路径、外部 URL、断链、Secret 和网络边界均为本地安全 Gate。
- 当前完整 UAT 为 Worker 130 项（9 项环境跳过）、前端 5 项；19 个 Gate、双入口 loop、Phase 8、编译和文档契约通过，网络/外部调用 0。
- 本轮边界审计将 Worker loop、Phase 8 和 Pages 三个结构化 Gate 的 JSON 摘要设为必需；摘要缺失、启动异常、超时或字段类型错误均失败但继续收集，编排契约当前 13 项。

## 当前 UAT/部署审计编排加固（2026-08-21）

- `run_uat.py` 固定执行 19 个 Gate；Worker loop、Phase 8 和 Pages 三个结构化边界 Gate 必须提供 JSON 摘要，再累计 `network_calls`/`external_calls` 并校验 `local_only=true`；失败、超时和启动异常仍继续收集。
- 五组 UAT 临时输出目录由 `ExitStack` 统一托管，正常和异常路径均自动清理；新增编排回归覆盖外部调用拒绝。
- 当前完整 UAT 为 Worker 130 项（9 项环境跳过）、前端 5 项；UAT 编排契约 11 项、Pages 19 文件、双入口 loop、Phase 8、编译和文档契约全部通过；网络/外部调用 0。

## 当前安全审计补强记录（2026-08-21）

- queue 领取/恢复采用不覆盖目标的原子硬链接发布；storage task/run 中间目录拒绝符号链接；Supabase header 拒绝 HTTP 控制字符；Pages、Secret 和网络边界继续保持本地只读。
- 本轮定向安全测试 46 项（9 项环境跳过）及完整 UAT Worker 128 项、前端 5 项通过；无真实 Provider、网络、部署、凭据或费用操作。

# Amazon-Keyword-Command-Center-YX · 最终项目计划

## 当前本地安全 Gate（2026-08-21）

- 输入路径、队列归档、artifact 不可覆盖写、task/run ID、Supabase URL/header 和私有报告边界已完成本地回归；符号链接、悬空失败归档、解析输出和 Pages 输出读取边界已加固；完整 UAT 当前为 Worker 128 项、前端 5 项。
- UAT 编排已覆盖 9 项防早停/本地边界回归：Gate 超时、Gate/loop 启动异常均结构化为失败并继续收集后续 Gate；契约测试验证失败后仍遍历完整 Gate 清单、拒绝子 Gate 报告的外部调用，并锁定双入口各 2 轮、2 心跳、`errors=0`、未提前停止。
- UAT 编排当前进一步锁定 19 个本地 Gate，并校验子 Gate 摘要累计的 `network_calls=0`、`external_calls=0`、`local_only=true`；loop 超时可通过 `KWCC_LOOP_TIMEOUT_SECONDS` 在本地调整且最小为 1 秒。
- Pages 输出与 Supabase 迁移契约仍保持本地只读审计；真实 RLS、私有 Storage、GitHub Pages 和 Provider schema 仍需外部权限确认。

> v1.4：吸收 Claude Code 审核意见，并冻结“**前期不备案域名，后期再迁移**”的部署路线。Phase 0/1/2 核心不依赖备案；前期前台优先 GitHub Pages，服务器只跑 Worker；备案完成后只迁移托管/域名/HTTPS/CORS/Auth Redirect，不借机重写规则引擎和数据层。

## 0. 计划目标

本计划用于把现有“关键词作战总表”从一次性报表升级成可持续使用的内部关键词运营决策系统。

最终核心能力：

```text
上传 Amazon 搜索词报表
→ 代码聚合并自动对账
→ 补齐西柚 / ABA / 自然位数据
→ 合并当前产品阶段与策略参数
→ 确定性规则引擎产生动作
→ AI 解释原因与下一步
→ 在线报告 / 历史任务 / 策略复盘
```

本计划优先保证：

1. 数据可信；
2. 规则确定；
3. 所有阈值可配置；
4. 五色作战结论 + 灰色数据状态可执行；
5. 同输入可复现；
6. 内部使用安全；
7. 后续能持续增加模块而不重写核心。

---

# 1. 最高优先级开发原则

## 1.1 不写死任何业务数值

所有涉及以下数值的条件都必须参数化：

- ACOS；
- CTR；
- CVR；
- CPC；
- 点击；
- 订单；
- 花费；
- 搜索量；
- 搜索量分位；
- 难度；
- Top3 点击占比；
- ABA 趋势变化率；
- 趋势窗口；
- 自然排名防守区；
- 防守 ACOS / CPC 上限；
- 止损点击；
- 止损花费；
- 竞价比例；
- 排序权重。

历史数值只能做模板默认值。

## 1.2 规则引擎做决定

最终动作必须由代码计算。

AI 只解释，不得改结论。

## 1.3 先数据，后规则，最后 UI

开发顺序不得反过来。

如果数据聚合还没完全对账，不进入规则结论开发。

## 1.4 先小样再付费全量

任何 Provider 或规则新版本先跑 10～30 个关键词小样。

通过后才放量。

## 1.5 先审计现有项目，不整项目重写

Phase 0 是**技术栈基线的产出阶段**，不是进入 Phase 0 的前置门槛。Phase 0 之前禁止直接重构。

Phase 0 必须回答：项目是否已存在、代码路径、语言/框架、数据库、中转台、Worker、任务模型、部署方式、现有模块、可复用资产、需替换资产。

## 1.6 业务阈值可配置，数据定义不可配置

策略中心只管理业务边界，不允许修改数据公式和系统不变量。

可配置：ACOS 边界、止损点击/花费、自然位防守区、市场机会阈值、证据门槛、排序业务优先级等。

不可配置：CTR/CPC/CVR/ACOS/ROAS 公式、聚合方式、Unknown 语义、ASIN 数据格式定义、销售额 0 时 ACOS=`—` 等。

## 1.7 当前部署决策：先未备案，后迁移

用户已明确：**前期先不做 ICP 备案，后期再调整。**

因此当前计划默认：

```text
前期前台：GitHub Pages（默认 Pages URL 优先，不把自定义域名作为 Phase 0～3 的阻断条件）
中转台：Supabase / 等效 Auth + Task + Config + RLS
Worker：云服务器后台进程，不通过大陆服务器 80/443 对外提供网页
报告/文件：保持私有，通过登录后的受控读取链路访问
```

后期备案完成后再切换到自有域名 + OSS/COS 静态托管或 nginx 等正式托管方式。迁移原则是“换门面，不换心脏”：Task/Rule/Config/Provider/Worker/Golden Tests 尽量保持不变。

---

# 2. V1 范围

## 2.1 V1 必须完成

### 数据与规则

- xlsx / csv 广告报表解析；
- 动态表头；
- 动态字段识别；
- 搜索词聚合；
- CTR / CPC / CVR / ACOS / ROAS 重算；
- 自动对账；
- 西柚 MCP；
- ABA / 搜索量 / 难度 / Top3；
- 自然排名 / 广告排名；
- Provider 缓存；
- 产品阶段；
- 策略模板；
- 多层配置覆盖；
- 广告证据等级；
- 市场机会；
- 自然位防守；
- 强制止损；
- 优先诊断；
- 小预算测试；
- 数据待补；
- 五色业务结论 + 灰色状态映射；
- 排序；
- 规则命中原因；
- `rule_version` / `config_version`；
- 规则确定性测试；
- AI 结论写保护与降级；
- 任务 `run_id` / 幂等重跑；
- V1 单任务单币种校验；
- 审计事件；
- 数据保留策略。

### 前台

- 登录；
- ASIN / 店铺 / 产品阶段；
- 策略选择；
- 临时阈值覆盖；
- 上传报表；
- 任务列表；
- 失败原因；
- 当前策略摘要；
- 策略设置 Drawer / Modal；
- 策略试算；
- 报告页；
- 五色业务结论筛选 + 灰色数据状态筛选；
- 宽表格横向滚动；
- 报告历史。

### 报告

1. 关键词作战总表；
2. 自然位标杆；
3. 否定词清单；
4. 竞对对比；
5. 图片与卖点诊断；
6. 广告诊断与优化方案。

### Module 与报告唯一映射

| Module | 报告 | 计划阶段 |
|---|---|---|
| Module 01 | 关键词作战总表 | Phase 3 |
| Module 02 | 自然位标杆 | Phase 4 |
| Module 03 | 否定词清单 | Phase 4 |
| Module 04 | 竞对对比 | Phase 5 |
| Module 05 | 图片与卖点诊断 | Phase 6 |
| Module 06 | 广告诊断与优化方案 | Phase 7 |

Module 编号、导航、文件名与报告标题以此表为唯一映射来源。

## 2.2 V1 明确不做

- 自动修改 Amazon 广告；
- 自动暂停 Campaign；
- 自动添加否定词；
- Amazon Ads API 写操作；
- 财务系统；
- 对外 SaaS；
- 复杂审批流；
- 为架构先进而引入微服务 / K8s / 集群型中间件。

---

# 3. 推荐项目结构

项目根目录建议：

```text
Amazon-Keyword-Command-Center-YX/
│
├─ PROJECT_MEMORY.md
├─ PROJECT_PLAN.md
├─ PROJECT_STATUS.md
├─ AGENTS.md
├─ DESIGN-airtable.md
│
├─ docs/
│  ├─ architecture.md
│  ├─ data-dictionary.md
│  ├─ provider-semantics.md
│  ├─ risks.md
│  ├─ decisions/
│  └─ acceptance/
│
├─ rules/
│  ├─ definitions/
│  ├─ defaults/
│  ├─ templates/
│  ├─ overrides/
│  └─ history/
│
├─ worker/
│  ├─ ingestion/
│  ├─ providers/
│  ├─ rule-engine/
│  ├─ modules/
│  ├─ report/
│  ├─ storage/
│  └─ tests/
│
├─ frontend/
│  ├─ auth/
│  ├─ workspace/
│  ├─ strategy/
│  ├─ tasks/
│  ├─ reports/
│  └─ shared/
│
├─ data/
│  ├─ samples/
│  ├─ fixtures/
│  ├─ golden/
│  └─ schemas/
│
└─ scripts/
```

如果现有结构已经合理，不为“目录好看”强迁移。

判断标准：

- 一个功能可独立定位；
- Codex 修改一个模块不需要读取整个项目；
- 改一个模块不会牵连全站。

---

# 4. 核心数据模型

## 4.1 Task

每个任务至少保存：

```text
task_id
run_id
previous_run_id
created_by
store_id
self_asin
competitor_asins
core_keywords
product_stage
strategy_id
task_config_override
current_effective_config_version
input_file_path
input_file_hash
currency_code
status
current_stage
failure_reason
report_path
created_at
started_at
completed_at
```

## 4.2 每任务留底

建议：

```text
data/{task_id}/
├─ input-meta.json
├─ ad-aggregated.json
├─ reconciliation.json
├─ xiyou-raw.json
├─ market-normalized.json
├─ master-table.json
├─ rules-snapshot.json
├─ action-results.json
├─ organic-rank.json
├─ negatives.json
├─ competitors.json
├─ images.json
├─ ad-plan.json
└─ report-meta.json
```

动作结果存储必须分区：

```text
rule_owned:
  action_group
  ui_conclusion
  rule_hits
  reason_facts
  effective_config_version

ai_owned:
  ai_explanation
  ai_next_action_text
  ai_status
```

AI 输出不得拥有 / 覆盖 `rule_owned` 字段。

每个 JSON 至少带：

```text
schema_version
task_id
generated_at
data_source
source_version
rule_version
config_version
```

---

# 5. 数据字典与 Provider 唯一语义

进入规则开发前必须建立两个版本化文档：

```text
docs/data-dictionary.md
docs/provider-semantics.md
```

## 5.1 关键枚举

至少定义：

```text
evidence_level = no_ads | insufficient | preliminary | sufficient
market_opportunity = unknown | low | medium | high
organic_defense_level = unknown | none | watch | defend | core_defend
acos_pressure = unknown | healthy | watch | high | over_break_even
ai_status = not_requested | success | degraded | unavailable
action_group = scale_up | defend_rank | hold_steady | cautious_test | continue_observation | optimize_listing | optimize_bid | optimize_structure | stop_loss | reduce_or_pause | data_missing
ui_conclusion = add | defend | keep | cautious | optimize | stop_loss | data_missing
ui_color = green | cyan | yellow | orange | red | gray
```

`missing_fields` 必须使用标准字段名数组，不允许自由文本代替。

## 5.2 Provider 语义

西柚 / ABA / 排名字段必须只从 `provider-semantics.md` 读取定义。

当前业务口径草案（**Phase 0 必须对照西柚实际 tools/list / schema 再验证，验证前不视为永久事实**）：

- 自然位：西柚关键词-ASIN分析 `ranks` 中 `or` 的最小 `totalRank`；
- 广告位：`sp/sb/sbv` 中最小 `totalRank`；
- 未出现对应位置码：`—`；
- `traffic` 不等于 ABA 点击份额；
- `trafficRatio` 与 `trafficAcquisitionRate` 方向相反；
- ABA Top3 使用 `topAsins.clickShare/conversionShare`；
- ABA 使用上一个完整周期。

文档同时定义缓存 TTL、刷新规则、429 重试策略、建议竞价来源、字段单位与空值语义。

---

# 6. 策略中心设计

## 6.1 这是 Phase 2 的核心，不得延后

策略中心负责所有业务阈值，不再把阈值散落在：

- Prompt；
- Worker 源码；
- 前端常量；
- SQL；
- 报告模板。

## 6.2 配置覆盖

```text
任务临时覆盖
>
ASIN 配置
>
产品阶段配置
>
店铺配置
>
全局默认
```

Worker 只读取：

```text
current_effective_config
```

## 6.3 第一版策略模板

- 新品增长；
- 平衡增长；
- 稳定利润；
- 强势防守；
- 低效流量清理；
- 清货；
- 季节性重启；
- 自定义。

模板 = 默认参数集合，不是固定规则。

## 6.4 前端入口

任务页顶部显示：

```text
当前策略：xxx
产品阶段：xxx
目标 ACOS：xx%
容忍 ACOS：xx%
0 单止损：xx 点击 / $xx
自然位防守：Top x
趋势窗口：xx 周

[修改策略]
```

点击进入策略设置。

## 6.5 设置区

```text
产品阶段
ACOS / 利润
广告证据
止损规则
转化诊断
市场机会
自然排名防守
排序规则
高级设置
```

## 6.6 设置操作

必须有：

```text
保存
取消
恢复默认
复制策略
另存为模板
应用到本 ASIN
应用到多个 ASIN
查看修改记录
试算影响
```

## 6.7 试算流程

```text
修改参数
↓
生成临时 config
↓
重算 action_group，不写正式配置
↓
显示结论变化数量
↓
可展开查看发生变化的关键词
↓
用户确认
↓
保存新 config_version
```

---

# 7. 规则引擎设计

## 7.1 推荐计算流水线

```text
输入完整性检查
↓
广告报表聚合与对账
↓
广告证据等级
↓
产品阶段与 ACOS 压力
↓
自然排名防守价值
↓
市场机会等级
↓
止损 / 诊断 / 测试 / 保持逻辑
↓
底层 action_group
↓
映射五色业务结论 + 灰色数据状态
↓
主表排序
↓
AI解释
```

## 7.2 冲突处理

```text
硬性止损 / 利润底线
>
关键数据完整性
>
广告证据
>
产品阶段
>
自然位防守
>
市场机会
>
优化 / 诊断
>
加投 / 保持
>
谨慎测试 / 观察
>
低优先级
```

## 7.3 规则结果必须输出的字段

每个关键词至少：

```text
keyword
product_stage
effective_config_version
evidence_level
market_opportunity
organic_rank
organic_defense_level
acos_pressure
action_group
ui_conclusion
rule_hits
reason_facts
next_action
missing_fields
```

## 7.4 AI 结论写保护

规则字段：

```text
action_group
ui_conclusion
rule_hits
reason_facts
effective_config_version
```

只能由规则引擎生成并进入只读区域。AI 调用只接收副本，AI response schema 禁止出现这些字段；存储层再次过滤。

AI 只允许返回：

```text
ai_explanation
ai_next_action_text
ai_status
```

AI 调用失败 / 超时 / 429 / JSON 校验失败：**报告继续生成**，`ai_status=degraded|unavailable`，直接展示规则原因，不得改变或阻塞最终动作。

---

# 8. 正式结论、动作映射与排序

## 8.1 统一术语

本项目使用：**五色作战结论 + 灰色数据状态**。

```text
绿色：加投 / 防守
青色：保持
黄色：谨慎投放
橙色：优化
红色：停止投放 / 止损
灰色：数据待补（状态，不计入五色业务结论）
```

“加投”和“防守”在 UI 可以同为绿色，但底层必须拆成 `add` / `defend` 两个 `ui_conclusion`，不得继续使用 `add_defend` 单枚举。

## 8.2 V1 默认动作映射表

| action_group | ui_conclusion | UI | 含义 |
|---|---|---|---|
| `scale_up` | `add` | 绿色 | 主动扩大有效流量 |
| `defend_rank` | `defend` | 绿色 | 守住核心自然位/关键词 |
| `hold_steady` | `keep` | 青色 | 保持当前策略 |
| `cautious_test` | `cautious` | 黄色 | 小预算测试 |
| `continue_observation` | `cautious` | 黄色 | 证据不足继续观察 |
| `optimize_listing` | `optimize` | 橙色 | Listing/转化承接优化 |
| `optimize_bid` | `optimize` | 橙色 | CPC/竞价/成本优化 |
| `optimize_structure` | `optimize` | 橙色 | 广告结构/内耗优化 |
| `stop_loss` | `stop_loss` | 红色 | 强止损 |
| `reduce_or_pause` | `stop_loss` | 红色 | 缩量/暂停/止损执行 |
| `data_missing` | `data_missing` | 灰色状态 | 关键数据不足，禁止强判 |

该映射必须只存在于版本化 rule definitions / data dictionary 中，由前后端共同读取，不允许散落复制。

## 8.3 默认展示顺序

```text
绿色（add / defend）
→ 青色（keep）
→ 黄色（cautious）
→ 橙色（optimize）
→ 红色（stop_loss）
→ 灰色状态（data_missing）
```

绿色组中 `add` 和 `defend` 不写死二级先后，默认一起按市场搜索量排序。

## 8.4 同组默认排序与稳定键

业务默认：

```text
市场搜索量 DESC
```

完整稳定键链：

```text
ui_color_group_order ASC
→ market_search_volume DESC（缺失值最后）
→ ad_spend DESC
→ normalized_keyword ASC
```

`normalized_keyword`：Unicode NFC；使用项目内固定 comparator，不依赖系统 locale；大小写规则固定并测试；原始 keyword 原样保存。

展示组顺序 + 组内主排序字段可配置；花费和规范化关键词属于稳定性 tie-break。

## 8.5 Phase 2 黄金规则样例

所有阈值引用 `current_effective_config`，不在样例里写死数字：

| Case | 输入事实 | 预期 |
|---|---|---|
| G01 | 核心数据不足 | `data_missing → data_missing` |
| G02 | 证据充分、0 单、越过强止损边界 | `stop_loss → stop_loss` |
| G03 | 核心自然位进入防守区且成本健康 | `defend_rank → defend` |
| G04 | 需防守但已突破硬成本/利润底线 | 不得判 `defend`，按止损/优化分流 |
| G05 | 证据充分、表现健康、市场机会高、有扩量空间 | `scale_up → add` |
| G06 | 表现稳定、无扩量/防守强信号 | `hold_steady → keep` |
| G07 | 证据不足但市场机会可接受 | `cautious_test/continue_observation → cautious` |
| G08 | 高机会、广告差、未到硬止损且承接有问题 | `optimize_* → optimize` |
| G09 | 多投放对象内耗 | `optimize_structure → optimize` |
| G10 | 低机会 + 证据充分低效 + 触发止损 | `reduce_or_pause/stop_loss → stop_loss` |
| G11 | 无广告历史但满足测试条件 | `cautious_test → cautious` |
| G12 | AI 输出与规则动作冲突 | 丢弃 AI 动作字段，规则动作不变 |

这些案例要进入 golden tests；Phase 2 Gate 前必须人工确认。


---

# 9. 分阶段施工计划

# Phase 0：现状审计与冻结基线

## 目标

先弄清楚现有项目是什么状态，不改代码。

## 要做

1. 读取当前目录；
2. 识别前端 / Worker / 数据库 / Provider / 报告代码；
3. 找出所有写死阈值；
4. 找出 Prompt 中直接决定动作的逻辑；
5. 找出重复的业务判断；
6. 找出旧“公共读报告”等安全实现；
7. 找出已有测试与样例；
8. 输出差异清单；
9. 强制建立“技术栈基线”：项目代码实际路径、语言/框架、包管理、数据库/中转台、任务机制、Worker 运行方式、部署方式、测试方式、现有模块清单；
10. 判断现有项目是“可增量改造”还是“不可复用需从零搭建”。若从零搭建，只允许给出轻量推荐栈与理由，不在 Phase 0 直接开工；
11. 输出当前 `action_group` 取值域、`ui_conclusion` 取值域、现有映射实现，与 §8 默认映射做差异清单；
12. 输出未决 Provider 假设清单：西柚 tools/schema/成本/限流、AI Provider、视觉 Provider、备用方案；
13. 确认 `DESIGN-airtable.md` 文件存在、版本可读，并检查术语与“五色结论 + 灰色状态”是否冲突；
14. 确认当前部署路线：前期未备案，前台不依赖大陆服务器 80/443；列出 GitHub Pages / 报告私有读取链路 / 后期备案迁移的差异。

## 输出

```text
当前架构图
数据流
目录结构
已完成能力
缺失能力
硬编码阈值清单
规则冲突清单
安全差异清单
建议修改文件清单
技术栈基线
复用 / 重建判断
Phase 1 前置阻断项
action_group / ui_conclusion / 颜色映射差异草案
Provider 未决假设清单
DESIGN-airtable.md 依赖检查
未备案部署路线检查
```

## Gate

用户确认：

> “现状理解正确，可以进入 Phase 1。”

未确认前禁止整项目重写。

---

# Phase 1：广告报表解析与数据底座

## 目标

先让自己的广告数据绝对可信。

## 开发项

- xlsx / csv；
- 动态表头；
- 动态列识别；
- 数值清洗；
- 搜索词聚合；
- CTR / CPC / CVR / ACOS / ROAS 重算；
- Unknown 处理；
- `reconciliation.json`；
- fixtures；
- unit tests；
- 单币种校验；
- 解析器版本留底。

## 正式对账定义

```text
SUM(raw.impressions) == SUM(aggregated.impressions)
SUM(raw.clicks)      == SUM(aggregated.clicks)
SUM(raw.orders)      == SUM(aggregated.orders)
ABS(SUM(raw.spend) - SUM(aggregated.spend)) <= 0.01
ABS(SUM(raw.sales) - SUM(aggregated.sales)) <= 0.01
```

- 展示 / 点击 / 订单：严格相等；
- 花费 / 销售额：货币计算容差 `0.01`；
- 比率内部比较精度 `1e-6`，展示层另行格式化；
- 同文件 + 同解析器版本连续解析两次，规范化结果逐字段一致；
- 任一关键原始量失败：立即停任务，不调用付费 Provider，不出正式报告；
- V1 一个任务只允许一个 `currency_code`；发现多币种直接报错，不自动换汇。

`reconciliation.json` 必须记录公式、原始合计、聚合合计、差值、容差、pass/fail。

## 演示表必须通过的基线

`商品推广_搜索词_报告_LED演示(1).xlsx`：

```text
原始数据行 = 118
去重搜索词 = 91
展示 = 1,230,627
点击 = 9,045
花费 = 5,123.10
销售额 = 20,982.29
订单 = 1,578
```

关键词 `led light` 聚合结果：

```text
4 行
展示 15,216
点击 131
花费 82.96
销售额 408.42
订单 30
```

该文件必须固化为 `data/fixtures/` / `data/golden/` 的 golden fixture，记录来源、脱敏状态、SHA-256、解析器版本。`led light` 固定为必测词；另外 2 个抽样词在 Phase 1 首次人工核对后固化，未经确认不随意更换。

## Gate

至少 3 份真实 / 样例报表：

- 对账差值 = 0；
- 随机抽 3 个搜索词人工计算一致；
- 同文件重复解析结果一致；
- 比率全部重算；
- 销售额 0 时 ACOS = `—`。

未通过不进入 Provider 和规则阶段。

---

# Phase 2：策略中心 + 规则引擎

## 目标

把判断逻辑从 Prompt 和硬编码中拿出来。

## 开发项

- rule definitions；
- config schema；
- defaults；
- strategy templates；
- store / stage / ASIN / task override；
- config merge；
- config validation；
- config version；
- rule version；
- rule snapshot；
- 试算 preview；
- deterministic tests；
- 五色业务结论 + 灰色状态映射表（§8.2）；
- 排序配置；
- `docs/data-dictionary.md` 枚举落地；
- `docs/provider-semantics.md` 语义落地；
- AI 字段级写保护；
- AI 降级路径；
- task/run 幂等模型；
- 12 条黄金规则样例转自动化测试；
- `add` / `defend` 底层拆分；
- rule_version 发布 / 回滚机制。

## 重点业务规则

- 先产品阶段，再 ACOS；
- 0 单必须看证据等级；
- 自然位进入防守区时提升战略价值；
- 防守不能突破利润 / 成本底线；
- 高机会差表现优先诊断；
- 无投放 + 有机会 → 小预算测试；
- 数据缺失 → 数据待补；
- ABA 趋势不能单独决定加投。

## Gate

选 20～30 个关键词小样，人工逐条核对：

- evidence；
- market opportunity；
- organic defense；
- stop loss；
- optimize；
- add/defend；
- cautious；
- data missing。

同输入 + 同 rule/config 跑 2 次：

> 五色业务结论/灰色状态与底层 action_group 必须按版本化映射 100% 一致；`add` 与 `defend` 必须可单独断言。

同时必须通过：

- AI response schema 不含动作字段；
- 模拟 AI 返回恶意 / 冲突动作字段时，存储层丢弃且规则动作不变；
- AI 完全不可用时报告仍可生成；
- 数值边界使用统一精度规则；
- 排序 tie-break 后重复运行行序一致。

---

# Phase 3：Module 01 关键词作战总表 + 报告骨架

## 目标

先把最重要的业务页面做成内部可用版本。

## 开发项

- 六模块报告导航骨架；
- Module 01；
- 当前策略摘要；
- 五色业务结论筛选；
- 灰色“数据待补”状态筛选；
- 主表默认排序；
- 组内市场搜索量降序；
- `rule_hits`；
- `missing_fields`；
- AI reason；
- next action；
- 宽表；
- 固定列宽；
- 横向滚动；
- 导出能力（如现有架构适合）。

## 建议列组

### 关键词

- 搜索词；
- 关键词角色；
- 产品阶段。

### 广告真实表现

- 展示；
- 点击；
- CTR；
- CPC；
- 花费；
- 订单；
- 销售额；
- CVR；
- ACOS；
- ROAS；
- 证据等级。

### 市场机会

- 搜索量；
- 难度；
- Top3 点击占比；
- ABA 趋势；
- 建议竞价。

### 排名

- 自然位；
- 广告位；
- 防守级别；
- 排名变化。

### 作战结论

- 业务结论（add / defend / keep / cautious / optimize / stop_loss）；
- 灰色数据状态（data_missing）；
- 底层动作；
- 命中规则；
- 原因；
- 下一步；
- 缺失字段。

## Gate

- 对账 = 0；
- 核心数据不丢；
- 五色业务组 + 灰色状态排序正确；
- 同色内搜索量降序；
- 缺失不是 0；
- 页面符合 `DESIGN-airtable.md`；
- PC 可高效使用；
- 窄屏可横滑；
- AI 不改变结论。

达到该阶段即可让内部运营开始试用核心功能。

---

# Phase 4：自然位标杆 + 否定词清单

## 目标

增加两个低成本、高频使用模块。

## Module 02 自然位标杆

优先复用已有西柚缓存，展示：

- 我的自然位；
- 我的广告位；
- 标杆 ASIN；
- 标杆自然位；
- 差距；
- 7/14/30 天排名变化（数据具备后）。

未上榜：`—`。

## Module 03 否定词清单

基于广告聚合 + 当前策略参数生成建议：

- 精准否定候选；
- 词组否定候选；
- 慎否；
- 待确认。

V1 不自动写 Amazon。

## Gate

抽样验证：

- 自然位语义；
- 未上榜不是 0；
- 2 条否词数字正确；
- 慎否不进入直接执行清单；
- 证据不足不被否死。

---

# Phase 5：竞对模块 + 任务输入升级

## 目标

支持自己 ASIN + 3～5 个竞对，并形成可复用竞对档案。

## 开发项

- 动态添加竞对；
- 标记自己 / 竞对；
- 核心关键词；
- 西柚竞对候选；
- 可选补充 Provider；
- `competitors.json`；
- 主图 / 图片 URL 留底；
- 竞对档案表；
- 缓存。

## Gate

- 老任务兼容；
- 新任务可运行；
- 抽 2 家竞品核对关键字段；
- Provider 调用量可追踪；
- 重跑不重复付费抓已有数据。

---

# Phase 6：图片与卖点诊断

## 目标

把 Listing 转化承接诊断产品化。

## 原则

视觉模型只负责识别“看到了什么”，最终评价标准来自明确 checklist。

## 开发项

- checklist；
- 自己图片组；
- 竞品图片组；
- 图片编号；
- 视觉 Provider；
- 对比矩阵；
- 卖点差异；
- “广告差但市场机会高”时自动引用相关转化检查项。

## Gate

抽 2 个检查项、2 张图片、1 家竞品人工复核：

- 识别事实正确；
- 不编造图片中不存在的信息；
- 结论和规则分开。

---

# Phase 7：广告诊断与优化方案

## 目标

把“动作结论”变成可执行运营清单。

## 开发项

- Broad / Phrase / Exact 内耗；
- Search Term → Exact 迁移建议；
- Broad 降价；
- 预算集中；
- 否定建议；
- 核心防守；
- 新词测试；
- 观察退出条件；
- 止损清单；
- 下一轮复盘指标。

## Gate

抽取至少 10 个动作：

每个动作必须能追溯：

```text
数据事实
→ 规则命中
→ 当前配置值
→ 最终动作
```

不能出现“AI 觉得应该”。

---

# Phase 8：内部 UAT + 正式部署

## 目标

让内部人员稳定使用，并建立可维护运行方式。

### 当前部署路线（未备案阶段）

Phase 8 的“正式部署”在当前版本不以 ICP 备案为前提：

```text
前台：GitHub Pages 默认地址优先
登录/任务/配置：Supabase / 等效中转台
Worker：云服务器后台进程
报告：私有文件 + 登录后的受控读取
```

当前阶段**不要求**：自有备案域名、备案号页脚、大陆服务器 nginx 对外网页托管。

当前阶段**仍然要求**：HTTPS（GitHub Pages / 平台提供）、RLS/鉴权、Secret 隔离、私有报告、CORS 精确 Origin。

备案完成后的迁移单独执行“Deployment Migration Gate”，不与业务 V1 Gate 混在一起。

### 当前执行状态（2026-09-10）

- 本地 Phase 8 Gate 已通过：完整 UAT 20/20 Gate、Worker 325 项（12 项环境能力跳过）、前端 8 项（Node 场景由前端门禁调用）、UAT 编排契约 25 项、连续执行契约 63 项、Pages 57 文件、live 候选49文件、Pages构建46项、迁移静态合同59项、Smoke、Phase 4～7 CLI、双Worker入口、Phase 8 静态审计、compileall 和文档契约 15 项均通过；network_calls=0、external_calls=0、Secret value 命中为0。
- Pages 生产候选已通过 allowlist 审计并发布到 GitHub Pages；根入口以及独立 `tool/`、`report/` 路由均 HTTPS 200。生产包共 49 个文件，不含演示报告、原始输入或 Secret；本地 demo 构建仍固定生成离线 public-config。
- 真实任务报告对象名使用 `report-` 加 48 位十六进制随机串，`run-meta.json.report_path` 固化 task/run/对象路径；解析器在 `reconciliation.header_mapping` 留存实际表头与列序号，6a/6b 本地证据见 `docs/acceptance/phase8-delivery-audit.md`。
- 前端 live Auth、私有上传、任务/run登记与重跑、策略追加版本/回滚、私有报告及六模块 bundle 读取、精确Origin Gateway、租约Worker和live打包均已完成线上复验；真实 B 任务已完成，报告经私有 Storage fetch 后在线渲染。报告仍明确标注广告范围，市场/竞品/图片证据待补。
- 当前临时 Supabase 项目已完成 001–006；public schema 匿名请求拒绝；双用户 RLS 与私有 reports Storage 读取矩阵已通过，跨店读取为 0、越权任务写入 403、自有报告 200、跨用户拒绝。Gateway 精确 Origin 预检与 Auth/REST 已复验；Provider 只读证据与西柚无测试接口、本地 fake 5xx 边界按既定规则保留。
- Provider 本地 HTTP transport 与一次性探测入口已通过离线验证；真实 Provider 业务缺失项继续按报告声明，不以广告部分报告宣布完整项目完成。
- 主 Agent 仍须在每个子 Agent 返回后重读状态、复核改动、运行相关 Gate、同步文档并清点下一项安全本地工作；不得因单个测试、UAT 或子 Agent 完成而结束项目。

### Phase 8 下一步定义

1. 无外部凭据时：继续维护本地契约、失败路径、静态审计、回归测试和文档一致性，不调用真实服务。
2. 获得外部凭据/确认后：按外部 Gate 顺序执行最小范围联调，并保留可回滚证据；不把外部 Gate 的未执行状态写成通过。
3. 若本地清单为空且外部 Gate 仍未授权：保留阻塞记录并暂停当前执行链，等待凭据、权限或服务确认。

## UAT 场景

至少覆盖：

1. 正常搜索词报表；
2. 多行重复搜索词；
3. 销售额为 0；
4. 低点击 0 单；
5. 高点击 0 单；
6. 高机会但广告差；
7. 自然位进入防守区；
8. CPC 已接近建议竞价上限；
9. 市场数据缺失；
10. 429 限流；
11. Provider 部分字段缺失；
12. 策略修改前后试算；
13. 同一任务重复运行；
14. 五色筛选与排序；
15. 权限与报告访问；
16. AI 完全不可用但报告仍生成；
17. 多币种文件被明确拒绝；
18. 重跑生成新 run_id 且历史可追溯；
19. 审计事件可查询。

## 安全基线

- 业务页面登录后访问；
- Admin / User 基础角色；
- RLS / 等效访问控制；
- 前端无 Secret；
- `.env` / 密钥不进 Git；
- 原始广告报表私有；
- 正式报告默认私有；
- 通过受控鉴权链路读取；
- CORS 精确限制当前前端 Origin（未备案阶段为 GitHub Pages Origin；后期迁移再替换）；
- HTTPS（未备案阶段使用托管平台 HTTPS；后期备案域名重新验收证书）；
- 基础审计；
- 店铺级数据隔离；
- Admin / User 最低权限矩阵；
- 数据保留 / 删除策略；
- Provider 防重复、重试上限、调用记录。

## Gate

- 关键业务场景全部通过；
- 无高风险 Secret 泄露；
- 规则确定性通过；
- 报表对账通过；
- 五色业务结论 + 灰色数据状态通过人工抽样；
- 策略中心可正常改值和回滚；
- 报告访问权限通过；
- GitHub Pages 未备案路线可用，服务器未通过 80/443 对外提供前台网页；
- UAT 问题有清单并分级。

## 后期备案完成后的 Deployment Migration Gate

备案完成后再执行，不阻塞当前 V1：

1. 选定正式托管：OSS/COS 静态站点或 nginx；
2. 自定义域名 DNS / 绑定完成；
3. HTTPS 证书通过；
4. CORS Origin 从 GitHub Pages 更新到正式域名；
5. Supabase / OAuth / Auth Redirect URL 更新；
6. 页脚按要求加入备案号；
7. 登录、上传、任务、报告、策略、导出做 smoke test；
8. Worker、Rule Engine、Task schema、Provider schema 不因迁移改写；
9. GitHub Pages 保留一段回退期，迁移验收后再决定是否下线。

---

# 10. 前端设计要求

## 2026-09-03 用户参考图修订（优先于下方旧视觉约束）

用户明确指出界面难看及模块缺页。本次采用深蓝标题区、蓝色主按钮、浅灰蓝页面底、白色内容卡与侧栏；保留固定列宽、表头居中、内容左对齐、表内横向滚动、五色结论与灰色缺失状态。`DESIGN-airtable.md` 保留为原始参考，不直接覆盖其营销页规范；它的黑色主按钮、纯白 hero、96px 大段距不再约束数据工作台。

六模块分别交付 `report/index.html`、`report/rank.html`、`report/negative.html`、`report/competitors.html`、`report/listing.html`、`report/optimization.html`，每个模块拥有独立脚本，共享样式/导航/登录校验；不使用大 HTML 切屏，也不以 iframe 嵌套整个应用。文件拆分降低修改耦合，但数据权限仍由后端/RLS保证。

缺口纠正：此前本地 Gate 通过证明计算器/契约可运行，不代表六模块前端已交付，更不代表生产链路完成。独立页面补齐须验证实际数据行、筛选、加载/空/失败和登录门禁。演示数据与真实数据分开，真实图片/视觉事实未接入时明确待补，不能以截图中的商品值填充。两份《实施计划》《分阶段验收与优化指南》仅作参考，不覆盖本计划的 V1 六模块及私有报告架构。

正式前端必须读取并记录 `DESIGN-airtable.md` 的版本/哈希后开发；Phase 0 若发现缺失或与本计划术语冲突，先形成差异清单，不允许前端自行猜。

本计划只固定功能边界：

- 白色为主要画布；
- 主按钮深墨色；
- 主要操作少而明确；
- 策略设置使用 Drawer / Modal；
- 报告主表是核心；
- 五色用于业务结论，灰色用于数据待补状态；不要用大面积彩色污染页面；
- 表格固定列宽；
- 横向滚动；
- 筛选器明显；
- 当前策略摘要始终可见；
- 修改策略后先试算；
- 加载 / 失败 / 空状态必须清楚。

---

# 11. 测试体系

## 11.1 数据测试

- 动态表头；
- 不同列顺序；
- 货币符号；
- 百分号；
- 空值；
- 重复词；
- 销售额 0；
- CSV / XLSX；
- 对账。

## 11.2 规则单元测试

每条规则至少：

- 正向案例；
- 反向案例；
- 边界值；
- 缺失值；
- 配置变更案例。

## 11.3 确定性测试

固定 fixture + provider_snapshot_version + rule_version + config_version 重跑两次：

```text
action_group 一致
ui_conclusion 一致
ui_color 一致
rule_hits 一致
排序行序一致
```

“可复现”指 `rule_owned` 业务字段级一致，不要求 `generated_at`、日志时间、trace id、AI 自然语言等非规则字段字节级一致。AI 文案可以有轻微措辞差异，但不能改变动作。

## 11.4 回归集

把人工确认过的 20～30 个关键词保存为 golden cases。

每次规则升级输出：

```text
旧结论
新结论
变化原因
是否预期
```

---

# 12. Provider 成本与缓存

每个 Provider 必须统一：

- `estimate()`；
- `fetch()`；
- `normalize()`；
- `cache_key()`；
- `retry_policy`；
- `usage_log`。

默认：

> 有缓存不重新付费抓取。

用户需要主动选择：

```text
[刷新市场数据]
```

才能强制更新。

小样不得只取“前 20 个词”造成偏差。默认用分层小样：

- 高花费词；
- 有订单核心词；
- 0 单高点击词；
- 高搜索量未投词；
- 自然位已进入防守区的词；
- Provider 缺失 / 未上榜词。

总量建议 10～30 个；通过字段语义、缓存、限流、规则与报告验收后才放全量。具体数量是运行策略参数，不写死在业务规则源码。

---

# 13. 任务幂等、数据生命周期、权限与审计

## 13.1 重跑语义

```text
task_id = 一次用户提交
run_id = 一次实际执行
previous_run_id = 上一次执行（如重跑）
```

- 上传文件变化 = 新 `task_id`；
- “重新分析” = 新 `run_id`，不得覆盖历史运行；
- 同 `task_id + input_hash + rule_version + config_version + provider_snapshot_version` 应可复现；
- Provider 缓存有效时重跑默认复用，不重复付费；
- 重跑结果通过 `run_id` 分目录 / 分记录保存，不允许互相覆盖。

## 13.2 V1 单币种规则

- 一个任务只允许一个 `currency_code`；
- 发现多币种直接报错并停止；
- V1 不自动换汇，不允许静默把不同币种相加。

## 13.3 数据保留默认建议

- 原始报表：90 天；
- Provider 原始缓存：30～90 天，按更新频率配置；
- 规则/配置快照、动作结果、正式报告：默认长期；
- 审计日志：至少 180 天。

这些是运维默认配置，可由管理员调整；自动删除必须留审计事件，核心证据删除需明确授权。

## 13.4 最低权限模型

V1 不提前做复杂 RBAC，但 schema 必须预留：

```text
created_by
store_id
role
```

最低要求：用户只能访问被授权店铺的数据；普通 User 不得修改全局策略 / 店铺级策略；Admin 可管理策略和用户授权。Phase 8 固化完整“角色 × 资源 × 操作”矩阵。

## 13.5 审计事件

至少记录：

```text
login_success / login_failure
file_uploaded
task_created / task_started / task_failed / task_completed / task_rerun
config_previewed / config_changed / config_rolled_back
provider_refreshed / provider_rate_limited
report_viewed / report_exported
file_deleted / permission_changed
```

## 13.6 rule_version 发布与回滚

- 每次规则变化创建新的 `rule_version`；
- 已发布旧版本不可覆盖删除；
- active rule pointer 可回退到已验证版本；
- 回滚只影响后续新 run，历史 run 保留原版本；
- `rule_version` 回滚与 `config_version` 回滚分别记录审计事件；
- 回滚后必须跑 golden rules + Phase 2 deterministic regression。

## 13.7 未备案 → 已备案迁移纪律

前期 GitHub Pages 是当前正式可用路线，不是“临时乱搭”。后期备案迁移必须：

- 不改规则语义；
- 不改任务 ID / run ID 语义；
- 不改 Provider 字段定义；
- 不丢历史报告；
- 只在必要位置更新前端 Origin、域名、HTTPS、Auth Redirect 和托管配置。

---

# 14. 项目状态管理

建议新建并持续维护：

```text
PROJECT_STATUS.md
```

每完成一个 Phase 记录：

- 日期；
- 完成项；
- Gate 结果；
- 当前规则版本；
- 当前配置版本；
- 已知问题；
- 下一步；
- 需要用户确认的事项。

新会话先读：

```text
PROJECT_MEMORY.md
PROJECT_PLAN.md
PROJECT_STATUS.md
```

## 14.1 Gate 未通过时的处理

- 默认停留在当前 Phase 修复，不跨阶段掩盖问题；
- 若发现根因属于上一 Phase 的数据 / 架构错误，回退到对应 Phase 修复并重跑后续 Gate；
- 任何“带缺陷继续”必须由用户明确接受，并在 `PROJECT_STATUS.md` 记录风险、临时措施与补偿计划。

## 14.2 工期与性能目标的确定时点

在 Phase 0 技术栈基线完成前，不写假工期。Phase 0 Gate 后再根据：现有代码复用率、典型报表行数、Provider 调用量、部署环境，给每个 Phase 形成工作量与性能预算。

## 14.3 连续执行与多 Agent 监督协议

当用户要求“继续执行”或未明确要求暂停时，主 Agent 以项目目标为唯一总目标，负责维护任务计划、分配安全的本地子任务、汇总子 Agent 结果并监督 Gate。子 Agent 的角色可以是代码、测试、安全、流程/文档或部署审计，但不得把自己的子任务通过误报为项目完成。

每个子任务必须返回：改动文件、验证命令与结果、未完成项、外部阻塞项。主 Agent 在接收结果后必须继续执行以下闭环：

```text
状态重读 → 本地任务清点 → 子 Agent 结果核验 → 源码/测试/UAT/契约检查
→ 进程级检查 → 文档同步 → 分配下一项安全任务
```

单次命令、单个测试、单个子 Agent 完成或完整 UAT 通过，都只能关闭对应子步骤，不能作为当前阶段或项目完成信号。若遇到外部凭据、权限或服务阻塞，必须先完成本地模拟、失败路径、契约和文档；只有不存在任何安全本地下一步时，主 Agent 才能暂停并报告阻塞。

执行状态由 `PROJECT_STATUS.md` 顶部的 `execution_state`、`current_objective`、`next_safe_action`、`stop_reason`、`last_action_fingerprint` 和 `verified_gate_snapshot` 驱动。`RUNNING` 时必须持续领取并执行下一项安全任务；只有 `BLOCKED_EXTERNAL`、`BLOCKED_RISK`、`USER_STOPPED`、`PROJECT_COMPLETE` 可结束执行链。`BLOCKED_EXTERNAL` 仅表示需要外部凭据、权限或业务确认，不等于项目完成。

用户要求持续推进整个项目时，平台级持续目标是执行轮次生命周期所有者。主 Agent 必须先调用 `get_goal`；结果为空时调用 `create_goal` 一次并绑定完整项目目标，已有 active 目标时复用，不能为每个命令或子任务创建新目标。单个回复、上下文压缩、UAT 或子 Agent 完成都不能关闭 active 持续目标。

防重复使用动作指纹和验证快照：输入源码、配置、计划、测试计数和 Gate 快照未变化时，跳过已验证动作并选择后续任务；不得重复运行同一套测试或审计来代替项目推进。若状态为 `RUNNING` 却没有具体 `next_safe_action`，必须重新清点任务或进入合法终止态，不能回复后等待用户再次说“继续”。

持久任务图存放在 `PROJECT_TASKS.json`，由 `scripts/project_supervisor.py` 校验依赖、状态、输入指纹和验证回执并选择唯一 `next_task`。执行本地任务前用 `--claim` 在跨平台并发锁内原子领取；完成后用 `--complete` 写入结构化通过回执，并在同一事务中自动领取下一项安全本地任务。外部 Gate 永不自动选择；用户明确授权、本地队列清空且依赖有效时，使用显式任务 ID、`--claim-external` 与非敏感授权回执领取，失败或授权撤回用 `--block-external` 原子回退。任务 ID、执行类型、依赖、验收条件和声明输入共同组成指纹；任一变化时自动 stale 重开。本地 `running` 期间输入变化时 `--complete` 拒绝旧证据，重新 `--claim` 刷新指纹后继续验证；外部输入变化必须回退并重新授权。输入未变且回执有效时必须跳过，防止重复执行。只要监督器返回 `RUNNING`，主 Agent 就继续任务，不能发送最终收尾。

平台级持续目标保存“为什么继续”，任务图保存“下一项做什么”，心跳自动化只在 `RUNNING` 时激活并跨轮继续上述闭环；进入合法终止态后立即暂停，避免完成态空转。恢复条件是用户新指令、外部阻塞解除或产生新的安全本地任务。心跳不扩大外部服务、费用、凭据、权限或删除授权。子 Agent 完成并被复核后必须关闭释放并发槽位，避免下一轮任务分配因已完成 Agent 占位而失败。

---

# 15. 当前最优先施工顺序

如果现在开始由 Codex 执行，顺序固定：

```text
1. Phase 0 现状审计
2. Phase 1 报表解析 + 对账
3. Phase 2 策略中心 + 规则引擎
4. Phase 3 关键词作战总表
5. 内部开始试用核心功能
6. 再依次扩充 Module 02～06
7. UAT / 安全 / 正式部署
```

不要先做漂亮 UI，再回头补业务规则。

---

# 16. Phase 0 给 Codex 的直接开工指令

可直接把下面内容交给 Codex：

```text
读取 PROJECT_MEMORY.md、PROJECT_PLAN.md 和现有 PROJECT_STATUS.md（如存在）。
当前只执行 Phase 0：现状审计，不改代码、不重构、不改数据库、不调用付费接口。

重点检查：
1. 当前目录结构与数据流；
2. 广告报表解析是否按客户搜索词做确定性聚合；
3. 是否存在把 ACOS/点击/花费/CTR/CVR/搜索量/难度/Top3/自然排名等数值直接写死的业务代码；
4. 是否存在由豆包/大模型自由决定 action_group 的逻辑；
5. 当前 action_group / ui_conclusion / 颜色 / 排序如何实现，是否把 add 与 defend 合并；
6. 是否有策略设置、配置覆盖和 config_version；
7. 是否有 reconciliation；
8. Provider 是否有缓存、调用量和 429 重试纪律；
9. 报告与原始报表的访问安全；
10. 前端是否读取 DESIGN-airtable.md，并记录文件存在性/版本/术语冲突；
11. 输出技术栈基线：真实代码路径、语言/框架、数据库、中转台、任务机制、Worker、部署、测试、现有模块；
12. 判断项目适合增量改造还是需要从零搭建；
13. 识别 Phase 1 前置阻断项：对账能力、输入格式、单币种、数据安全；
14. 输出西柚/AI/视觉 Provider 未决假设与验证方法；
15. 核对当前部署路线：前期不备案，前台优先 GitHub Pages，服务器不通过 80/443 对外提供网页；
16. 对照 PROJECT_PLAN §8 输出 action_group → ui_conclusion → UI颜色 的差异表，Phase 0 只冻结草案，不直接改代码。

输出：当前架构、数据流、技术栈基线、完成能力、缺失能力、硬编码阈值清单、冲突逻辑、安全差异、建议修改文件清单、复用/重建判断、Phase 1 前置阻断项、动作映射差异表、Provider 未决假设、DESIGN 依赖检查、未备案部署路线检查。
若用户没有明确要求暂停，完成 Phase 0 检查后继续执行当前计划中的下一项安全本地工作；只有需要用户判断、凭据/权限、危险操作，或确实没有安全下一步时，才报告并暂停。Phase 0 Gate 结果必须写入 `PROJECT_STATUS.md`，不得把这段开工模板当作当前会话的自动收尾指令。
```

---

# 17. 项目完成定义

只有同时满足以下条件，V1 才算完成：

- 广告报表聚合可证明正确；
- 聚合前后对账为 0；
- 规则和参数已分离；
- 所有关键阈值可在策略中心调整；
- 支持多层配置覆盖；
- 支持试算与版本记录；
- 同输入重复运行结论一致；
- AI 无权改最终动作，且字段级写保护已有自动测试；
- AI 不可用时不阻塞报告；
- 使用“五色作战结论 + 灰色数据状态”，且 add / defend 底层语义独立；
- 默认展示组顺序为“绿色 add/defend → 保持 → 谨慎投放 → 优化 → 停止投放/止损 → 灰色数据待补”；
- 同组**默认可配置**为市场搜索量降序，并有稳定 tie-break；
- Unknown 不等于 0；
- 自然位防守不突破成本底线；
- 付费 Provider 有小样、缓存、限流与调用量记录；
- Module 01 可供内部运营真实使用；
- 报告与原始文件权限符合内部生产安全基线；
- 关键规则、配置、任务、报告都可追溯版本；
- `task_id/run_id` 重跑语义明确；
- V1 单任务单币种，不做静默汇率换算；
- Provider 语义和关键枚举有唯一版本化文档；
- 审计与数据生命周期可追溯；
- 前期未备案路线可独立通过 V1 Gate，后期备案迁移不要求重写核心。

最终验收问题：

> 任意点开一条关键词，系统能否明确说明：用了哪份原始数据、哪个规则版本、哪个配置版本、命中了哪条规则、为什么得出这个动作，以及如果改一个阈值会发生什么变化？

如果能，项目才真正从“AI 报告”升级成了“关键词运营决策系统”。
