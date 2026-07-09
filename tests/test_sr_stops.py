"""Support/resistance stop placement tests."""

import pandas as pd

from risk.sr_stops import compute_sr_stops


def _sample_ohlcv() -> pd.DataFrame:
    rows = []
    price = 100.0
    for i in range(60):
        high = price + 2
        low = price - 2
        rows.append(
            {
                "open": price,
                "high": high,
                "low": low,
                "close": price,
                "volume": 1000 + i,
            }
        )
        price += 0.1 if i % 5 else -0.05
    return pd.DataFrame(rows)


class TestSrStops:
    def test_long_uses_resistance_for_target(self) -> None:
        df = _sample_ohlcv()
        entry = float(df["close"].iloc[-1])
        sl, tp, details = compute_sr_stops("LONG", entry, df, atr=2.0, lookback=50)
        assert sl < entry
        assert tp > entry
        assert details["nearest_support"] is not None or details["nearest_resistance"] is not None

    def test_short_uses_support_for_target(self) -> None:
        df = _sample_ohlcv()
        entry = float(df["close"].iloc[-1])
        sl, tp, _ = compute_sr_stops("SHORT", entry, df, atr=2.0, lookback=50)
        assert sl > entry
        assert tp < entry

    def test_clamps_reward_risk(self) -> None:
        df = _sample_ohlcv()
        entry = 100.0
        sl, tp, _ = compute_sr_stops(
            "LONG",
            entry,
            df,
            atr=1.0,
            lookback=50,
            fallback_take_profit_rr=1.25,
            min_rr=1.0,
            max_rr=1.5,
        )
        sl_dist = entry - sl
        rr = (tp - entry) / sl_dist
        assert 1.0 <= rr <= 1.5
