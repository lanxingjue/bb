"""深入调试策略信号"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import talib.abstract as ta

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "freqtrade" / "user_data" / "data" / "binance"
sys.path.insert(0, str(BASE_DIR / "freqtrade"))

# 加载策略
from freqtrade.resolvers.strategy_resolver import StrategyResolver
# 手动加载
import importlib.util, inspect
strategy_path = BASE_DIR / "freqtrade" / "user_data" / "strategies" / "SampleStrategy.py"
spec = importlib.util.spec_from_file_location("SampleStrategy", strategy_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
StrategyClass = getattr(mod, "SampleStrategy")
strategy = StrategyClass(config={})

print(f"stratup_candle_count: {strategy.startup_candle_count}")
print(f"timeframe: {strategy.timeframe}")
print(f"buy_rsi: {strategy.buy_rsi.value}")
print(f"sell_rsi: {strategy.sell_rsi.value}")

# 加载 1h 数据
df = pd.read_feather(DATA_DIR / "BTCUSDTUSDT-1h.feather")
df["date"] = pd.to_datetime(df["date"])
df.set_index("date", inplace=True)

# 取一段数据
test_df = df.loc["2025-11-01":"2025-11-10"].copy()
print(f"\n测试数据: {len(test_df)} 行, 价格 {test_df['close'].min():.1f} - {test_df['close'].max():.1f}")

# 调用 populate_indicators
meta = {"pair": "BTC/USDT:USDT"}
result = strategy.populate_indicators(test_df.copy(), meta)
print(f"\n指标列: {result.columns.tolist()}")

# 检查 RSI
print(f"\nRSI 统计:")
print(f"  NaN 数: {result['rsi'].isna().sum()} / {len(result)}")
print(f"  范围: {result['rsi'].min():.1f} - {result['rsi'].max():.1f}")
print(f"  < 30: {(result['rsi'] < 30).sum()}")
print(f"  > 70: {(result['rsi'] > 70).sum()}")

# 检查信号
entry = strategy.populate_entry_trend(result.copy(), meta)
print(f"\nentry_trend 列: {entry.columns.tolist() if entry is not None else 'None'}")
if entry is not None and 'enter_long' in entry.columns:
    print(f"  enter_long 信号: {entry['enter_long'].sum()}")
    with_signals = entry[entry['enter_long'] == 1]
    if len(with_signals) > 0:
        print(f"  有信号的时段: {with_signals.index[0]} → {with_signals.index[-1]}")
        print(with_signals[['close','rsi','ema_short','ema_long']].head())
    else:
        print("  no enter_long signals found")
        # 检查具体值
        sample = entry[['close','rsi','ema_short','ema_long']].head(50)
        print(f"\n前 50 行数据:")
        print(sample)
