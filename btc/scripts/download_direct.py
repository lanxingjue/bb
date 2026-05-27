#!/usr/bin/env python3
"""
直接用 requests 下载 OKX K 线数据（不走 ccxt / freqtrade）。
代理用环境变量 HTTPS_PROXY。
保存为 Freqtrade 兼容的 feather 格式。
"""

import os
import sys
import time
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ── 代理 ──────────────────────────────────────────────
PROXY = "http://127.0.0.1:1087"
proxy_handler = urllib.request.ProxyHandler({
    "http": PROXY,
    "https": PROXY,
})
opener = urllib.request.build_opener(proxy_handler)
urllib.request.install_opener(opener)

# ── 路径 ──────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "freqtrade" / "user_data" / "data" / "okx"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── 交易对配置 ─────────────────────────────────────────
# 合约永续: instId -> filename prefix
SWAP_PAIRS = {
    "BTC-USDT-SWAP": "BTCUSDTUSDT",
    "ETH-USDT-SWAP": "ETHUSDTUSDT",
    "SOL-USDT-SWAP": "SOLUSDTUSDT",
    "BNB-USDT-SWAP": "BNBUSDTUSDT",
}

# 现货: instId -> filename prefix
SPOT_PAIRS = {
    "BTC-USDT": "BTCUSDT",
    "ETH-USDT": "ETHUSDT",
    "SOL-USDT": "SOLUSDT",
    "BNB-USDT": "BNBUSDT",
}

# OKX 的 bar 参数
TF_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1H",
    "4h": "4H",
    "1d": "1D",
}

# 粗粒度（1h 及以上）下载天数
DAYS_COARSE = 365
# 细粒度（1m, 5m, 15m）下载天数 — 短一点避免太慢
DAYS_FINE = 90
OKX_LIMIT = 300  # OKX 单次最多 300 根


def fetch_okx(inst_id: str, bar: str, after: str = "") -> list | None:
    """调用 OKX 历史 K 线 API"""
    url = f"https://www.okx.com/api/v5/market/history-candles?instId={inst_id}&bar={bar}&limit={OKX_LIMIT}"
    if after:
        url += f"&after={after}"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
        if body.get("code") == "0":
            return body.get("data", [])
        print(f"    API 错误: {body}")
        return None
    except Exception as e:
        print(f"    请求失败: {e}")
        return None


def download_all(pairs: dict, mode: str):
    """下载一个模式（现货/合约）的所有交易对"""
    total_files = 0
    for inst_id, prefix in pairs.items():
        print(f"\n📥 {inst_id}")

        for tf_name, okx_bar in TF_MAP.items():
            # 细粒度数据只下载较短时间
            if tf_name in ("1m", "5m", "15m"):
                days = DAYS_FINE
            else:
                days = DAYS_COARSE

            since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
            print(f"  ⏱ {tf_name} ({days}d)...", end=" ")
            sys.stdout.flush()

            all_candles = []
            after = ""
            empty_count = 0
            max_pages = 10000  # 安全上限
            page = 0

            while page < max_pages:
                page += 1
                data = fetch_okx(inst_id, okx_bar, after)
                if not data:
                    break
                if len(data) == 0:
                    empty_count += 1
                    if empty_count >= 3:
                        break
                    continue

                # 过滤：只保留 >= since 的数据
                filtered = [d for d in data if int(d[0]) >= since]
                all_candles.extend(filtered)
                after = data[-1][0]
                print(f"{len(all_candles)}", end=" ", flush=True)

                last_ts = int(data[-1][0])
                if last_ts < since or len(data) < OKX_LIMIT:
                    break
                time.sleep(0.12)
                data = fetch_okx(inst_id, okx_bar, after)
                if not data:
                    break
                if len(data) == 0:
                    empty_count += 1
                    if empty_count >= 3:
                        break
                    continue

                all_candles.extend(data)
                after = data[-1][0]  # 最后一根的时间戳作为分页标记

                # 少于 limit 说明到底了
                if len(data) < OKX_LIMIT:
                    break
                time.sleep(0.15)  # rate limit

            if not all_candles:
                print("无数据 ❌")
                continue

            # OKX 返回格式: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
            # → 我们只需要前 6 个字段
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
            # 去重 + 按时间排序
            df["date"] = pd.to_datetime(df["date"])
            df = df.drop_duplicates(subset=["date"]).sort_values("date")

            fp = DATA_DIR / f"{prefix}-{tf_name}.feather"
            df.to_feather(fp)
            total_files += 1
            print(f"✅ {len(df)} 行 ({df['close'].min():.1f}~{df['close'].max():.1f})")

    return total_files


def main():
    print("🌐 OKX 直连下载 (代理: 127.0.0.1:1087)")
    print(f"   天数: 粗粒度={DAYS_COARSE}d, 细粒度={DAYS_FINE}d")
    print(f"   目录: {DATA_DIR}")
    print()

    # 先测试连接
    test_url = "https://www.okx.com/api/v5/public/time"
    req = urllib.request.Request(test_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
            print(f"✅ OKX 连接成功: {body}")
    except Exception as e:
        print(f"❌ OKX 连接失败: {e}")
        print("   代理 127.0.0.1:1087 没通？")
        sys.exit(1)

    # 下载合约
    print("\n═══ 永续合约 (Swap) ═══")
    n1 = download_all(SWAP_PAIRS, "swap")

    # 下载现货
    print("\n═══ 现货 (Spot) ═══")
    n2 = download_all(SPOT_PAIRS, "spot")

    # 完成
    print(f"\n{'='*50}")
    print(f"✅ 完成！共 {n1 + n2} 个数据文件")
    print(f"   目录: {DATA_DIR}")
    print()
    print("🚀 启动系统:")
    print("   (.venv) $ python backend/main.py")
    print("   $ npm --prefix frontend run dev")


if __name__ == "__main__":
    main()
