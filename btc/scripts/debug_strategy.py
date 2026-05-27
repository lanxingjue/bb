"""调试策略信号"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "freqtrade"))
import pandas as pd
import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "freqtrade" / "user_data" / "data" / "binance"

# 加载数据
df = pd.read_feather(DATA_DIR / "BTCUSDTUSDT-1h.feather")
df["date"] = pd.to_datetime(df["date"])
df.set_index("date", inplace=True)
print(f"数据范围: {df.index[0]} → {df.index[-1]}")
print(f"数据行数: {len(df)}")
print(f"列: {df.columns.tolist()}")
print(f"\n前5行:")
print(df.head())

# 导入策略
from freqtrade.resolvers.strategy_resolver import StrategyResolver

# 简单手动算 RSI 和 EMA
import talib.abstract as ta

close = df["close"].values
rsi = ta.RSI(pd.DataFrame({"close": close}), timeperiod=14)
ema_short = ta.EMA(pd.DataFrame({"close": close}), timeperiod=9)
ema_long = ta.EMA(pd.DataFrame({"close": close}), timeperiod=21)

df["rsi"] = rsi
df["ema_short"] = ema_short
df["ema_long"] = ema_long

# 检查 RSI 范围
print(f"\nRSI 统计:")
print(f"  min: {df['rsi'].min():.1f}")
print(f"  max: {df['rsi'].max():.1f}")
print(f"  mean: {df['rsi'].mean():.1f}")
print(f"  < 30 次数: {(df['rsi'] < 30).sum()}")
print(f"  > 70 次数: {(df['rsi'] > 70).sum()}")

# 检查 EMA 交叉
print(f"\nEMA 交叉:")
print(f"  ema_short > ema_long 次数: {(df['ema_short'] > df['ema_long']).sum()}")
print(f"  ema_short < ema_long 次数: {(df['ema_short'] < df['ema_long']).sum()}")

# 检查进入信号
buy_signal = (df['rsi'] < 30) & (df['ema_short'] > df['ema_long'])
sell_signal = (df['rsi'] > 70) & (df['ema_short'] < df['ema_long'])
print(f"\n买入信号次数: {buy_signal.sum()}")
print(f"卖出信号次数: {sell_signal.sum()}")

# 展示有信号的时段
if buy_signal.sum() > 0:
    print(f"\n买入信号示例:")
    print(df[buy_signal][["close", "rsi", "ema_short", "ema_long"]].head(10))
    print(f"...")
    print(f"时长: {df[buy_signal].index[0]} → {df[buy_signal].index[-1]}")

if sell_signal.sum() > 0:
    print(f"\n卖出信号示例:")
    print(df[sell_signal][["close", "rsi", "ema_short", "ema_long"]].head(10))
