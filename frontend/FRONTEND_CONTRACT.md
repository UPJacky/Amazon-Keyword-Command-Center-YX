# 前端契约静态检查

## 页面入口

- `index.html`：主登录入口；
- `login.html`：独立登录页演示；
- `workspace.html`：登录后工作台；
- `tasks.html`：任务列表 / 新建任务；
- `strategy.html`：策略中心 / 试算；
- `report.html`：Module 01 报告。

## 当前边界

- 页面使用演示交互，不宣称已接入真实 Auth、Storage 或 Task API；
- 页面不保存 Provider Secret；
- 正式接入时，前端只能使用公开型 Auth 配置，报告通过受控 API 或短时签名能力读取；
- `action_group`、`ui_conclusion`、`rule_hits` 等规则字段必须由 Worker 返回，前端不得自行推断。

## 已检查

- HTML 页面、样式和脚本文件存在；
- 页面资源引用为本地相对路径；
- Secret-like token 扫描未发现命中；
- 任务、策略、报告入口可从工作台导航到达。
- 后台页面使用 `data-page` 或 `app-shell` 保护标记；演示会话缺失时由 `app.js` 重定向到 `login.html`。
- 自动化契约检查同时校验会话标记、重定向代码和四个后台页面的保护标记。
