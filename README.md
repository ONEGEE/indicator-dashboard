# Indicator Dashboard

全球大类资产配置数据台：资产规模占比、相对旋转图（JdK RRG）、宏观数据目录。

- **在线演示**：https://onegee.github.io/indicator-dashboard/
- **本地开发**：React + Vite 前端，`scripts/` 下 Python 数据管道

## 项目结构

```
indicator-dashboard/
├── static/               # 前端生产构建（npm run build / GitHub Actions 生成）
├── web/                  # React 前端源码
├── scripts/              # 数据拉取、目录构建、RRG 回测
├── data/                 # 原始/中间数据与 manifest
├── .github/workflows/    # GitHub Pages 部署
└── requirements.txt      # 数据脚本依赖
```

## 快速开始（本地浏览）

```bash
cd web
npm install
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。

生产构建（输出到 `../static/`，base 为 `/indicator-dashboard/`）：

```bash
./scripts/build_web.sh
# 或：cd web && npm ci && npm run build
```

## GitHub Pages 部署

仓库：https://github.com/ONEGEE/indicator-dashboard

1. 仓库 **Settings → Pages → Source** 选 **GitHub Actions**
2. 推送到 `main` 后，workflow `Deploy GitHub Pages` 会自动 `npm run build` 并发布 `static/`
3. 也可在 Actions 页手动 **Run workflow**
4. 站点：https://onegee.github.io/indicator-dashboard/

## 数据更新

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/ensure_playwright.py   # 首次：安装 Chromium（cn_housing 需要）
cp .env.example .env   # 填入 FRED_API_KEY
```

**推荐一键更新**（分阶段执行，避免 `fetch_rrg --mode all` 单次过长超时）：

```bash
./scripts/update_all.sh
```

常用命令（分步）：

```bash
# 轮动规模占比
python scripts/fetch_rotation.py
python scripts/build_rotation_catalog.py

# RRG 价格序列（建议分模式，不要一次 --mode all）
python scripts/fetch_rrg.py --mode cross_asset
python scripts/fetch_rrg.py --mode us_gics
python scripts/fetch_rrg.py --mode cn_sw
python scripts/fetch_rrg.py --mode country

# 宏观/指数目录
python scripts/build_catalog.py
```

更新 JSON 后重新构建前端（同步 `web/public/` → `static/`）并 push：

```bash
./scripts/build_web.sh
git add static web/public && git commit -m "Update dashboard data" && git push
```

（若只用 GitHub Actions 构建，确保数据已写入 `web/public/` 再 push，workflow 会重新 build。）

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `FRED_API_KEY` | 拉取宏观/轮动数据时 | [FRED API](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `EIA_API_KEY` | 否 | EIA 能源序列；缺省使用 DEMO_KEY |

## 许可证

MIT
