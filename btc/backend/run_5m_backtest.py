"""
Run 5m backtest on Binance data with RealChanTheory.
Monkey-patches DATA_DIR to point to binance.
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'btc/freqtrade')

from pathlib import Path

# Patch DATA_DIR before importing backtest_engine
import btc.backend.backtest_engine as be
be.DATA_DIR = Path('btc/freqtrade/user_data/data/binance')
print(f'DATA_DIR set to: {be.DATA_DIR}')

from btc.backend.backtest_engine import run, save

# ─── 5m backtest: full year 2025 ───
print('\n' + '='*60)
print('Running 5m BTC/USDT RealChanTheory FULL YEAR 2025')
print('='*60)
r = run(
    strategy_name='RealChanTheory',
    pairs=['BTC/USDT:USDT'],
    timeframe='5m',
    timerange='20250105-20251230',
    stake_amount=100,
    initial_balance=1000,
    max_open_trades=3,
    leverage_val=3.0,
)
save(r, 'backtest_chan_v6_5m_btc_full_year.json')
m = r['metrics']
print('\n=== 5m FULL YEAR (Jan-Dec 2025) ===')
print(f'Trades: {m["total_trades"]}')
print(f'Win Rate: {m["win_rate"]}%')
print(f'Total Profit: {m["total_profit_pct"]}%')
print(f'Profit USDT: {m["total_profit_usdt"]}')
print(f'Avg Profit/Trade: {m["avg_profit_pct"]}%')
print(f'Sharpe: {m["sharpe_ratio"]}')
print(f'Max DD: {m["max_drawdown_pct"]}%')
print(f'Final Balance: {m["final_balance"]}')

# ─── 1h comparison (same period) ───
print('\n' + '='*60)
print('Running 1h BTC/USDT RealChanTheory (baseline comparison)')
print('='*60)
r2 = run(
    strategy_name='RealChanTheory',
    pairs=['BTC/USDT:USDT'],
    timeframe='1h',
    timerange='20250105-20251230',
    stake_amount=100,
    initial_balance=1000,
    max_open_trades=3,
    leverage_val=3.0,
)
save(r2, 'backtest_chan_v6_1h_btc_full_year.json')
m2 = r2['metrics']
print('\n=== 1h FULL YEAR (Jan-Dec 2025) ===')
print(f'Trades: {m2["total_trades"]}')
print(f'Win Rate: {m2["win_rate"]}%')
print(f'Total Profit: {m2["total_profit_pct"]}%')
print(f'Profit USDT: {m2["total_profit_usdt"]}')
print(f'Avg Profit/Trade: {m2["avg_profit_pct"]}%')
print(f'Sharpe: {m2["sharpe_ratio"]}')
print(f'Max DD: {m2["max_drawdown_pct"]}%')
print(f'Final Balance: {m2["final_balance"]}')

print('\n' + '='*60)
print('COMPARISON TABLE')
print('='*60)
print(f'{"Metric":<20} {"5m":>12} {"1h":>12}')
print(f'{"-"*20} {"-"*12} {"-"*12}')
print(f'{"Trades":<20} {m["total_trades"]:>12} {m2["total_trades"]:>12}')
print(f'{"Win Rate %":<20} {m["win_rate"]:>12.2f} {m2["win_rate"]:>12.2f}')
print(f'{"Total Profit %":<20} {m["total_profit_pct"]:>12.2f} {m2["total_profit_pct"]:>12.2f}')
print(f'{"Avg Profit %":<20} {m["avg_profit_pct"]:>12.2f} {m2["avg_profit_pct"]:>12.2f}')
print(f'{"Sharpe":<20} {m["sharpe_ratio"]:>12.2f} {m2["sharpe_ratio"]:>12.2f}')
print(f'{"Max DD %":<20} {m["max_drawdown_pct"]:>12.2f} {m2["max_drawdown_pct"]:>12.2f}')
print(f'{"Final Balance":<20} {m["final_balance"]:>12.2f} {m2["final_balance"]:>12.2f}')
