#!/usr/bin/env python3
"""
实时 K 线更新器 — 每 60 秒从 OKX 拉取最新 1m/5m K 线。

通过 SOCKS5 代理 (127.0.0.1:1086) 连接 OKX API。
追加到 feather 文件，模拟盘引擎下次 tick 自动发现新数据。

API: GET /api/v5/market/candles?instId=BTC-USDT-SWAP&bar=1m&limit=3
     confirm=1 表示已完成的 K 线
"""
import json
import time
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import subprocess

def _okx_request(path: str) -> dict:
    """通过 curl + SOCKS5 请求 OKX API"""
    import subprocess
    url = f"https://www.okx.com{path}"
    r = subprocess.run(['curl', '-s', '--socks5', '127.0.0.1:1086', '--max-time', '10', url],
        capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        return {"code": "-1", "msg": r.stderr}
    return json.loads(r.stdout)

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "freqtrade" / "user_data" / "data" / "okx"

# 交易对映射: (pair_name, okx_instId, timeframes)
WATCH_LIST = [
    ("BTC/USDT:USDT", "BTC-USDT-SWAP", ["1m", "5m"]),
    ("ETH/USDT:USDT", "ETH-USDT-SWAP", ["1m", "5m"]),
    ("SOL/USDT:USDT", "SOL-USDT-SWAP", ["1m", "5m"]),
    ("BNB/USDT:USDT", "BNB-USDT-SWAP", ["1m", "5m"]),
]

def fetch_latest(inst_id: str, bar: str, limit: int = 3) -> list:
    """从 OKX 获取最新 K 线"""
    path = f"/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}"
    data = _okx_request(path)
    if data.get("code") != "0":
        print(f"  ⚠️ API 错误: {data.get('msg', '?')}")
        return []
    return data.get("data", [])


def append_to_feather(pair_file: str, tf: str, new_rows: list) -> int:
    """将新 K 线追加到 feather 文件，返回新增条数"""
    fp = DATA_DIR / f"{pair_file}-{tf}.feather"
    
    records = []
    for row in new_rows:
        ts = int(row[0])
        records.append({
            "date": datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
            "open": float(row[1]), "high": float(row[2]),
            "low": float(row[3]), "close": float(row[4]),
            "volume": float(row[5]),
        })
    
    if not records:
        return 0
    
    df_new = pd.DataFrame(records)
    old_count = 0
    
    if fp.exists():
        df_old = pd.read_feather(fp)
        df_old["date"] = pd.to_datetime(df_old["date"])
        old_count = len(df_old)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
        df_all = df_all.drop_duplicates(subset=["date"], keep="last")
        df_all = df_all.sort_values("date").reset_index(drop=True)
    else:
        df_all = df_new.sort_values("date").reset_index(drop=True)
    
    df_all.to_feather(fp)
    return len(df_all) - old_count


def main():
    print(f"🚀 实时 K 线更新器启动")
    print(f"   监控: {[(p, tfs) for p, _, tfs in WATCH_LIST]}")
    print(f"   间隔: 60秒")
    print(f"   SOCKS5: 127.0.0.1:1086")
    print("-" * 50)
    
    while True:
        now = datetime.now().strftime("%H:%M:%S")
        updated = False
        
        for pair_name, inst_id, tfs in WATCH_LIST:
            pair_file = pair_name.replace("/", "").replace(":", "")
            
            for tf in tfs:
                try:
                    candles = fetch_latest(inst_id, tf, limit=3)
                    if not candles:
                        continue
                    
                    # 只取已确认的 K 线 (confirm=1)
                    confirmed = [c for c in candles if len(c) >= 9 and c[8] == "1"]
                    if not confirmed:
                        continue
                    
                    # 追加到 feather
                    added = append_to_feather(pair_file, tf, confirmed)
                    if added:
                        print(f"[{now}] {pair_name} {tf}: +{added}根 (最新: {confirmed[-1][0]})")
                        updated = True
                        
                except Exception as e:
                    print(f"[{now}] {pair_name} {tf}: 错误 {e}")
        
        if not updated and int(time.time()) % 300 < 2:
            # 每5分钟输出一次心跳
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 心跳 ✓ (无新数据)")
        
        time.sleep(60)


if __name__ == "__main__":
    main()
