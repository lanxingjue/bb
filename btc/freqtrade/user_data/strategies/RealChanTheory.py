"""
RealChanTheory v3+ — 详细标签版

基于 v3 最优参数 (+14.63%, 夏普2.26)
改进: 更详细的入场依据标签
"""

from pathlib import Path

import pandas as pd
from pandas import DataFrame
import numpy as np
import talib.abstract as ta
from freqtrade.strategy import IStrategy


def get_strokes_and_pivots(h, l, min_stroke_len=6):
    """缠论核心算法：包含处理→分型→笔→中枢
    min_stroke_len: 笔的最小间隔（动态参数，默认6）
    """
    mh, ml = [], []
    tr = 0
    for i in range(len(h)):
        if not mh: mh.append(h[i]); ml.append(l[i]); continue
        if (h[i] <= mh[-1] and l[i] >= ml[-1]) or (h[i] >= mh[-1] and l[i] <= ml[-1]):
            if tr >= 0: mh[-1] = max(mh[-1], h[i]); ml[-1] = max(ml[-1], l[i])
            else: mh[-1] = min(mh[-1], h[i]); ml[-1] = min(ml[-1], l[i])
        else:
            mh.append(h[i]); ml.append(l[i])
            if h[i] > mh[-2] and l[i] > ml[-2]: tr = 1
            elif h[i] < mh[-2] and l[i] < ml[-2]: tr = -1
    m = len(mh)

    top, bot = np.zeros(m), np.zeros(m)
    for i in range(3, m - 3):
        if all(mh[i] > mh[i - j] for j in range(1, 4)) and all(mh[i] >= mh[i + j] for j in range(1, 4)):
            top[i] = 1
        if all(ml[i] < ml[i - j] for j in range(1, 4)) and all(ml[i] <= ml[i + j] for j in range(1, 4)):
            bot[i] = 1

    strokes = []
    li, lt, lp = -1, 0, 0
    for i in range(m):
        if top[i] and lt == -1 and i - li >= min_stroke_len:
            strokes.append((li, i, 1, mh[i], ml[li], '顶')); li, lt, lp = i, 1, mh[i]
        if top[i] and lt == 0: li, lt, lp = i, 1, mh[i]
        if bot[i] and lt == 1 and i - li >= min_stroke_len:
            strokes.append((li, i, -1, mh[li], ml[i], '底')); li, lt, lp = i, -1, ml[i]
        if bot[i] and lt == 0: li, lt, lp = i, -1, ml[i]

    pivots = []
    for i in range(len(strokes)-2):
        s = [strokes[i], strokes[i+1], strokes[i+2]]
        zl = max(min(s[0][3],s[0][4]), min(s[1][3],s[1][4]), min(s[2][3],s[2][4]))
        zh = min(max(s[0][3],s[0][4]), max(s[1][3],s[1][4]), max(s[2][3],s[2][4]))
        if zl < zh: pivots.append((i, i+2, zh, zl))
    return strokes, pivots, m


def classify_market(strokes, pivots):
    """
    缠论走势分类：用中枢结构判断当前市场状态（方向五）
    
    核心思想：
      - 连续 2+ 个中枢同向移动 → 趋势（trend_up / trend_down）
      - 中枢重叠或方向不定 → 盘整（range）
    
    Returns:
        'trend_up'   上升趋势 —— 只做多，不做空
        'trend_down' 下降趋势 —— 只做空，不做多
        'range'      盘整震荡 —— 双向交易但收紧过滤
    """
    if len(pivots) < 2:
        # 中枢不足 → 用最近 3 笔的方向倾向判断
        if len(strokes) >= 3:
            recent = strokes[-3:]
            up_vol = sum(abs(float(s[3]) - float(s[4])) for s in recent if s[2] == 1)
            dn_vol = sum(abs(float(s[3]) - float(s[4])) for s in recent if s[2] == -1)
            if up_vol > dn_vol * 2.0:
                return 'trend_up'
            elif dn_vol > up_vol * 2.0:
                return 'trend_down'
        return 'range'

    last_p = pivots[-1]    # (ps, pe, upper, lower)
    prev_p = pivots[-2]

    upper_diff = float(last_p[2]) - float(prev_p[2])
    lower_diff = float(last_p[3]) - float(prev_p[3])
    mid_diff = (upper_diff + lower_diff) / 2  # 中枢中轴偏移

    # 以中枢宽度为基准衡量偏移幅度
    prev_width = float(prev_p[2]) - float(prev_p[3])
    threshold = prev_width * 0.3 if prev_width > 0 else 0

    if mid_diff > threshold:
        return 'trend_up'
    elif mid_diff < -threshold:
        return 'trend_down'
    else:
        return 'range'


