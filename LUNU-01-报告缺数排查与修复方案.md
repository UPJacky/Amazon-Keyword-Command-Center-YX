# Lunu 执行方案 01：六模块报告数据与判断逻辑补全

日期：2026-09-07。本文是审查结果与待执行方案，未修改业务代码、部署、数据库或调用付费 Provider。用户要求本轮只出方案，后续由 Lunu 执行。

## 1. 审查结论及证据边界

此前宣布整个项目完成不成立。17 项任务台账与本地测试通过，仅覆盖台账列出的有限条件；不能证明原计划六模块的数据采集、业务判断和生产输出已完整交付。原计划第 2.1 节要求西柚、ABA/搜索量/Top3、自然及广告排名等；`docs/acceptance/six-module-workbench.md` 已明确记录多项缺口，后续却没有进入完整实施任务图。

本次以本地源码、既有真实链路记录和用户参考图片为依据。尝试打开用户指定线上地址时 BrowserSkill 导航超时，已关闭会话；未取得当前登录态下的网络响应或私有报告 JSON。因此下文区分“源码证实的缺口”与“该历史 run 待核实的内容”，不把源码推断写成线上实测。

用户链接的 task 为 `a32651d2-63cd-4466-8e60-9d79c182e516`，run 为 `ec431cab-f078-4abd-b607-d74f61ac8b0a`，参数完整。本次问题不能继续归因于用户漏传 task/run。历史截图显示该 run 为广告数据报告，市场/竞品/图片证据未补齐。

## 2. 已证实的根因

| 层次 | 源码定位（函数名优先，避免行号漂移） | 发现与后果 |
|---|---|---|
| 生产入口 | `scripts/run_production_worker.py:main` | 只提供 `--ad-only` 或最多 1–10 个词的 `--xiyou-keywords`；后者只接 `get_keyword_info`。没有六模块完整采集入口。当前服务器启动参数待读回确认。 |
| 西柚映射 | `worker/providers/xiyou_live_enrichment.py:XiyouLiveEnricher._market_row` | 初始化全部 MARKET_FIELDS 为 null，仅给 competitive_difficulty 赋值。ABA 报告虽被解析，却放在 provider_observations；未映射为正式搜索量/趋势字段。自然位、Top3、竞对、图片均未采集。只开启开关不足以补全。 |
| 中间数据丢失 | `worker/providers/market_merge.py:MARKET_FIELDS / merge_market_data` | 白名单没有 asin、benchmark_asins、rank_change_7d/14d/30d、provider_observations 等。即使注入这些信息，也不会沿当前 merge 进入总表行。必须做端到端字段追踪。 |
| 自然位构建 | `worker/report/modules.py:build_rank_benchmark` | 从既有行取排名，不调用 Provider；仅选择一个标杆，而且按 ASIN 字符串排序选最小值，并非自然位最强前三。 |
| ASIN 上下文 | `worker/pipeline/task_runner.py:run_task` | 调用 build_rank_benchmark 时未传 my_asin；结合 merge 不保留 asin，可能导致自己 ASIN 为空。bundle 顶部 self_asin 不会自动填充模块行。 |
| 竞对 | `worker/competitors/profile.py:build_competitor_profile` | 只保留 ASIN、品牌、标题、图片 URL、关键词等描述；传入价格、评分、订单估计、BSR等也不会保留。无采集动作。 |
| 竞对接线 | `task_runner.py`、`worker/runtime/production.py` | 只有传入 competitor_profile 才生成 competitors.json；生产 CLI 未接入按任务生成的竞对档案。全局固定档案也不适合多 ASIN 任务。 |
| 图片诊断 | `scripts/build_listing_diagnostics.py`、`worker/diagnostics/listing_checklist.py` | 只有独立本地 CLI；checklist 固定 unknown，图片 observations 固定空数组，没有实际视觉判断。 |
| 生产打包 | `worker/runtime/production.py:ProductionWorker._bundle` | 只收 rank-benchmark、negative-keywords、optimization-plan、可选 competitors；完全没有 listing-diagnostics。full_report_complete 固定 False。 |
| 前端 | `frontend/client.js:liveReports.readModule`、`frontend/report/shared.js:load` | 正确地只读取私有 bundle.modules[name]；缺模块时拒绝，不回退演示。这使未生成的数据在页面暴露出来，不能通过放开存储权限解决。 |
| 页面导航 | `frontend/report/shared.js:ready`、各模块 HTML 顶栏 | 侧栏已保留 task/run；但 rank.html 顶栏“报告”仍是 index.html 裸链接，会丢失上下文。要检查其他顶栏及返回链接。 |
| 否词判断 | `worker/report/modules.py:build_negative_keywords` | 当前零单且点击/花费同时达到止损线进精准候选；初步点击证据即进词组候选。没有相关性保护、低 CVR 高花费独立分组与词组误伤审查。 |
| 广告优化 | `worker/diagnostics/optimization.py` | 主要是把 action_group 转为动作类型和事实，不等于完成匹配类型内耗、预算迁移、观察退出判断。缺少相应广告实体粒度。 |

