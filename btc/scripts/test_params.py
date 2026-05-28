#!/usr/bin/env python3
import subprocess, json, re
from pathlib import Path

strat = Path('btc/freqtrade/user_data/strategies/ChanTheoryStrategy.py')
code = strat.read_text()
base = '{"strategy":"ChanTheoryStrategy","pairs":["BTC/USDT:USDT","ETH/USDT:USDT"],"timeframe":"15m","timerange":"20260227-20260527","stake_amount":300,"initial_balance":1000,"fee":0.0004,"leverage":5,"max_open_trades":3}'

configs = [
    (0.012, 0.012, 0.04),
    (0.015, 0.015, 0.05),
    (0.010, 0.010, 0.04),
    (0.012, 0.010, 0.06),
    (0.018, 0.015, 0.06),
]

for sl, tp, to in configs:
    c = code
    c = re.sub(r'stoploss = -?[\d.]+', f'stoploss = -{sl}', c)
    c = re.sub(r'trailing_stop_positive = [\d.]+', f'trailing_stop_positive = {tp}', c)
    c = re.sub(r'trailing_stop_positive_offset = [\d.]+', f'trailing_stop_positive_offset = {to}', c)
    strat.write_text(c)
    
    r = subprocess.run(['curl','-s','-X','POST','http://127.0.0.1:8765/api/backtest','-H','Content-Type: application/json','-d',base],capture_output=True,text=True,timeout=120)
    try:
        d = json.loads(r.stdout)
        m = d['metrics']
        pct = m['total_profit_pct']
        wr = m['win_rate']
        sh = m['sharpe_ratio']
        dd = m['max_drawdown_pct']
        print(f'SL={sl:.3f} TP={tp:.3f} TO={to:.2f}:  {m["total_trades"]:3d}笔  胜{wr:5.1f}%  收{pct:+6.2f}%  夏{sh:+5.2f}  回撤{dd:4.1f}%')
    except Exception as e:
        print(f'SL={sl:.3f}: ERROR {str(e)[:50]}')
