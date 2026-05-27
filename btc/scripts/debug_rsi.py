"""调试 RSI 计算"""
import pandas as pd
import numpy as np
import talib.abstract as ta

DATA_DIR = "/Users/wangerde/code/btc/btc/freqtrade/user_data/data/binance"

df = pd.read_feather(f"{DATA_DIR}/BTCUSDTUSDT-1h.feather")
df["date"] = pd.to_datetime(df["date"])
df.set_index("date", inplace=True)

c = df["close"].values[:100]

# 手动算 RSI
def calc_rsi(prices, period=14):
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.zeros(len(prices))
    avg_loss = np.zeros(len(prices))
    avg_gain[period] = np.mean(gains[:period])
    avg_loss[period] = np.mean(losses[:period])
    for i in range(period + 1, len(prices)):
        avg_gain[i] = (avg_gain[i-1] * (period - 1) + gains[i-1]) / period
        avg_loss[i] = (avg_loss[i-1] * (period - 1) + losses[i-1]) / period
    rs = avg_gain / np.where(avg_loss == 0, 0.001, avg_loss)
    rsi = 100 - (100 / (1 + rs))
    return rsi

rsi = calc_rsi(c)
print("前 30 个 RSI 值 (非 NaN):")
valid = rsi[~np.isnan(rsi)]
print(valid[:20])
print(f"\n非 NaN 总数: {len(valid)}")
print(f"< 30: {np.sum(valid < 30)}")
print(f"> 70: {np.sum(valid > 70)}")

# 也检查一下价格范围
print(f"\n价格范围: {df['close'].min():.2f} - {df['close'].max():.2f}")
print(f"价格均值: {df['close'].mean():.2f}")
