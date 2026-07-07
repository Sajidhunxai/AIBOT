"""Indicator unit tests."""

import pandas as pd

from indicators.momentum import adx, macd, rsi
from indicators.support_resistance import find_support_resistance
from indicators.trend import ema, sma, supertrend
from indicators.volatility import atr, bollinger_bands
from indicators.volume import volume_profile, vwap


class TestTrendIndicators:
    def test_ema(self, sample_ohlcv: pd.DataFrame) -> None:
        result = ema(sample_ohlcv["close"], 20)
        assert len(result.values) == len(sample_ohlcv)
        assert not pd.isna(result.values.iloc[-1])

    def test_sma(self, sample_ohlcv: pd.DataFrame) -> None:
        result = sma(sample_ohlcv["close"], 20)
        assert len(result.values) == len(sample_ohlcv)
        assert pd.isna(result.values.iloc[0])

    def test_supertrend(self, sample_ohlcv: pd.DataFrame) -> None:
        result = supertrend(sample_ohlcv, period=10, multiplier=3.0)
        assert "supertrend" in result.values.columns
        assert "direction" in result.values.columns


class TestMomentumIndicators:
    def test_rsi(self, sample_ohlcv: pd.DataFrame) -> None:
        result = rsi(sample_ohlcv["close"], 14)
        assert 0 <= result.last <= 100 or result.last == 0

    def test_macd(self, sample_ohlcv: pd.DataFrame) -> None:
        result = macd(sample_ohlcv["close"])
        assert "macd" in result.values.columns
        assert "signal" in result.values.columns
        assert "histogram" in result.values.columns

    def test_adx(self, sample_ohlcv: pd.DataFrame) -> None:
        result = adx(sample_ohlcv, 14)
        assert "adx" in result.values.columns


class TestVolatilityIndicators:
    def test_atr(self, sample_ohlcv: pd.DataFrame) -> None:
        result = atr(sample_ohlcv, 14)
        assert result.last >= 0

    def test_bollinger_bands(self, sample_ohlcv: pd.DataFrame) -> None:
        result = bollinger_bands(sample_ohlcv["close"], 20, 2.0)
        upper = float(result.values["upper"].iloc[-1])
        lower = float(result.values["lower"].iloc[-1])
        assert upper >= lower


class TestVolumeIndicators:
    def test_vwap(self, sample_ohlcv: pd.DataFrame) -> None:
        result = vwap(sample_ohlcv)
        assert result.last > 0

    def test_volume_profile(self, sample_ohlcv: pd.DataFrame) -> None:
        result = volume_profile(sample_ohlcv, num_bins=10, lookback=50)
        assert result.metadata is not None
        assert "poc" in result.metadata


class TestSupportResistance:
    def test_find_levels(self, sample_ohlcv: pd.DataFrame) -> None:
        result = find_support_resistance(sample_ohlcv, lookback=50)
        assert result.metadata is not None
        assert "support" in result.metadata
        assert "resistance" in result.metadata
