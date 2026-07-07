"""Feature extraction for AI filter."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from indicators.momentum import adx, macd, rsi
from indicators.trend import ema
from indicators.volatility import atr, bollinger_bands
from indicators.volume import vwap


class FeatureExtractor:
    """Extract features from market data for ML model."""

    FEATURE_NAMES = [
        "trend_ema_ratio",
        "trend_price_ema_dist",
        "momentum_rsi",
        "momentum_macd_hist",
        "momentum_adx",
        "volume_ratio",
        "volume_vwap_dist",
        "funding_rate",
        "open_interest_change",
        "bb_position",
    ]

    def extract(
        self,
        candles: pd.DataFrame,
        funding_rate: float = 0.0,
        open_interest: float = 0.0,
        prev_open_interest: float = 0.0,
    ) -> np.ndarray:
        """Extract feature vector from market context."""
        if len(candles) < 30:
            return np.zeros(len(self.FEATURE_NAMES))

        close = candles["close"]
        volume = candles["volume"]
        price = float(close.iloc[-1])

        ema_20 = ema(close, 20).values
        ema_50 = ema(close, 50).values
        rsi_vals = rsi(close, 14).values
        macd_vals = macd(close).values
        adx_vals = adx(candles, 14).values
        atr_vals = atr(candles, 14).values
        bb = bollinger_bands(close, 20, 2.0).values
        vwap_vals = vwap(candles).values

        ema20 = float(ema_20.iloc[-1])
        ema50 = float(ema_50.iloc[-1])
        curr_rsi = float(rsi_vals.iloc[-1])
        macd_hist = float(macd_vals["histogram"].iloc[-1])
        curr_adx = float(adx_vals["adx"].iloc[-1])
        curr_atr = float(atr_vals.iloc[-1])
        bb_upper = float(bb["upper"].iloc[-1])
        bb_lower = float(bb["lower"].iloc[-1])
        curr_vwap = float(vwap_vals.iloc[-1])

        avg_vol = float(volume.rolling(20).mean().iloc[-1])
        curr_vol = float(volume.iloc[-1])
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

        bb_range = bb_upper - bb_lower
        bb_position = (price - bb_lower) / bb_range if bb_range > 0 else 0.5

        oi_change = (
            (open_interest - prev_open_interest) / prev_open_interest
            if prev_open_interest > 0
            else 0.0
        )

        features = np.array(
            [
                ema20 / ema50 if ema50 > 0 else 1.0,
                (price - ema20) / curr_atr if curr_atr > 0 else 0.0,
                curr_rsi / 100.0,
                macd_hist / price if price > 0 else 0.0,
                curr_adx / 100.0,
                vol_ratio,
                (price - curr_vwap) / curr_atr if curr_atr > 0 else 0.0,
                funding_rate,
                oi_change,
                bb_position,
            ],
            dtype=np.float64,
        )
        return np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

    def extract_dict(
        self,
        candles: pd.DataFrame,
        funding_rate: float = 0.0,
        open_interest: float = 0.0,
        prev_open_interest: float = 0.0,
    ) -> dict[str, float]:
        features = self.extract(candles, funding_rate, open_interest, prev_open_interest)
        return dict(zip(self.FEATURE_NAMES, features.tolist(), strict=True))
