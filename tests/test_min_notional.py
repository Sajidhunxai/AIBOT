"""Tests for min notional quantity helpers."""

from __future__ import annotations

from utils.helpers import ensure_min_notional_quantity, parse_symbol_filters


def test_parse_min_notional_filter() -> None:
    info = {
        "symbol": "ETHUSDT",
        "filters": [
            {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
            {"filterType": "MIN_NOTIONAL", "notional": "20"},
        ],
    }
    filters = parse_symbol_filters(info)
    assert filters.min_notional == 20.0


def test_ensure_min_notional_bumps_small_order() -> None:
    # 0.001 ETH @ 2500 = $2.50, below $20 min
    qty = ensure_min_notional_quantity(0.001, 2500.0, 20.0, 0.001, 0.001)
    assert qty * 2500.0 >= 20.0
    assert qty >= 0.008


def test_ensure_min_notional_keeps_large_order() -> None:
    qty = ensure_min_notional_quantity(0.1, 2500.0, 20.0, 0.001, 0.001)
    assert qty == 0.1
