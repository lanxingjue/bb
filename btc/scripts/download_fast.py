#!/usr/bin/env python3
"""
加快版数据下载 — 只下载粗粒度数据（1h/4h/1d），细粒度可要可不要。
1m/5m/15m 可选下载（默认跳过，太慢）。

用法：
  source freqtrade/.venv/bin/activate
  python scripts/download_fast.py
"""

import os
import sys
import time
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

PROXY = "http://127.0.0.1:1087"
proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
urllib.request.install_opener(urllib.request.build_opener(proxy_handler))

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "freqtrade" / "user_data" / "data" / "okx"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 所有交易对
SWAP = {
    "BTC-USDT-SWAP": "BTCUSDTUSDT",
    "ETH-USDT-SWAP": "ETHUSDTUSDT",
    "SOL-USDT-SWAP": "SOLUSDTUSDT",
    "BNB-USDT-SWAP": "BNBUSDTUSDT",
}
SPOT = {
    "BTC-USDT": "BTCUSDT",
    "ETH-USDT": "ETHUSDT",
    "SOL-USDT": "SOLUSDT",
    "BNB-USDT": "BNBUSDT",
}

# 时间粒度: OKX bar → 天数
TIMEFRAMES = {
    "1m": 7,      # 仅 7 天（示范）
    "5m": 30,     # 30 天
    "15m": 90,    # 90 天
    "1H": 365,    # 365 天
    "4H": 365,
    "1D": 365,
}

OKX_LIMIT = 300


def fetch_okx(inst_id: str, bar: str, after: str = ""):
    url = f"https://www.okx.com/api/v5/market/history-candles?instId={inst_id}&bar={bar}&limit={OKX_LIMIT}"
    if after:
        url += f"&after={after}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    if body.get("code") == "0":
        return body.get("data", [])
    return None


def download_pair(inst_id: str, prefix: str, mode: str):
    print(f"  {inst_id}")
    for okx_bar, days in TIMEFRAMES.items():
        # 文件名用标准化的 tf 名
        tf_map = {"1H": "1h", "4H": "4h", "1D": "1d"}
        tf_name = tf_map.get(okx_bar, okx_bar.lower())
        fp = DATA_DIR / f"{prefix}-{tf_name}.feather"
        if fp.exists():
            print(f"    ⏱ {tf_name} ({days}d) — 跳过（已存在）")
            continue

        since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
        print(f"    ⏱ {tf_name} ({days}d)...", end=" ", flush=True)

        all_candles = []
        after = ""
        page = 0
        while page < 5000:
            page += 1
            data = fetch_okx(inst_id, okx_bar, after)
            if not data:
                break
            filtered = [d for d in data if int(d[0]) >= since]
            all_candles.extend(filtered)
            after = data[-1][0]
            if int(after) < since or len(data) < OKX_LIMIT:
                break
            time.sleep(0.1)

        if not all_candles:
            print("无数据")
            continue

        import pandas as pd
        records = []
        for item in all_candles:
            ts = datetime.fromtimestamp(int(item[0]) / 1000, tz=timezone.utc)
            records.append({
                "date": ts.strftime("%Y-%m-%d %H:%M:%S%z"),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            })
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df = df.drop_duplicates(subset=["date"]).sort_values("date")
        df.to_feather(fp)
        print(f"✅ {len(df)} 行")


def main():
    print("🌐 快速下载 OKX 数据 (代理: 127.0.0.1:1087)")
    print(f"   合约: {', '.join(SWAP.keys())}")
    print(f"   现货: {', '.join(SPOT.keys())}")
    print(f"   粒度: {', '.join(TIMEFRAMES.keys())}")
    print()

    for mode, pairs in [("swap", SWAP), ("spot", SPOT)]:
        print(f"\n─── {mode.upper()} ───")
        for inst_id, prefix in pairs.items():
            download_pair(inst_id, prefix, mode)

    files = sorted(DATA_DIR.glob("*.feather"))
    total = sum(f.stat().st_size for f in files)
    print(f"\n{'='*50}")
    print(f"✅ 完成！{len(files)} 个文件, {total/1024:.0f} KB")
    print(f"   目录: {DATA_DIR}")
    print()
    print("🚀 启动:")
    print("   (.venv) $ python backend/main.py")
    print("   $ npm --prefix frontend run dev")


if __name__ == "__main__":
    main()
