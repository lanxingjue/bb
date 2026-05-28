# 模拟盘系统 — 数据流转文档

## 系统架构总览

```
auto_updater.py (数据采集)
     ↓ feather 文件
PaperTradingEngine (模拟交易引擎)
     ↓ 状态 API
FastAPI (main.py)
     ↓ JSON
PaperTradePanel (前端 React)
```

---

## ① 数据层：auto_updater.py

### 位置
`btc/scripts/auto_updater.py`

### 功能
通过 Freqtrade CLI 调用 `freqtrade download-data` 从 **OKX 交易所** 下载 K 线数据。

### 运行方式
```bash
# 单次运行
btc/freqtrade/.venv/bin/python3 scripts/auto_updater.py

# 后台守护（每4小时自动运行）
btc/freqtrade/.venv/bin/python3 scripts/auto_updater.py --daemon
```

### 下载内容
| 粒度 | 每次下载天数 | 用途 |
|------|-------------|------|
| 1m / 5m / 15m | 最新 3 天 | 超短线策略 |
| 1h / 4h / 1d | 最新 30 天 | 中长线策略 |

### 存储位置
`btc/freqtrade/user_data/data/okx/`

### 文件格式
Feather 文件（Apache Arrow 列式格式），6 列：

| 列名 | 类型 | 说明 |
|------|------|------|
| `date` | datetime64[ns] UTC | K 线开盘时间 |
| `open` | float64 | 开盘价 |
| `high` | float64 | 最高价 |
| `low` | float64 | 最低价 |
| `close` | float64 | 收盘价 |
| `volume` | float64 | 成交量 |

### 文件名命名规则
```
{交易对标识}-{时间粒度}.feather

交易对标识：将 / 和 : 替换为空
  例：BTC/USDT:USDT → BTCUSDTUSDT
  例：ETH/USDT → ETHUSDT

时间粒度：1m / 5m / 15m / 1h / 4h / 1d
```

### 数据目录自动发现
`backtest_engine.py` 按优先级搜索：
```
okx → bybit → binance
```
取第一个存在 `.feather` 文件的目录作为 `DATA_DIR`。

---

## ② 加载层：PaperTradingEngine

### 位置
`btc/backend/papertrade.py`

### 启动入口
```python
POST /api/papertrade/start  →  PaperTradingEngine.start(config)
  → 重置状态（清空持仓/交易记录）
  → 启动后台线程 _loop()
```

### 主循环 `_loop()`
```python
while running:
    self._tick()         # 检查新数据并运行策略
    time.sleep(60)       # 每分钟 tick 一次
```

### 一次 Tick 流程 `_tick()`
```
for each pair in self.pairs:
    _process_pair(pair)
```

### 处理单个交易对 `_process_pair(pair)`
```python
1. 加载数据
   pd.read_feather(fp) → df.set_index("date")
   df.tail(load_bars)   # 1m=5000, 5m=2000, 1h=1000

2. 增量检测
   last_processed = self._last_bar_times.get(pair)
   if last_processed:
       new_bars = df[df.index > last_processed]  # 只处理新 bar
   else:
       new_bars = df.tail(n)  # 首次运行处理全部

3. 加载策略（缓存）
   if not self._strat_cache:
       self._strat_cache = load_strategy(strategy_name)

4. 运行策略信号
   df2 = strat.populate_indicators(df.copy(), meta)
   df2 = strat.populate_entry_trend(df2, meta)
   df2 = strat.populate_exit_trend(df2, meta)

5. 逐 K 线执行交易
   for idx in new_bars.index:
       row = df2.loc[idx]
       
       # 入场检查
       if pair not in positions and enter_long/short:
           entry()  # 扣保证金，开仓
       
       # 出场检查
       if pair in positions:
           ① exit_long/short == 1  → 信号出场（背驰）
           ② stoploss 触发         → 止损
           ③ trailing_stop 触发     → 移动止盈
           ④ minimal_roi 触发       → 止盈
       
       # 更新权益曲线
       update equity_curve

6. 记录最后处理时间
   self._last_bar_times[pair] = df.index[-1]
```

---

## ③ 策略层：populate_indicators

### 位置
`btc/freqtrade/user_data/strategies/ChanTheoryScalp.py`

### 三阶段信号生成

| 阶段 | 产出 | 说明 |
|------|------|------|
| 基础指标 | EMA50/200, ATR, MACD, RSI, vol_ratio | TA-Lib 标准指标 |
| 缠论结构 | strokes, pivots | 包含处理→分型→笔→中枢 |
| 入场信号 | enter_long/short = 1/0 | 1买/1卖（中枢外突破） |
| 出场信号 | exit_long/short = 1/0 | 背驰（隔笔力度≤60%） |

### 缠论算法流程
```
原始 high/low 数组
  → 包含处理（相邻K线合并）
  → 分型识别（顶分型/底分型，左右各3根）
  → 笔连接（顶→底，min_stroke_len=6）
  → 中枢构建（连续3笔重叠区，zh=次高，zl=次低）
```

### 信号生成条件

