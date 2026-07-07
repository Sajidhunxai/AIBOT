"""Tests for Binance SL/TP helpers."""

from __future__ import annotations

from core.bot import TradingBot
from utils.helpers import format_exchange_value, parse_symbol_filters


def test_parse_symbol_filters() -> None:
    info = {
        "symbol": "BTCUSDT",
        "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
            {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
        ],
    }
    filters = parse_symbol_filters(info)
    assert filters.tick_size == 0.10
    assert filters.step_size == 0.001


def test_format_exchange_value() -> None:
    assert format_exchange_value(50123.456, 0.1) == "50123.4"
    assert format_exchange_value(0.01234, 0.001) == "0.012"


def test_valid_stop_price() -> None:
    assert TradingBot._valid_stop_price("LONG", 90.0, 100.0, "sl")
    assert not TradingBot._valid_stop_price("LONG", 110.0, 100.0, "sl")
    assert TradingBot._valid_stop_price("LONG", 110.0, 100.0, "tp")
    assert TradingBot._valid_stop_price("SHORT", 110.0, 100.0, "sl")
    assert TradingBot._valid_stop_price("SHORT", 90.0, 100.0, "tp")