否词与广告优化在当前 pipeline 中本应生成。因此如果这两个页面也完全加载失败，应检查实际 bundle、旧版本输出、权限、结构与脚本错误，不能笼统说“都是缺西柚”。自然位可能有 91 行关键词但排名全空，这与模块文件缺失是两类问题。

## 3. Lunu 先做的最小线上诊断

只读登录后的指定 run，记录以下非敏感摘要：task/run、bundle schema、report_scope、full_report_complete、Object.keys(modules)、各模块行数、排名有效数、竞对有效数、图片有效数。记录请求 HTTP 状态与安全错误码，不记录 token、密码、私有对象完整访问链接。

逐页分类：

- 401/403：会话或权限问题；保留 RLS，排查登录和所属店铺。
- task/run 查询成功但没有 report_path：运行未完成或任务绑定问题。
- 私有报告 200，但 modules 缺键：生产链未生成/未打包，或历史输出缺失。
- 键存在且 rows 有值，但排名字段 null：采集/映射缺口。
- 键存在但结构验证失败：生产 schema 与页面 schema 不一致。
- 数据结构正常但无渲染：检查该页 JS 异常、ready 状态和选择器。
- 只有点击某条导航后失败：核对 task/run 是否丢失。

再只读服务器的启动参数、部署提交、非敏感 Worker 日志，确认该 run 是否 ad-only；不要打印 .env。对照线上 client.js/shared.js/rank.js 与本地源码摘要，排除发布版本不一致。

## 4. 目标数据流与契约（拟新增，非现有实现）

广告原始明细 → 聚合/对账 → 按任务采集市场与排名快照 → 保留字段的标准化 → 确定性规则 → 六模块生成 → 同一个私有 bundle → 各独立 HTML 读取。

保留现有独立 HTML + JS 和私有 bundle 架构，不需要 iframe、SPA 重写或六套鉴权。旧 report-0.2 仍可读；为新增模块内容显式版本化，不静默改变字段含义。

建议新增 `module_status`（保留现有 modules[name] 对象兼容性）：每个模块记录 status=complete/partial/unavailable/failed、reason_code、missing_fields、source_refs、coverage、generated_at、rule_version/config_version。complete 必须来自必需字段及规则验收，不能依据数组非空。运行完成与六模块完整分别显示；六个完整才允许 full_report_complete=true。

每个模块都带 task_id/run_id/self_asin/marketplace/currency_code、统计周期与快照来源。价格/评分允许不同时间采集，但必须显示其各自时间；排名比较要求同站点、同位置类型、同统计周期/快照。缺失、未采集、未上榜、超预算、失败分别记录；未知不填 0。

历史 run 不可被 CSS、刷新页面或重新发布 HTML 自动补齐。新代码与 Provider 接好后创建新 run，保留旧 run 和旧报告不覆盖；工具页显示新 run 的查看地址，旧页可提示已有更新版本。

## 5. 六模块具体补全要求

### 01 总表：修复字段贯通与规则可解释性

- 修改 xiyou_live_enrichment.py、market_merge.py、generate_report.py：逐字段校验原始响应→标准字段→总表→模块，不只测试适配器返回值。
- 工具候选：get_keyword_info（搜索量/难度等）、get_keyword_aba_trends（周趋势）、get_keyword_asin_analysis（竞争 ASIN/排名）。这些名称来自用户工具目录；参数、响应字段、分页和费用必须依照已保存工具 schema 或实际 discovery，禁止按名称猜请求体。
- weeklySearchVolume 按周展示；不能贴成月搜索量，不得乘 4 假造月量。ABA 排名与搜索量分开；Top3 点击份额与自然位标杆分开；份额单位核实后统一内部 0–1。
- 用 PROJECT_PLAN 和版本化策略定义机会/成本/证据规则；不照抄图片上的 25%、30%、45% 等。当前 stable 模板 target=20%、tolerance=30%、break_even=35%，实际运行以生效配置为准。
- 未知 market_opportunity_score 不能推断为低机会或健康；检查 engine.py 最终 hold_steady 兜底。允许保留广告侧事实结论，但必须注明市场未核验，不输出缺证据的防守/加投理由。

