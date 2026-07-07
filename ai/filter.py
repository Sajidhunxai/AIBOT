"""AI signal filter orchestrator."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ai.features import FeatureExtractor
from ai.model import TradeFilterModel
from strategies.base import Signal
from utils.logger import get_logger

logger = get_logger(__name__)


class AIFilter:
    """Optional AI filter to approve or reject trade signals."""

    def __init__(self, config: dict[str, Any], model_path: str | None = None) -> None:
        self.enabled = config.get("enabled", False)
        self.min_confidence = float(config.get("min_confidence", 0.6))
        self.feature_extractor = FeatureExtractor()
        self.model = TradeFilterModel(model_path=model_path)

    def evaluate(
        self,
        signal: Signal,
        candles: pd.DataFrame,
        funding_rate: float = 0.0,
        open_interest: float = 0.0,
        prev_open_interest: float = 0.0,
    ) -> tuple[bool, float, dict[str, float]]:
        """
        Evaluate signal with AI filter.
        Returns (approved, confidence, features).
        """
        features = self.feature_extractor.extract_dict(
            candles, funding_rate, open_interest, prev_open_interest
        )

        if not self.enabled:
            return True, 1.0, features

        if not self.model.is_ready:
            logger.warning("ai_filter_not_trained", action="passing_signal")
            return True, 0.5, features

        feature_array = self.feature_extractor.extract(
            candles, funding_rate, open_interest, prev_open_interest
        )
        confidence = self.model.predict_proba(feature_array)
        approved = confidence >= self.min_confidence

        logger.info(
            "ai_filter_decision",
            signal=signal.action.value,
            symbol=signal.symbol,
            approved=approved,
            confidence=confidence,
        )
        return approved, confidence, features
