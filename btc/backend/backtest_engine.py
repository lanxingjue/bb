"""
轻量回测引擎 v2 — 兼容 Freqtrade 策略接口。

流程：
  1. 加载数据（全部时间范围）
  2. 批量调用 populate_indicators → populate_entry_trend → populate_exit_trend
  3. 逐 K 线扫描，遇信号开/平仓
  4. 输出结构化 JSON（指标 + 交易明细 + 资金曲线）

兼容 Freqtrade 策略文件，可直接在 Freqtrade CLI 下使用。
"""

import json
import sys
import importlib.util
import inspect
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import pandas as pd
import numpy as np


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR_CANDIDATES = [
    BASE_DIR / "freqtrade" / "user_data" / "data" / "okx",
    BASE_DIR / "freqtrade" / "user_data" / "data" / "bybit",
    BASE_DIR / "freqtrade" / "user_data" / "data" / "binance",
]
DATA_DIR = None
for d in DATA_DIR_CANDIDATES:
    if d.exists() and any(d.glob("*.feather")):
        DATA_DIR = d
        break
if DATA_DIR is None:
    DATA_DIR = DATA_DIR_CANDIDATES[0]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

FEE_CONFIG = {
    "futures": {"taker": 0.0004, "maker": 0.0002},
    "spot": {"taker": 0.001, "maker": 0.001},
}


def load_feather(pair: str, tf: str, start: str = "", end: str = "") -> pd.DataFrame:
    pf = pair.replace("/", "").replace(":", "")
    fp = DATA_DIR / f"{pf}-{tf}.feather"
    if not fp.exists():
        raise FileNotFoundError(f"数据不存在: {fp}")
    df = pd.read_feather(fp)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    if start:
        df = df[df.index >= start]
    if end:
        df = df[df.index <= end]
    return df


def load_strategy(name: str):
    sp = BASE_DIR / "freqtrade" / "user_data" / "strategies" / f"{name}.py"
    # 清除缓存，确保每次重新加载
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, sp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for _, cls in inspect.getmembers(mod, inspect.isclass):
        if cls.__name__ == name and issubclass(cls, object):
            return cls(config={})
    raise ValueError(f"找不到策略类 {name}")


