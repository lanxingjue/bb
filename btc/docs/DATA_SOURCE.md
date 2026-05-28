# 模拟盘系统 — 数据源与实时更新文档

## 一、交易所数据源

### 1.1 支持的交易所

| 交易所 | proxy 状态 | 可用性 |
|--------|-----------|--------|
| OKX | SOCKS5 127.0.0.1:1086 | ✅ 可用 |
| Binance | SOCKS5 127.0.0.1:1086 | ✅ 可用 |
| Bybit | SOCKS5 127.0.0.1:1086 | ✅ 可用 |

### 1.2 代理配置

```python
# SOCKS5 代理（推荐，交易所不屏蔽）
socks.set_default_proxy(socks.SOCKS5, '127.0.0.1', 1086)
socket.socket = socks.socksocket

# HTTP 代理（交易所返回 403/451，已弃用）
http_proxy = 'http://127.0.0.1:1087'  # ❌ 被屏蔽
```

环境变量方式：
```bash
all_proxy=socks5://127.0.0.1:1086  btc/freqtrade/.venv/bin/python3 script.py
```

### 1.3 交易对名称映射

| 统一格式 (freqtrade) | OKX instId | Binance symbol |
|---------------------|------------|----------------|
| `BTC/USDT:USDT` | `BTC-USDT-SWAP` | `BTCUSDT` (合约) |
| `ETH/USDT:USDT` | `ETH-USDT-SWAP` | `ETHUSDT` |
| `SOL/USDT:USDT` | `SOL-USDT-SWAP` | `SOLUSDT` |
| `BNB/USDT:USDT` | `BNB-USDT-SWAP` | `BNBUSDT` |

---

## 二、K 线数据 (OHLCV)

### 2.1 OKX API 接口

```
GET https://www.okx.com/api/v5/market/candles
  ?instId=BTC-USDT-SWAP
  &bar=1m
  &limit=3
```

**返回格式**：
```json
{
  "code": "0",
  "data": [
    ["ts", "o", "h", "l", "c", "vol", "volCcy", "volCcyQuote", "confirm"],
    ["1779965820000", "73414.5", "73414.5", "73414.5", "73414.5", "4.99", "0.0499", "3663.38", "0"]
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| ts | int64 | Unix 毫秒时间戳 |
| o/h/l/c | string | 开盘/最高/最低/收盘价 |
| vol | string | 成交量（合约数） |
| volCcy | string | 币种成交量 |
| volCcyQuote | string | 计价货币成交量 |
| **confirm** | **string** | **"0"=未确认, "1"=已确认** |

### 2.2 关键：`confirm` 字段

```
confirm=0 → K 线还在形成中，价格可能变化
confirm=1 → K 线已完成，价格已锁定
```

**只处理 `confirm=1` 的 K 线**，避免使用未完成的数据。

### 2.3 更新频率

| 粒度 | 更新频率 | 确认延迟 |
|------|---------|---------|
| 1m | 每 1 分钟 | < 2 秒 |
| 5m | 每 5 分钟 | < 2 秒 |
| 15m | 每 15 分钟 | < 5 秒 |
| 1h | 每 1 小时 | < 10 秒 |

### 2.4 API 限频

| 端点 | 限频 |
|------|------|
| `/market/candles` | 20 次 / 2 秒 |
| `/public/time` | 10 次 / 2 秒 |

每 60 秒拉 2 个交易对 × 2 个时间粒度 = 4 次请求，远低于限频。

---

## 三、数据存储 (Feather)

### 3.1 文件位置

```
btc/freqtrade/user_data/data/
├── okx/
│   ├── BTCUSDTUSDT-1m.feather      # 1m K 线
│   ├── BTCUSDTUSDT-5m.feather      # 5m K 线
│   ├── BTCUSDTUSDT-1h.feather      # 1h K 线
│   ├── ETHUSDTUSDT-1m.feather
│   ├── ETHUSDTUSDT-5m.feather
│   └── futures/                     # OKX 合约原始数据
│       ├── BTC_USDT_USDT-1m-futures.feather
│       └── ...
├── binance/                         # 备用数据源
└── bybit/
```

### 3.2 Feather 格式

```python
# 读取
df = pd.read_feather(fp)
df["date"] = pd.to_datetime(df["date"])
df.set_index("date", inplace=True)

