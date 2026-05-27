#!/usr/bin/env python3
"""生成模拟 OHLCV K 线数据（Freqtrade 兼容格式）

用法: python scripts/generate_data.py
"""

from pathlib import Path
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "freqtrade" / "user_data" / "data" / "bybit"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PAIRS_INFO = {
    "BTC/USDT:USDT": {"base": 65000.0, "vol": 0.015},
    "ETH/USDT:USDT": {"base": 3400.0, "vol": 0.02},
    "SOL/USDT:USDT": {"base": 145.0, "vol": 0.03},
}
TIMEFRAMES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
DAYS = 360
END_DATE = datetime(2025, 12, 31, tzinfo=timezone.utc)
START_DATE = END_DATE - timedelta(days=DAYS)


def make_price_series(n, base, vol, seed):
    """生成 realistic 价格序列 — 使用 bounded random walk"""
    rng = np.random.default_rng(seed)
    
    # 生成日收益率（带均值回归）
    daily_vol = vol * np.sqrt(1/24)  # 小时波动率
    returns = rng.normal(0, daily_vol, n)
    
    # 加入微弱趋势
    trend = np.linspace(0, 0.3, n) / n  # 整体最多涨 30%
    returns += trend
    
    # 价格从 base 开始，累积收益率
    price = base * np.exp(np.cumsum(returns))
    
    # 确保价格为正且合理
    price = np.clip(price, base * 0.1, base * 10)
    
    return price


def make_ohlcv(prices):
    """从价格序列生成 OHLCV"""
    n = len(prices)
    rng = np.random.default_rng(abs(hash(str(prices[:10]))))
    
    df = pd.DataFrame({"close": prices})
    df["open"] = df["close"].shift(1).fillna(df["close"].iloc[0])
    
    # 计算日内波动
    intra_vol = np.abs(np.diff(prices, prepend=prices[0])) * 0.3 + prices * 0.002
    up = rng.uniform(0, 1, n)
    df["high"] = df[["open", "close"]].max(axis=1) + intra_vol * up
    df["low"] = df[["open", "close"]].min(axis=1) - intra_vol * (1 - up)
    
    # 成交量
    df["volume"] = rng.exponential(500, n) * (prices / 50000) + 100
    df["volume"] = df["volume"].clip(10)
    
    return df[["open", "high", "low", "close", "volume"]]


def generate_pair(pair_key: str):
    pair, info = pair_key, PAIRS_INFO[pair_key]
    base_price = info["base"]
    vol = info["vol"]
    symbol = pair.replace("/", "").replace(":", "_")
    
    print(f"生成 {pair} (base={base_price}, vol={vol}) ...")
    
    total_minutes = DAYS * 24 * 60
    seed = abs(hash(pair)) % 10000
    
    # 生成 1m 的价格
    price_1m = make_price_series(total_minutes, base_price, vol, seed)
    df_1m = make_ohlcv(price_1m)
    df_1m.index = pd.date_range(start=START_DATE, periods=total_minutes, freq="min", tz="UTC")
    
    for tf_name, tf_minutes in TIMEFRAMES.items():
        if tf_name == "1m":
            df = df_1m.copy()
        else:
            rule = f"{tf_minutes}min"
            resampled = df_1m.resample(rule)
            df = pd.DataFrame({
                "open": resampled["open"].first(),
                "high": resampled["high"].max(),
                "low": resampled["low"].min(),
                "close": resampled["close"].last(),
                "volume": resampled["volume"].sum(),
            }).dropna()
        
        df_reset = df.reset_index()
        df_reset.index.name = None
        df_reset.rename(columns={"index": "date"}, inplace=True)
        df_reset["date"] = df_reset["date"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
        
        pair_file = pair.replace("/", "").replace(":", "")
        filename = f"{pair_file}-{tf_name}.feather"
        filepath = DATA_DIR / filename
        
        df_reset.to_feather(filepath)
        print(f"  → {filename}  ({len(df_reset)} 行, 价格范围 {df['close'].min():.1f} - {df['close'].max():.1f})")


if __name__ == "__main__":
    print(f"生成 {DAYS} 天 ({DAYS*24}h) 模拟数据...")
    print(f"输出目录: {DATA_DIR}")
    print("=" * 50)
    for pair in PAIRS_INFO:
        generate_pair(pair)
    print("=" * 50)
    print("完成！")
