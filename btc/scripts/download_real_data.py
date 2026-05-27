#!/usr/bin/env python3
"""
下载真实 K 线数据 — 通过 config.json 里的代理设置。

用法：
  source freqtrade/.venv/bin/activate
  python scripts/download_real_data.py
"""

import subprocess
import sys
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
FREQTRADE = BASE / "freqtrade" / ".venv" / "bin" / "freqtrade"
USERDIR = BASE / "freqtrade" / "user_data"
CONFIG = BASE / "config.json"

SPOT_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
FUTURES_PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]
DAYS = 365


def run(cmd: list[str], timeout: int = 300) -> bool:
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (result.stdout or "") + (result.stderr or "")
        if result.returncode == 0:
            # 显示最后几行
            lines = [l for l in out.split("\n") if l.strip()]
            for l in lines[-3:]:
                print(f"  {l}")
            return True
        else:
            # 显示关键错误
            for line in out.split("\n"):
                if "ERROR" in line or "error" in line or "CRITICAL" in line:
                    print(f"  ⚠️ {line[:150]}")
            return False
    except subprocess.TimeoutExpired:
        print("  ⚠️ 超时")
        return False
    except Exception as e:
        print(f"  ⚠️ {e}")
        return False


def main():
    print("🌐 通过代理下载 OKX 数据")
    print(f"   交易对: BTC, ETH, SOL, BNB (现货+合约)")
    print(f"   粒度: {', '.join(TIMEFRAMES)}")
    print(f"   天数: {DAYS}")
    print()

    if not CONFIG.exists():
        print("❌ config.json 不存在")
        sys.exit(1)

    # 1. 测试连接
    print("🔌 测试 OKX 连接...")
    ok = run([
        str(FREQTRADE), "list-markets",
        "--exchange", "okx",
        "-c", str(CONFIG),
        "--userdir", str(USERDIR),
    ], timeout=30)
    if not ok:
        print("\n❌ 连接失败。检查代理设置是否正确:")
        print("   1. Shadowsocks 已开？")
        print("   2. HTTP 端口是 1087？")
        print(f"   3. 手动测试: curl -x http://127.0.0.1:1087 https://www.okx.com/api/v5/public/time")
        sys.exit(1)

    # 2. 下载现货
    print("\n📥 现货数据...")
    spot_ok = run([
        str(FREQTRADE), "download-data",
        "--exchange", "okx",
        "--trading-mode", "spot",
        "-c", str(CONFIG),
        "--pairs", *SPOT_PAIRS,
        "--timeframes", *TIMEFRAMES,
        "--days", str(DAYS),
        "--userdir", str(USERDIR),
    ], timeout=600)
    if spot_ok:
        print("   ✅ 现货完成")
    else:
        print("   ⚠️ 现货失败，继续尝试合约")

    # 3. 下载合约
    print("\n📥 合约数据...")
    fut_ok = run([
        str(FREQTRADE), "download-data",
        "--exchange", "okx",
        "--trading-mode", "futures",
        "-c", str(CONFIG),
        "--pairs", *FUTURES_PAIRS,
        "--timeframes", *TIMEFRAMES,
        "--days", str(DAYS),
        "--userdir", str(USERDIR),
    ], timeout=600)
    if fut_ok:
        print("   ✅ 合约完成")
    else:
        print("   ⚠️ 合约失败")

    # 4. 检查结果
    data_dir = USERDIR / "data" / "okx"
    files = sorted(data_dir.glob("*.feather")) if data_dir.exists() else []
    print(f"\n{'='*50}")
    if files:
        print(f"✅ 成功！共 {len(files)} 个数据文件:")
        for f in files:
            size = f.stat().st_size / 1024
            print(f"   {f.name} ({size:.0f} KB)")
        print()
        print("启动系统:")
        print("   (.venv) $ python backend/main.py")
        print("   $ npm --prefix frontend run dev")
    else:
        print("❌ 没有下载到任何数据文件")
        # 回退到 CoinGecko
        print("\n尝试 CoinGecko 备用方案...")
        subprocess.run([sys.executable, str(BASE / "scripts" / "download_fallback.py")])


if __name__ == "__main__":
    main()