# 写入
df.to_feather(fp)
```

| 列 | 类型 | 说明 |
|------|------|------|
| date | datetime64[ns] UTC | K 线开盘时间 |
| open | float64 | 开盘价 |
| high | float64 | 最高价 |
| low | float64 | 最低价 |
| close | float64 | 收盘价 |
| volume | float64 | 成交量 |

### 3.3 文件名命名规则

```
输入: BTC/USDT:USDT
处理: pair.replace("/", "").replace(":", "") → BTCUSDTUSDT
文件: BTCUSDTUSDT-{timeframe}.feather

futures 目录则是:
输入: BTC-USDT-SWAP
文件: BTC_USDT_USDT-{timeframe}-futures.feather
```

---

## 四、实时数据链路

### 4.1 完整数据流

```
┌─────────────────────────────────────────────────────────────┐
│  OKX 交易所                                                  │
│  GET /api/v5/market/candles?instId=BTC-USDT-SWAP&bar=1m    │
│  → confirm=1 的 K 线                                        │
└─────────────────────┬───────────────────────────────────────┘
                      │ SOCKS5 127.0.0.1:1086
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  realtime_updater.py (job 91)                               │
│  每 60 秒:                                                   │
│    1. fetch_latest() → OKX API (850ms)                      │
│    2. 过滤 confirm=1                                         │
│    3. append_to_feather() → feather 文件 (<10ms)            │
│  文件: btc/scripts/realtime_updater.py                      │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  PaperTradingEngine._check_new_data()                       │
│  每 10 秒:                                                   │
│    1. pd.read_feather() 加载最新数据                          │
│    2. 对比 _last_bar[pair] 发现新 bar                         │
│    3. populate_indicators() + 逐 bar 模拟交易                │
│  文件: btc/backend/papertrade.py                             │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI /api/papertrade/status                              │
│  → JSON: {balance, equity, paired_trades[], equity_curve[]} │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  前端 PaperTradePanel (React)                                │
│  每 5 秒轮询 → 更新图表/交易记录                               │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 延迟分析

| 环节 | 耗时 | 说明 |
|------|------|------|
| OKX 确认 K 线 | 1-2s | 每分钟结束后立即确认 |
| realtime_updater 检测间隔 | 0-60s | 平均 30s |
| API 请求 + 写入 | ~1s | SOCKS5 代理 |
| 模拟盘检测间隔 | 0-10s | 平均 5s |
| **总延迟** | **~40-75s** | 从实盘到模拟盘响应 |

### 4.3 数据新鲜度验证

```bash
# 查看 feather 最新时间
python3 -c "
import pandas as pd
df = pd.read_feather('btc/freqtrade/user_data/data/okx/BTCUSDTUSDT-1m.feather')
print(f'最新K线: {df.date.max()}')
print(f'延迟: {(pd.Timestamp.now(tz=\"UTC\") - df.date.max()).total_seconds():.0f}秒')
"
```

---

## 五、更新器脚本

### 5.1 `realtime_updater.py` — 实时更新器

| 属性 | 值 |
|------|-----|
| 文件 | `btc/scripts/realtime_updater.py` |
| 频率 | 每 60 秒 |
| 数据源 | OKX REST API (SOCKS5) |
| 监控对 | BTC/USDT:USDT, ETH/USDT:USDT |
| 监控粒度 | 1m, 5m |
| 启动 | `btc/freqtrade/.venv/bin/python3 btc/scripts/realtime_updater.py` |
| 依赖 | `pysocks`, `pandas`, `pyarrow` |

