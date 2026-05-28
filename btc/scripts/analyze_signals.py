"""
缠论策略回测诊断系统 — 按买卖点/中枢位置/量比分组分析

用法:
  python3 btc/scripts/analyze_signals.py <回测结果JSON路径>
  
示例:
  python3 btc/scripts/analyze_signals.py btc/backend/results/backtest_20260528_093832.json
  python3 btc/scripts/analyze_signals.py btc/backend/results/backtest_20260528_093832.json --group-by tag,pair
"""

import json
import sys
from pathlib import Path
from collections import defaultdict


def load_result(path: str) -> dict:
    fp = Path(path)
    if not fp.exists():
        # Try relative to project root
        fp = Path("btc/backend/results") / path
    if not fp.exists():
        print(f"❌ 文件不存在: {path}")
        sys.exit(1)
    return json.loads(fp.read_text())


def classify_tag(tag: str) -> tuple:
    """从 enter_tag 提取买卖点类型和方向"""
    tag = tag or ""
    # 提取前2-3个字符
    if "1买" in tag:
        return ("1买", "long")
    elif "1卖" in tag:
        return ("1卖", "short")
    elif "2买" in tag:
        return ("2买", "long")
    elif "2卖" in tag:
        return ("2卖", "short")
    elif "3买" in tag:
        return ("3买", "long")
    elif "3売" in tag:
        return ("3卖", "short")
    elif "3卖" in tag:
        return ("3卖", "short")
    return ("unknown", "unknown")


