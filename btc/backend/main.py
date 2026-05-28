"""
FastAPI 后端 — 策略回测系统 API

API 端点：
  POST /api/backtest  运行回测
  GET  /api/strategies  策略列表
  GET  /api/strategies/{name}  策略详情
  PUT  /api/strategies/{name}  保存策略
  GET  /api/results  回测结果列表
  GET  /api/results/{filename}  加载指定结果
  GET  /api/pairs  可用交易对
  GET  /api/timeframes  可用时间粒度
  GET  /api/data/{pair}/{timeframe}  K 线数据
"""

import json
import sys
from pathlib import Path
from typing import Optional, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Add backend to path
BACKEND_DIR = Path(__file__).parent
BASE_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from backtest_engine import run as run_backtest, save as save_result, load_feather, list_results

app = FastAPI(title="Crypto Strategy Backtest API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STRATEGIES_DIR = BASE_DIR / "freqtrade" / "user_data" / "strategies"
# 数据目录 — 优先用 bybit，若不存在则用 binance
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
RESULTS_DIR = BACKEND_DIR / "results"


# ─── Models ────────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    strategy: str = "TestStrategy"
    pairs: list[str] = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
    timeframe: str = "1h"
    timerange: str = "20251101-20251231"
    stake_amount: float = 100
    initial_balance: float = 1000
    max_open_trades: int = 3
    leverage: float = 1.0
    fee: Optional[float] = None
    slippage: float = 0.0
    position_pct: Optional[float] = None
    custom_stoploss: Optional[float] = None
    trading_mode: str = "futures"


class StrategySave(BaseModel):
    content: str


# ─── API ───────────────────────────────────────────────────────────────────

@app.get("/api/ping")
def ping():
    return {"status": "ok"}


@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    """运行回测"""
    try:
        result = run_backtest(
            strategy_name=req.strategy,
            pairs=req.pairs,
            timeframe=req.timeframe,
            timerange=req.timerange,
            stake_amount=req.stake_amount,
            initial_balance=req.initial_balance,
            max_open_trades=req.max_open_trades,
            leverage_val=req.leverage,
            fee_rate=req.fee,
            slippage=req.slippage,
            custom_stoploss=req.custom_stoploss,
            position_pct=req.position_pct,
            trading_mode=req.trading_mode,
        )
        # 保存结果
        save_result(result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/strategies")
def list_strategies():
    """策略列表"""
    strategies = []
    for f in sorted(STRATEGIES_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        strategies.append({
            "name": f.stem,
            "path": str(f),
            "modified": f.stat().st_mtime,
            "size": f.stat().st_size,
        })
    return {"strategies": strategies}


@app.get("/api/strategies/{name}")
def get_strategy(name: str):
    """读取策略源码"""
    fp = STRATEGIES_DIR / f"{name}.py"
    if not fp.exists():
        raise HTTPException(status_code=404, detail="策略不存在")
    return {"name": name, "content": fp.read_text()}


@app.put("/api/strategies/{name}")
def save_strategy(name: str, body: StrategySave):
    """保存策略源码"""
    fp = STRATEGIES_DIR / f"{name}.py"
    fp.write_text(body.content)
    return {"status": "ok", "name": name}


@app.get("/api/results")
def results_list():
    """回测结果列表"""
    return {"results": list_results()}


@app.get("/api/results/{filename}")
def get_result(filename: str):
    """读取指定回测结果"""
    fp = RESULTS_DIR / filename
    if not fp.exists():
        raise HTTPException(status_code=404, detail="结果不存在")
    return json.loads(fp.read_text())


@app.get("/api/pairs")
def available_pairs():
    """可用交易对（从文件名还原）"""
    seen = set()
    pairs = []
    for f in sorted(DATA_DIR.glob("*.feather")):
        parts = f.stem.rsplit("-", 1)
        if len(parts) != 2:
            continue
        raw = parts[0]
        if raw not in seen:
            seen.add(raw)
            # BTCUSDTUSDT → BTC/USDT:USDT
            pair = raw
            # 根据文件名推断交易对
            mapping = {
                "BTCUSDT": "BTC/USDT:USDT",
                "ETHUSDT": "ETH/USDT:USDT",
                "SOLUSDT": "SOL/USDT:USDT",
                "BNBUSDT": "BNB/USDT:USDT",
            }
            for key, val in mapping.items():
                if key in raw:
                    pair = val
                    break
            else:
                pair = raw  # fallback
            pairs.append(pair)
    return {"pairs": pairs}


@app.get("/api/timeframes")
def available_timeframes():
    """可用时间粒度"""
    tfs = set()
    for f in DATA_DIR.glob("*.feather"):
        parts = f.stem.rsplit("-", 1)
        if len(parts) == 2:
            tfs.add(parts[1])
    return {"timeframes": sorted(tfs)}


@app.get("/api/data")
def kline_data(
    pair: str = Query(..., description="BTC/USDT:USDT"),
    timeframe: str = Query("1h"),
    limit: int = Query(500, ge=10, le=10000),
):
    """K 线数据（用于前端绘图）"""
    pair_file = pair.replace("/", "").replace(":", "")
    fp = DATA_DIR / f"{pair_file}-{timeframe}.feather"
    if not fp.exists():
        raise HTTPException(status_code=404, detail=f"数据不存在: {pair}@{timeframe}")

    df = load_feather(pair, timeframe)
    df = df.tail(limit).reset_index()

    records = []
    for _, row in df.iterrows():
        records.append({
            "time": int(row["date"].timestamp()),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": round(float(row["volume"]), 2),
        })
    return {"pair": pair, "timeframe": timeframe, "data": records}


# ─── 模拟盘 ────────────────────────────────────────────────────────────────

from papertrade import PaperTradingEngine

_paper_engine = PaperTradingEngine()


class PaperTradeConfig(BaseModel):
    strategy: str = "RealChanTheory"
    pairs: list[str] = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    timeframe: str = "1h"
    leverage: float = 3.0
    fee: float = 0.0004
    slippage: float = 0.0005
    position_pct: float = 25.0
    max_positions: int = 3
    initial_balance: float = 1000.0


@app.post("/api/papertrade/start")
def papertrade_start(cfg: PaperTradeConfig):
    """启动模拟盘"""
    return _paper_engine.start(cfg.model_dump())


@app.get("/api/papertrade/status")
def papertrade_status():
    """模拟盘状态"""
    return _paper_engine.get_status()


@app.post("/api/papertrade/stop")
def papertrade_stop():
    """停止模拟盘"""
    return _paper_engine.stop()


# ─── 实盘 ──────────────────────────────────────────────────────────────────

from livetrade import LiveTradingEngine

_live_engine = LiveTradingEngine()


class LiveTradeConfig(BaseModel):
    exchange_name: str = "okx"
    strategy: str = "ChanTheoryScalp"
    pairs: list[str] = ["BTC/USDT:USDT"]
    timeframe: str = "1h"
    leverage: float = 3.0
    position_pct: float = 20.0
    max_positions: int = 2


@app.post("/api/livetrade/start")
def livetrade_start(cfg: LiveTradeConfig):
    """启动实盘"""
    return _live_engine.start(cfg.model_dump())


@app.get("/api/livetrade/status")
def livetrade_status():
    """实盘状态"""
    return _live_engine.get_status()


@app.post("/api/livetrade/stop")
def livetrade_stop():
    """停止实盘"""
    return _live_engine.stop()


@app.post("/api/livetrade/close-all")
def livetrade_close_all():
    """一键平仓"""
    return _live_engine.close_all()


# ─── 启动 ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
