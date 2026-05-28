"""
缠论调试器 — 输出笔和中枢的识别结果
"""
import subprocess, json
from pathlib import Path

# 发请求
r = subprocess.run(['curl','-s','-X','POST','http://127.0.0.1:8765/api/backtest','-H','Content-Type: application/json',
    '-d','{"strategy":"RealChanTheory","pairs":["BTC/USDT:USDT"],"timeframe":"1h","timerange":"20260101-20260520","stake_amount":100,"initial_balance":1000,"fee":0.0004,"leverage":1,"max_open_trades":1}'],
    capture_output=True,text=True,timeout=120)

d = json.loads(r.stdout)
if 'metrics' not in d:
    print('ERROR:', str(d)[:200])
    exit()

trades = d['trades']
entries = [t for t in trades if t['type'] == 'entry']
exits = [t for t in trades if t['type'] == 'exit']

print(f'总交易: {len(entries)}笔')
print()

# 统计各买卖点类型
from collections import Counter
tag_counts = Counter(t.get('enter_tag','?') for t in entries)
print('买卖点分布:')
for tag, count in sorted(tag_counts.items()):
    print(f'  {tag}: {count}笔')

print()

# 详细查看每笔交易
print('交易明细:')
print(f'{"时间":16s} {"方向":4s} {"买卖点":10s} {"入场价":10s} {"PnL":8s} {"PnL%":8s}')
print('-' * 60)
for i, entry in enumerate(entries):
    # 找对应的exit
    match = [t for t in exits if t['pair'] == entry['pair'] and t['side'] == entry['side']]
    exit_t = match[i] if i < len(match) else None
    pnl = exit_t['pnl'] if exit_t else 0
    pnl_pct = exit_t['pnl_pct'] if exit_t else 0
    tag = entry.get('enter_tag', '?')
    ts = entry['timestamp'][:16]
    side = entry['side']
    price = entry['price']
    print(f'{ts} {side:4s} {tag:10s} {price:>8.0f}  {pnl:>+7.2f} {pnl_pct:>+7.2f}%')

# 胜率
wins = sum(1 for t in exits if t.get('pnl',0) > 0)
total = len(exits)
print(f'\n胜率: {wins}/{total} = {wins/total*100:.1f}%' if total else '\n无交易')
