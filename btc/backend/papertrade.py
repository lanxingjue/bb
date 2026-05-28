"""
模拟盘引擎 — 多币种同步时间轴版

修复：_run_all() 按时间轴同步推进所有币种，防止前视偏差。
出场顺序：止损 > 移动止盈 > 结构出场 > ROI
"""
import threading, time, json
from pathlib import Path
from typing import Optional
import pandas as pd
import numpy as np
from backtest_engine import load_strategy, DATA_DIR, FEE_CONFIG


class PaperTradingEngine:
    def __init__(self):
        self.strategy_name = "ChanTheoryScalp"
        self.pairs = ["BTC/USDT:USDT"]
        self.timeframe = "1m"
        self.leverage = 3.0
        self.fee = 0.0004
        self.slippage = 0.0015
        self.position_pct = 25.0
        self.max_positions = 2
        self.balance = 1000.0
        self.equity = 1000.0
        self.positions: dict = {}
        self.trades: list = []
        self.equity_curve: list = []
        self.signal_log: list = []
        self.daily_pnl: dict = {}
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._bar_idx: dict = {}  # 每个币种当前处理到的 bar 索引
        self._strat_cache = None
        self._dfs: dict = {}      # 所有币种的 df2（含信号）
        self._all_times: list = []  # 统一时间轴

    def start(self, config: dict = None):
        if self.running:
            return {"status": "already_running"}
        if config:
            if 'strategy' in config:
                config['strategy_name'] = config.pop('strategy')
            for k in ['strategy_name', 'pairs', 'timeframe', 'leverage', 'fee', 'slippage', 'position_pct', 'max_positions']:
                if k in config:
                    setattr(self, k, config[k])
            self.balance = config.get("initial_balance", self.balance)
            self.equity = self.balance

        self.positions, self.trades, self.equity_curve = {}, [], []
        self.signal_log, self.daily_pnl = [], {}
        self._bar_idx = {}
        self._dfs = {}
        self._all_times = []
        self._strat_cache = None

        self._run_all()

        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return {"status": "started", "config": self._get_config()}

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        return {"status": "stopped"}

    def get_status(self) -> dict:
        with self._lock:
            pt = self._paired_trades()
            return {
                "running": self.running,
                "balance": round(self.balance, 2),
                "equity": round(self.equity, 2),
                "total_trades": len(pt),
                "open_positions": len(self.positions),
                "positions": list(self.positions.values()),
                "paired_trades": pt,
                "recent_signals": self.signal_log[-30:],
                "equity_curve": self.equity_curve[-500:],
                "config": self._get_config(),
            }

    def _loop(self):
        print(f"[PaperTrade] 启动: {self.strategy_name} @ {self.timeframe}")
        while self.running:
            try:
                self._check_new_data()
            except Exception as e:
                print(f"[PaperTrade] 错误: {e}")
            time.sleep(10 if self.timeframe == '1m' else 60)

    def _load_df(self, pair):
        pf = pair.replace("/", "").replace(":", "")
        fp = DATA_DIR / f"{pf}-{self.timeframe}.feather"
        if not fp.exists():
            return None
        df = pd.read_feather(fp)
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        return df

    def _calc_signals(self, pair, df):
        """计算策略信号"""
        if not self._strat_cache:
            try:
                self._strat_cache = load_strategy(self.strategy_name)
            except Exception as e:
                print(f"[PaperTrade] 策略加载失败: {e}")
                return None
        meta = {"pair": pair}
        df2 = self._strat_cache.populate_indicators(df.copy(), meta)
        df2 = self._strat_cache.populate_entry_trend(df2, meta)
        df2 = self._strat_cache.populate_exit_trend(df2, meta)
        return df2

    # ─── 同步时间轴模式 ───

    def _run_all(self):
        """同步时间轴：所有币种按统一时间戳推进"""
        # 1. 加载所有币种数据 + 计算信号
        dfs = {}
        for pair in self.pairs:
            df = self._load_df(pair)
            if df is None or len(df) < 2000:
                continue
            df2 = self._calc_signals(pair, df)
            if df2 is not None:
                dfs[pair] = df2

        if not dfs:
            return

        self._dfs = dfs

        # 2. 找到公共时间范围（取所有币种都有数据的范围）
        all_starts = [df.index[0] for df in dfs.values()]
        all_ends = [df.index[-1] for df in dfs.values()]
        common_start = max(all_starts)
        common_end = min(all_ends)

        # 3. 对每个币种截取公共时间范围，记录起始索引
        for pair, df2 in dfs.items():
            mask = (df2.index >= common_start) & (df2.index <= common_end)
            self._bar_idx[pair] = df2[mask].index[0]  # 起始时间戳

        # 4. 生成统一时间轴（取第一个币种的时间轴，其他币种在对应时间戳查数据）
        first_pair = list(dfs.keys())[0]
        self._all_times = dfs[first_pair][
            (dfs[first_pair].index >= common_start) & (dfs[first_pair].index <= common_end)
        ].index.tolist()

        print(f"[PaperTrade] 同步回放: {len(self._all_times)}根K线, {list(dfs.keys())}")
        self._tick_batch(self._all_times)

    def _check_new_data(self):
        """检查增量新数据（同步处理）"""
        if not self._dfs:
            return

        for pair in self._dfs:
            df = self._load_df(pair)
            if df is None:
                continue
            last_bar = self._bar_idx.get(pair)
            if last_bar is not None:
                new = df[df.index > last_bar]
                if len(new) > 0:
                    # 有新增数据，重新加载全部数据并重新计算信号
                    print(f"[PaperTrade] 新数据: {pair} +{len(new)}根")
                    df2 = self._calc_signals(pair, df)
                    if df2 is not None:
                        self._dfs[pair] = df2
                        self._bar_idx[pair] = df.index[-1]
                        # 把新时间戳加入统一时间轴
                        new_times = [t for t in df2.index if t > (self._all_times[-1] if self._all_times else df2.index[0])]
                        self._all_times.extend(new_times)

    def _tick_batch(self, times):
        """批量处理一批时间戳（同步推进所有币种）"""
        for ts in times:
            # 先处理所有持仓的出场
            for pair in list(self.positions.keys()):
                df2 = self._dfs.get(pair)
                if df2 is None:
                    continue
                try:
                    row = df2.loc[ts]
                except KeyError:
                    continue
                self._process_exit(pair, row, ts)

            # 再处理入场
            for pair, df2 in self._dfs.items():
                if pair in self.positions:
                    continue
                if len(self.positions) >= self.max_positions:
                    continue
                try:
                    row = df2.loc[ts]
                except KeyError:
                    continue
                self._process_entry(pair, row, ts)

            # 更新权益曲线（用第一个有数据的币种时间戳）
            eq = self.balance
            for p, pos in self.positions.items():
                df2 = self._dfs.get(p)
                if df2 is None:
                    continue
                try:
                    c = df2.loc[ts, "close"]
                except KeyError:
                    continue
                m = pos["size"] * pos["entry_price"]
                u = (c - pos["entry_price"]) * pos["size"] * pos["leverage"] if pos["side"] == "long" else \
                    (pos["entry_price"] - c) * pos["size"] * pos["leverage"]
                eq += m + u
            self.equity = eq
            self.equity_curve.append({"timestamp": str(ts), "equity": round(eq, 2), "balance": round(self.balance, 2)})

            # 更新 bar 索引
            for pair in self._dfs:
                self._bar_idx[pair] = ts

    def _process_entry(self, pair, row, ts):
        """处理入场"""
        for side, col in [("long", "enter_long"), ("short", "enter_short")]:
            if row.get(col) == 1:
                tag = str(row.get("enter_tag", ""))
                price = float(row["close"])
                price *= 1 + self.slippage if side == "long" else 1 - self.slippage

                n_pos = len(self.positions)
                if n_pos == 0: pct = 30
                elif n_pos == 1: pct = 20
                elif n_pos == 2: pct = 15
                else: pct = 10

                amt = max(10, min(self.balance * pct / 100, self.balance * 0.4))
                size = amt / price
                cost = size * price
                fee = cost * self.leverage * self.fee
                if cost + fee <= self.balance:
                    self.balance -= cost + fee
                    self.positions[pair] = {"pair": pair, "side": side,
                        "size": round(size, 6), "entry_price": round(price, 2),
                        "entry_time": str(ts), "enter_tag": tag,
                        "highest": price, "lowest": price, "leverage": self.leverage}
                    self.trades.append({"pair": pair, "type": "entry", "side": side,
                        "price": round(price, 2), "size": round(size, 6),
                        "timestamp": str(ts), "enter_tag": tag})
                    self.signal_log.append({"time": str(ts), "pair": pair,
                        "action": "买入" if side == "long" else "卖出", "tag": tag})
                break

    def _process_exit(self, pair, row, ts):
        """处理出场（止损优先于结构出场）"""
        pos = self.positions.get(pair)
        if not pos:
            return

        cp = float(row["close"])
        ep = pos["entry_price"]
        bh = float(row.get("high", cp))
        bl = float(row.get("low", cp))
        pos["highest"] = max(pos["highest"], bh) if pos["side"] == "long" else pos["highest"]
        pos["lowest"] = min(pos["lowest"], bl) if pos["side"] == "short" else pos["lowest"]

        s, rsn = False, ""

        # ① 止损（优先）
        sl = abs(getattr(self._strat_cache, 'stoploss', 0.015))
        if (pos["side"] == "long" and bl < ep * (1 - sl)) or \
           (pos["side"] == "short" and bh > ep * (1 + sl)):
            s, rsn = True, "止损"

        # ② 移动止盈
        if not s:
            tp = getattr(self._strat_cache, 'trailing_stop_positive', 0.008)
            to = getattr(self._strat_cache, 'trailing_stop_positive_offset', 0.03)
            if pos["side"] == "long" and pos["highest"] > ep * (1 + to) and bl < pos["highest"] * (1 - tp):
                s, rsn = True, "移动止盈"
            elif pos["side"] == "short" and pos["lowest"] < ep * (1 - to) and bh > pos["lowest"] * (1 + tp):
                s, rsn = True, "移动止盈"

        # ③ 结构出场（背驰）
        if not s:
            if (pos["side"] == "long" and row.get("exit_long") == 1) or \
               (pos["side"] == "short" and row.get("exit_short") == 1):
                s, rsn = True, "结构出场"

        # ④ ROI 止盈
        if not s:
            hold_h = (ts - pd.Timestamp(pos["entry_time"])).total_seconds() / 3600
            pnl_pct = (cp - ep) / ep * 100 if pos["side"] == "long" else (ep - cp) / ep * 100
            if pnl_pct > 0:
                roi = getattr(self._strat_cache, 'minimal_roi', {"240": 0.015})
                best = 999.0
                for mins_str, ratio in sorted(roi.items(), key=lambda x: int(x[0])):
                    if hold_h * 60 >= int(mins_str):
                        best = abs(ratio) * 100
                if pnl_pct >= best:
                    s, rsn = True, "止盈"

        if s:
            xp = cp * (1 - self.slippage) if pos["side"] == "long" else cp * (1 + self.slippage)
            sz = pos["size"]
            pnl = (xp - ep) * sz * pos["leverage"] if pos["side"] == "long" else (ep - xp) * sz * pos["leverage"]
            pnl_pct = pnl / (sz * ep) * 100
            fee = xp * sz * pos["leverage"] * self.fee
            self.balance += sz * ep + pnl - fee
            self.trades.append({"pair": pair, "type": "exit", "side": pos["side"],
                "price": round(xp, 2), "size": sz, "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 4), "timestamp": str(ts),
                "exit_reason": f"{pos['side']}_{rsn}", "leverage": pos["leverage"],
                "entry_price": pos["entry_price"]})
            self.signal_log.append({"time": str(ts), "pair": pair, "action": "平仓",
                "price": round(xp, 2), "pnl": round(pnl, 2), "reason": rsn})
            # 记录每日盈亏
            dk = str(ts.date())
            self.daily_pnl[dk] = self.daily_pnl.get(dk, 0) + pnl
            del self.positions[pair]

    def _paired_trades(self) -> list:
        pt, pending, cum = [], {}, 0.0
        for t in self.trades:
            key = (t["pair"], t["side"])
            if t["type"] == "entry":
                pending[key] = t
            elif t["type"] == "exit" and key in pending:
                e = pending.pop(key)
                cum += t.get("pnl", 0)
                try:
                    h = (pd.Timestamp(t["timestamp"]) - pd.Timestamp(e["timestamp"])).total_seconds() / 3600
                    d = f"{h:.0f}h" if h < 24 else f"{h/24:.1f}d"
                except:
                    d = ""
                pt.append({"entry_time": str(e["timestamp"])[:16], "exit_time": str(t["timestamp"])[:16],
                    "pair": t["pair"], "direction": t["side"],
                    "entry_price": e["price"], "exit_price": t["price"],
                    "pnl": round(t.get("pnl", 0), 2), "pnl_pct": round(t.get("pnl_pct", 0), 2),
                    "enter_tag": (e.get("enter_tag", "") or "")[:30],
                    "exit_reason": t.get("exit_reason", ""), "duration": d,
                    "cumulative_pnl": round(cum, 2)})
        return pt

    def _get_config(self):
        return {k: getattr(self, k) for k in ['strategy_name', 'pairs', 'timeframe', 'leverage',
            'fee', 'slippage', 'position_pct', 'max_positions']}