### 02 自然位标杆：三标杆及历史变化

- 模块构建器接收显式 self_asin、站点与排名快照；不依赖广告文件携带 ASIN。
- 新增 benchmarks 数组（最多三项），先去重/排除自身/排除无有效自然位的 ASIN，再按自然位升序、ASIN 稳定排序取三项；不足三项保留真实数量。若采用流量排序，必须另命名并记录口径，不混用“自然位前三”。
- 每项带 ASIN、标题、图片、自然位、page/position（供应商有才展示）、价格/评分及来源时间。自己的自然位与标杆必须同口径。
- rank_gap=自己自然位−标杆自然位；正数落后，负数领先。历史变化建议定义 current_rank−past_rank，负数改善；前后缺任一快照则 null。不得按页大小猜总排名。
- 自己未进入已采集前 N 个位置只记“采集范围内未见”，不能认定 Amazon 上完全未收录。
- 修改 modules.py、task_runner.py、market_merge.py 与 rank.js；用独立快照传参也可，但写清转换边界和版本。

### 03 否定词：候选、相关性与可复制内容分开

- 保留原广告聚合事实；新增 relevance=related/unrelated/unknown 与证据来源。优先使用用户确认产品功能和场景，AI 只能提出待核查解释。
- 建议判断顺序：必需字段缺失→待确认；相关性未知→待确认；相关→慎否；明确不相关且达版本化证据门槛→精准候选。已有订单的词不能被零单规则覆盖。
- 词组否定必须有影响范围审查，检测该词组是否覆盖已转化或已确认相关词；存在冲突时禁止进入直接复制清单。不能仅凭“零单+10次点击”自动判为词组否定。
- 低 CVR + 高花费单独记录筛查原因，避免同词多组计数重复；如果用花费百分位，定义样本集合、并列处理、阈值算法和版本。
- 参考图的 clicks≥15、CVR<2%、花费前20%是示例，不是已批准的新默认值。新增配置字段必须同步 Python 校验、策略 UI、SQL JSON 校验、版本回滚和测试。
- 每行展示事实、命中规则、实际阈值、一句话理由、人工复核状态。慎否/待确认/词组冲突不进复制；导出与复制复用同一资格函数。

### 04 竞对：实际采集与档案扩展

- 从排名快照按关键词覆盖选择 3–5 个竞对，或用户指定；记录选择理由和核心关键词来源。采集不足时显示 partial，不填演示 ASIN 凑数。
- 按任务调用档案 factory，取代固定全局 competitor_profile。扩展 profile.py 的字段白名单，保留 self_product 完整资料，而不只有 self_asin。
- 候选工具：get_asin_info、get_asin_bsr_trends、get_asin_variations、get_asin_orders_last_30_days。30 天订单估计不能写成后台真实销量；日期范围、估计口径必须保留。
- 价格/币种/评分/评分数/BSR/变体/图组逐字段记录来源；上架日期、视频/A+/旗舰店等工具未返回则 unavailable，不能推导为“无”。参考图用了其他供应商，不保证西柚独自提供全部字段。
- 扩展 runtime bundle 与 competitors.js，使生产值能到表格；不把第三方估计与本店真实订单或利润混算。

### 05 图片与卖点：从空 checklist 到有证据的对比

- 把 build_listing_diagnostics.py 的构建功能提取为可复用函数，接入 task_runner 和 production._bundle；仅把四项 unknown 塞进包不算完成。
- 收集同一商品图组的真实图片 URL/序号/ASIN/采集时间；主图仅一张时不能声称分析完整详情图。
- 建立视觉适配器，输出结构化 observations 与 image_id 证据，不允许无图生成“已看图”判断。视觉 API 的能力、输入格式与账户配置由后续执行核实。
- 每个要素（商品形态/套装、尺寸、功能、场景、证据等）对比三维：确认速度（首次明确出现的图序）、证据可靠性（画面/文字/实测证据的具体依据）、表达清晰度（可读性和指代）。先给各维结论，不合成无依据总分。
- 只有明确观察到的内容才写事实；推测/待人工确认单独显示。模型失败时标 unavailable，保留已有广告报告；记录模型、提示词版本、图片引用与输出校验结果。
- 页面实现“我的图/竞品图”成对展示，下方三维结论+证据+建议，不输出原始 Markdown 长墙。

