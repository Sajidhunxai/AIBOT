"""Persist and list AI model files on disk."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from ai.model import TradeFilterModel
from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL_NAME = "trade_filter"


class ModelStore:
    """Save/load/list `.joblib` models under `models/` (Docker volume on EC2)."""

    def __init__(self, models_dir: str | Path = "models") -> None:
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str = DEFAULT_MODEL_NAME) -> Path:
        filename = name if name.endswith(".joblib") else f"{name}.joblib"
        return self.models_dir / filename

    def list_models(self) -> list[dict[str, str | int | float | bool]]:
        entries: list[dict[str, str | int | float | bool]] = []
        for path in sorted(self.models_dir.glob("*.joblib"), key=lambda p: p.stat().st_mtime, reverse=True):
            stat = path.stat()
            entries.append(
                {
                    "name": path.stem,
                    "filename": path.name,
                    "path": str(path),
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                    "ready": TradeFilterModel(str(path)).is_ready,
                }
            )
        return entries

    def save(
        self,
        model: TradeFilterModel,
        name: str = DEFAULT_MODEL_NAME,
        *,
        set_active: bool = True,
        archive: bool = True,
    ) -> Path:
        target = self.path_for(name)
        model.save(str(target))

        if set_active and name != DEFAULT_MODEL_NAME:
            active = self.path_for(DEFAULT_MODEL_NAME)
            shutil.copy2(target, active)
            logger.info("ai_model_set_active", path=str(active))

        if archive:
            stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            archive_path = self.models_dir / f"{Path(name).stem}_{stamp}.joblib"
            shutil.copy2(target, archive_path)
            logger.info("ai_model_archived", path=str(archive_path))

        return target

    def load(self, name: str = DEFAULT_MODEL_NAME) -> TradeFilterModel:
        path = self.path_for(name)
        return TradeFilterModel(model_path=str(path))
