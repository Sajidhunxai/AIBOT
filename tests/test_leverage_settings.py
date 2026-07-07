"""Tests for per-account leverage settings."""

from __future__ import annotations

from utils.leverage_settings import leverage_for_symbol, load_account_leverage, save_account_leverage


class FakeConfig:
    def get(self, key: str, default: object = None) -> object:
        data = {
            "leverage.default": 10,
            "leverage.per_symbol": {"BTCUSDT": 10, "ETHUSDT": 5},
        }
        return data.get(key, default)


def test_leverage_for_symbol_uses_override() -> None:
    settings = {"default": 10, "per_symbol": {"ETHUSDT": 7}}
    assert leverage_for_symbol(settings, "ETHUSDT") == 7
    assert leverage_for_symbol(settings, "BTCUSDT") == 10


def test_load_defaults_without_file(tmp_path, monkeypatch) -> None:
    import utils.leverage_settings as mod

    monkeypatch.setattr(mod, "ACCOUNTS_DIR", tmp_path)
    settings = load_account_leverage(1, FakeConfig())
    assert settings["default"] == 10
    assert settings["per_symbol"]["ETHUSDT"] == 5


def test_save_and_load_roundtrip(tmp_path, monkeypatch) -> None:
    import utils.leverage_settings as mod

    monkeypatch.setattr(mod, "ACCOUNTS_DIR", tmp_path)
    save_account_leverage(2, {"default": 8, "per_symbol": {"BTCUSDT": 12}})
    loaded = load_account_leverage(2, FakeConfig())
    assert loaded["default"] == 8
    assert loaded["per_symbol"]["BTCUSDT"] == 12
