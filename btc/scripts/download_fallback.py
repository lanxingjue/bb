#!/usr/bin/env python3
"""
备用方案：从 CoinGecko 等公开 API 下载 K 线数据。
不需要交易所 API，网络要求低。

用法：
  source freqtrade/.venv/bin/activate
  python scripts/download_fallback.py
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

import urllib.request
import urllib.error

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "freqtrade" / "user_data" / "data" / "bybit"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 交易对配置 (symbol -> display_name)
PAIRS = {
    "bitcoin": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "solana": "SOLUSDT",
    "binancecoin": "BNBUSDT",
}

TIMEFRAMES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

# CoinGecko 最多返回 500 条，需要分页
# 每页天数 = 500 * 粒度(天)
DAYS_TOTAL = 365
COINGECKO_BASE = "https://api.coingecko.com/api/v3"


def fetch_ohlcv(coin_id: str, vs_currency: str = "usd", days: int = 365) -> list | None:
    """从 CoinGecko 获取 OHLCV 数据"""
    url = f"{COINGECKO_BASE}/coins/{coin_id}/ohlc?vs_currency={vs_currency}&days={days}"
    print(f"  📡 GET {url}")

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            print(f"    返回 {len(data)} 条数据")
            return data
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}: {e.reason}")
        return None
    except Exception as e:
        print(f"    错误: {e}")
        return None


def convert_to_feather(coin_id: str, symbol: str):
    """下载数据并转换为 feather 格式"""
    print(f"\n📥 {symbol} ({coin_id})")

    # 获取 1 天粒度数据
    raw_data = fetch_ohlcv(coin_id, days=DAYS_TOTAL)
    if not raw_data or len(raw_data) < 10:
        print(f"  ⚠️ 数据不足")
        return False

    # CoinGecko 返回 [timestamp_ms, open, high, low, close]
    import pandas as pd

    records = []
    for item in raw_data:
        records.append({
            "date": datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S%z"),
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4]),
            "volume": 0.0,  # CoinGecko OHLC 不包含成交量
        })

    # 用 1d 数据合成更细粒度（简单插值）
    df_day = pd.DataFrame(records)
    df_day["date"] = pd.to_datetime(df_day["date"])

    # 保存 1d
    for tf_name in ["1d"]:
        filepath = DATA_DIR / f"{symbol}-{tf_name}.feather"
        if tf_name == "1d":
            df_day.to_feather(filepath)
            print(f"  ✅ {filepath.name} ({len(df_day)} 行)")
        else:
            # 其他粒度需要插值生成 — 简化处理
            pass

    return True


def main():
    print("🌐 备用方案: 从 CoinGecko 下载数据")
    print(f"   数据目录: {DATA_DIR}")
    print()

    # 测试连接
    test_url = f"{COINGECKO_BASE}/ping"
    req = urllib.request.Request(test_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"✅ CoinGecko 连接正常")
    except Exception as e:
        print(f"❌ CoinGecko 不可用: {e}")
        print()
        print("所有外部数据源都不可用，最后方案：生成模拟数据")
        ans = input("是否生成模拟数据？(y/n): ")
        if ans.lower() == "y":
            import subprocess
            subprocess.run([sys.executable, str(BASE / "scripts" / "generate_data.py")])
        return

    # 下载每个交易对
    success = 0
    for coin_id, symbol in PAIRS.items():
        if convert_to_feather(coin_id, symbol):
            success += 1
        time.sleep(1.5)  # CoinGecko rate limit

    print(f"\n{'='*50}")
    print(f"完成: {success}/{len(PAIRS)} 个交易对")
    print()
    print("启动系统:")
    print("  (.venv) $ python backend/main.py")
    print("  $ npm --prefix frontend run dev")


if __name__ == "__main__":
    main()
