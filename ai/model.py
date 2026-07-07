"""ML model for trade filtering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

from ai.features import FeatureExtractor
from utils.logger import get_logger

logger = get_logger(__name__)


class TradeFilterModel:
    """Gradient boosting classifier for trade approval."""

    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = model_path
        self.model: GradientBoostingClassifier | None = None
        self.scaler = StandardScaler()
        self.feature_extractor = FeatureExtractor()
        self._is_trained = False

        if model_path and Path(model_path).exists():
            self.load(model_path)

    def train(self, X: np.ndarray, y: np.ndarray) -> dict[str, Any]:
        """Train the model on historical features and labels."""
        X_scaled = self.scaler.fit_transform(X)
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42,
        )
        self.model.fit(X_scaled, y)
        self._is_trained = True
        score = float(self.model.score(X_scaled, y))
        logger.info("ai_model_trained", accuracy=score, samples=len(y))
        return {"accuracy": score, "samples": len(y)}

    def predict_proba(self, features: np.ndarray) -> float:
        """Return probability of trade success."""
        if not self._is_trained or self.model is None:
            return 0.5
        X = features.reshape(1, -1)
        X_scaled = self.scaler.transform(X)
        proba = self.model.predict_proba(X_scaled)[0]
        return float(proba[1]) if len(proba) > 1 else float(proba[0])

    def save(self, path: str | None = None) -> None:
        save_path = Path(path or self.model_path or "models/trade_filter.joblib")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"model": self.model, "scaler": self.scaler, "trained": self._is_trained},
            save_path,
        )
        logger.info("ai_model_saved", path=str(save_path))

    def load(self, path: str) -> None:
        data = joblib.load(path)
        self.model = data["model"]
        self.scaler = data["scaler"]
        self._is_trained = data.get("trained", True)
        logger.info("ai_model_loaded", path=path)

    @property
    def is_ready(self) -> bool:
        return self._is_trained and self.model is not None
