#!/usr/bin/env python3
"""启动自动更新器（SOCKS5 代理）"""
import os, sys

os.environ['all_proxy'] = 'socks5://127.0.0.1:1086'
os.environ['ALL_PROXY'] = 'socks5://127.0.0.1:1086'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.auto_updater import run_cmd, BASE, FREQTRADE, USERDIR, CONFIG, EXCHANGE, FUTURES_PAIRS, DAYS, INTERVAL_HOURS
from datetime import datetime
import time

def download_all():
    for pair in FUTURES_PAIRS:
        for tf in ['1m', '5m', '15m']:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 下载 {pair} {tf}")
            cmd = [str(FREQTRADE), 'download-data', '--exchange', EXCHANGE,
                   '--trading-mode', 'futures', '-c', str(CONFIG),
                   '--pairs', pair, '--timeframes', tf, '--days', str(DAYS),
                   '--userdir', str(USERDIR), '--prepend']
            run_cmd(cmd, timeout=300)
        for tf in ['1h', '4h', '1d']:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 下载 {pair} {tf}")
            cmd = [str(FREQTRADE), 'download-data', '--exchange', EXCHANGE,
                   '--trading-mode', 'futures', '-c', str(CONFIG),
                   '--pairs', pair, '--timeframes', tf, '--days', '30',
                   '--userdir', str(USERDIR), '--prepend']
            run_cmd(cmd, timeout=300)

if __name__ == '__main__':
    print(f"🚀 更新器启动 (每{INTERVAL_HOURS}小时, SOCKS5代理)")
    while True:
        download_all()
        print(f"⏳ 等待 {INTERVAL_HOURS} 小时...")
        time.sleep(INTERVAL_HOURS * 3600)
