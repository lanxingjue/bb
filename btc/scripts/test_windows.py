#!/usr/bin/env python3
"""测试不同中枢窗口大小的缠论表现"""
import subprocess, json, sys
from pathlib import Path

STRAT = Path(__file__).resolve().parent.parent / "freqtrade" / "user_data" / "strategies" / "ChanTheoryStrategy.py"

for window in [48, 64, 80, 96, 120]:
    code = STRAT.read_text()
    # 替换 rolling/shift 的值
    import re
    code = re.sub(r'\.rolling\(\d+\)', f'.rolling({window})', code)
    code = re.sub(r'\.shift\(\d+\)', f'.shift({window})', code)
    STRAT.write_text(code)

    cmd = f'curl -s -X POST http://127.0.0.1:8765/api/backtest -H "Content-Type: application/json" -d \'{{"strategy":"ChanTheoryStrategy","pairs":["BTC/USDT:USDT","ETH/USDT:USDT"],"timeframe":"15m","timerange":"20260201-20260520","stake_amount":100,"initial_balance":1000,"fee":0.0004,"leverage":3,"max_open_trades":3}}\''
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    try:
        d = json.loads(result.stdout)
        m = d.get('metrics', {})
        print(f"窗口{window:3d}:  {m.get('total_trades',0):3d}笔  胜率{m.get('win_rate',0):5.1f}%  收益{m.get('total_profit_pct',0):+6.2f}%  夏普{m.get('sharpe_ratio',0):+5.2f}  回撤{m.get('max_drawdown_pct',0):4.1f}%  余额{m.get('final_balance',0):.0f}")
    except:
        print(f"窗口{window:3d}:  ERROR")
