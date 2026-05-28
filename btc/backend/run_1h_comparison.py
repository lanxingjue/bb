"""
Run 1h multi-pair backtest for fair comparison with 5m.
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'btc/freqtrade')
from pathlib import Path

import btc.backend.backtest_engine as be
be.DATA_DIR = Path('btc/freqtrade/user_data/data/binance')

from btc.backend.backtest_engine import run, save

# 1h multi-pair comparison
print('Running 1h multi-pair RealChanTheory...')
r = run(
    strategy_name='RealChanTheory',
    pairs=['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT'],
    timeframe='1h',
    timerange='20250105-20251230',
    stake_amount=100,
    initial_balance=1000,
    max_open_trades=3,
    leverage_val=3.0,
)
save(r, 'backtest_chan_v6_1h_multipair_full_year.json')
m = r['metrics']
print(f'\n=== 1h Multi-Pair FULL YEAR ===')
print(f'Trades: {m["total_trades"]}')
print(f'Win Rate: {m["win_rate"]}%')
print(f'Total Profit: {m["total_profit_pct"]}%')
print(f'Avg Profit/Trade: {m["avg_profit_pct"]}%')
print(f'Sharpe: {m["sharpe_ratio"]}')
print(f'Max DD: {m["max_drawdown_pct"]}%')
print(f'Final Balance: {m["final_balance"]}')
