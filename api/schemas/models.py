"""Pydantic schemas for API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TradeResponse(BaseModel):
    id: int
    symbol: str
    side: str
    status: str
    strategy: str
    entry_price: float
    exit_price: float | None = None
    quantity: float
    pnl: float | None = None
    pnl_pct: float | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None


class SignalResponse(BaseModel):
    id: int
    symbol: str
    timeframe: str
    strategy: str
    action: str
    price: float
    confidence: float
    ai_approved: bool | None = None
    created_at: datetime | None = None


class PositionResponse(BaseModel):
    id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    unrealized_pnl: float = 0.0
    leverage: int = 1
    stop_loss: float | None = None
    take_profit: float | None = None
    strategy: str = ""
    account_id: int | None = None
    account_name: str | None = None


class PerformanceResponse(BaseModel):
    balance: float
    equity: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    total_trades: int
    open_positions: int
    daily_pnl: float
    strategy_stats: dict[str, Any] = Field(default_factory=dict)
    account_id: int | None = None
    account_name: str | None = None


class BotStatusResponse(BaseModel):
    running: bool
    engine_running: bool = False
    mode: str
    balance: float
    equity: float = 0.0
    unrealized_pnl: float = 0.0
    symbols: list[str]
    strategies: list[str]
    open_positions: int
    total_open_positions: int = 0
    running_accounts: list[dict[str, Any]] = Field(default_factory=list)
    risk: dict[str, Any] = Field(default_factory=dict)
    account: dict[str, Any] = Field(default_factory=dict)
    recent_signals: list[dict[str, Any]] = Field(default_factory=list)
    strategy_scan: dict[str, Any] = Field(default_factory=dict)


class AccountResponse(BaseModel):
    id: int
    name: str
    account_type: str
    paper_balance: float
    current_balance: float
    is_active: bool
    is_trading: bool = False
    notes: str | None = None


class CreateAccountRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    account_type: str = Field(default="demo", pattern="^(demo|live)$")
    paper_balance: float | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=255)


class ActivateAccountRequest(BaseModel):
    start: bool = Field(
        default=False,
        description="Start the bot on this account after switching (stops first if running)",
    )


class ActivateAccountResponse(BaseModel):
    id: int
    name: str
    account_type: str
    paper_balance: float
    current_balance: float
    is_active: bool
    is_trading: bool = False
    notes: str | None = None
    switched: bool
    running: bool
    running_accounts: list[dict[str, Any]] = Field(default_factory=list)
    started: bool
    message: str


class SetBalanceRequest(BaseModel):
    balance: float = Field(..., gt=0)


class ResetDemoRequest(BaseModel):
    balance: float | None = Field(default=None, gt=0)
    clear_history: bool = True
    close_positions: bool = True


class ManualTradeRequest(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=20)
    side: str = Field(..., pattern="^(BUY|SELL|LONG|SHORT)$")
    quantity: float = Field(..., gt=0)
    order_type: str = Field(default="MARKET", pattern="^(MARKET|LIMIT)$")
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    auto_sl_tp: bool = Field(default=True, description="Auto-calculate SL/TP from ATR if not provided")


class ClosePositionRequest(BaseModel):
    symbol: str | None = Field(default=None, min_length=3, max_length=20)
    position_id: str | None = None
    close_all: bool = False
    account_id: int | None = Field(default=None, description="Account to close (defaults to viewing account)")


class LogResponse(BaseModel):
    id: int
    level: str
    logger_name: str
    message: str
    created_at: datetime | None = None


class CandleResponse(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketSnapshotResponse(BaseModel):
    symbol: str
    price: float
    funding_rate: float = 0.0
    open_interest: float = 0.0


class TradeMarker(BaseModel):
    time: int
    type: str  # entry | exit
    side: str
    price: float
    strategy: str = ""
    pnl: float | None = None


class PriceLine(BaseModel):
    price: float
    color: str
    title: str
    style: str = "dashed"  # solid | dashed


class TradeMarkersResponse(BaseModel):
    markers: list[TradeMarker]
    price_lines: list[PriceLine]


class RiskSettingsResponse(BaseModel):
    risk_per_trade_pct: float
    max_concurrent_positions: int
    max_positions_per_symbol: int
    max_daily_loss_pct: float
    max_drawdown_pct: float
    max_unrealized_loss_pct: float
    emergency_close_unrealized_loss_pct: float
    max_total_exposure_pct: float
    signal_cooldown_minutes: int
    cooldown_after_loss_minutes: int
    block_duplicate_side: bool
    use_equity_for_limits: bool
    atr_stop_multiplier: float
    take_profit_rr: float
    trailing_stop_atr_multiplier: float
    break_even_trigger_rr: float
    position_size_method: str = "fixed_risk"
    trading_halted: bool = False
    halt_reason: str = ""
    open_positions: int = 0
    account_id: int | None = None
    account_name: str | None = None


class RiskSettingsUpdate(BaseModel):
    risk_per_trade_pct: float | None = Field(default=None, ge=0.1, le=10.0)
    max_concurrent_positions: int | None = Field(default=None, ge=1, le=50)
    max_positions_per_symbol: int | None = Field(default=None, ge=1, le=10)
    max_daily_loss_pct: float | None = Field(default=None, ge=0.5, le=50.0)
    max_drawdown_pct: float | None = Field(default=None, ge=1.0, le=50.0)
    max_unrealized_loss_pct: float | None = Field(default=None, ge=0.5, le=50.0)
    emergency_close_unrealized_loss_pct: float | None = Field(default=None, ge=1.0, le=50.0)
    max_total_exposure_pct: float | None = Field(default=None, ge=5.0, le=200.0)
    signal_cooldown_minutes: int | None = Field(default=None, ge=0, le=240)
    cooldown_after_loss_minutes: int | None = Field(default=None, ge=0, le=240)
    block_duplicate_side: bool | None = None
    use_equity_for_limits: bool | None = None
    atr_stop_multiplier: float | None = Field(default=None, ge=0.5, le=10.0)
    take_profit_rr: float | None = Field(default=None, ge=0.5, le=10.0)
    trailing_stop_atr_multiplier: float | None = Field(default=None, ge=0.5, le=10.0)
    break_even_trigger_rr: float | None = Field(default=None, ge=0.1, le=5.0)
    position_size_method: str | None = Field(default=None, pattern="^(fixed_risk|fixed_amount)$")


class StrategiesSettingsResponse(BaseModel):
    primary_timeframe: str
    active_strategies: list[str]
    strategies: dict[str, dict[str, Any]]
    account_id: int | None = None
    account_name: str | None = None


class StrategiesSettingsUpdate(BaseModel):
    strategies: dict[str, dict[str, Any]]


class TestSessionResponse(BaseModel):
    account_id: int | None = None
    account_name: str | None = None
    mode: str
    started_at: datetime
    days_running: float
    starting_balance: float
    current_equity: float
    return_pct: float
    session_pnl: float
    max_drawdown_pct: float
    closed_trades: int
    win_rate: float
    profit_factor: float
    auto_initialized: bool = False


class LeverageSettingsResponse(BaseModel):
    default: int
    max_leverage: int
    per_symbol: dict[str, int] = Field(default_factory=dict)
    resolved_per_symbol: dict[str, int] = Field(default_factory=dict)
    symbols: list[str] = Field(default_factory=list)
    mode: str
    account_id: int | None = None
    account_name: str | None = None


class LeverageSettingsUpdate(BaseModel):
    default: int | None = Field(default=None, ge=1, le=125)
    per_symbol: dict[str, int] | None = None