### 06 广告诊断与优化：可执行建议与观察条件

- 保留现有 deterministic action_group 及其原始事实，补齐 action 的配置引用；scale_up 等动作同样要显示实际成本/证据阈值。
- 每条建议输出：对象、事实、规则版本、操作建议、观察窗口、退出条件、复盘指标、缺失前提。观察窗口和阈值必须来自有效配置，不写死在前端。
- 匹配类型内耗/预算迁移需要 campaign/ad_group/target/match_type 粒度。保留广告原始实体明细与聚合表的关系；缺实体数据时只给关键词级诊断，不能凭聚合词表判断 Broad/Phrase/Exact 冲突。
- 建议只读输出，不增加 Amazon 自动写回。

## 6. 执行顺序：每个任务一个可审查提交

| 任务 | 修改范围 | 通过条件 |
|---|---|---|
| P0 实际 run 核对与台账纠正 | 只读线上摘要；MEMORY/STATUS/TASKS | 六页逐一分类；撤销“全项目完成”结论；把下列工作纳入任务图，不能绕过监督器 |
| P1 契约与上下文 | client/shared、pipeline/runtime、schema测试 | 模块状态与 task/run 贯通，所有导航保留参数，旧 bundle 可读 |
| P2 市场/排名 | Provider→merge→rank 构建→rank UI | 至少一份真实小样有自己排名和三标杆；未找到/失败场景明确；字段跨层未丢 |
| P3 否词 | modules、策略配置/校验、negative UI | 相关/未知词受到保护；导出拒绝慎否与词组冲突；阈值可追溯 |
| P4 竞对 | profile、按任务采集、bundle、UI | 自己+3个真实竞对（供数不足标 partial），已提供产品字段无静默丢失 |
| P5 视觉 | 视觉适配器、diagnostics、bundle、UI | 真图、结构化观察、三维证据；失败降级；人工抽查与图片对应 |
| P6 广告优化 | 实体输入、optimization、UI | 可用粒度内的事实/判断/观察退出完整，缺明细不伪判结构 |
| P7 视觉样式 | 按第二份设计方案 | 桌面与手机可读、六模块有业务内容、不破坏鉴权 |
| P8 发布与新 run | 审计后的发布包、Worker、验收 | 新 run 六页登录后实际验收；无登录/跨店拒绝；原始对账仍为零；旧 run 不被覆盖 |

真实采集沿用用户已有授权与账户费用边界，采用小样→验证字段→扩大覆盖；按调用次数与实际 Credit 记录。无限调用次数授权不等于主动压测或无限重试。缓存键至少含工具/站点/关键词或ASIN/周期/契约版本；记录命中与过期；429/5xx 有界处理。西柚没有测试接口，故障路径沿用本地模拟，不再索要测试接口。

## 7. 必须补的回归（不是重跑测试数量充当完成）

1. Provider 返回三标杆/ASIN/时间→合并→规则→模块→私有 bundle→DOM，逐值一致。
2. 自己 ASIN 不依赖广告文件；排除自身；按排名而非字母选标杆；同位次稳定排序。
3. 模块不存在、空结果、部分覆盖、失效会话、越权、坏 schema 的 UI 分别正确。
4. 否词测试相关/未知/有订单/词组覆盖已转化词/重复冲突/边界等于阈值。
5. 竞对字段及币种保留；视觉无图不能 complete；任一模块失败不假报完整。
6. 发布产物不含演示数据和 Secret；前端不携带 service_role；跨店读取仍被拒。
7. 修复后用新 run 验收六页，每页至少核对实际数据、结论、理由与来源；总表一张截图不能代替其他五页。

本次不运行这些测试。Lunu 按修改范围运行对应测试，代码合并前再完整 UAT 一次；纯文档调整不用反复完整 UAT。

## 8. 可复制给 Lunu 的接手提示词

> 阅读根目录 LUNU-01-报告缺数排查与修复方案.md 和 LUNU-02-报告工作台设计方案.md。按 P0→P8 执行，先核对真实 run 的 modules，再修复数据贯通。每次只处理一个小任务，写清修改文件、测试结果、未完成项和下一步并保存 Git。遵守用户既有授权，不反复要求“继续”。不得以页面存在、HTTP 200、空数组、unknown checklist 或 UAT 全绿宣布业务完成；不得复制参考截图商品数据。参数和数据 schema 先核实后写适配器，缺数据必须标明原因。旧 run 不覆盖，最后创建新 run 做六页真实验收。先处理本地安全任务，仅真实无法继续才请求协助。
