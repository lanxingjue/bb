# 实盘部署指南

## 一、需要准备的东西

### 1.1 交易所账户

| 项目 | 推荐 | 说明 |
|------|------|------|
| 交易所 | **OKX** 或 **Binance** | 当前数据源以 OKX 为主 |
| 账户类型 | 合约账户 (futures) | 需要能做空、加杠杆 |
| 充值 | 至少 $200-500 USDT | 每笔 $200 × 3x 杠杆 = $600 名义价值 |

### 1.2 API Key

在交易所创建 API Key，需要以下权限：

| 权限 | 必需？ | 说明 |
|------|--------|------|
| 读取 (Read) | ✅ 必需 | 获取行情、持仓 |
| 交易 (Trade) | ✅ 必需 | 开仓/平仓 |
| 提现 (Withdraw) | ❌ 不要勾 | 安全考虑 |

> ⚠️ **安全建议**：API Key 只绑定交易功能，不要开通提现权限。

### 1.3 运行环境

| 项目 | 要求 |
|------|------|
| 服务器 | **VPS** 或长期开机的电脑 |
| 系统 | macOS / Linux |
| Python | 3.10+ |
| 网络 | 能连接交易所 API（可能需要代理） |

---

## 二、部署步骤

### 2.1 配置 API Key

编辑 `btc/config.json`，在 `exchange` 段添加 key 和 secret：

```json
{
  "exchange": {
    "name": "okx",
    "key": "YOUR_API_KEY_HERE",
    "secret": "YOUR_API_SECRET_HERE",
    "password": "YOUR_API_PASSPHRASE",  // OKX 需要，Binance 不需要
    "pair_whitelist": [
      "BTC/USDT:USDT",
      "ETH/USDT:USDT"
    ],
    "ccxt_config": {
      "options": {"defaultType": "swap"},
      "httpsProxy": "http://127.0.0.1:1087"
    }
  },
  "dry_run": true,
  "dry_run_wallet": 1000
}
```

### 2.2 测试连接

```bash
# 测试 API Key 是否有效
btc/freqtrade/.venv/bin/python3 -c "
import ccxt, json
with open('btc/config.json') as f:
    cfg = json.load(f)['exchange']
exchange = ccxt.okx({
    'apiKey': cfg['key'],
    'secret': cfg['secret'],
    'password': cfg['password'],
    'options': {'defaultType': 'swap'},
})
balance = exchange.fetch_balance()
total = balance['USDT']['total']
print(f'账户余额: {total} USDT')
print('✅ API 连接成功')
"
```

如果返回余额数字，说明 API Key 配置正确。

### 2.3 选择运行模式

#### 方案 A：用 Freqtrade 直接跑（推荐）

Freqtrade 内置了完整的实盘交易引擎：

```bash
# 创建 Freqtrade 实盘配置文件
cat > freqtrade_live.json << 'EOF'
{
  "max_open_trades": 3,
  "stake_currency": "USDT",
  "stake_amount": 200,
  "trading_mode": "futures",
  "margin_mode": "isolated",
  "dry_run": false,
  "exchange": {
    "name": "okx",
    "key": "YOUR_KEY",
    "secret": "YOUR_SECRET",
    "password": "YOUR_PASSPHRASE",
    "pair_whitelist": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
    "ccxt_config": {"options": {"defaultType": "swap"}}
  },
  "pairlists": [{"method": "StaticPairList"}],
  "telegram": {"enabled": false},
  "api_server": {"enabled": true, "listen_ip_address": "127.0.0.1", "listen_port": 8080},
  "initial_state": "running",
  "db_url": "sqlite:///tradesv3_live.sqlite"
}
EOF

# 运行实盘
btc/freqtrade/.venv/bin/freqtrade trade \
  --strategy ChanTheoryScalp \
  --config freqtrade_live.json
```

#### 方案 B：用当前模拟盘引擎改造

把 `papertrade.py` 的 `_process_entry()` 改成真实下单：

```python
# 伪代码示意
if cost + fee <= self.balance:
    # 改为真实下单
    exchange.create_market_order(
        symbol=pair,
        type='market',
        side='buy' if side == 'long' else 'sell',
        amount=size,
        params={'leverage': self.leverage}
    )
```

### 2.4 风控设置

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| 单笔仓位 | 10-15% | 实盘比模拟盘保守 |
| 最大持仓 | 2 笔 | 总暴露不超过 30% |
| 杠杆 | 2-3x | 不要超过 5x |
| 止损 | 1.5% | 从策略读取 |
| 初始资金 | $500 | 建议先用小资金验证 |

### 2.5 启动顺序

```bash
# 1. 启动实时数据更新器
btc/freqtrade/.venv/bin/python3 btc/scripts/realtime_updater.py

# 2. 启动后端（监控用）
btc/freqtrade/.venv/bin/python3 btc/backend/main.py

# 3. 启动前端（看盘用）
npm --prefix btc/frontend run dev

# 4. 启动 Freqtrade 实盘
btc/freqtrade/.venv/bin/freqtrade trade \
  --strategy ChanTheoryScalp \
  --config freqtrade_live.json

# 5. 打开前端查看
open http://localhost:3000
```

---

## 三、首次实盘建议

### 第一步：模拟盘跑一周
先用模拟盘观察策略在当前市场下的表现。

### 第二步：最小资金验证
用 **$100-200** 跑实盘，即使亏损也在可控范围。

### 第三步：观察出场逻辑
实盘中滑点、延迟会影响出场价格。观察策略的止损和止盈是否按预期触发。

### 第四步：逐步加仓
确认策略稳定后，逐步增加资金到目标规模。

---

## 四、风险提示

1. **回测不代表实盘** — 实盘有滑点、延迟、资金费率等额外成本
2. **杠杆放大亏损** — 3x 杠杆下 1.5% 止损对应 4.5% 本金亏损
3. **资金费率** — 永续合约每 8 小时收一次资金费，方向不对会持续扣费
4. **网络中断** — VPS 断网可能导致止损无法执行
5. **先小后大** — 建议首次实盘资金不超过 $500
