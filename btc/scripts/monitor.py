#!/usr/bin/env python3
"""模拟盘状态监控器 — 每分钟输出一次状态"""
import urllib.request
import json
import time
import sys
from datetime import datetime

API = "http://127.0.0.1:8765/api/papertrade/status"

def get_status():
    try:
        r = urllib.request.urlopen(API, timeout=5)
        return json.loads(r.read())
    except:
        return None

def format_status(d):
    if not d:
        return "❌ API 不可达"
    pt = d.get('paired_trades', [])
    wins = sum(1 for t in pt if t['pnl'] > 0)
    eq = d.get('equity', 0)
    pnl = eq - 1000
    icon = '🟢' if d.get('running') else '🔴'
    win_rate = f"{wins/len(pt)*100:.0f}%" if pt else "—"
    # 最近一笔交易
    last = pt[-1] if pt else None
    last_str = ""
    data_range = ""
    if pt:
        data_range = f" {pt[0]['entry_time'][:10]}~{pt[-1]['entry_time'][:10]}"
        l_icon = '🟢' if last['pnl'] > 0 else '🔴'
        last_str = f" {l_icon} {last['enter_tag'][:15]} {last['pnl']:+.2f}"
    return f"{icon} ${eq:.0f} {len(pt)}笔 {win_rate} {pnl:+.2f}{last_str}{data_range}"

print("📊 模拟盘监控启动 (每60秒)")
print("─" * 50)

while True:
    now = datetime.now().strftime("%H:%M:%S")
    status = get_status()
    line = f"[{now}] {format_status(status)}"
    print(line)
    sys.stdout.flush()
    time.sleep(60)
