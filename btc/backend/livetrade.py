"""
实盘引擎 v2 — 完整风控系统

对接交易所 API 真实交易，完整实现策略的风控参数：
  - stoploss / trailing_stop / minimal_roi（从策略读取）
  - 每日亏损限额 / 最大回撤限额（前端可配）
  - Webhook 通知（每笔交易推送）
"""
import threading, time, json
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone, date
import pandas as pd
import ccxt
from backtest_engine import load_strategy


class LiveTradingEngine:
    def __init__(self):
        self.exchange_name = "okx"
        self.strategy_name = "ChanTheoryScalp"
        self.pairs = ["BTC/USDT:USDT"]
        self.timeframe = "1h"
        self.leverage = 3.0
        self.max_positions = 2
        self.position_pct = 20.0
        # 风控参数
        self.daily_loss_limit = -10.0   # 当日亏损超过 10% 自动停止
        self.max_drawdown = -25.0       # 总回撤超过 25% 自动停止
        self.webhook_url = ""            # 交易通知 URL
        
        self.exchange: Optional[ccxt.Exchange] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._strat_cache = None
        
        self.trades: list = []
        self.signal_log: list = []
        self.equity_curve: list = []
        self._last_candle: dict = {}
        self._pos_tracker: dict = {}  # pair → {highest, lowest, entry_time}
        self._start_equity = 0.0
        self._daily_pnl = 0.0
        self._today = date.today()

    def start(self, config: dict = None) -> dict:
        if self.running:
            return {"status": "already_running"}
        if config:
            for k in ['exchange_name', 'strategy_name', 'pairs', 'timeframe',
                      'leverage', 'max_positions', 'position_pct',
                      'daily_loss_limit', 'max_drawdown', 'webhook_url']:
                if k in config:
                    setattr(self, k, config[k])
            if 'strategy' in config:
                self.strategy_name = config.pop('strategy')

        cfg_path = Path(__file__).resolve().parent.parent / "config.json"
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
            ex_cfg = cfg.get("exchange", {})
        except:
            return {"status": "error", "message": "config.json 读取失败"}

        try:
            exchange_class = getattr(ccxt, self.exchange_name)
            self.exchange = exchange_class({
                'apiKey': ex_cfg.get('key', ''),
                'secret': ex_cfg.get('secret', ''),
                'password': ex_cfg.get('password', ''),
                'options': {'defaultType': 'swap'},
                'enableRateLimit': True,
            })
            bal = self.exchange.fetch_balance()
            self._start_equity = float(bal.get('USDT', {}).get('total', 0))
            print(f"[LiveTrade] 连接 {self.exchange_name} 成功, 余额: ${self._start_equity:.2f}")
        except Exception as e:
            return {"status": "error", "message": f"交易所连接失败: {e}"}

        try:
            for pair in self.pairs:
                mid = self.exchange.market_id(pair)
                self.exchange.set_leverage(self.leverage, mid)
        except:
            pass

        self._load_strategy()
        self.running = True
        self.trades, self.signal_log, self.equity_curve = [], [], []
        self._last_candle, self._pos_tracker = {}, {}
        self._daily_pnl = 0.0
        self._today = date.today()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return {"status": "started", "config": self._get_config()}

    def stop(self) -> dict:
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        return {"status": "stopped"}

    def update_config(self, config: dict) -> dict:
        """运行时更新配置（不重启引擎）"""
        for k in ['daily_loss_limit', 'max_drawdown', 'webhook_url',
                  'max_positions', 'position_pct']:
            if k in config:
                setattr(self, k, config[k])
        return {"status": "ok", "config": self._get_config()}

    def close_all(self) -> dict:
        if not self.exchange:
            return {"status": "error", "message": "未连接"}
        try:
            positions = self.exchange.fetch_positions()
            closed = 0
            for pos in positions:
                if abs(float(pos['contracts'])) > 0:
                    side = 'sell' if float(pos['contracts']) > 0 else 'buy'
                    amt = abs(float(pos['contracts']))
                    self.exchange.create_market_order(pos['symbol'], side, amt)
                    closed += 1
            return {"status": "ok", "closed": closed}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_status(self) -> dict:
        with self._lock:
            try:
                bal = self.exchange.fetch_balance() if self.exchange else {}
                positions = self.exchange.fetch_positions() if self.exchange else []

                total = float(bal.get('USDT', {}).get('total', 0))
                free = float(bal.get('USDT', {}).get('free', 0))
                used = float(bal.get('USDT', {}).get('used', 0))
                
                today = date.today()
                if today != self._today:
                    self._daily_pnl = 0.0
                    self._today = today

                open_positions = []
                total_upnl = 0.0
                for p in positions:
                    if abs(float(p['contracts'])) > 0:
                        upnl = float(p['unrealizedPnl'])
                        total_upnl += upnl
                        tracker = self._pos_tracker.get(p['symbol'], {})
                        open_positions.append({
                            "pair": p['symbol'],
                            "side": "long" if float(p['contracts']) > 0 else "short",
                            "size": abs(float(p['contracts'])),
                            "entry_price": float(p['entryPrice']),
                            "mark_price": float(p.get('markPrice', 0)),
                            "pnl": round(upnl, 2),
                            "pnl_pct": round(float(p.get('percentage', 0)), 2),
                            "liquidation": float(p.get('liquidationPrice', 0)),
                            "highest": tracker.get('highest', 0),
                            "lowest": tracker.get('lowest', 0),
                        })

                paired = self._paired_trades()
                session_pnl = sum(t.get('pnl', 0) for t in self.trades if t['type'] == 'exit')
                total_pnl = session_pnl + total_upnl
                dd_pct = (total_pnl / self._start_equity * 100) if self._start_equity > 0 else 0

                return {
                    "running": self.running,
                    "exchange": self.exchange_name,
                    "balance": round(total, 2),
                    "free": round(free, 2),
                    "used": round(used, 2),
                    "start_equity": round(self._start_equity, 2),
                    "unrealized_pnl": round(total_upnl, 2),
                    "session_pnl": round(session_pnl, 2),
                    "daily_pnl": round(self._daily_pnl, 2),
                    "open_positions": len(open_positions),
                    "positions": open_positions,
                    "paired_trades": paired,
                    "trades": self.trades[-100:],
                    "recent_signals": self.signal_log[-30:],
                    "equity_curve": self.equity_curve[-500:],
                    "drawdown_pct": round(dd_pct, 2),
                    "config": self._get_config(),
                }
            except Exception as e:
                return {"running": self.running, "error": str(e), "config": self._get_config()}

    def _load_strategy(self):
        try:
            self._strat_cache = load_strategy(self.strategy_name)
        except Exception as e:
            print(f"[LiveTrade] 策略加载失败: {e}")

    def _get_strat_param(self, name, default):
        return getattr(self._strat_cache, name, default) if self._strat_cache else default

    def _loop(self):
        print(f"[LiveTrade] 启动: {self.strategy_name} | 风控: 日亏{self.daily_loss_limit}% 回撤{self.max_drawdown}%")
        while self.running:
            try:
                self._tick()
            except Exception as e:
                print(f"[LiveTrade] 错误: {e}")
            time.sleep(60)

    def _tick(self):
        if not self.exchange:
            return
        for pair in self.pairs:
            self._process_pair(pair)
        self._check_risk_limits()

    def _process_pair(self, pair):
        try:
            mid = self.exchange.market_id(pair)
            candles = self.exchange.fetch_ohlcv(mid, self.timeframe, limit=200)
            if len(candles) < 50:
                return

            df = pd.DataFrame(candles, columns=['timestamp','open','high','low','close','volume'])
            df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('date', inplace=True)

            last_ts = self._last_candle.get(pair)
            if last_ts is not None:
                new_bars = df[df['timestamp'] > last_ts]
                if len(new_bars) == 0:
                    return

            if not self._strat_cache:
                self._load_strategy()
            if not self._strat_cache:
                return

            meta = {"pair": pair}
            df2 = self._strat_cache.populate_indicators(df.copy(), meta)
            df2 = self._strat_cache.populate_entry_trend(df2, meta)
            df2 = self._strat_cache.populate_exit_trend(df2, meta)

            last_row = df2.iloc[-1]
            last_ts = int(df2.index[-1].timestamp() * 1000)
            self._last_candle[pair] = last_ts

            self._check_and_trade(pair, last_row, df2.index[-1], df2)

            try:
                bal = self.exchange.fetch_balance()
                eq = float(bal.get('USDT', {}).get('total', 0))
                self.equity_curve.append({"timestamp": str(df2.index[-1]), "equity": round(eq, 2)})
            except:
                pass
        except Exception as e:
            print(f"[LiveTrade] {pair}: {e}")

    def _check_and_trade(self, pair, row, ts, df2):
        """检查信号并交易（完整风控）"""
        try:
            positions = self.exchange.fetch_positions()
            current_pos = None
            for p in positions:
                if p['symbol'] == pair and abs(float(p['contracts'])) > 0:
                    current_pos = p
                    break
        except:
            current_pos = None

        has_position = current_pos is not None
        close_price = float(row['close'])
        high_price = float(row['high'])
        low_price = float(row['low'])

        # ── 更新价格跟踪 ──
        if pair not in self._pos_tracker:
            self._pos_tracker[pair] = {'highest': 0, 'lowest': 999999, 'entry_time': ''}

        # ── 出场检查 ──
        if has_position:
            pos_side = "long" if float(current_pos['contracts']) > 0 else "short"
            entry_price = float(current_pos['entryPrice'])
            self._pos_tracker[pair]['highest'] = max(self._pos_tracker[pair]['highest'], high_price)
            self._pos_tracker[pair]['lowest'] = min(self._pos_tracker[pair]['lowest'], low_price)
            if not self._pos_tracker[pair]['entry_time']:
                self._pos_tracker[pair]['entry_time'] = str(ts)

            should_exit = False
            reason = ""
            strat = self._strat_cache

            # ① 止损 (从策略读取)
            sl = abs(self._get_strat_param('stoploss', 0.015))
            if (pos_side == "long" and low_price < entry_price * (1 - sl)) or \
               (pos_side == "short" and high_price > entry_price * (1 + sl)):
                should_exit, reason = True, "止损"

            # ② 移动止盈 (从策略读取)
            if not should_exit:
                tp = self._get_strat_param('trailing_stop_positive', 0.008)
                to = self._get_strat_param('trailing_stop_positive_offset', 0.03)
                if pos_side == "long":
                    if self._pos_tracker[pair]['highest'] > entry_price * (1 + to):
                        if low_price < self._pos_tracker[pair]['highest'] * (1 - tp):
                            should_exit, reason = True, "移动止盈"
                else:
                    if self._pos_tracker[pair]['lowest'] < entry_price * (1 - to):
                        if high_price > self._pos_tracker[pair]['lowest'] * (1 + tp):
                            should_exit, reason = True, "移动止盈"

            # ③ 结构出场 (策略信号)
            if not should_exit:
                if (pos_side == "long" and row.get("exit_long") == 1) or \
                   (pos_side == "short" and row.get("exit_short") == 1):
                    should_exit, reason = True, "结构出场"

            # ④ ROI 止盈 (从策略读取)
            if not should_exit:
                hold_h = (ts - pd.Timestamp(self._pos_tracker[pair]['entry_time'])).total_seconds() / 3600 if self._pos_tracker[pair]['entry_time'] else 0
                pnl_pct = (close_price - entry_price) / entry_price * 100 if pos_side == "long" else (entry_price - close_price) / entry_price * 100
                if pnl_pct > 0:
                    roi = self._get_strat_param('minimal_roi', {"240": 0.015})
                    best = 999.0
                    for mins_str, ratio in sorted(roi.items(), key=lambda x: int(x[0])):
                        if hold_h * 60 >= int(mins_str):
                            best = abs(ratio) * 100
                    if pnl_pct >= best:
                        should_exit, reason = True, "止盈"

            if should_exit:
                side = 'sell' if pos_side == 'long' else 'buy'
                amt = abs(float(current_pos['contracts']))
                try:
                    order = self.exchange.create_market_order(pair, side, amt)
                    fill_price = order.get('price', close_price)
                    pnl = (fill_price - entry_price) * amt if pos_side == "long" else (entry_price - fill_price) * amt
                    self.trades.append({"pair": pair, "type": "exit", "side": pos_side,
                        "price": fill_price, "amount": amt, "pnl": round(pnl, 2),
                        "timestamp": str(ts), "exit_reason": reason})
                    self.signal_log.append({"time": str(ts), "pair": pair, "action": "平仓", "reason": reason})
                    self._daily_pnl += pnl
                    self._send_webhook(f"🔴 平仓 {pair} {pos_side} | {reason} | PnL: {pnl:+.2f}")
                except Exception as e:
                    print(f"[LiveTrade] 平仓失败: {e}")
                finally:
                    self._pos_tracker.pop(pair, None)

        # ── 入场检查 ──
        if not has_position and len(self._get_open_positions_count()) < self.max_positions:
            side = None
            tag = ""
            if row.get("enter_long") == 1:
                side, tag = "long", str(row.get("enter_tag", ""))
            elif row.get("enter_short") == 1:
                side, tag = "short", str(row.get("enter_tag", ""))

            if side:
                try:
                    bal = self.exchange.fetch_balance()
                    equity = float(bal.get('USDT', {}).get('total', 0))
                    amt_usdt = equity * self.position_pct / 100
                    size = amt_usdt / close_price
                    order_side = 'buy' if side == 'long' else 'sell'
                    order = self.exchange.create_market_order(pair, order_side, size)
                    fill_price = order.get('price', close_price)
                    self.trades.append({"pair": pair, "type": "entry", "side": side,
                        "price": fill_price, "amount": size, "timestamp": str(ts), "enter_tag": tag})
                    self.signal_log.append({"time": str(ts), "pair": pair,
                        "action": "买入" if side == "long" else "卖出", "tag": tag})
                    self._pos_tracker[pair] = {'highest': fill_price, 'lowest': fill_price, 'entry_time': str(ts)}
                    self._send_webhook(f"🟢 开仓 {pair} {side} @ ${fill_price:.2f} | {tag}")
                except Exception as e:
                    print(f"[LiveTrade] 开仓失败: {e}")

    def _check_risk_limits(self):
        """风控检查：每日亏损限额 + 最大回撤"""
        try:
            bal = self.exchange.fetch_balance()
            equity = float(bal.get('USDT', {}).get('total', 0))
        except:
            return

        # 每日亏损
        daily_pnl_pct = (self._daily_pnl / self._start_equity * 100) if self._start_equity > 0 else 0
        if daily_pnl_pct < self.daily_loss_limit:
            msg = f"⛔ 每日亏损限额触发: {daily_pnl_pct:.1f}% < {self.daily_loss_limit}%，已停止交易"
            print(f"[LiveTrade] {msg}")
            self._send_webhook(msg)
            self.running = False
            return

        # 总回撤
        total_pnl = equity - self._start_equity
        dd_pct = (total_pnl / self._start_equity * 100) if self._start_equity > 0 else 0
        if dd_pct < self.max_drawdown:
            msg = f"⛔ 最大回撤限额触发: {dd_pct:.1f}% < {self.max_drawdown}%，已停止交易"
            print(f"[LiveTrade] {msg}")
            self._send_webhook(msg)
            self.running = False
            return

    def _send_webhook(self, message: str):
        if not self.webhook_url:
            return
        try:
            import urllib.request
            data = json.dumps({"text": message, "msgtype": "text"}).encode()
            req = urllib.request.Request(self.webhook_url, data=data,
                headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=5)
        except:
            pass

    def _get_open_positions_count(self) -> int:
        try:
            positions = self.exchange.fetch_positions()
            return sum(1 for p in positions if abs(float(p['contracts'])) > 0)
        except:
            return 0

    def _paired_trades(self) -> list:
        pt, pending, cum = [], {}, 0.0
        for t in self.trades:
            key = (t["pair"], t["side"])
            if t["type"] == "entry":
                pending[key] = t
            elif t["type"] == "exit" and key in pending:
                e = pending.pop(key)
                cum += t.get("pnl", 0)
                pt.append({"entry_time": str(e["timestamp"])[:16], "exit_time": str(t["timestamp"])[:16],
                    "pair": t["pair"], "direction": t["side"],
                    "entry_price": e["price"], "exit_price": t["price"],
                    "pnl": round(t.get("pnl", 0), 2),
                    "enter_tag": (e.get("enter_tag", "") or "")[:30],
                    "exit_reason": t.get("exit_reason", ""), "cumulative_pnl": round(cum, 2)})
        return pt

    def _get_config(self):
        return {"exchange": self.exchange_name, "strategy": self.strategy_name,
            "pairs": self.pairs, "timeframe": self.timeframe, "leverage": self.leverage,
            "position_pct": self.position_pct, "max_positions": self.max_positions,
            "daily_loss_limit": self.daily_loss_limit, "max_drawdown": self.max_drawdown,
            "webhook_url": self.webhook_url[:40] if self.webhook_url else ""}