def analyze(data: dict, group_by: list[str] = None):
    if group_by is None:
        group_by = ["tag"]

    trades = data.get("trades", [])
    metrics = data.get("metrics", {})
    config = data.get("config", {})

    # 配对 entry → exit
    entries = [t for t in trades if t["type"] == "entry"]
    exits = [t for t in trades if t["type"] == "exit"]

    # ==== 摘要 ====
    print("=" * 70)
    print(f"策略: {config.get('strategy','?')}  |  周期: {config.get('timeframe','?')}")
    print(f"交易对: {config.get('pairs','?')}  |  时间: {config.get('timerange','?')}")
    print(f"杠杆: {config.get('leverage',1)}x  |  费率: {config.get('fee','?')}  |  滑点: {config.get('slippage','?')}")
    print(f"仓位: {config.get('stake_amount','?')} USDT | 初始资金: {config.get('initial_balance','?')} USDT")
    print("-" * 70)
    m = metrics
    print(f"总交易: {m.get('total_trades',0)}笔  |  胜率: {m.get('win_rate',0):.1f}%")
    print(f"总收益: {m.get('total_profit_pct',0):+.2f}%  |  夏普: {m.get('sharpe_ratio',0):.2f}")
    print(f"最大回撤: {m.get('max_drawdown_pct',0):.2f}%  |  最终权益: {m.get('final_balance',0):.2f} USDT")
    print("=" * 70)

    # ==== 配对 ====
    # 用 entry 的下标匹配对应 exit（按顺序）
    paired = []
    entry_idx = 0
    for t in trades:
        if t["type"] == "entry":
            entry_idx += 1
        elif t["type"] == "exit":
            # 找对应的 entry（前一个 entry）
            prev_entries = [e for e in entries if e["timestamp"] <= t["timestamp"]]
            matched_entry = prev_entries[-1] if prev_entries else None
            if matched_entry:
                paired.append((matched_entry, t))

    if not paired:
        print("\n⚠️  没有完整的入场→出场配对")
        return

    # ==== 分组分析 ====
    def get_groups(entry, exit_):
        tag, direction = classify_tag(entry.get("enter_tag", ""))
        return {
            "tag": tag,
            "direction": direction,
            "pair": entry.get("pair", "?").split("/")[0],
        }

    groups = defaultdict(list)
    for entry, exit_ in paired:
        g = get_groups(entry, exit_)
        key = tuple(g[k] for k in group_by)
        groups[key].append((entry, exit_))

    print(f"\n📊 分组分析（按 {', '.join(group_by)}）\n")
    print(f"{'分组':<25s} {'笔数':>5s} {'胜率':>7s} {'平均盈亏%':>10s} {'总盈亏%':>9s} {'夏普':>6s} {'平均持仓':>10s} {'总盈亏U':>10s}")
    print("-" * 85)

    for key, trade_list in sorted(groups.items()):
        pnls = [ex["pnl"] for _, ex in trade_list]
        pnl_pcts = [ex["pnl_pct"] for _, ex in trade_list]
        wins = sum(1 for p in pnls if p > 0)
        total = len(trade_list)
        win_rate = wins / total * 100 if total > 0 else 0
        avg_pnl = sum(pnl_pcts) / total if total > 0 else 0
        total_pnl = sum(pnls)
        total_pnl_pct = sum(pnl_pcts)

        # 夏普（简化：用pnl_pcts的均值/标准差 * sqrt(365) 不合适，用日和）
        # 简化夏普: avg / std * sqrt(n)
        import numpy as np
        pnl_arr = np.array(pnl_pcts)
        sharpe = float(np.mean(pnl_arr) / np.std(pnl_arr) * np.sqrt(total)) if np.std(pnl_arr) > 0 else 0

        # 平均持仓时间
        durations = []
        for _, ex in trade_list:
            dur = ex.get("duration", "0 days 00:00:00")
            # format: "X days HH:MM:SS" or "0:00:00"
            days = 0
            hours = 0
            if "day" in dur:
                parts = dur.split()
                try:
                    days = int(parts[0])
                    time_str = parts[2] if len(parts) > 2 else "0:0:0"
                except (IndexError, ValueError):
                    time_str = "0:0:0"
            else:
                time_str = dur
            time_parts = time_str.split(":")
            if len(time_parts) >= 1:
                try:
                    hours = int(time_parts[0])
                except ValueError:
                    hours = 0
            durations.append(days * 24 + hours)
        avg_dur = sum(durations) / len(durations) if durations else 0

        label = str(key) if len(key) > 1 else key[0]
        print(f"{label:<25s} {total:>5d} {win_rate:>6.1f}% {avg_pnl:>+9.2f}% {total_pnl_pct:>+8.2f}% {sharpe:>6.2f} {avg_dur:>8.1f}h {total_pnl:>+10.2f}")

    print("-" * 85)

    # ==== 按对子分解 ====
    if "pair" not in group_by:
        print(f"\n📊 按交易对分解\n")
        pair_groups = defaultdict(list)
        for entry, exit_ in paired:
            pair_groups[entry.get("pair", "?").split("/")[0]].append((entry, exit_))
        for pair, trade_list in sorted(pair_groups.items()):
            pnls = [ex["pnl"] for _, ex in trade_list]
            wins = sum(1 for p in pnls if p > 0)
            total = len(trade_list)
            total_pnl = sum(pnls)
            win_rate = wins / total * 100 if total > 0 else 0
            print(f"  {pair:<6s}: {total:>3d}笔  胜率{win_rate:>5.1f}%  总盈亏{total_pnl:>+8.2f}U")

    # ==== 亏损分析 ====
    print(f"\n📉 亏损明细（最大亏损 TOP 10）\n")
    losers = [(entry, exit_) for entry, exit_ in paired if exit_["pnl"] < 0]
    losers.sort(key=lambda x: x[1]["pnl"])
    print(f"{'交易对':<8s} {'买卖点':<10s} {'盈亏%':>8s} {'盈亏U':>8s} {'持仓':>12s} {'出场原因':<40s}")
    print("-" * 85)
    for entry, exit_ in losers[:10]:
        tag, _ = classify_tag(entry.get("enter_tag", ""))
        pair_short = entry.get("pair", "?").split("/")[0]
        exit_reason = exit_.get("exit_reason", "")
        # 只保留中文+英文 +数字
        exit_reason = exit_reason.replace("多单_", "").replace("空单_", "").replace("_", " ")
        print(f"{pair_short:<8s} {tag:<10s} {exit_['pnl_pct']:>+7.2f}% {exit_['pnl']:>+7.2f} {exit_.get('duration','?'):<12s} {exit_reason[:40]:<40s}")

    # ==== 盈利分析 ====
    print(f"\n📈 盈利明细（最大盈利 TOP 10）\n")
    winners = [(entry, exit_) for entry, exit_ in paired if exit_["pnl"] > 0]
    winners.sort(key=lambda x: x[1]["pnl"], reverse=True)
    print(f"{'交易对':<8s} {'买卖点':<10s} {'盈亏%':>8s} {'盈亏U':>8s} {'持仓':>12s} {'出场原因':<40s}")
    print("-" * 85)
    for entry, exit_ in winners[:10]:
        tag, _ = classify_tag(entry.get("enter_tag", ""))
        pair_short = entry.get("pair", "?").split("/")[0]
        exit_reason = exit_.get("exit_reason", "")
        exit_reason = exit_reason.replace("多单_", "").replace("空单_", "").replace("_", " ")
        print(f"{pair_short:<8s} {tag:<10s} {exit_['pnl_pct']:>+7.2f}% {exit_['pnl']:>+7.2f} {exit_.get('duration','?'):<12s} {exit_reason[:40]:<40s}")

    # ==== 出场原因分布 ====
    print(f"\n🚪 出场原因分布\n")
    from collections import Counter
    reasons = Counter()
    for _, exit_ in paired:
        r = exit_.get("exit_reason", "?")
        # 提取原始原因（去掉方向/标签前缀）
        for kw in ["止损", "移动止盈", "止盈", "信号出场", "回测结束"]:
            if kw in r:
                reasons[kw] += 1
                break
        else:
            reasons["其他"] += 1
    for reason, cnt in reasons.most_common():
        print(f"  {reason:<10s}: {cnt:>3d}笔")

    # ==== 日均表现 ====
    print(f"\n📅 每日盈亏分布\n")
    daily = data.get("daily_pnl", {})
    if daily:
        import numpy as np
        vals = list(daily.values())
        pos_days = sum(1 for v in vals if v > 0)
        neg_days = sum(1 for v in vals if v < 0)
        print(f"  盈利天数: {pos_days} | 亏损天数: {neg_days} | 胜日率: {pos_days/(pos_days+neg_days)*100:.1f}%")
        print(f"  日均盈亏: {np.mean(vals):+.2f} | 日盈亏中位数: {np.median(vals):+.2f}")
        print(f"  最大日盈利: {max(vals):+.2f} | 最大日亏损: {min(vals):+.2f}")

    return groups


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="缠论策略回测诊断系统")
    parser.add_argument("result", nargs="?", help="回测结果 JSON 文件路径",
                        default="btc/backend/results/backtest_20260528_093832.json")
    parser.add_argument("--group-by", default="tag", 
                        help="分组字段，逗号分隔 (tag, direction, pair) 默认 tag")
    args = parser.parse_args()

    data = load_result(args.result)
    analyze(data, group_by=[g.strip() for g in args.group_by.split(",")])
