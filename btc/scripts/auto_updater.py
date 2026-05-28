#!/usr/bin/env python3
"""
自动数据更新器 — 每 4 小时运行一次，增量下载最新 K 线数据。

用法:
  python scripts/auto_updater.py          # 运行一次
  python scripts/auto_updater.py --daemon # 后台持续运行(每4小时)

会自动:
  1. 下载最新 7 天的 1m/5m/15m 数据（细粒度）
  2. 下载最新 30 天的 1h/4h/1d 数据（粗粒度）
  3. 跳过已存在的数据，只补充缺失的
"""

import subprocess
import sys
import time
import os
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
FREQTRADE = BASE / "freqtrade" / ".venv" / "bin" / "freqtrade"
USERDIR = BASE / "freqtrade" / "user_data"
CONFIG = BASE / "config.json"

# 数据配置
EXCHANGE = "okx"
FUTURES_PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
SPOT_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]

# 增量下载天数（每次只下载最新的）
DAYS = 3

INTERVAL_HOURS = 4


def run_cmd(cmd: list, timeout: int = 300) -> bool:
    """运行命令"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            return True
        # 显示关键错误
        for line in (r.stderr or "").split("\n"):
            if "ERROR" in line or "error" in line:
                print(f"  ⚠️  {line[:120]}")
        return False
    except subprocess.TimeoutExpired:
        print("  ⚠️  超时")
        return False
    except Exception as e:
        print(f"  ⚠️  {e}")
        return False


def update_data():
    """更新一次数据"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{ts}] 🔄 开始数据更新...")

    # 合约数据
    print("  📥 永续合约...")
    ok = run_cmd([
        str(FREQTRADE), "download-data",
        "--exchange", EXCHANGE,
        "--trading-mode", "futures",
        "-c", str(CONFIG),
        "--pairs", *FUTURES_PAIRS,
        "--timeframes", "1m", "5m", "15m",
        "--days", str(DAYS),
        "--userdir", str(USERDIR),
    ])
    print(f"  {'✅' if ok else '⚠️'} 合约细粒度(1m/5m/15m)")

    ok = run_cmd([
        str(FREQTRADE), "download-data",
        "--exchange", EXCHANGE,
        "--trading-mode", "futures",
        "-c", str(CONFIG),
        "--pairs", *FUTURES_PAIRS,
        "--timeframes", "1h", "4h", "1d",
        "--days", "30",
        "--userdir", str(USERDIR),
    ])
    print(f"  {'✅' if ok else '⚠️'} 合约粗粒度(1h/4h/1d)")

    print(f"  ✅ 更新完成")


def daemon_loop():
    """后台循环运行"""
    print(f"🔄 自动更新器已启动，每 {INTERVAL_HOURS} 小时运行一次")
    print(f"   按 Ctrl+C 停止")
    print()

    update_data()

    while True:
        print(f"\n⏳ 等待 {INTERVAL_HOURS} 小时...")
        time.sleep(INTERVAL_HOURS * 3600)
        update_data()


if __name__ == "__main__":
    if "--daemon" in sys.argv:
        daemon_loop()
    else:
        update_data()