def _load_15m_df(pair):
    """加载15m数据并计算次级别RSI/Volume指标（方向三）"""
    pair_file = pair.replace("/", "").replace(":", "")
    # 与 engine 相同的 BASE_DIR 解析逻辑
    base = Path(__file__).resolve().parent.parent.parent.parent
    for sub in ['freqtrade/user_data/data/okx',
                'freqtrade/user_data/data/binance',
                'freqtrade/user_data/data/bybit']:
        fp = base / sub / f"{pair_file}-15m.feather"
        if fp.exists():
            df = pd.read_feather(fp)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df['rsi'] = ta.RSI(df, timeperiod=14)
            df['vol_ma'] = df['volume'].rolling(20).mean()
            df['vol_ratio'] = df['volume'] / df['vol_ma']
            return df
    return None


def _check_15m(df_15m, ts, direction):
    """
    15m次级别逆向过滤（方向三）
    
    只拦截 15m 趋势与 1h 信号方向严重背离的情况：
    - 做多：最后3根15m RSI持续下降（RSI仍在加速跌）→ 拦截
    - 做空：最后3根15m RSI持续上升（RSI仍在加速涨）→ 拦截
    
    其他情况放行（常态回调或盘整不拦截）
    """
    last_3 = df_15m[df_15m.index <= ts].tail(3)
    if len(last_3) < 3:
        return True
    
    rsi = last_3['rsi'].values
    
    if direction == 'long':
        # 仅当 RSI 连续 3 根加速下跌时拦截（15m 还在恐慌抛售）
        if rsi[-1] < rsi[-2] < rsi[-3] and rsi[-1] < 35:
            return False
    else:
        # 仅当 RSI 连续 3 根加速上涨时拦截（15m 还在狂热追涨）
        if rsi[-1] > rsi[-2] > rsi[-3] and rsi[-1] > 65:
            return False
    
    return True


