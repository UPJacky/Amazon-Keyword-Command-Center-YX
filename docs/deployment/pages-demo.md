# GitHub Pages 演示站打包

本地打包命令：

```text
python scripts/build_pages_demo.py --output <empty-output-directory>
```

打包器只复制：

- `frontend/` 静态页面和本地脚本；
- `data/golden/market-demo-report/`、`market-demo-modules/` 演示 artifact；
- `rules/defaults/stable.json`；
- `.nojekyll`。

同时生成站点根 `index.html`，并提供独立 `tool/index.html` 与 `report/index.html` 路由，保证 Pages 根地址和三个验收地址可直接打开。

打包完成后会对最终输出目录再次审计：禁止原始 XLSX/CSV/TSV、`.env`、私有运行目录、Secret-like 内容、外部 URL、符号链接和越界/断开的 HTML 本地引用。打包器不会自动发布到 GitHub，且报告 artifact 仍只来自明确 allowlist。真实 Auth、Storage、CORS 和私有报告链路仍需外部部署验收。

Phase 8 审计还会在临时目录重建并核对精确的 57 个文件集合，包含根目录共享脚本与独立 `tool/`、`report/` 路由。打包器固定生成离线 demo 配置，不复制现场 live 配置；扫描允许密钥类型的拒绝校验字面量，但拦截实际凭据值和私钥。该检查是本地只读发布边界验证，不代表 GitHub Pages 已发布。
