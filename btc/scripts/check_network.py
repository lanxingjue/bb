#!/usr/bin/env python3
"""检查哪些数据源可用"""
import urllib.request
import json

URLS = {
    "OKX API": "https://www.okx.com/api/v5/public/time",
    "Bybit API": "https://api.bybit.com/v5/market/time",
    "Binance API": "https://api.binance.com/api/v3/ping",
    "CoinGecko": "https://api.coingecko.com/api/v3/ping",
    "CoinGecko BTC": "https://api.coingecko.com/api/v3/coins/bitcoin/ohlc?vs_currency=usd&days=1",
}

for name, url in URLS.items():
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()[:100]
            print(f"✅ {name} — HTTP {resp.status}")
    except Exception as e:
        print(f"❌ {name} — {type(e).__name__}")