def run(
    strategy_name: str = "TestStrategy",
    pairs: Optional[list[str]] = None,
    timeframe: str = "1h",
    timerange: str = "20251101-20251231",
    stake_amount: float = 100,
    initial_balance: float = 1000,
    max_open_trades: int = 3,
    leverage_val: float = 1.0,
    fee_rate: Optional[float] = None,
    slippage: float = 0.0,
    custom_stoploss: Optional[float] = None,
    position_pct: Optional[float] = None,
    trading_mode: str = "futures",
) -> dict:
    if pairs is None:
        pairs = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]

    parts = timerange.split("-")
    start_str = parts[0] if parts[0] else ""
    end_str = parts[1] if len(parts) > 1 and parts[1] else ""

    strat = load_strategy(strategy_name)
    if custom_stoploss is not None:
        strat.stoploss = -abs(custom_stoploss) / 100  # 前端的 % 转成负小数
    fees = FEE_CONFIG.get(trading_mode, FEE_CONFIG["futures"])
    fee = fee_rate if fee_rate is not None else fees["taker"]
    startup = getattr(strat, "startup_candle_count", 30)
    can_short = getattr(strat, "can_short", True)
    max_positions = max_open_trades

    # 1. 加载 + 预处理所有交易对
    all_dfs = {}
    for p in pairs:
        df = load_feather(p, timeframe, start_str, end_str)
        all_dfs[p] = df

    # 2. 对所有交易对批量计算信号
    print(f"计算策略信号 ({strategy_name})...")
    for p, df in all_dfs.items():
        meta = {"pair": p}
        if len(df) < startup:
            print(f"  {p}: 数据不足 ({len(df)} < {startup})")
            continue
        df2 = strat.populate_indicators(df.copy(), meta)
        df2 = strat.populate_entry_trend(df2, meta)
        df2 = strat.populate_exit_trend(df2, meta)
        all_dfs[p] = df2
    print("  完成")

    # 3. 取所有时间戳并集
    all_times = pd.DatetimeIndex([])
    for df in all_dfs.values():
        all_times = all_times.union(df.index)
    all_times = all_times.sort_values()
    print(f"时间范围: {all_times[0]} → {all_times[-1]}")
    print(f"K 线总数: {len(all_times)}")

    # 4. 交易引擎
    class Engine:
        def __init__(self):
            self.balance = initial_balance
            self.equity = initial_balance
            self.positions: dict[str, dict] = {}
            self.trades: list[dict] = []
            self.equity_curve: list[dict] = []
            self.daily_pnl: dict[str, float] = {}
            self.prev_equity = initial_balance

        def entry(self, pair, side, price, ts, tag=""):
            if len(self.positions) >= max_positions:
                return False
            # 动态仓位：按当前权益百分比，或固定金额
            if position_pct:
                trade_amount = self.balance * position_pct / 100
                trade_amount = max(10, min(trade_amount, self.balance * 0.5))  # 不超过50%
            else:
                trade_amount = stake_amount
            size = trade_amount / price
            cost = size * price
            if cost > self.balance:
                return False
            notional = cost * leverage_val  # 名义价值 = 保证金 × 杠杆
            fee_cost = notional * fee  # 手续费按名义价值算
            self.balance -= cost + fee_cost
            self.positions[pair] = {
                "side": side, "size": size, "entry_p": price,
                "ts": ts, "lev": leverage_val,
                "highest": price, "lowest": price,
                "enter_tag": tag,
            }
            self.trades.append({"pair": pair, "type": "entry", "side": side,
                                "price": round(price, 2), "size": round(size, 6),
                                "cost": round(cost, 2), "fee": round(fee_cost, 6),
                                "timestamp": str(ts), "enter_tag": tag})
            return True

        def exit(self, pair, price, ts, reason=""):
            pos = self.positions.pop(pair, None)
            if not pos:
                return False
            sz = pos["size"]
            ep = pos["entry_p"]
            direction = "多单" if pos["side"] == "long" else "空单"
            entry_tag = pos.get("enter_tag", "")
            if pos["side"] == "long":
                pnl = (price - ep) * sz
            else:
                pnl = (ep - price) * sz
            pnl *= pos["lev"]
            pnl_pct = pnl / (sz * ep) * 100
            notional_value = price * sz * pos["lev"]
            fee_cost = notional_value * fee
            self.balance += sz * ep + pnl - fee_cost
            dk = str(ts.date())
            self.daily_pnl[dk] = self.daily_pnl.get(dk, 0) + pnl

            # 构建详细出场原因: 多单_1买_4h升势_中枢下方_止盈_赚7.6%
            pnl_txt = f"赚{abs(pnl_pct):.1f}%" if pnl > 0 else f"亏{abs(pnl_pct):.1f}%"
            detail_reason = f"{direction}_{entry_tag[:25]}_{reason}_{pnl_txt}"

            self.trades.append({"pair": pair, "type": "exit", "side": pos["side"],
                                "price": round(price, 2), "size": round(sz, 6),
                                "pnl": round(pnl, 2),
                                "pnl_pct": round(pnl_pct, 4),
                                "fee": round(fee_cost, 6), "timestamp": str(ts),
                                "duration": str(ts - pos["ts"]),
                                "exit_reason": detail_reason, "leverage": pos["lev"],
                                "entry_price": round(pos["entry_p"], 2)})
            return True

        def snapshot(self, ts):
            eq = self.balance
            for p, pos in self.positions.items():
                if pos["side"] == "long":
                    up = 0
                else:
                    up = 0
                eq += pos["size"] * pos["entry_p"]
            self.equity = eq
            self.equity_curve.append({"timestamp": str(ts), "equity": round(eq, 2), "balance": round(self.balance, 2)})

    eng = Engine()

    # 5. 逐 K 线执行
    print("执行交易模拟...")
    batch = max(1, len(all_times) // 20)

    for i, t in enumerate(all_times):
        for p in pairs:
            df = all_dfs.get(p)
            if df is None:
                continue
            try:
                row = df.loc[t]
            except KeyError:
                continue

            # 入场（含滑点：买入用更高价，卖出用更低价）
            if p not in eng.positions:
                if row.get("enter_long") == 1:
                    tag = str(row.get("enter_tag", ""))
                    eng.entry(p, "long", row["close"] * (1 + slippage), t, tag)
                elif row.get("enter_short") == 1 and can_short:
                    tag = str(row.get("enter_tag", ""))
                    eng.entry(p, "short", row["close"] * (1 - slippage), t, tag)

            # 出场: 信号 + 风控
            if p in eng.positions:
                pos = eng.positions[p]
                side = pos["side"]
                cp = float(row["close"])
                ep = pos["entry_p"]
                hold_minutes = (t - pos["ts"]).total_seconds() / 60

                # 更新最高/最低价（用于 trailing，用 HIGH/LOW 不是 CLOSE）
                bar_high = float(row.get("high", cp))
                bar_low = float(row.get("low", cp))
                if side == "long":
                    pos["highest"] = max(pos["highest"], bar_high)
                else:
                    pos["lowest"] = min(pos["lowest"], bar_low)

                # 当前盈亏 %
                if side == "long":
                    pnl_pct = (cp - ep) / ep * 100
                else:
                    pnl_pct = (ep - cp) / ep * 100

                should_exit = False
                exit_reason = ""

                # 1) 信号出场
                if side == "long" and row.get("exit_long") == 1:
                    should_exit = True; exit_reason = "信号出场"
                elif side == "short" and row.get("exit_short") == 1:
                    should_exit = True; exit_reason = "信号出场"

                # 2) stoploss — 用 LOW(做多)/HIGH(做空) 判断
                sl = abs(getattr(strat, 'stoploss', 0.05))
                if not should_exit:
                    bar_low = float(row.get("low", cp))
                    bar_high = float(row.get("high", cp))
                    if side == "long" and bar_low < ep * (1 - sl):
                        should_exit = True; exit_reason = "止损"
                    elif side == "short" and bar_high > ep * (1 + sl):
                        should_exit = True; exit_reason = "止损"

                # 3) trailing stop — 用 LOW/HIGH
                if not should_exit and getattr(strat, 'trailing_stop', False):
                    trail_pos = getattr(strat, 'trailing_stop_positive', 0.01)
                    trail_off = getattr(strat, 'trailing_stop_positive_offset', 0.02)
                    bar_low = float(row.get("low", cp))
                    bar_high = float(row.get("high", cp))
                    if side == "long":
                        if pos["highest"] > ep * (1 + trail_off):
                            if bar_low < pos["highest"] * (1 - trail_pos):
                                should_exit = True; exit_reason = "移动止盈"
                    else:
                        if pos["lowest"] < ep * (1 - trail_off):
                            if bar_high > pos["lowest"] * (1 + trail_pos):
                                should_exit = True; exit_reason = "移动止盈"

                # 4) minimal_roi
                if not should_exit and pnl_pct > 0:
                    roi = getattr(strat, 'minimal_roi', {})
                    # Freqtrade: {"60": 0.01, "30": 0.02, "0": 0.04}
                    # → after 60min: 1%, after 30min: 2%, immediately: 4%
                    # 选 hold_minutes 能匹配的最长时间阈值
                    best_threshold = 999.0
                    for mins_str, ratio in sorted(roi.items(), key=lambda x: int(x[0])):
                        mins = int(mins_str)
                        if hold_minutes >= mins:
                            best_threshold = abs(ratio) * 100  # 转 %
                    if pnl_pct >= best_threshold:
                        should_exit = True; exit_reason = "止盈"

                if should_exit:
                    exit_price = cp * (1 - slippage) if side == "long" else cp * (1 + slippage)
                    eng.exit(p, exit_price, t, exit_reason)

        # 更新权益曲线
        eq = eng.balance
        for p, pos in eng.positions.items():
            margin = pos["size"] * pos["entry_p"]  # 冻结的保证金
            df = all_dfs.get(p)
            if df is None:
                continue
            try:
                cp = df.loc[t, "close"]
            except KeyError:
                continue
            if pos["side"] == "long":
                up = (cp - pos["entry_p"]) * pos["size"] * pos["lev"]
            else:
                up = (pos["entry_p"] - cp) * pos["size"] * pos["lev"]
            eq += margin + up

        eng.equity = eq
        eng.equity_curve.append({"timestamp": str(t), "equity": round(eq, 2), "balance": round(eng.balance, 2)})

        if (i + 1) % batch == 0:
            print(f"  进度: {(i+1)/len(all_times)*100:.0f}% ({i+1}/{len(all_times)})", end="\r")
    print()

    # 关剩余仓位
    for p in list(eng.positions.keys()):
        df = all_dfs.get(p)
        if df is not None:
            eng.exit(p, df["close"].iloc[-1], all_times[-1], "回测结束")

    # 6. 计算指标
    exits = [t for t in eng.trades if t["type"] == "exit"]
    n_exits = len(exits)
    config_block = {
        "strategy": strategy_name, "pairs": pairs, "timeframe": timeframe,
        "timerange": timerange, "stake_amount": stake_amount,
        "initial_balance": initial_balance, "max_open_trades": max_open_trades,
        "leverage": leverage_val, "fee": fee, "slippage": slippage, "position_pct": position_pct, "trading_mode": trading_mode,
    }

    if n_exits == 0:
        r = {"success": True, "metrics": {
            "total_trades": 0, "total_profit_pct": 0, "total_profit_usdt": 0,
            "win_rate": 0, "avg_profit_pct": 0,
            "sharpe_ratio": 0, "max_drawdown_pct": 0,
            "starting_balance": initial_balance, "final_balance": initial_balance,
        }, "trades": [], "equity_curve": eng.equity_curve, "daily_pnl": eng.daily_pnl,
            "config": config_block, "error": "no trades"}
        return r

    pnls = np.array([t["pnl"] for t in exits])
    pnl_pcts = np.array([t["pnl_pct"] for t in exits])
    total_pnl = float(pnls.sum())
    wins = int((pnls > 0).sum())

    # 夏普
    eq_df = pd.DataFrame(eng.equity_curve)
    eq_df["timestamp"] = pd.to_datetime(eq_df["timestamp"])
    eq_df["ret"] = eq_df["equity"].pct_change().fillna(0)
    dret = eq_df.set_index("timestamp").resample("D")["ret"].sum()
    sharpe = float(np.sqrt(365) * dret.mean() / dret.std()) if dret.std() > 0 else 0

    # 最大回撤
    peak = eq_df["equity"].cummax()
    dd = ((peak - eq_df["equity"]) / peak * 100).max()

    total_pct = (eng.balance - initial_balance) / initial_balance * 100
    avg_pnl_pct = float(np.mean(pnl_pcts)) if len(pnl_pcts) > 0 else 0

    metrics = {
        "total_trades": n_exits,
        "total_entries": len([t for t in eng.trades if t["type"] == "entry"]),
        "total_profit_usdt": round(total_pnl, 2),
        "total_profit_pct": round(total_pct, 2),
        "win_rate": round(wins / n_exits * 100, 2),
        "avg_profit_pct": round(avg_pnl_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(float(dd), 2),
        "starting_balance": initial_balance,
        "final_balance": round(eng.balance, 2),
        "total_fees": round(sum(t.get("fee", 0) for t in eng.trades), 4),
        "win_trades": wins,
        "loss_trades": n_exits - wins,
    }

    # 资金曲线简洁化（每 4h 一个点，减少前端渲染量）
    eq_curve = eng.equity_curve
    step = max(1, len(eq_curve) // 500)

    return {
        "success": True,
        "metrics": metrics,
        "trades": eng.trades,
        "equity_curve": eq_curve[::step],
        "equity_curve_full_len": len(eq_curve),
        "daily_pnl": eng.daily_pnl,
        "config": config_block,
    }


def list_results() -> list[dict]:
    """列出所有回测结果"""
    results = []
    for f in sorted(RESULTS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        results.append({
            "filename": f.name,
            "timestamp": f.stat().st_mtime,
            "strategy": data.get("config", {}).get("strategy", ""),
            "metrics": data.get("metrics", {}),
        })
    return results


def save(r: dict, fn: Optional[str] = None):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn = fn or f"backtest_{ts}.json"
    fp = RESULTS_DIR / fn
    with open(fp, "w") as f:
        json.dump(r, f, indent=2, default=str)
    print(f"保存: {fp}")
    return str(fp)


if __name__ == "__main__":
    r = run()
    save(r)
    print("\n=== 回测摘要 ===")
    print(json.dumps(r["metrics"], indent=2))
    print(f"\n交易数: {len(r['trades'])}")
