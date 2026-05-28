# 缠论策略交易系统

基于缠中说禅理论的自动化交易系统，支持回测、模拟盘和实盘交易。

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│  实时数据 (OKX API)                                   │
│  ↓ SOCKS5 代理                                       │
│  realtime_updater (60s) → feather 文件               │
│  ↓                                                   │
│  模拟盘引擎 (同步时间轴, 多币种)                       │
│  ↓                                                   │
│  FastAPI → 前端 (React + lightweight-charts)         │
└─────────────────────────────────────────────────────┘
```

## 策略

### RealChanTheory (1h 中长线)
- 完整缠论算法：包含处理→分型→笔→中枢→买卖点
- 1买/1卖 + 3买/3卖 + 走势分类 + 背驰出场
- 11个月回测: 60笔, 66.7%胜率, +28.4%, 夏普3.21

### ChanTheoryScalp (5m/1m 超短线)
- 基于 RealChanTheory 核心逻辑，针对短周期优化
- 仅 1买/1卖（中枢外突破，3买已禁用）
- 自适应 EMA/ATR 参数
- 1m 回测(3个月): 389笔, 54.5%胜率, +89.9%, 夏普6.85

## 功能

| 功能 | 说明 |
|------|------|
| **回测** | 全周期历史回测，含权益曲线/交易明细/指标面板 |
| **模拟盘** | 多币种同步时间轴，动态仓位，实时数据更新 |
| **诊断** | 按买卖点/币种/出场原因分组分析 |
| **数据更新** | SOCKS5 代理自动拉取 OKX 最新 K 线 |

## 快速开始

```bash
# 1. 后端
btc/freqtrade/.venv/bin/python3 btc/backend/main.py

# 2. 前端
npm --prefix btc/frontend run dev

# 3. 实时数据更新器
btc/freqtrade/.venv/bin/python3 btc/scripts/realtime_updater.py

# 4. 启动模拟盘
curl -X POST http://127.0.0.1:8765/api/papertrade/start \
  -H "Content-Type: application/json" \
  -d '{"strategy":"ChanTheoryScalp","pairs":["BTC/USDT:USDT","ETH/USDT:USDT"],"timeframe":"1h","leverage":3}'

# 5. 打开浏览器
open http://localhost:3000
```

## 配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 杠杆 | 3x | 合约杠杆倍数 |
| 费率 | 0.04% | 吃单费率 |
| 滑点 | 0.15% | 模拟滑点 |
| 仓位 | 动态(30%/20%/15%/10%) | 按持仓数递减 |
| 最大持仓 | 3笔 | 同时持仓上限 |
| 止损 | 1.5% | 策略读取 |
| 追踪止盈 | 0.8%回撤/3%触发 | 策略读取 |

## 数据

| 时间粒度 | 数据源 | 覆盖范围 |
|---------|--------|---------|
| 1m | OKX 合约 | 近3天 (实时更新) |
| 5m | OKX 合约 | 近3天 (实时更新) |
| 1h | OKX 合约 | 2022-2026 (4年) |
| 代理 | SOCKS5 127.0.0.1:1086 | 通过 `all_proxy` 环境变量 |

## 文档

| 文件 | 内容 |
|------|------|
| `btc/docs/CHAN_THEORY_STRATEGY.md` | 策略算法和回测数据 |
| `btc/docs/PAPER_TRADE_FLOW.md` | 模拟盘数据流转 |
| `btc/docs/DATA_SOURCE.md` | 数据源和实时更新 |
| `btc/docs/LIVE_TRADING.md` | 实盘部署指南 |

## 关键技术决策

1. **同步时间轴** — 多币种模拟盘按统一时间戳推进，防止前视偏差
2. **出场顺序** — 止损 > 移动止盈 > 结构出场 > ROI，优先保护本金
3. **动态仓位** — 持仓越多单笔越小，总暴露不超过50%
4. **SOCKS5 代理** — HTTP代理被交易所屏蔽，SOCKS5 正常工作
5. **Feather 存储** — Apache Arrow 列式格式，读写速度快
