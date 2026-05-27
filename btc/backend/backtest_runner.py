"""
Freqtrade Backtest Runner — calls Freqtrade's internal backtesting API
and returns structured JSON results.

Handles network-restricted environments by providing fallback market data.
"""

import json
import os
import sys
import copy
from pathlib import Path
from typing import Optional
from datetime import datetime

# ---------------------------------------------------------------------------
# Freqtrade internal imports
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "freqtrade"))

from freqtrade.configuration import Configuration
from freqtrade.enums import RunMode, TradingMode
from freqtrade.resolvers import StrategyResolver
from freqtrade.data.history import get_datahandler
from freqtrade.optimize.backtesting import Backtesting
from freqtrade.data.dataprovider import DataProvider
from freqtrade.exchange import Exchange
from freqtrade.exceptions import OperationalException


BASE_DIR = Path(__file__).resolve().parent.parent
FREQTRADE_DIR = BASE_DIR / "freqtrade"
USER_DATA_DIR = FREQTRADE_DIR / "user_data"
DATA_DIR = USER_DATA_DIR / "data" / "binance"
RESULTS_DIR = BASE_DIR / "backend" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Fallback market data for offline use (Binance futures)
# ---------------------------------------------------------------------------
FALLBACK_MARKETS = {
    "BTC/USDT:USDT": {
        "id": "BTCUSDT",
        "symbol": "BTC/USDT:USDT",
        "base": "BTC",
        "quote": "USDT",
        "settle": "USDT",
        "active": True,
        "linear": True,
        "inverse": False,
        "taker": 0.0004,
        "maker": 0.0002,
        "precision": {"amount": 0.001, "price": 0.1},
        "limits": {
            "amount": {"min": 0.001, "max": 1000},
            "price": {"min": 0.1, "max": 1e6},
            "leverage": {"min": 1, "max": 125},
        },
        "contract": True,
        "contractSize": 1,
    },
    "ETH/USDT:USDT": {
        "id": "ETHUSDT",
        "symbol": "ETH/USDT:USDT",
        "base": "ETH",
        "quote": "USDT",
        "settle": "USDT",
        "active": True,
        "linear": True,
        "inverse": False,
        "taker": 0.0004,
        "maker": 0.0002,
        "precision": {"amount": 0.001, "price": 0.01},
        "limits": {
            "amount": {"min": 0.001, "max": 10000},
            "price": {"min": 0.01, "max": 1e6},
            "leverage": {"min": 1, "max": 100},
        },
        "contract": True,
        "contractSize": 1,
    },
    "SOL/USDT:USDT": {
        "id": "SOLUSDT",
        "symbol": "SOL/USDT:USDT",
        "base": "SOL",
        "quote": "USDT",
        "settle": "USDT",
        "active": True,
        "linear": True,
        "inverse": False,
        "taker": 0.0004,
        "maker": 0.0002,
        "precision": {"amount": 0.01, "price": 0.01},
        "limits": {
            "amount": {"min": 0.01, "max": 100000},
            "price": {"min": 0.01, "max": 1e6},
            "leverage": {"min": 1, "max": 100},
        },
        "contract": True,
        "contractSize": 1,
    },
}


def make_config(
    pairs: list[str],
    timeframe: str = "1h",
    timerange: str = "",
    stake_amount: float = 100,
    dry_run_wallet: float = 1000,
    max_open_trades: int = 3,
    leverage: float = 1.0,
    fee: Optional[float] = None,
) -> dict:
    """Build a Freqtrade config dict for backtesting."""
    cfg = {
        "max_open_trades": max_open_trades,
        "stake_currency": "USDT",
        "stake_amount": stake_amount,
        "trading_mode": "futures",
        "margin_mode": "isolated",
        "dry_run": True,
        "dry_run_wallet": dry_run_wallet,
        "exchange": {
            "name": "binance",
            "pair_whitelist": pairs,
            "pair_blacklist": [],
            "ccxt_config": {
                "options": {"defaultType": "swap"},
                "rateLimit": 100,
            },
            "_ft_has_params": {
                "ohlcv_candle_limit": 1000,
                "trades_pagination": "time",
                "ohlcv_has_history": True,
                "funding_fee_timeframe": "8h",
            },
        },
        "pairlists": [{"method": "StaticPairList"}],
        "telegram": {"enabled": False},
        "api_server": {"enabled": False},
        "initial_state": "running",
        "db_url": "",
        "user_data_dir": str(USER_DATA_DIR),
        "dataformat_ohlcv": "feather",
        "datadir": str(DATA_DIR),
        "timeframe": timeframe,
    }

    if timerange:
        cfg["timerange"] = timerange
    if fee is not None:
        cfg["fee"] = fee

    return cfg


def patch_exchange_markets(exchange_obj: Exchange):
    """
    Inject fallback markets into an Exchange instance to bypass API call.
    """
    try:
        exchange_obj.markets = FALLBACK_MARKETS
        exchange_obj._trading_mode = TradingMode.FUTURES
        # Set precision mode
        exchange_obj.precision_mode = 2
        # Set contract size
        for pair, market in FALLBACK_MARKETS.items():
            exchange_obj._contract_sizes[pair] = market["contractSize"]
    except Exception:
        pass


def run_backtest(
    strategy_name: str = "SampleStrategy",
    pairs: Optional[list[str]] = None,
    timeframe: str = "1h",
    timerange: str = "20251001-20251231",
    stake_amount: float = 100,
    dry_run_wallet: float = 1000,
    max_open_trades: int = 3,
    leverage: float = 1.0,
    fee: Optional[float] = None,
) -> dict:
    """
    Run a full backtest and return structured results.
    """
    if pairs is None:
        pairs = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]

    cfg = make_config(
        pairs=pairs,
        timeframe=timeframe,
        timerange=timerange,
        stake_amount=stake_amount,
        dry_run_wallet=dry_run_wallet,
        max_open_trades=max_open_trades,
        leverage=leverage,
        fee=fee,
    )

    # Build Configuration object
    config = Configuration(args=[], config_dict=cfg)
    config.get_config()

    # Patch the exchange
    from freqtrade.resolvers.exchange_resolver import ExchangeResolver

    exchange_config = copy.deepcopy(config.get_config())
    exchange = ExchangeResolver.load_exchange(exchange_config, config.get_config().get("exchange", {}))
    patch_exchange_markets(exchange)

    # Now build the backtesting engine with the patched exchange
    backtesting = Backtesting(config, exchange)

    try:
        # Run backtest
        result = backtesting.backtest(
            strategy=StrategyResolver.load_strategy(
                config=config,
                exchange=exchange,
            ),
            start=datetime.now(),
        )

        # Parse result into structured JSON
        stats = result.get("results", {})
        trades = result.get("trades", [])
        rejected = result.get("rejected_signals", 0)

        # Build metrics
        profit_total = stats.get("profit_total", 0)
        profit_total_ratio = stats.get("profit_total_ratio", 0)
        # ... parse other metrics
        metrics = {
            "total_trades": len(trades),
            "rejected_signals": rejected,
            "profit_total_ratio": profit_total_ratio,
            "profit_total": profit_total,
            **stats,
        }

        return {
            "success": True,
            "metrics": metrics,
            "trades": trades,
            "config_used": cfg,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "config_used": cfg,
        }
    finally:
        try:
            backtesting.cleanup()
        except Exception:
            pass