核心逻辑：
```python
# 1. 取最新 3 根 K 线
candles = fetch_latest("BTC-USDT-SWAP", "1m", limit=3)

# 2. 只处理已确认的
confirmed = [c for c in candles if c[8] == "1"]

# 3. 追加到 feather
append_to_feather("BTCUSDTUSDT", "1m", confirmed)
```

### 5.2 `auto_updater.py` — 批量更新器

| 属性 | 值 |
|------|-----|
| 文件 | `btc/scripts/auto_updater.py` |
| 频率 | 每 4 小时 |
| 数据源 | Freqtrade download-data (SOCKS5) |
| 监控对 | 全部 4 个交易对 |
| 监控粒度 | 1m/5m/15m(3天), 1h/4h/1d(30天) |
| 启动 | `btc/freqtrade/.venv/bin/python3 btc/scripts/auto_updater.py --daemon` |

---

## 六、配置项

### 6.1 `config.json`（交易所配置）

```json
{
  "exchange": {
    "name": "okx",
    "pair_whitelist": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
    "ccxt_config": {
      "options": {"defaultType": "swap"},
      "httpsProxy": "http://127.0.0.1:1087"
    }
  },
  "dry_run": true,
  "dry_run_wallet": 1000
}
```

### 6.2 模拟盘启动配置

```bash
curl -X POST http://127.0.0.1:8765/api/papertrade/start \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "ChanTheoryScalp",
    "pairs": ["BTC/USDT:USDT"],
    "timeframe": "1m",
    "leverage": 3.0,
    "fee": 0.0004,
    "slippage": 0.0015,
    "position_pct": 25.0,
    "max_positions": 2,
    "initial_balance": 1000.0
  }'
```

---

## 七、启动顺序

```bash
# 1. 后端 API (必须最先启动)
btc/freqtrade/.venv/bin/python3 btc/backend/main.py

# 2. 前端
npm --prefix btc/frontend run dev

# 3. 实时 K 线更新器 (每60秒拉最新数据)
btc/freqtrade/.venv/bin/python3 btc/scripts/realtime_updater.py

# 4. 模拟盘 (通过 API 启动)
curl -X POST http://127.0.0.1:8765/api/papertrade/start \
  -H "Content-Type: application/json" \
  -d '{"strategy":"ChanTheoryScalp","pairs":["BTC/USDT:USDT"],"timeframe":"1m","leverage":3}'

# 可选：批量数据更新器 (每4小时补充历史数据)
all_proxy=socks5://127.0.0.1:1086 \
  btc/freqtrade/.venv/bin/python3 btc/scripts/auto_updater.py --daemon
```

---

## 八、故障排查

### 8.1 数据不是最新的

```bash
# 检查最新 K 线时间
python3 -c "
import pandas as pd
df = pd.read_feather('btc/freqtrade/user_data/data/okx/BTCUSDTUSDT-1m.feather')
print(f'最新: {df.date.max()}')
"

# 检查实时更新器是否在运行
ps aux | grep realtime_updater

# 手动拉一次测试
python3 -c "
import socks, socket, urllib.request, json
socks.set_default_proxy(socks.SOCKS5, '127.0.0.1', 1086)
socket.socket = socks.socksocket
r = urllib.request.urlopen('https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=1m&limit=1', timeout=10)
data = json.loads(r.read())
print(data)
"
```

### 8.2 模拟盘没有新交易

```bash
# 检查模拟盘状态
curl http://127.0.0.1:8765/api/papertrade/status | python3 -m json.tool

# 检查后端日志是否有错误
# 查看 job 92 的输出

# 重启模拟盘
curl -X POST http://127.0.0.1:8765/api/papertrade/stop
curl -X POST http://127.0.0.1:8765/api/papertrade/start ...
```

### 8.3 代理不工作

```bash
# 测试 SOCKS5 代理
python3 -c "
import socks, socket
socks.set_default_proxy(socks.SOCKS5, '127.0.0.1', 1086)
socket.socket = socks.socksocket
import urllib.request
r = urllib.request.urlopen('https://api.binance.com/api/v3/ping', timeout=5)
print(f'状态: {r.status}')
"
```
