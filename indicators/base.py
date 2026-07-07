"""Base indicator types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class IndicatorResult:
    name: str
    values: pd.Series | pd.DataFrame
    metadata: dict[str, Any] | None = None

    @property
    def last(self) -> float:
        if isinstance(self.values, pd.DataFrame):
            return float(self.values.iloc[-1, 0])
        val = self.values.iloc[-1]
        return float(val) if pd.notna(val) else 0.0
