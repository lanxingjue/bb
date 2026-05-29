#!/usr/bin/env python3
"""从 15m/5m 数据插值生成 1m 数据，填补 2026-01~04 的空缺"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path('btc/freqtrade/user_data/data/okx')

def generate_1m_from_15m(pair_file: str, output_file: str):
    """用 15m 数据插值生成 1m 数据"""
    fp_15m = DATA_DIR / f"{pair_file}-15m.feather"
    fp_out = DATA_DIR / output_file
    
    if not fp_15m.exists():
        print(f'❌ 没有 15m 数据: {fp_15m.name}')
        return False
    
    df_15m = pd.read_feather(fp_15m)
    df_15m['date'] = pd.to_datetime(df_15m['date'])
    df_15m.set_index('date', inplace=True)
    
    print(f'15m 数据: {len(df_15m)}根, {df_15m.index.min()} ~ {df_15m.index.max()}')
    
    # 生成 1m 时间轴 (15m 范围内每1分钟)
    all_1m_times = pd.date_range(
        start=df_15m.index.min(),
        end=df_15m.index.max(),
        freq='1min',
        tz='UTC'
    )
    
    # 对每个 OHLC 列做线性插值
    result = pd.DataFrame(index=all_1m_times)
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        # 在 15m 点上已知值，其余 NaN
        series = pd.Series(index=all_1m_times, dtype=float)
        series.loc[df_15m.index] = df_15m[col].values
        
        if col in ['high', 'low']:
            series = series.ffill().bfill()
        elif col == 'volume':
            series = series.ffill() / 15
            series[df_15m.index] = df_15m[col].values / 15
        else:
            # OHLC 线性插值
            series = series.interpolate(method='linear')
        
        result[col] = series.round(2).fillna(0)
    
    result['date'] = result.index
    result = result[result.index.isin(all_1m_times)]
    
    print(f'生成 1m 数据: {len(result)}根, {result.index.min()} ~ {result.index.max()}')
    
    # 保存为 feather
    result.reset_index(drop=True)[['date', 'open', 'high', 'low', 'close', 'volume']].to_feather(fp_out)
    print(f'✅ 已保存: {fp_out.name}')
    return True


def merge_with_existing(pair_file: str):
    """将新生成的 1m 数据与已有的 1m 数据合并"""
    fp_new = DATA_DIR / f"{pair_file}_synthetic-1m.feather"
    fp_existing = DATA_DIR / f"{pair_file}-1m.feather"
    
    if not fp_new.exists():
        return
    
    df_new = pd.read_feather(fp_new)
    df_new['date'] = pd.to_datetime(df_new['date'])
    
    if fp_existing.exists():
        df_old = pd.read_feather(fp_existing)
        df_old['date'] = pd.to_datetime(df_old['date'])
        
        # 合并、去重、排序
        combined = pd.concat([df_old, df_new], ignore_index=True)
        combined = combined.drop_duplicates(subset=['date'], keep='last')
        combined = combined.sort_values('date').reset_index(drop=True)
    else:
        combined = df_new
    
    # 检查完整性
    min_d = combined['date'].min()
    max_d = combined['date'].max()
    expected = int((max_d - min_d).total_seconds() / 60) + 1
    actual = len(combined)
    coverage = actual / expected * 100
    
    print(f'合并后: {len(combined)}根, {min_d} ~ {max_d}')
    print(f'覆盖率: {coverage:.1f}% ({actual}/{expected})')
    
    combined.to_feather(fp_existing)
    if fp_new.exists():
        fp_new.unlink()  # 删除临时文件
    print(f'✅ 已合并到 {fp_existing.name}')


if __name__ == '__main__':
    for pair, pf in [('BTC/USDT:USDT', 'BTCUSDTUSDT'), ('ETH/USDT:USDT', 'ETHUSDTUSDT')]:
        print(f'\n=== {pair} ===')
        if generate_1m_from_15m(pf, f"{pf}_synthetic-1m.feather"):
            merge_with_existing(pf)
    
    print('\n完成!')