| 信号 | 条件 | 说明 |
|------|------|------|
| 1买 | 下跌笔结束 + 中枢下方 + EMA50升势 + vol_ok | 趋势背驰买点 |
| 1卖 | 上涨笔结束 + 中枢上方 + EMA50降势 + vol_ok | 趋势背驰卖点 |

### 走势分类（方向五）
`classify_market()` 用中枢移动方向判断市场状态：
- `trend_up`：只做多
- `trend_down`：只做空
- `range`：双向

### 背驰出场（方向四）
隔笔同向比较：当前笔幅度 < 前同向笔 × 60% → 趋势衰竭 → 出场

---

## ④ 交易模拟层

### 风控参数来源
从策略类属性读取（非硬编码）：

| 参数 | 策略属性 | ChanTheoryScalp 值 |
|------|---------|-------------------|
| stoploss | `strat.stoploss` | -1.5% |
| trailing_stop_positive | `strat.trailing_stop_positive` | 0.8% |
| trailing_stop_positive_offset | `strat.trailing_stop_positive_offset` | 3.0% |
| minimal_roi | `strat.minimal_roi` | 阶梯止盈 |

### 滑点处理
```
入场做多:  price = close × (1 + slippage)
入场做空:  price = close × (1 - slippage)
出场做多:  price = close × (1 - slippage)
出场做空:  price = close × (1 + slippage)
```

滑点默认 0.15%（1m 适用）。

### 仓位计算
```
trade_amount = balance × position_pct / 100
size = trade_amount / entry_price
notional = cost × leverage
```

---

## ⑤ API 层

### 位置
`btc/backend/main.py`

### 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/papertrade/start` | POST | 启动模拟盘 |
| `/api/papertrade/status` | GET | 获取状态 |
| `/api/papertrade/stop` | POST | 停止模拟盘 |

### `GET /api/papertrade/status` 返回字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `running` | bool | 运行中 |
| `balance` | float | 余额 |
| `equity` | float | 权益（含浮动盈亏） |
| `open_positions` | int | 持仓数 |
| `total_trades` | int | 已平仓数 |
| `positions[]` | array | 当前持仓明细 |
| `trades[]` | array | 原始 entry/exit 记录 |
| `paired_trades[]` | array | entry+exit 配对交易 |
| `equity_curve[]` | array | 权益序列（500个点） |
| `signal_log[]` | array | 最近30条信号 |
| `config` | object | 当前配置 |

### 线程安全
所有状态操作持有 `self._lock`（threading.Lock）。

---

## ⑥ 前端层：PaperTradePanel

### 位置
`btc/frontend/src/app/page.tsx`（`function PaperTradePanel`）

### 数据轮询
```
挂载 → fetchStatus()
if running → setInterval(fetchStatus, 5000ms)
```

### 用户操作链
```
点击「▶ 启动」
  → POST /api/papertrade/start { strategy, pairs, ... }
  → 等待 5 秒
  → fetchStatus() 刷新

点击「⏹ 停止」
  → POST /api/papertrade/stop
  → setRunning(false) → 定时器清除

点击「🔄 刷新」
  → fetchStatus() 立即拉取
```

### UI 组件

| 区域 | 数据来源 | 渲染 |
|------|---------|------|
| 策略选择 | 策略列表 API | 下拉框 |
| 统计卡片 | `equity`, `paired_trades` | 7 格网格 |
| 权益曲线 | `equity_curve[]` | lightweight-charts LineSeries |
| 信号分组 | `paired_trades[].enter_tag` | 网格卡片 |
| 当前持仓 | `positions[]` | 表格 |
| 交易记录 | `paired_trades[]` | 卡片列表 |
| 最佳/最差 | `paired_trades` 排序 | 独立卡片 |

---

## 完整数据流图

```
┌─────────────────────────────────────────────────────────────┐
│  auto_updater.py (每4h)                                     │
│  → OKX API → feather 文件                                   │
│  → btc/.../data/okx/{Pair}-{TF}.feather                     │
└─────────────────────┬───────────────────────────────────────┘
                      ↓
┌─────────────────────┴───────────────────────────────────────┐
│  PaperTradingEngine._process_pair()                         │
│  ① pd.read_feather() → df.tail(N)                          │
│  ② _strat_cache.populate_indicators(df)                    │
│     → TA-Lib 指标 → 缠论结构 → 入场/出场信号                │
│  ③ 逐K线循环 → entry() / exit()                             │
│     → trades[] / equity_curve[]                             │
└─────────────────────┬───────────────────────────────────────┘
                      ↓
┌─────────────────────┴───────────────────────────────────────┐
│  FastAPI /api/papertrade/status                             │
│  → JSON: {balance, equity, pairs_trades[], equity_curve[]}  │
└─────────────────────┬───────────────────────────────────────┘
                      ↓
┌─────────────────────┴───────────────────────────────────────┐
│  PaperTradePanel (React, 轮询5s)                           │
│  → 统计卡片 / 权益曲线 / 持仓表 / 交易记录卡片               │
└─────────────────────────────────────────────────────────────┘
```
