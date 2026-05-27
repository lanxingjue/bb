# 策略回测系统 — Crypto Strategy Backtest

基于 Freqtrade 引擎 + Next.js 前端的加密货币策略回测与 AI 策略迭代系统。

## 快速启动

```bash
# 1. 启动后端 API
btc/freqtrade/.venv/bin/python btc/backend/main.py

# 2. 启动前端（另一个终端）
npm --prefix btc/frontend run dev

# 3. 打开浏览器
open http://localhost:3000
```

## 系统架构

```
你（对话优化策略）←→ 我 → 编辑策略文件 → 运行回测 → Web UI 看结果
                                ↓
                         FastAPI 后端 (:8765)
                                ↓
                    轻量回测引擎 / Freqtrade
                                ↓
                    Binance / Hyperliquid / 模拟数据
```

## 目录结构

```
btc/
├── backend/
│   ├── main.py                # FastAPI 后端 API
│   ├── backtest_engine.py     # 轻量回测引擎
│   └── results/               # 回测结果 JSON
├── frontend/
│   └── src/app/page.tsx       # React 主页面
├── freqtrade/
│   └── user_data/
│       ├── strategies/        # 策略文件（可编辑）
│       │   ├── TestStrategy.py
│       │   ├── SampleStrategy.py
│       │   └── AIStrategy.py  # AI 策略模板
│       └── data/binance/      # K 线数据
├── scripts/
│   └── generate_data.py       # 模拟数据生成器
├── config.json                # 回测配置
└── docker-compose.yml         # 一键启动
```

## 策略开发

策略是 Python 文件，放在 `freqtrade/user_data/strategies/` 下。
兼容 Freqtrade CLI 和本系统的轻量引擎。

1. 在 Web UI 的「策略」标签编辑策略
2. 切回「回测」标签，选策略 → 点运行
3. K 线图上看到买卖标记，下方看 P&L 指标

## AI 策略

`AIStrategy.py` 支持调用 LLM (OpenAI/Claude) 辅助判断信号：

```bash
export AI_PROVIDER=openai
export OPENAI_API_KEY=sk-xxx
# 或
export AI_PROVIDER=claude
export CLAUDE_API_KEY=sk-ant-xxx
```

AI 不可用时自动回退到纯技术指标策略。

## 数据

默认使用模拟数据（360 天，BTC/ETH/SOL）。
如需真实数据，在能访问 Binance 的环境下运行：

```bash
freqtrade download-data --exchange binance --trading-mode futures \
  --pairs BTC/USDT:USDT ETH/USDT:USDT --timeframes 1m 5m 1h 1d --days 365
```