class RealChanTheory(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = '1h'
    can_short = True
    startup_candle_count = 500
    use_exit_signal = False
    minimal_roi = {"240": 0.015, "120": 0.025, "60": 0.04, "30": 0.06, "0": 0.10}
    stoploss = -0.015  # 1.5% 适应多币种
    trailing_stop = True
    trailing_stop_positive = 0.008
    trailing_stop_positive_offset = 0.03

    def populate_indicators(self, df, metadata):
        h, l, c, v = df['high'].values, df['low'].values, df['close'].values, df['volume'].values
        n = len(df)

        df['ema_50'] = ta.EMA(df, timeperiod=50)
        df['ema_200'] = ta.EMA(df, timeperiod=200)
        df['atr'] = ta.ATR(df, timeperiod=14)
        df['atr_pct'] = df['atr'] / df['close'] * 100
        macd = ta.MACD(df); df['macd'] = macd['macd']; df['macdhist'] = macd['macdhist']
        df['rsi'] = ta.RSI(df, timeperiod=14)
        df['vol_ma'] = df['volume'].rolling(30).mean()
        df['vol_ratio'] = v / df['vol_ma']

        # ── ATR动态参数（方向七 — 留空，固定阈值更稳定） ──

        # ── MACD 背驰 ──
        df['price_low'] = df['low'].rolling(60).min()
        df['price_high'] = df['high'].rolling(60).max()
        df['price_low_prev'] = df['low'].shift(30).rolling(60).min()
        df['price_high_prev'] = df['high'].shift(30).rolling(60).max()
        df['macd_min'] = df['macd'].rolling(60).min()
        df['macd_max'] = df['macd'].rolling(60).max()
        df['macd_min_prev'] = df['macd'].shift(30).rolling(60).min()
        df['macd_max_prev'] = df['macd'].shift(30).rolling(60).max()
        df['div_bull'] = ((df['price_low'] < df['price_low_prev'] * 0.998) & (df['macd_min'] > df['macd_min_prev'] * 1.005)).astype(int)
        df['div_bear'] = ((df['price_high'] > df['price_high_prev'] * 1.002) & (df['macd_max'] < df['macd_max_prev'] * 0.995)).astype(int)

        # ── 缠论结构 ──
        strokes, pivots, m = get_strokes_and_pivots(h, l)

        # ── 15m次级别数据加载（方向三） ──
        pair_name = metadata.get('pair', '')
        df_15m = _load_15m_df(pair_name)
        if df_15m is not None:
            pass
        elif pair_name:
            print(f'[DEBUG] 15m data NOT FOUND for {pair_name}')

        trend_up = c > df['ema_50'].values
        trend_dn = c < df['ema_50'].values

        df['enter_long'], df['enter_short'] = 0, 0
        df['enter_tag'] = ''

        for si, (sid, eid, stype, sh, sl, sf) in enumerate(strokes):
            ebar = min(n-1, int(eid * n / m) if m > 0 else 0)
            entry_price = c[ebar]
            pen_len = eid - sid

            # 找最近的枢轴及价格位置
            pivot_info = None
            for ps, pe, pu, pl in pivots:
                if ps <= si <= pe:
                    pivot_info = (pu, pl)
                    break

            # 价格相对于枢轴的位置
            if pivot_info:
                pu, pl = pivot_info
                if entry_price > pu: price_pos = '上方'
                elif entry_price < pl: price_pos = '下方'
                else: price_pos = '内部'
            else:
                price_pos = '无中枢'

            # 大级别趋势（EMA50 ≈ 2天，比EMA200反应更快）
            big_up = c[ebar] > df['ema_50'].iloc[ebar]
            big_dn = c[ebar] < df['ema_50'].iloc[ebar]
            h4_txt = '升势' if big_up else '降势'

            # ═══ 走势分类控制（方向五） ═══
            # 滚动分类：只用当前 stroke 之前的枢轴判断局部市场状态
            local_pivots = [p for p in pivots if p[1] <= si]
            local_state = classify_market(strokes[:si + 1], local_pivots)
            # 核心规则：趋势中只做一个方向 → 过滤逆势交易
            if local_state == 'trend_down' and stype == -1: continue
            if local_state == 'trend_up' and stype == 1: continue

            if stype == -1:  # 下跌笔结束 → 买入
                if not big_up: continue
                if price_pos == '上方': continue
                if df['atr_pct'].iloc[ebar] > 1.2: continue
                vol_ok = df['vol_ratio'].iloc[ebar] > 0.5

                if price_pos == '下方':
                    # 1买 + 15m确认
                    if vol_ok:
                        if df_15m is not None and not _check_15m(df_15m, df.index[ebar], 'long'):
                            continue
                        tag = f'1买_{h4_txt}_中枢下方_笔{si}({pen_len}K)'
                        df.at[df.index[max(0, ebar - 1)], 'enter_long'] = 1
                        df.at[df.index[max(0, ebar - 1)], 'enter_tag'] = tag

                elif price_pos in ('内部', '无中枢'):
                    # 3买 + 15m次级别确认（方向三）
                    if df['rsi'].iloc[ebar] > 35 and df['vol_ratio'].iloc[ebar] > 0.6:
                        if df_15m is not None and not _check_15m(df_15m, df.index[ebar], 'long'):
                            continue
                        tag = f'3买_{h4_txt}_中枢内_笔{si}({pen_len}K)'
                        df.at[df.index[max(0, ebar - 1)], 'enter_long'] = 1
                        df.at[df.index[max(0, ebar - 1)], 'enter_tag'] = tag

            if stype == 1:  # 上涨笔结束 → 卖出
                if not big_dn: continue
                if price_pos == '下方': continue
                if df['atr_pct'].iloc[ebar] > 1.2: continue
                vol_ok = df['vol_ratio'].iloc[ebar] > 0.5

                if price_pos == '上方':
                    # 1卖 + 15m确认
                    if vol_ok:
                        if df_15m is not None and not _check_15m(df_15m, df.index[ebar], 'short'):
                            continue
                        tag = f'1卖_{h4_txt}_中枢上方_笔{si}({pen_len}K)'
                        df.at[df.index[max(0, ebar - 1)], 'enter_short'] = 1
                        df.at[df.index[max(0, ebar - 1)], 'enter_tag'] = tag

                elif price_pos in ('内部', '无中枢'):
                    # 3卖 + 15m确认
                    if df['rsi'].iloc[ebar] > 50 and df['rsi'].iloc[ebar] < 75 and df['vol_ratio'].iloc[ebar] > 0.7:
                        if df_15m is not None and not _check_15m(df_15m, df.index[ebar], 'short'):
                            continue
                        tag = f'3卖_{h4_txt}_中枢内_笔{si}({pen_len}K)'
                        df.at[df.index[max(0, ebar - 1)], 'enter_short'] = 1
                        df.at[df.index[max(0, ebar - 1)], 'enter_tag'] = tag

        # ── 缠论结构出场信号（方向四） ──
        # 补充引擎的 trailing_stop，不是替代
        # 只在趋势明显终结或突破失败时触发
        df['exit_long'] = 0
        df['exit_short'] = 0

        for si, (sid, eid, stype, sh, sl, sf) in enumerate(strokes):
            ebar = min(n-1, int(eid * n / m) if m > 0 else 0)
            if si < 2:
                continue

            prev2 = strokes[si - 2]

            # 背驰出场：隔笔同向比较，力度减弱 ≥ 40% → 趋势衰竭退出
            # 保留 trailing_stop 吃主升浪，背驰是趋势末尾的安全带
            if stype == prev2[2]:  # 与 si-2 同向（跳过中间反向笔）
                curr_amp = abs(float(sh) - float(sl))
                prev2_amp = abs(float(prev2[3]) - float(prev2[4]))
                if prev2_amp > 0 and curr_amp < prev2_amp * 0.6:
                    if stype == 1:      # 上涨笔力度减弱 → 顶背驰 → 平多
                        df.at[df.index[max(0, ebar - 1)], 'exit_long'] = 1
                    else:               # 下跌笔力度减弱 → 底背驰 → 平空
                        df.at[df.index[max(0, ebar - 1)], 'exit_short'] = 1

        return df

    def populate_entry_trend(self, df, metadata): return df
    def populate_exit_trend(self, df, metadata):
        # 出场信号已在 populate_indicators 中通过缠论结构生成
        # 此处只做 pass-through，不清零 exit_long/exit_short
        return df
