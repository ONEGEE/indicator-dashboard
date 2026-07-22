# Indicator Dashboard

全球大类资产配置数据台：资产规模占比、相对旋转图（JdK RRG）、宏观数据目录。

- **在线演示**：部署于 [Streamlit Community Cloud](https://streamlit.io/cloud)（见下方部署说明）
- **本地开发**：React + Vite 前端，`scripts/` 下 Python 数据管道

## 项目结构

```
indicator-dashboard/
├── streamlit_app.py      # Streamlit Cloud 入口
├── static/               # 前端生产构建（npm run build 生成，需提交）
├── web/                  # React 前端源码
├── scripts/              # 数据拉取、目录构建、RRG 回测
├── data/                 # 原始/中间数据与 manifest
└── requirements*.txt     # 运行时 vs 数据脚本依赖
```

## 快速开始（本地浏览）

### 1. 前端开发模式

```bash
cd web
npm install
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。

### 2. Streamlit 本地预览（与线上一致）

```bash
cd web && npm ci && npm run build   # 生成 ../static/
cd ..
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## 数据更新

数据脚本需要额外依赖：

```bash
pip install -r requirements-data.txt
cp .env.example .env   # 填入 FRED_API_KEY
```

常用命令：

```bash
# 轮动规模占比
python scripts/fetch_rotation.py
python scripts/build_rotation_catalog.py

# RRG 价格序列（四类模式）
python scripts/fetch_rrg.py --mode all

# 宏观/指数目录
python scripts/build_catalog.py
```

更新后重新构建前端以同步 `web/public/` → `static/`：

```bash
./scripts/build_web.sh
```

## Streamlit Community Cloud 部署

1. 将本仓库推送到 GitHub（**不要**提交 `.env`）
2. 在 [share.streamlit.io](https://share.streamlit.io) 新建 App
3. 配置：
   - **Main file path**: `streamlit_app.py`
   - **Requirements file**: `requirements.txt`
4. 确保仓库中已包含 `static/` 目录（执行过 `npm run build`）
5. 如需在云端定时刷新数据，请在 GitHub Actions 或本地更新后 push；Streamlit Cloud 不执行 `npm build`

### Secrets（Streamlit Secrets）

在线只读展示**不需要** API Key。若在云端运行数据拉取脚本，在 App Settings → Secrets 中配置：

```toml
FRED_API_KEY = "your_key"
# EIA_API_KEY = "optional"
```

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `FRED_API_KEY` | 拉取宏观/轮动数据时 | [FRED API](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `EIA_API_KEY` | 否 | EIA 能源序列；缺省使用 DEMO_KEY |

## 许可证

MIT
