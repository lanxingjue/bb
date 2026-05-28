"""
实盘引擎 — 通过交易所 API 直接交易。

与模拟盘引擎的区别：
  模拟盘: feather 数据 → 本地模拟交易
  实盘:   ccxt 连接交易所 → 真实下单

API 端点（通过 main.py）:
  POST /api/livetrade/start
  GET  /api/livetrade/status
  POST /api/livetrade/stop
  POST /api/livetrade/close-all
"""
import threading, time, json
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

import pandas as pd
import ccxt

from backtest_engine import load_strategy, DATA_DIR


class LiveTradingEngine:
    def __init__(self):
        self.exchange_name = "okx"
        self.strategy_name = "ChanTheoryScalp"
        self.pairs = ["BTC/USDT:USDT"]
        self.timeframe = "1h"
        self.leverage = 3.0
        self.max_positions = 2
        self.position_pct = 20.0
        
        self.exchange: Optional[ccxt.Exchange] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._strat_cache = None
        
        # 交易记录
        self.trades: list = []
        self.signal_log: list = []
        self.equity_curve: list = []
        self._last_candle: dict = {}

    def start(self, config: dict = None) -> dict:
        if self.running:
            return {"status": "already_running"}
            
        if config:
            if 'strategy' in config:
                config['strategy_name'] = config.pop('strategy')
            for k in ['exchange_name', 'strategy_name', 'pairs', 'timeframe', 
                      'leverage', 'max_positions', 'position_pct']:
                if k in config:
                    setattr(self, k, config[k])

        # 读取 API 配置
        cfg_path = Path(__file__).resolve().parent.parent / "config.json"
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
            ex_cfg = cfg.get("exchange", {})
        except:
            return {"status": "error", "message": "无法读取 config.json"}

        # 连接交易所
        try:
            exchange_class = getattr(ccxt, self.exchange_name)
            self.exchange = exchange_class({
                'apiKey': ex_cfg.get('key', ''),
                'secret': ex_cfg.get('secret', ''),
                'password': ex_cfg.get('password', ''),
                'options': {'defaultType': 'swap'},
                'enableRateLimit': True,
            })
            # 测试连接
            self.exchange.fetch_balance()
            print(f"[LiveTrade] 连接 {self.exchange_name} 成功")
        except Exception as e:
            return {"status": "error", "message": f"交易所连接失败: {e}"}

        # 设置杠杆
        try:
            for pair in self.pairs:
                market_id = self.exchange.market_id(pair)
                self.exchange.set_leverage(self.leverage, market_id)
        except:
            pass  # 部分交易所不支持通过 API 设杠杆

        self.running = True
        self.trades, self.signal_log, self.equity_curve = [], [], []
        self._last_candle = {}
        self._strat_cache = None

        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return {"status": "started", "config": self._get_config()}

    def stop(self) -> dict:
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        return {"status": "stopped"}

    def close_all(self) -> dict:
        """平掉所有持仓"""
        if not self.exchange:
            return {"status": "error", "message": "未连接"}
        try:
            positions = self.exchange.fetch_positions()
            closed = 0
            for pos in positions:
                if abs(float(pos['contracts'])) > 0:
                    symbol = pos['symbol']
                    side = 'sell' if float(pos['contracts']) > 0 else 'buy'
                    amount = abs(float(pos['contracts']))
                    self.exchange.create_market_order(symbol, side, amount)
                    closed += 1
            return {"status": "ok", "closed": closed}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_status(self) -> dict:
        with self._lock:
            try:
                balance = self.exchange.fetch_balance() if self.exchange else {"total": {}}
                positions = self.exchange.fetch_positions() if self.exchange else []
                
                total_equity = float(balance.get('USDT', {}).get('total', 0))
                open_positions = [
                    {
                        "pair": p['symbol'],
                        "side": "long" if float(p['contracts']) > 0 else "short",
                        "size": abs(float(p['contracts'])),
                        "entry_price": float(p['entryPrice']),
                        "pnl": float(p['unrealizedPnl']),
                        "pnl_pct": float(p['percentage']),
                    }
                    for p in positions if abs(float(p['contracts'])) > 0
                ]
                
                return {
                    "running": self.running,
                    "exchange": self.exchange_name,
                    "balance": round(total_equity, 2),
                    "open_positions": len(open_positions),
                    "positions": open_positions,
                    "trades": self.trades[-100:],
                    "recent_signals": self.signal_log[-30:],
                    "equity_curve": self.equity_curve[-500:],
                    "config": self._get_config(),
                }
            except Exception as e:
                return {
                    "running": self.running,
                    "error": str(e),
                    "config": self._get_config(),
                }

    def _loop(self):
        print(f"[LiveTrade] 启动: {self.strategy_name} on {self.exchange_name}")
        while self.running:
            try:
                self._tick()
            except Exception as e:
                print(f"[LiveTrade] 错误: {e}")
            time.sleep(60)  # 每分钟检查一次

    def _tick(self):
        """每次 tick: 获取最新K线 → 跑策略 → 检查信号 → 下单"""
        if not self.exchange:
            return

        for pair in self.pairs:
            try:
                market_id = self.exchange.market_id(pair)
                # 获取最新 K 线
                candles = self.exchange.fetch_ohlcv(market_id, self.timeframe, limit=100)
                if len(candles) < 50:
                    continue

                df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('date', inplace=True)

                # 检查是否有新 K 线
                last_ts = self._last_candle.get(pair)
                if last_ts is not None:
                    new_candles = df[df['timestamp'] > last_ts]
                    if len(new_candles) == 0:
                        continue

                # 运行策略
                if not self._strat_cache:
                    self._strat_cache = load_strategy(self.strategy_name)

                meta = {"pair": pair}
                df2 = self._strat_cache.populate_indicators(df.copy(), meta)
                df2 = self._strat_cache.populate_entry_trend(df2, meta)
                df2 = self._strat_cache.populate_exit_trend(df2, meta)

                # 检查最后一根 K 线的信号
                last_row = df2.iloc[-1]
                last_ts = int(df2.index[-1].timestamp() * 1000)
                self._last_candle[pair] = last_ts

                # 检查是否需要下单
                self._check_and_trade(pair, last_row, df2.index[-1])

                # 更新权益曲线
                try:
                    bal = self.exchange.fetch_balance()
                    eq = float(bal.get('USDT', {}).get('total', 0))
                    self.equity_curve.append({
                        "timestamp": str(df2.index[-1]),
                        "equity": round(eq, 2),
                    })
                except:
                    pass

            except Exception as e:
                print(f"[LiveTrade] {pair} 错误: {e}")

    def _check_and_trade(self, pair, row, ts):
        """检查信号并执行交易"""
        # 获取当前持仓
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

        # ── 出场 ──
        if has_position:
            pos_side = "long" if float(current_pos['contracts']) > 0 else "short"
            should_exit = False
            reason = ""

            # 信号出场
            if pos_side == "long" and row.get("exit_long") == 1:
                should_exit, reason = True, "结构出场"
            elif pos_side == "short" and row.get("exit_short") == 1:
                should_exit, reason = True, "结构出场"

            if should_exit:
                side = 'sell' if pos_side == 'long' else 'buy'
                amount = abs(float(current_pos['contracts']))
                try:
                    order = self.exchange.create_market_order(pair, side, amount)
                    self.trades.append({
                        "pair": pair, "type": "exit", "side": pos_side,
                        "price": order.get('price', 0),
                        "amount": amount, "timestamp": str(ts),
                        "exit_reason": reason,
                    })
                    self.signal_log.append({
                        "time": str(ts), "pair": pair, "action": "平仓",
                        "reason": reason,
                    })
                except Exception as e:
                    print(f"[LiveTrade] 平仓失败: {e}")

        # ── 入场 ──
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
                    amount_usdt = equity * self.position_pct / 100
                    close_price = float(row['close'])
                    size = amount_usdt / close_price

                    order_side = 'buy' if side == 'long' else 'sell'
                    order = self.exchange.create_market_order(pair, order_side, size)

                    self.trades.append({
                        "pair": pair, "type": "entry", "side": side,
                        "price": order.get('price', close_price),
                        "amount": size, "timestamp": str(ts),
                        "enter_tag": tag,
                    })
                    self.signal_log.append({
                        "time": str(ts), "pair": pair,
                        "action": "买入" if side == "long" else "卖出",
                        "tag": tag,
                    })
                except Exception as e:
                    print(f"[LiveTrade] 开仓失败: {e}")

    def _get_open_positions_count(self) -> int:
        try:
            positions = self.exchange.fetch_positions()
            return sum(1 for p in positions if abs(float(p['contracts'])) > 0)
        except:
            return 0

    def _get_config(self):
        return {
            "exchange": self.exchange_name,
            "strategy": self.strategy_name,
            "pairs": self.pairs,
            "timeframe": self.timeframe,
            "leverage": self.leverage,
            "position_pct": self.position_pct,
            "max_positions": self.max_positions,
        }
