# 币圈策略回测系统

**Freqtrade 引擎 + 轻量回测 + Next.js Web UI + 12 个策略**

一键回测、可视化、AI 辅助、缠论/Z-Score/趋势跟踪，支持 5m~1d 多周期，现货+合约。

---

## 目录

- [环境要求](#环境要求)
- [快速启动（5 分钟）](#快速启动5-分钟)
- [下载真实数据](#下载真实数据)
- [Web UI 使用](#web-ui-使用)
- [策略列表](#策略列表)
- [项目结构](#项目结构)
- [常见问题](#常见问题)

---

## 环境要求

| 工具 | 版本要求 |
|------|---------|
| Python | 3.10+ |
| Node.js | 18+ |
| npm | 9+ |
| Git | 任意 |

---

## 快速启动（5 分钟）

### 1. 克隆项目

```bash
git clone https://github.com/lanxingjue/bb.git
cd bb
```

### 2. 配置 Freqtrade 引擎（核心回测引擎）

```bash
cd btc/freqtrade
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
cd ../..
```

### 3. 安装前端依赖

```bash
npm --prefix btc/frontend install
```

### 4. 生成模拟数据（无代理时）

```bash
cd btc
source freqtrade/.venv/bin/activate
python scripts/generate_data.py
```

模拟数据包含：BTC/ETH/SOL/BNB 四个交易对，1m/5m/15m/1h/4h/1d 六种粒度，90-360 天。

### 5. 启动系统

开两个终端：

```bash
# 终端 1: 后端 API（端口 8765）
cd btc && source freqtrade/.venv/bin/activate && python backend/main.py

# 终端 2: 前端 Web UI（端口 3000）
cd btc && npm --prefix frontend run dev
```

打开浏览器访问 **http://localhost:3000**

---

## 下载真实数据

数据默认使用模拟数据（随机生成的价格曲线）。如需真实 OKX/Bybit 数据：

### 有代理（Shadowsocks/V2Ray）

```bash
cd btc
source freqtrade/.venv/bin/activate

# 设代理
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087

# 自动下载（先测网络，再下载）
python scripts/download_real_data.py

# 或快速版（跳过 1m 细粒度，节省时间）
python scripts/download_fast.py
```

### 无代理

```bash
cd btc
source freqtrade/.venv/bin/activate
python scripts/download_fallback.py   # 从 CoinGecko 下载
```

CoinGecko 只有 1d 数据，但可以用来验证系统跑通。

### 切换交易所

修改 `btc/config.json` 中的 `exchange.name`：

```json
"exchange": {
    "name": "okx",     # 可选: okx / bybit / binance
    ...
}
```

---

## Web UI 使用

### 回测页面

左侧参数面板，可配置：

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| 策略 | 选择策略 | 见下方策略列表 |
| 交易对 | BTC/ETH/SOL/BNB | 1-2 个 |
| 时间粒度 | 1m/5m/15m/1h/4h/1d | 短线用 5-15m |
| 时间范围 | 7/30/90 天 | 至少 30 天 |
| 本金 | 初始资金 | 1000 |
| 每笔投入 | 每笔交易金额 | 10-50% 本金 |
| 杠杆 | 倍率 | 1-10x |
| 费率 | 交易所手续费 | 0.04(吃单)/0.02(做市) |
| 最大持仓 | 同时持仓数 | 2-3 |
| 滑点 | 额外成本 | 0.05 |

### 策略库

顶部导航「策略库」Tab，展示 12 个策略，点「使用此策略」自动跳转回测面板。

### 策略编辑器

顶部导航「策略」Tab，在线修改 Python 策略代码，保存后即生效。

---

## 策略列表

| 策略 | 周期 | 核心逻辑 | 预期胜率 |
|------|------|---------|---------|
| **ZScorePro** 🏆 | 5m | Z-Score 均值回归 + 10x杠杆 | 52% |
| **ChanTheoryStrategy** 🏆 | 15m | 缠论第三类买卖点 + MACD过滤 | 41% |
| VwapReversionStrategy | 5m | VWAP 均值回归 | 51% |
| MacdStrategy | 1h | MACD 金叉死叉 | 50%+ |
| EmaCrossStrategy | 1h | EMA9/21 金叉死叉 | 45%+ |
| BollingerStrategy | 1h | 布林带均值回归 | 55%+ |
| SupertrendStrategy | 1h | 超级趋势跟踪 | 45%+ |
| CandlestickPatternStrategy | 5m | K 线形态识别 | 40%+ |
| VegasStrategy | 5m | 维加斯通道 | 45%+ |
| MacdDivergenceStrategy | 1m | MACD 背离 | 35%+ |
| TimeStrategy | 5m | 特定时段交易 | 45%+ |
| AggressiveMomentumStrategy | 1h | 激进趋势跟踪 | 40%+ |

### 推荐配置

**缠论（推荐，不需要做市费率）**
```
策略: ChanTheoryStrategy
周期: 15m · 杠杆: 5x · 每笔: $200 · 费率: 0.04
```

**Z-Score PRO（需做市费率 0.02%）**
```
策略: ZScorePro
周期: 5m · 杠杆: 10x · 每笔: $500 · 费率: 0.02
```

---

## 项目结构

```
bb/
├── btc/
│   ├── backend/
│   │   ├── main.py               # FastAPI 后端 (端口 8765)
│   │   ├── backtest_engine.py     # 轻量回测引擎
│   │   └── results/               # 回测结果 JSON
│   ├── frontend/
│   │   └── src/app/page.tsx       # React 主页面
│   ├── freqtrade/                 # Freqtrade 引擎
│   │   └── user_data/
│   │       ├── strategies/        # 策略 Python 文件
│   │       └── data/okx/          # K 线数据 feather 格式
│   ├── scripts/                   # 工具脚本
│   │   ├── generate_data.py       # 模拟数据生成
│   │   ├── download_real_data.py  # 真实数据下载(有代理)
│   │   ├── download_fast.py       # 快速下载(跳过细粒度)
│   │   ├── download_fallback.py   # CoinGecko 备用
│   │   └── check_network.py       # 网络检测
│   ├── config.json                # 交易所配置
│   └── README.md
```

---

## 自动数据更新

系统支持每 4 小时自动更新 K 线数据，确保回测始终使用最新行情。

### 安装定时任务（macOS）

```bash
bash btc/scripts/install_updater.sh
```

安装后会自动每 4 小时运行 `scripts/auto_updater.py`，增量下载最新数据。

### 手动运行一次

```bash
cd btc && source freqtrade/.venv/bin/activate
python scripts/auto_updater.py
```

### 后台持续运行

```bash
cd btc && source freqtrade/.venv/bin/activate
nohup python scripts/auto_updater.py --daemon &
```

---

## 常见问题

**Q: 没有网络/被墙，怎么用？**
先用 `python scripts/generate_data.py` 生成模拟数据，系统完全可离线运行。

**Q: 策略回测结果不稳定？**
30 天数据不够，建议下载 365 天完整数据。5m/15m 数据越长时间范围越可靠。

**Q: 为什么 Z-Score 和缠论结果不一样？**
Z-Score 对日期范围敏感（30 天内收益从 +1% 到 +27%），缠论更稳定。
建议选缠论做主要策略。

**Q: 如何加新策略？**
在 `freqtrade/user_data/strategies/` 下创建 `.py` 文件，继承 `IStrategy`。
刷新页面后自动出现在策略库和回测面板中。

**Q: 报错 "Markets were not loaded"？**
交易所 API 连接失败。检查网络/代理，或切换到模拟数据：
```bash
python scripts/generate_data.py
```

---

## 技术栈

| 组件 | 用途 |
|------|------|
| Freqtrade | 回测引擎（pip install -e .） |
| FastAPI | Python 后端 API |
| Next.js | React 前端框架 |
| TradingView Lightweight Charts | K 线图 |
| TailwindCSS | UI 样式 |
| shadcn/ui | UI 组件库 |
| TA-Lib | 技术指标计算 |
| Pandas/NumPy | 数据处理 |

---

## 许可

MIT
