"""Main trading bot orchestrator."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from ai.filter import AIFilter
from core.account_manager import AccountManager
from core.engine import StrategyEngine
from core.paper_trader import PaperPosition, PaperTrader
from core.state import BotState, StateManager
from database.models import Signal as DBSignal
from database.models import SignalAction, Trade, TradeSide, TradeStatus
from database.repositories.signals import SignalRepository
from database.repositories.trades import TradeRepository
from database.session import get_async_session
from exchange.base import PositionInfo
from exchange.binance_futures import BinanceFuturesClient
from exchange.market_data import MarketDataManager
from exchange.websocket_manager import WebSocketManager
from indicators.volatility import atr
from notifications.telegram import TelegramNotifier
from risk.manager import OpenPositionSnapshot, RiskContext, RiskManager
from risk.stops import build_initial_stop_state, stop_state_from_dict, stop_state_to_dict
from strategies.base import Signal, SignalType
from utils.config import AppConfig, load_config
from utils.helpers import SymbolFilters, ensure_min_notional_quantity, safe_float
from utils.logger import get_logger, setup_logging
from utils.leverage_settings import leverage_for_symbol as resolve_leverage
from utils.leverage_settings import load_account_leverage
from utils.risk_settings import load_account_risk, save_account_risk
from utils.strategy_settings import save_account_strategy

logger = get_logger(__name__)


def _as_utc_aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class TradingBot:
    """Production trading bot with live, testnet, and paper modes."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_config()
        self.settings = self.config.settings
        self._running = False
        self._tasks: list[asyncio.Task[None]] = []
        self._engine_lock = asyncio.Lock()

        setup_logging(
            level=self.config.get("logging.level", self.settings.log_level),
            log_dir=self.settings.log_dir,
            max_bytes=int(self.config.get("logging.max_bytes", 10485760)),
            backup_count=int(self.config.get("logging.backup_count", 10)),
            json_format=self.config.get("logging.format") == "json",
        )

        self.exchange = BinanceFuturesClient(
            api_key=self.settings.binance_api_key,
            api_secret=self.settings.binance_api_secret,
            testnet=self.config.is_testnet,
            recv_window=int(self.config.get("exchange.recv_window", 5000)),
        )
        self.ws_manager = WebSocketManager(
            testnet=self.config.is_testnet,
            reconnect_delay=float(self.config.get("exchange.reconnect_delay_seconds", 5)),
            max_reconnect_attempts=int(self.config.get("exchange.max_reconnect_attempts", 10)),
            ping_interval=float(self.config.get("market_data.websocket_ping_interval", 30)),
        )
        self.market_data = MarketDataManager(
            exchange=self.exchange,
            ws_manager=self.ws_manager,
            symbols=self.config.symbols,
            timeframes=self.config.timeframes,
            candle_limit=int(self.config.get("market_data.candle_limit", 500)),
        )
        self.ai_filter = AIFilter(
            self.config.get("ai_filter", {}),
            model_path=self.settings.ai_model_path,
        )
        ai_filter = self.ai_filter if self.config.ai_filter_enabled else None
        self.account_manager = AccountManager(
            risk_config=self.config.risk,
            strategies_yaml=self.config.strategies,
            primary_timeframe=self.config.primary_timeframe,
            ai_filter=ai_filter,
            default_balance=float(self.config.get("paper_trading.initial_balance", 10000)),
            slippage_pct=float(self.config.get("paper_trading.slippage_pct", 0.02)),
        )
        self.state_manager = StateManager(self.settings.state_file)
        self.telegram = TelegramNotifier(
            token=self.settings.telegram_bot_token,
            chat_id=self.settings.telegram_chat_id,
            enabled=self.settings.telegram_enabled,
            config=self.config.get("notifications.telegram", {}),
        )
        self._balance: float = 0.0
        self._equity: float = 0.0
        self._total_assets: float = 0.0
        self._unrealized_pnl: float = 0.0
        self._exchange_open_positions: int = 0
        self._exchange_positions: list[PositionInfo] = []
        self._signals: list[Signal] = []
        self._running_accounts: set[int] = set()
        self._account_names: dict[int, str] = {}

    @property
    def paper_trader(self) -> PaperTrader:
        return self.account_manager.paper_trader

    @property
    def risk_manager(self) -> RiskManager:
        return self.account_manager.risk_manager

    @property
    def strategy_engine(self) -> StrategyEngine:
        return self.account_manager.strategy_engine

    @property
    def running_accounts(self) -> set[int]:
        return set(self._running_accounts)

    def reload_ai_model(self, model_path: str | None = None) -> bool:
        path = model_path or self.settings.ai_model_path
        self.ai_filter = AIFilter(self.config.get("ai_filter", {}), model_path=path)
        ai = self.ai_filter if self.config.ai_filter_enabled else None
        self.account_manager.set_ai_filter(ai)
        ready = self.ai_filter.model.is_ready
        logger.info("ai_model_reloaded", path=path, ready=ready)
        return ready

    async def initialize_accounts(self) -> None:
        """Load or create trading accounts (call once at API startup)."""
        await self.account_manager.initialize()
        accounts = await self.account_manager.list_accounts()
        for account in accounts:
            self._account_names[account.id] = account.name
        self._balance = self.account_manager.paper_trader.balance
        if not self.config.is_paper:
            try:
                await self.sync_exchange_state()
            except Exception as e:
                logger.warning("exchange_balance_init_failed", error=str(e))

    async def sync_exchange_state(self) -> None:
        """Refresh balance/equity from Binance (testnet or live)."""
        if self.config.is_paper:
            return
        await self.exchange.connect()
        snap = await self.exchange.get_wallet_snapshot()
        self._balance = snap["balance"]
        self._equity = snap["equity"]
        self._total_assets = snap.get("total_assets", snap["equity"])
        self._unrealized_pnl = snap["unrealized_pnl"]
        positions = await self.exchange.get_positions()
        self._exchange_positions = positions
        self._exchange_open_positions = len(positions)
        aid = self.account_manager.active_account_id
        if aid and self.account_manager.has_runtime(aid):
            risk = self.account_manager.get_runtime(aid).risk_manager
            risk.set_balance(self._equity)
            if risk._peak_equity < self._equity:
                risk._peak_equity = self._equity
        for account_id in list(self._running_accounts):
            await self._sync_db_trades_with_exchange(account_id)

    async def _resolve_exchange_close(
        self, trade: Trade
    ) -> tuple[float, float, datetime]:
        """Find exit price and realized PnL from Binance fills after trade opened."""
        symbol = trade.symbol
        side = trade.side.value.upper()
        opened_at = _as_utc_aware(trade.opened_at) - timedelta(seconds=30)

        try:
            fills = await self.exchange.get_user_trades(symbol, limit=100)
        except Exception as e:
            logger.warning("exchange_close_fills_failed", symbol=symbol, error=str(e))
            fills = []

        close_fills: list[tuple[float, float, datetime]] = []
        for fill in fills:
            pnl = safe_float(fill.get("realizedPnl"))
            if abs(pnl) < 1e-12:
                continue
            pos_side = str(fill.get("positionSide", "")).upper()
            if pos_side not in ("LONG", "SHORT"):
                order_side = str(fill.get("side", "")).upper()
                pos_side = "LONG" if order_side == "BUY" else "SHORT"
            if pos_side != side:
                continue
            ts_ms = int(fill.get("time", 0))
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC) if ts_ms else datetime.min.replace(tzinfo=UTC)
            if ts >= opened_at:
                close_fills.append((safe_float(fill.get("price")), pnl, ts))

        if close_fills:
            close_fills.sort(key=lambda row: row[2])
            total_pnl = sum(row[1] for row in close_fills)
            exit_price, _, closed_at = close_fills[-1]
            return exit_price, total_pnl, closed_at

        try:
            items = await self.exchange.get_income_history("REALIZED_PNL", symbol=symbol, limit=50)
        except Exception:
            items = []
        for item in sorted(items, key=lambda row: int(row.get("time", 0)), reverse=True):
            ts_ms = int(item.get("time", 0))
            if not ts_ms:
                continue
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
            if ts >= opened_at:
                pnl = safe_float(item.get("income"))
                if abs(pnl) > 0:
                    return float(trade.entry_price or 0.0), pnl, ts

        return float(trade.entry_price or 0.0), 0.0, datetime.now(UTC)

    async def _sync_db_trades_with_exchange(self, account_id: int) -> None:
        """Close stale DB rows when exchange positions disappear; dedupe extras."""
        if self.config.is_paper:
            return

        exchange_keys = {
            (pos.symbol, pos.side.upper()): pos
            for pos in self._exchange_positions
            if pos.quantity > 0
        }

        try:
            async with get_async_session() as session:
                repo = TradeRepository(session)
                open_trades = [
                    trade
                    for trade in await repo.get_open_trades(account_id=account_id)
                    if not trade.is_paper
                ]

                by_key: dict[tuple[str, str], list[Trade]] = {}
                for trade in open_trades:
                    key = (trade.symbol, trade.side.value.upper())
                    by_key.setdefault(key, []).append(trade)

                for key, trades in by_key.items():
                    if key not in exchange_keys:
                        trades.sort(
                            key=lambda trade: _as_utc_aware(trade.opened_at),
                        )
                        exit_price, total_pnl, closed_at = await self._resolve_exchange_close(
                            trades[-1]
                        )
                        for index, trade in enumerate(trades):
                            pnl = total_pnl if index == len(trades) - 1 else 0.0
                            pnl_pct = (
                                (pnl / (trade.entry_price * trade.quantity) * 100)
                                if pnl and trade.entry_price and trade.quantity
                                else 0.0
                            )
                            await repo.close_trade(
                                trade.id,
                                exit_price,
                                pnl,
                                pnl_pct,
                                closed_at=closed_at,
                            )
                            logger.info(
                                "db_trade_closed_exchange_sync",
                                trade_id=trade.id,
                                symbol=trade.symbol,
                                side=trade.side.value,
                                account_id=account_id,
                                exit_price=exit_price,
                                pnl=pnl,
                            )
                        runtime = self.account_manager.get_runtime(account_id)
                        daily_pnl = await repo.get_daily_pnl(account_id)
                        runtime.risk_manager.update_daily_pnl(daily_pnl)
                        continue

                    if len(trades) <= 1:
                        continue

                    position = exchange_keys[key]
                    trades.sort(key=lambda trade: abs(trade.quantity - position.quantity))
                    for duplicate in trades[1:]:
                        await repo.close_trade(
                            duplicate.id,
                            float(duplicate.entry_price or 0.0),
                            0.0,
                            0.0,
                        )
                        logger.info(
                            "db_duplicate_open_closed",
                            trade_id=duplicate.id,
                            symbol=duplicate.symbol,
                            side=duplicate.side.value,
                            account_id=account_id,
                        )
        except Exception as e:
            logger.error("db_trade_exchange_sync_failed", account_id=account_id, error=str(e))

    def save_account_risk_settings(self, account_id: int | None = None) -> None:
        aid = account_id or self.account_manager.active_account_id
        if aid is None or not self.account_manager.has_runtime(aid):
            return
        risk = self.account_manager.get_runtime(aid).risk_manager
        settings = risk.get_settings()
        for key in ("trading_halted", "halt_reason", "open_positions", "account_id", "account_name"):
            settings.pop(key, None)
        save_account_risk(aid, settings)

    def leverage_for_symbol(self, symbol: str, account_id: int | None = None) -> int:
        aid = account_id or self.account_manager.active_account_id
        settings = load_account_leverage(aid, self.config)
        return resolve_leverage(settings, symbol)

    async def _order_filters_for(self, symbol: str) -> SymbolFilters:
        if self.config.is_paper:
            return SymbolFilters(tick_size=0.01, step_size=0.001, min_notional=0.0)
        return await self.exchange.get_symbol_filters(symbol)

    async def apply_account_leverage(self, account_id: int | None = None) -> None:
        """Push saved leverage to Binance for each configured symbol."""
        if self.config.is_paper:
            return
        aid = account_id or self.account_manager.active_account_id
        if aid is None:
            return
        await self.exchange.connect()
        for symbol in self.config.symbols:
            lev = self.leverage_for_symbol(symbol, account_id=aid)
            await self.exchange.set_leverage(symbol, lev)
            logger.info("exchange_leverage_set", symbol=symbol, leverage=lev, account_id=aid)

    def reload_account_risk(self, account_id: int | None = None) -> None:
        """Rebuild risk manager for one account from saved settings."""
        aid = account_id or self.account_manager.active_account_id
        if aid is None:
            return
        if not self.account_manager.has_runtime(aid):
            account = self.account_manager.active_account
            if account and account.id == aid:
                self.account_manager.ensure_runtime(account)
            else:
                return
        runtime = self.account_manager.get_runtime(aid)
        trader = runtime.paper_trader
        runtime.risk_manager = RiskManager(self.config.risk)
        overrides = load_account_risk(aid, migrate_global=(aid == 1))
        if overrides:
            runtime.risk_manager.apply_settings(overrides)
        runtime.risk_manager.set_balance(trader.balance)
        runtime.risk_manager._peak_equity = trader.balance
        runtime.risk_manager._initial_balance = trader.balance

    def save_account_strategy_settings(self, account_id: int | None = None) -> None:
        aid = account_id or self.account_manager.active_account_id
        if aid is None or not self.account_manager.has_runtime(aid):
            return
        runtime = self.account_manager.get_runtime(aid)
        save_account_strategy(aid, runtime.strategies_config)

    def reload_account_strategies(self, account_id: int | None = None) -> None:
        aid = account_id or self.account_manager.active_account_id
        if aid is None:
            return
        if not self.account_manager.has_runtime(aid):
            account = self.account_manager.active_account
            if account and account.id == aid:
                self.account_manager.ensure_runtime(account)
            else:
                return
        self.account_manager.reload_strategy_for_account(aid)

    async def _ensure_engine_running(self) -> None:
        async with self._engine_lock:
            alive = self._running and any(not task.done() for task in self._tasks)
            if alive:
                return
            if self._tasks:
                self._tasks.clear()
            self._running = False

            logger.info(
                "bot_engine_starting",
                mode=self.settings.trading_mode.value,
                symbols=self.config.symbols,
            )
            await self.exchange.connect()
            if not self.config.is_paper:
                if self.config.hedge_mode:
                    await self.exchange.set_hedge_mode(True)
                for symbol in self.config.symbols:
                    await self.exchange.set_leverage(
                        symbol,
                        self.leverage_for_symbol(
                            symbol, account_id=self.account_manager.active_account_id
                        ),
                    )
            self.market_data.reset_strategy_eval_gate()
            await self.market_data.initialize()
            self._running = True
            self._tasks.append(asyncio.create_task(self._main_loop()))
            self._tasks.append(asyncio.create_task(self._report_loop()))

    async def _sync_account_risk_state(self, account_id: int) -> None:
        runtime = self.account_manager.get_runtime(account_id)
        trader = runtime.paper_trader
        risk = runtime.risk_manager
        if self.config.is_paper:
            balance = trader.balance
        else:
            await self.sync_exchange_state()
            balance = self._equity if self._equity > 0 else self._balance
        risk.set_balance(balance)
        risk._peak_equity = balance
        risk._initial_balance = balance
        risk.resume_trading()
        try:
            async with get_async_session() as session:
                repo = TradeRepository(session)
                daily_pnl = await repo.get_daily_pnl(account_id)
                risk.update_daily_pnl(daily_pnl)
        except Exception as e:
            logger.error("risk_sync_failed", account_id=account_id, error=str(e))

    async def start_account(self, account_id: int) -> bool:
        """Start trading for one account without stopping others."""
        account = await self.account_manager.get_account(account_id)
        if account is None:
            raise ValueError("Account not found")
        self.account_manager.ensure_runtime(account)
        self._account_names[account_id] = account.name
        if account_id in self._running_accounts:
            return False
        await self._ensure_engine_running()
        self._running_accounts.add(account_id)
        await self._sync_account_risk_state(account_id)
        if not self.config.is_paper:
            await self.apply_account_leverage(account_id)
        if self.config.is_paper:
            self._balance = self.account_manager.get_runtime(account_id).paper_trader.balance
        logger.info("account_trading_started", account_id=account_id, name=account.name)
        return True

    async def stop_account(self, account_id: int, *, notify: bool = True) -> bool:
        """Stop trading for one account; engine stops when no accounts remain."""
        if account_id not in self._running_accounts:
            return False
        self.account_manager.save_runtime(account_id)
        self.save_account_risk_settings(account_id)
        self.save_account_strategy_settings(account_id)
        self._running_accounts.discard(account_id)
        if not self._running_accounts:
            await self.stop(notify=notify)
        else:
            account = await self.account_manager.get_account(account_id)
            name = account.name if account else str(account_id)
            if notify:
                await self.telegram.send_message(f"🛑 Stopped trading on {name}")
            logger.info("account_trading_stopped", account_id=account_id)
        return True

    async def start(self) -> None:
        """Start trading on the active account."""
        aid = self.account_manager.active_account_id
        if aid is None:
            raise RuntimeError("No active account")
        started = await self.start_account(aid)
        if started:
            account = self.account_manager.active_account
            name = account.name if account else str(aid)
            await self.telegram.send_message(
                f"🚀 AIBotTrade started on {name}\n"
                f"Mode: {self.settings.trading_mode.value}\n"
                f"Symbols: {', '.join(self.config.symbols)}"
            )
        logger.info("bot_started", running_accounts=list(self._running_accounts))

    async def stop(self, *, notify: bool = True) -> None:
        """Gracefully stop the bot engine and all account trading."""
        async with self._engine_lock:
            running = list(self._running_accounts)
            for aid in running:
                self.account_manager.save_runtime(aid)
                self.save_account_risk_settings(aid)
                self.save_account_strategy_settings(aid)
            self._running_accounts.clear()
            self._running = False
            tasks = list(self._tasks)
            self._tasks.clear()
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await self.ws_manager.stop_all()
            if not self.config.is_paper:
                await self.exchange.disconnect()
            self._save_state()
            if notify:
                await self.telegram.send_message("🛑 AIBotTrade stopped")
            logger.info("bot_stopped")

    async def switch_account(self, account_id: int, *, start: bool = False) -> dict[str, Any]:
        """Switch dashboard focus; optionally start trading on this account (others keep running)."""
        current_id = self.account_manager.active_account_id

        if current_id == account_id and not start:
            account = self.account_manager.active_account
            if account is None:
                raise ValueError("No active account")
            return self._switch_result(account, switched=False, started=False)

        switched = current_id != account_id
        if switched:
            if current_id is not None:
                self.save_account_risk_settings(current_id)
                self.save_account_strategy_settings(current_id)
            account = await self.account_manager.activate_account(account_id)
            self._balance = self.account_manager.get_runtime(account_id).paper_trader.balance
            self.reload_account_risk(account_id)
            self.reload_account_strategies(account_id)
        else:
            account = self.account_manager.active_account
            if account is None:
                raise ValueError("Account not found")

        started = False
        if start:
            started = await self.start_account(account_id)

        return self._switch_result(account, switched=switched, started=started)

    def _switch_result(
        self, account: Any, *, switched: bool, started: bool
    ) -> dict[str, Any]:
        return {
            "account_id": account.id,
            "account_name": account.name,
            "account_type": account.account_type.value,
            "switched": switched,
            "running": account.id in self._running_accounts,
            "running_accounts": self._running_accounts_payload(),
            "started": started,
        }

    def _running_accounts_payload(self) -> list[dict[str, Any]]:
        return [
            {"id": aid, "name": self._account_names.get(aid, f"Account {aid}")}
            for aid in sorted(self._running_accounts)
        ]

    async def _main_loop(self) -> None:
        interval = 5
        while self._running:
            try:
                if not self.config.is_paper:
                    await self.sync_exchange_state()
                for account_id in list(self._running_accounts):
                    for symbol in self.config.symbols:
                        await self._process_symbol_for_account(account_id, symbol)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("main_loop_error", error=str(e))
                await self.telegram.send_error(str(e))
                await asyncio.sleep(interval)

    async def _process_symbol_for_account(self, account_id: int, symbol: str) -> None:
        runtime = self.account_manager.get_runtime(account_id)
        trader = runtime.paper_trader
        risk = runtime.risk_manager
        price = self.market_data.get_latest_price(symbol)
        if price <= 0:
            return

        risk_context = self._build_risk_context_for(account_id)

        if self.config.is_paper and risk.should_emergency_close(risk_context):
            await self._emergency_close_all(account_id, "emergency_unrealized_loss")
            return

        if self.config.is_paper:
            candles = self.market_data.get_candles(symbol, self.config.primary_timeframe)
            atr_val = (
                float(atr(candles, 14).values.iloc[-1]) if not candles.empty else price * 0.01
            )
            trader.update_trailing_stops(symbol, price, risk.stop_manager, atr_val)
            for pos_id, reason in trader.check_stops(symbol, price):
                trade = await trader.close_position(pos_id, price, reason)
                if trade:
                    await self._persist_closed_trade(trade, account_id)
                    if trade["pnl"] < 0:
                        risk.record_loss()
        elif self.config.get("orders.update_exchange_trailing_sl", True):
            candles = self.market_data.get_candles(symbol, self.config.primary_timeframe)
            atr_val = (
                float(atr(candles, 14).values.iloc[-1]) if not candles.empty else price * 0.01
            )
            await self._update_exchange_trailing_stops(
                account_id, symbol, price, risk, atr_val
            )

        if risk.trading_halted:
            return

        tf = self.config.primary_timeframe
        if not self.market_data.should_evaluate_strategies(symbol, tf):
            return

        signals = runtime.strategy_engine.evaluate(symbol, self.market_data, tf)
        if signals:
            self._signals = (self._signals + signals)[-50:]
        else:
            scan = runtime.strategy_engine.diagnose(symbol, self.market_data)
            logger.info(
                "strategy_scan",
                symbol=symbol,
                account_id=account_id,
                timeframe=tf,
                strategies=scan.get("strategies", {}),
            )

        for signal in signals:
            await self._handle_signal(signal, account_id)

    def _build_risk_context_for(self, account_id: int) -> RiskContext:
        runtime = self.account_manager.get_runtime(account_id)
        trader = runtime.paper_trader
        if self.config.is_paper:
            balance = trader.balance
            equity, unrealized = self.get_paper_equity_for(account_id)
            snapshots = [
                OpenPositionSnapshot(
                    symbol=pos.symbol,
                    side=pos.side,
                    quantity=pos.quantity,
                    entry_price=pos.entry_price,
                    opened_at=pos.opened_at,
                )
                for pos in trader.positions.values()
            ]
        else:
            balance = self._balance
            equity = self._equity if self._equity > 0 else self._balance
            unrealized = self._unrealized_pnl
            snapshots = [
                OpenPositionSnapshot(
                    symbol=pos.symbol,
                    side=pos.side,
                    quantity=pos.quantity,
                    entry_price=pos.entry_price,
                    opened_at=pos.opened_at,
                )
                for pos in self._exchange_positions
            ]
        return RiskContext(
            balance=balance,
            equity=equity,
            open_positions=snapshots,
            unrealized_pnl=unrealized,
        )

    async def _emergency_close_all(self, account_id: int, reason: str) -> None:
        """Force-close all paper positions for one account."""
        logger.warning("emergency_close_all", account_id=account_id, reason=reason)
        closed = await self.close_paper_positions(account_id=account_id)
        account = await self.account_manager.get_account(account_id)
        name = account.name if account else str(account_id)
        await self.telegram.send_message(
            f"⚠️ Emergency close on {name}: {reason}\nClosed {len(closed)} position(s)"
        )

    async def place_manual_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        account_id: int | None = None,
    ) -> dict[str, Any]:
        """Place a manual paper trade with optional custom SL/TP."""
        aid = account_id or self.account_manager.active_account_id
        if aid is None:
            raise RuntimeError("No active account")
        if aid not in self._running_accounts:
            raise RuntimeError("Account is not trading — start it first")

        runtime = self.account_manager.get_runtime(aid)
        trader = runtime.paper_trader
        risk = runtime.risk_manager

        price = self.market_data.get_latest_price(symbol)
        if price <= 0:
            raise ValueError(f"No price data for {symbol}")

        candles = self.market_data.get_candles(symbol, self.config.primary_timeframe)
        atr_val = float(atr(candles, 14).values.iloc[-1]) if not candles.empty else price * 0.01

        pos_side = "LONG" if side.upper() in ("BUY", "LONG") else "SHORT"
        order_side = "BUY" if pos_side == "LONG" else "SELL"

        if stop_loss is None or take_profit is None:
            auto_sl, auto_tp = risk.stop_manager.initial_stops(pos_side, price, atr_val)
            stop_loss = stop_loss if stop_loss is not None else auto_sl
            take_profit = take_profit if take_profit is not None else auto_tp

        risk_context = self._build_risk_context_for(aid)
        filters = await self._order_filters_for(symbol)
        quantity = ensure_min_notional_quantity(
            quantity,
            price,
            filters.min_notional,
            filters.step_size,
            filters.min_qty,
        )
        if filters.min_notional > 0 and quantity * price < filters.min_notional:
            raise ValueError(
                f"Order size too small — Binance minimum is ${filters.min_notional:.0f} notional"
            )
        risk_result = risk.check_manual_trade(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=price,
            context=risk_context,
            lot_step=filters.step_size,
            min_notional=filters.min_notional,
            min_qty=filters.min_qty,
        )
        if not risk_result.approved:
            raise ValueError(f"Trade blocked by risk rules: {risk_result.reason}")

        quantity = risk_result.quantity or quantity

        leverage = self.leverage_for_symbol(symbol, account_id=aid)

        if self.config.is_paper:
            await trader.place_market_order(
                symbol=symbol,
                side=order_side,
                quantity=quantity,
                strategy="manual",
                stop_loss=stop_loss,
                take_profit=take_profit,
                leverage=leverage,
                current_price=price,
            )
            await self.telegram.notify_entry(symbol, pos_side, price, quantity, "manual")
        else:
            position_side = pos_side if self.config.hedge_mode else "BOTH"
            order = await self.exchange.place_market_order(
                symbol, order_side, quantity, position_side, entry_price=price
            )
            sl_tp_orders = await self._place_exchange_sl_tp(
                symbol=symbol,
                position_side=pos_side,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            await self._persist_open_trade(
                account_id=aid,
                symbol=symbol,
                side=pos_side,
                quantity=quantity,
                entry_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy="manual",
                is_paper=False,
                leverage=leverage,
                exchange_order_id=order.order_id,
                metadata_json=sl_tp_orders,
            )
            await self.telegram.notify_entry(symbol, pos_side, price, quantity, "manual")

        logger.info(
            "manual_trade_placed",
            symbol=symbol,
            side=pos_side,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        self.account_manager.save_runtime(aid)
        return {
            "symbol": symbol,
            "side": pos_side,
            "quantity": quantity,
            "entry_price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }

    async def _handle_signal(self, signal: Signal, account_id: int) -> None:
        runtime = self.account_manager.get_runtime(account_id)
        trader = runtime.paper_trader
        risk = runtime.risk_manager
        candles = self.market_data.get_candles(signal.symbol, signal.timeframe)
        if candles.empty:
            return

        atr_val = float(atr(candles, 14).values.iloc[-1])
        risk_context = self._build_risk_context_for(account_id)
        filters = await self._order_filters_for(signal.symbol)
        risk_result = risk.check_signal(
            signal,
            risk_context,
            atr_val,
            lot_step=filters.step_size,
            min_notional=filters.min_notional,
            min_qty=filters.min_qty,
        )
        if not risk_result.approved:
            logger.info(
                "signal_rejected",
                reason=risk_result.reason,
                symbol=signal.symbol,
                account_id=account_id,
            )
            return

        await self._persist_signal(signal, risk_result, account_id)

        if signal.action == SignalType.BUY:
            side = "BUY"
            pos_side = "LONG"
        elif signal.action == SignalType.SELL:
            side = "SELL"
            pos_side = "SHORT"
        else:
            return

        leverage = self.leverage_for_symbol(signal.symbol, account_id=account_id)

        if self.config.is_paper:
            await trader.place_market_order(
                symbol=signal.symbol,
                side=side,
                quantity=risk_result.quantity,
                strategy=signal.strategy,
                stop_loss=risk_result.stop_loss,
                take_profit=risk_result.take_profit,
                leverage=leverage,
                current_price=signal.price,
            )
            await self.telegram.notify_entry(
                signal.symbol, pos_side, signal.price, risk_result.quantity, signal.strategy
            )
            self.account_manager.save_runtime(account_id)
        else:
            position_side = pos_side if self.config.hedge_mode else "BOTH"
            order_type = self.config.get("orders.default_type", "market")
            stop_loss = risk_result.stop_loss or signal.stop_loss
            take_profit = risk_result.take_profit or signal.take_profit
            try:
                if order_type == "limit":
                    offset = float(self.config.get("orders.limit_offset_pct", 0.05)) / 100
                    limit_price = signal.price * (1 - offset) if side == "BUY" else signal.price * (1 + offset)
                    order = await self.exchange.place_limit_order(
                        signal.symbol, side, risk_result.quantity, limit_price, position_side
                    )
                else:
                    order = await self.exchange.place_market_order(
                        signal.symbol,
                        side,
                        risk_result.quantity,
                        position_side,
                        entry_price=signal.price,
                    )
                sl_tp_orders = await self._place_exchange_sl_tp(
                    symbol=signal.symbol,
                    position_side=pos_side,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )
                await self._persist_open_trade(
                    account_id=account_id,
                    symbol=signal.symbol,
                    side=pos_side,
                    quantity=risk_result.quantity,
                    entry_price=signal.price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    strategy=signal.strategy,
                    is_paper=False,
                    leverage=leverage,
                    exchange_order_id=order.order_id,
                    metadata_json=sl_tp_orders,
                )
                await self.telegram.notify_entry(
                    signal.symbol, pos_side, signal.price, risk_result.quantity, signal.strategy
                )
                logger.info(
                    "auto_trade_placed",
                    symbol=signal.symbol,
                    side=pos_side,
                    quantity=risk_result.quantity,
                    strategy=signal.strategy,
                    account_id=account_id,
                )
            except Exception as e:
                logger.error(
                    "auto_trade_failed",
                    symbol=signal.symbol,
                    side=pos_side,
                    quantity=risk_result.quantity,
                    strategy=signal.strategy,
                    account_id=account_id,
                    error=str(e),
                )
                return

    async def _persist_signal(
        self, signal: Signal, risk_result: Any, account_id: int
    ) -> None:
        try:
            async with get_async_session() as session:
                repo = SignalRepository(session)
                action_map = {
                    SignalType.BUY: SignalAction.BUY,
                    SignalType.SELL: SignalAction.SELL,
                    SignalType.CLOSE: SignalAction.CLOSE,
                    SignalType.HOLD: SignalAction.HOLD,
                }
                db_signal = DBSignal(
                    symbol=signal.symbol,
                    timeframe=signal.timeframe,
                    strategy=signal.strategy,
                    action=action_map[signal.action],
                    price=signal.price,
                    confidence=signal.confidence,
                    ai_approved=signal.metadata.get("ai_approved"),
                    ai_confidence=signal.metadata.get("ai_confidence"),
                    indicators_json=signal.metadata,
                    account_id=account_id,
                )
                await repo.create(db_signal)
        except Exception as e:
            logger.error("persist_signal_failed", error=str(e))

    async def _place_exchange_sl_tp(
        self,
        *,
        symbol: str,
        position_side: str,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> dict[str, str | None]:
        """Place Binance STOP_MARKET and TAKE_PROFIT_MARKET after entry."""
        empty: dict[str, str | None] = {"sl_order_id": None, "tp_order_id": None}
        if self.config.is_paper or not self.config.get("orders.place_exchange_sl_tp", True):
            return empty

        pos = position_side.upper()
        hedge = self.config.hedge_mode
        mark = self.market_data.get_latest_price(symbol)
        if mark <= 0:
            try:
                mark = (await self.exchange.get_ticker(symbol)).price
            except Exception:
                mark = 0.0

        sl_id: str | None = None
        tp_id: str | None = None

        try:
            if stop_loss and stop_loss > 0 and self._valid_stop_price(pos, stop_loss, mark, "sl"):
                sl_order = await self.exchange.place_stop_loss_market(
                    symbol, pos, stop_loss, hedge_mode=hedge
                )
                sl_id = sl_order.order_id
                logger.info(
                    "exchange_sl_placed",
                    symbol=symbol,
                    side=pos,
                    stop_loss=stop_loss,
                    order_id=sl_id,
                )
            elif stop_loss:
                logger.warning(
                    "exchange_sl_skipped",
                    symbol=symbol,
                    side=pos,
                    stop_loss=stop_loss,
                    mark=mark,
                )

            if take_profit and take_profit > 0 and self._valid_stop_price(
                pos, take_profit, mark, "tp"
            ):
                tp_order = await self.exchange.place_take_profit_market(
                    symbol, pos, take_profit, hedge_mode=hedge
                )
                tp_id = tp_order.order_id
                logger.info(
                    "exchange_tp_placed",
                    symbol=symbol,
                    side=pos,
                    take_profit=take_profit,
                    order_id=tp_id,
                )
            elif take_profit:
                logger.warning(
                    "exchange_tp_skipped",
                    symbol=symbol,
                    side=pos,
                    take_profit=take_profit,
                    mark=mark,
                )
        except Exception as e:
            logger.error("exchange_sl_tp_failed", symbol=symbol, side=pos, error=str(e))
            if sl_id:
                try:
                    await self.exchange.cancel_algo_order(symbol, sl_id)
                except Exception:
                    pass
            if tp_id:
                try:
                    await self.exchange.cancel_algo_order(symbol, tp_id)
                except Exception:
                    pass
            return empty

        return {"sl_order_id": sl_id, "tp_order_id": tp_id}

    @staticmethod
    def _valid_stop_price(position_side: str, stop_price: float, mark: float, kind: str) -> bool:
        if mark <= 0:
            return True
        pos = position_side.upper()
        if kind == "sl":
            return stop_price < mark if pos == "LONG" else stop_price > mark
        return stop_price > mark if pos == "LONG" else stop_price < mark

    def _exchange_has_position(self, symbol: str, side: str) -> bool:
        pos_side = side.upper()
        for pos in self._exchange_positions:
            if pos.symbol != symbol or pos.quantity <= 0:
                continue
            if pos.side.upper() == pos_side:
                return True
            if pos.position_side and pos.position_side.upper() == pos_side:
                return True
        return False

    @staticmethod
    def _sl_improved(side: str, old_sl: float | None, new_sl: float, min_move_pct: float) -> bool:
        if old_sl is None:
            return True
        if new_sl == old_sl:
            return False
        if min_move_pct > 0:
            delta_pct = abs(new_sl - old_sl) / old_sl * 100
            if delta_pct < min_move_pct:
                return False
        pos = side.upper()
        if pos in ("LONG", "BUY"):
            return new_sl > old_sl
        return new_sl < old_sl

    async def _replace_exchange_stop_loss(
        self,
        *,
        symbol: str,
        position_side: str,
        old_sl_id: str | None,
        new_sl: float,
    ) -> str | None:
        hedge = self.config.hedge_mode
        if old_sl_id:
            try:
                await self.exchange.cancel_algo_order(symbol, old_sl_id)
            except Exception as e:
                logger.warning(
                    "cancel_old_sl_failed",
                    symbol=symbol,
                    algo_id=old_sl_id,
                    error=str(e),
                )

        await self.exchange.cancel_position_conditional_orders(
            symbol,
            position_side,
            order_types=("STOP_MARKET", "STOP"),
            hedge_mode=hedge,
        )
        await asyncio.sleep(0.4)

        if await self.exchange.has_position_conditional_order(
            symbol,
            position_side,
            order_types=("STOP_MARKET", "STOP"),
            hedge_mode=hedge,
        ):
            logger.warning(
                "trailing_sl_existing_order",
                symbol=symbol,
                side=position_side,
                message="Stop order still open after cancel; skipping replace",
            )
            return old_sl_id

        mark = self.market_data.get_latest_price(symbol)
        if mark <= 0:
            try:
                mark = (await self.exchange.get_ticker(symbol)).price
            except Exception:
                mark = 0.0

        if not self._valid_stop_price(position_side, new_sl, mark, "sl"):
            logger.warning(
                "trailing_sl_skipped_invalid",
                symbol=symbol,
                side=position_side,
                stop_loss=new_sl,
                mark=mark,
            )
            return old_sl_id

        order = await self.exchange.place_stop_loss_market(
            symbol,
            position_side,
            new_sl,
            hedge_mode=hedge,
        )
        return order.order_id

    async def _update_exchange_trailing_stops(
        self,
        account_id: int,
        symbol: str,
        price: float,
        risk: RiskManager,
        atr_val: float,
    ) -> None:
        if not self.config.get("orders.place_exchange_sl_tp", True):
            return

        min_move_pct = float(self.config.get("orders.min_trailing_sl_move_pct", 0.05))

        try:
            async with get_async_session() as session:
                repo = TradeRepository(session)
                trades = await repo.get_open_trades(symbol=symbol, account_id=account_id)
                by_side: dict[str, list[Any]] = {}
                for trade in trades:
                    if trade.is_paper:
                        continue
                    side = trade.side.value.upper()
                    if not self._exchange_has_position(symbol, side):
                        continue
                    if not trade.stop_loss or not trade.take_profit:
                        continue
                    by_side.setdefault(side, []).append(trade)

                for side, side_trades in by_side.items():
                    best: dict[str, Any] | None = None
                    old_sl_id: str | None = None

                    for trade in side_trades:
                        meta = dict(trade.metadata_json or {})
                        stop_state = stop_state_from_dict(
                            meta.get("stop_state"),
                            entry_price=trade.entry_price,
                            stop_loss=trade.stop_loss,
                            take_profit=trade.take_profit,
                        )
                        if stop_state is None:
                            continue

                        old_sl = trade.stop_loss
                        updated = risk.stop_manager.update_trailing(
                            stop_state, side, price, atr_val
                        )
                        new_sl = updated.stop_loss
                        meta["stop_state"] = stop_state_to_dict(updated)

                        if not self._sl_improved(side, old_sl, new_sl, min_move_pct):
                            await repo.update_open_trade_stops(trade.id, metadata_json=meta)
                            continue

                        sl_id = meta.get("sl_order_id")
                        if sl_id and not old_sl_id:
                            old_sl_id = str(sl_id)

                        candidate = {
                            "trade": trade,
                            "meta": meta,
                            "old_sl": old_sl,
                            "new_sl": new_sl,
                            "updated": updated,
                        }
                        if best is None:
                            best = candidate
                        elif side in ("LONG", "BUY"):
                            if new_sl > best["new_sl"]:
                                best = candidate
                        elif new_sl < best["new_sl"]:
                            best = candidate

                    if best is None:
                        continue

                    try:
                        new_sl_id = await self._replace_exchange_stop_loss(
                            symbol=symbol,
                            position_side=side,
                            old_sl_id=old_sl_id,
                            new_sl=float(best["new_sl"]),
                        )
                    except Exception as e:
                        logger.error(
                            "exchange_trailing_sl_failed",
                            symbol=symbol,
                            side=side,
                            account_id=account_id,
                            trade_id=best["trade"].id,
                            error=str(e),
                        )
                        continue

                    for trade in side_trades:
                        meta = dict(trade.metadata_json or {})
                        stop_state = stop_state_from_dict(
                            meta.get("stop_state"),
                            entry_price=trade.entry_price,
                            stop_loss=trade.stop_loss,
                            take_profit=trade.take_profit,
                        )
                        if stop_state is None:
                            continue
                        updated = risk.stop_manager.update_trailing(
                            stop_state, side, price, atr_val
                        )
                        meta["stop_state"] = stop_state_to_dict(updated)
                        meta["sl_order_id"] = new_sl_id
                        await repo.update_open_trade_stops(
                            trade.id,
                            stop_loss=float(best["new_sl"]),
                            trailing_stop=updated.trailing_stop,
                            metadata_json=meta,
                        )

                    logger.info(
                        "exchange_trailing_sl_updated",
                        symbol=symbol,
                        side=side,
                        account_id=account_id,
                        trade_id=best["trade"].id,
                        old_stop=best["old_sl"],
                        new_stop=best["new_sl"],
                        break_even=best["updated"].break_even_triggered,
                        order_id=new_sl_id,
                        trades_synced=len(side_trades),
                    )
        except Exception as e:
            logger.error(
                "exchange_trailing_stops_failed",
                symbol=symbol,
                account_id=account_id,
                error=str(e),
            )

    async def _persist_open_trade(
        self,
        *,
        account_id: int,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        stop_loss: float | None,
        take_profit: float | None,
        strategy: str,
        is_paper: bool,
        leverage: int = 1,
        exchange_order_id: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> None:
        meta = dict(metadata_json or {})
        if stop_loss and take_profit and "stop_state" not in meta:
            meta["stop_state"] = stop_state_to_dict(
                build_initial_stop_state(entry_price, stop_loss, take_profit)
            )
        try:
            async with get_async_session() as session:
                repo = TradeRepository(session)
                if not is_paper:
                    for existing in await repo.get_open_trades(
                        symbol=symbol, account_id=account_id
                    ):
                        if existing.is_paper:
                            continue
                        if existing.side.value.upper() == side.upper():
                            logger.warning(
                                "duplicate_open_trade_skipped",
                                symbol=symbol,
                                side=side,
                                account_id=account_id,
                                existing_trade_id=existing.id,
                            )
                            return
                await repo.create(
                    Trade(
                        symbol=symbol,
                        side=TradeSide.LONG if side == "LONG" else TradeSide.SHORT,
                        status=TradeStatus.OPEN,
                        strategy=strategy,
                        entry_price=entry_price,
                        quantity=quantity,
                        leverage=leverage,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        is_paper=is_paper,
                        account_id=account_id,
                        exchange_order_id=exchange_order_id,
                        metadata_json=meta or None,
                        opened_at=datetime.now(UTC),
                    )
                )
        except Exception as e:
            logger.error("persist_open_trade_failed", error=str(e))

    async def _persist_closed_trade(self, trade: dict[str, Any], account_id: int) -> None:
        try:
            async with get_async_session() as session:
                repo = TradeRepository(session)
                db_trade = Trade(
                    symbol=trade["symbol"],
                    side=TradeSide.LONG if trade["side"] == "LONG" else TradeSide.SHORT,
                    status=TradeStatus.CLOSED,
                    strategy=trade.get("strategy", ""),
                    entry_price=trade["entry_price"],
                    exit_price=trade["exit_price"],
                    quantity=trade["quantity"],
                    pnl=trade["pnl"],
                    pnl_pct=trade.get("pnl_pct"),
                    is_paper=trade.get("is_paper", True),
                    account_id=account_id,
                    closed_at=datetime.now(UTC),
                )
                await repo.create(db_trade)
                runtime = self.account_manager.get_runtime(account_id)
                daily_pnl = await repo.get_daily_pnl(account_id)
                runtime.risk_manager.update_daily_pnl(daily_pnl)
        except Exception as e:
            logger.error("persist_trade_failed", error=str(e))

        await self.telegram.notify_exit(
            trade["symbol"],
            trade["side"],
            trade["exit_price"],
            trade["pnl"],
            trade.get("reason", ""),
        )

    async def _report_loop(self) -> None:
        while self._running:
            try:
                now = datetime.now(UTC)
                report_hour = int(self.config.get("notifications.telegram.daily_report_hour", 0))
                if now.hour == report_hour and now.minute < 5:
                    await self._send_daily_report()
                await asyncio.sleep(300)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("report_loop_error", error=str(e))

    async def _send_daily_report(self) -> None:
        if self.config.is_paper:
            balance = self.paper_trader.balance
            win_rate = self.paper_trader.win_rate
            trades = len(self.paper_trader.closed_trades)
        else:
            balance = await self.exchange.get_balance()
            win_rate = 0.0
            trades = 0
        await self.telegram.send_daily_report(balance, win_rate, trades)

    def _save_state(self) -> None:
        if self.config.is_paper:
            for aid in self.account_manager.runtime_ids():
                self.account_manager.save_runtime(aid)
        aid = self.account_manager.active_account_id
        if aid and self.account_manager.has_runtime(aid):
            runtime = self.account_manager.get_runtime(aid)
            state = BotState(
                balance=runtime.paper_trader.balance if self.config.is_paper else self._balance,
                daily_pnl=runtime.risk_manager._daily_pnl,
                total_trades=len(runtime.paper_trader.closed_trades),
                symbols=self.config.symbols,
                enabled_strategies=self.strategy_engine.active_strategies,
            )
            self.state_manager.save(state)

    def get_paper_equity(self) -> tuple[float, float]:
        aid = self.account_manager.active_account_id
        if aid is None:
            return 0.0, 0.0
        return self.get_paper_equity_for(aid)

    def get_paper_equity_for(self, account_id: int) -> tuple[float, float]:
        """Return (equity, unrealized_pnl) for one paper account."""
        from utils.helpers import calculate_pnl

        trader = self.account_manager.get_runtime(account_id).paper_trader
        unrealized = 0.0
        for pos in trader.positions.values():
            price = self.market_data.get_latest_price(pos.symbol)
            unrealized += calculate_pnl(pos.side, pos.entry_price, price, pos.quantity)
        balance = trader.balance
        return balance + unrealized, unrealized

    async def close_paper_positions(
        self,
        position_id: str | None = None,
        symbol: str | None = None,
        account_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Close one or more paper positions manually."""
        aid = account_id or self.account_manager.active_account_id
        if aid is None:
            return []
        trader = self.account_manager.get_runtime(aid).paper_trader

        to_close: list[tuple[str, PaperPosition]] = []
        for pid, pos in list(trader.positions.items()):
            if position_id and pid != position_id:
                continue
            if symbol and pos.symbol != symbol:
                continue
            to_close.append((pid, pos))

        if not to_close:
            return []

        closed: list[dict[str, Any]] = []
        for pid, pos in to_close:
            price = self.market_data.get_latest_price(pos.symbol)
            if price <= 0:
                continue
            trade = await trader.close_position(pid, price, reason="manual")
            if trade:
                await self._persist_closed_trade(trade, aid)
                closed.append(trade)
        if closed:
            self.account_manager.save_runtime(aid)
        return closed

    async def close_exchange_positions(
        self,
        position_id: str | None = None,
        symbol: str | None = None,
        account_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Close one or more Binance futures positions (testnet/live)."""
        from utils.helpers import calculate_pnl

        aid = account_id or self.account_manager.active_account_id
        await self.exchange.connect()
        positions = await self.exchange.get_positions()

        def _matches(pos: Any) -> bool:
            pid = f"{pos.symbol}-{pos.side}"
            if position_id:
                return pid == position_id or pos.symbol == position_id
            if symbol:
                return pos.symbol == symbol
            return True

        to_close = [p for p in positions if _matches(p)]
        if not to_close:
            return []

        closed: list[dict[str, Any]] = []
        for pos in to_close:
            price = self.market_data.get_latest_price(pos.symbol)
            if price <= 0:
                price = pos.entry_price

            try:
                await self.exchange.cancel_all_open_orders(pos.symbol)
            except Exception as e:
                logger.warning("cancel_open_orders_failed", symbol=pos.symbol, error=str(e))

            await self.exchange.close_position_market(
                pos.symbol,
                pos.side,
                pos.quantity,
                hedge_mode=self.config.hedge_mode,
            )

            pnl = calculate_pnl(pos.side, pos.entry_price, price, pos.quantity)
            trade_side = TradeSide.LONG if pos.side == "LONG" else TradeSide.SHORT
            try:
                async with get_async_session() as session:
                    repo = TradeRepository(session)
                    db_trade = await repo.close_open_trade(
                        pos.symbol, trade_side, price, pnl, account_id=aid
                    )
                    if aid and self.account_manager.has_runtime(aid):
                        daily_pnl = await repo.get_daily_pnl(aid)
                        self.account_manager.get_runtime(aid).risk_manager.update_daily_pnl(
                            daily_pnl
                        )
            except Exception as e:
                logger.error("close_exchange_db_failed", error=str(e))

            closed.append(
                {
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "exit_price": price,
                    "pnl": pnl,
                    "reason": "manual",
                    "strategy": "manual",
                }
            )
            await self.telegram.notify_exit(pos.symbol, pos.side, price, pnl, "manual")

        if closed:
            await self.sync_exchange_state()
        return closed

    async def _fetch_exchange_closed_trades(self, limit: int = 100) -> list[dict[str, Any]]:
        """Pull realized-PnL fills from Binance for history charts."""
        await self.exchange.connect()
        trades: list[dict[str, Any]] = []
        idx = 0
        for symbol in self.config.symbols:
            try:
                fills = await self.exchange.get_user_trades(symbol, limit=limit)
            except Exception as e:
                logger.warning("exchange_user_trades_failed", symbol=symbol, error=str(e))
                continue
            fills_sorted = sorted(fills, key=lambda fill: int(fill.get("time", 0)))
            open_prices: dict[str, list[float]] = {"LONG": [], "SHORT": []}
            for fill in fills_sorted:
                pnl = safe_float(fill.get("realizedPnl"))
                order_side = str(fill.get("side", "BUY")).upper()
                pos_side = str(fill.get("positionSide", "")).upper()
                if pos_side not in ("LONG", "SHORT"):
                    pos_side = "LONG" if order_side == "BUY" else "SHORT"
                price = safe_float(fill.get("price"))
                qty = safe_float(fill.get("qty"))
                if abs(pnl) < 1e-12:
                    open_prices[pos_side].append(price)
                    continue
                entry_price = open_prices[pos_side].pop() if open_prices[pos_side] else price
                ts_ms = int(fill.get("time", 0))
                closed_at = datetime.fromtimestamp(ts_ms / 1000, tz=UTC) if ts_ms else datetime.now(UTC)
                trades.append(
                    {
                        "id": -(idx + 1),
                        "symbol": symbol,
                        "side": pos_side,
                        "status": "CLOSED",
                        "strategy": "binance_fill",
                        "entry_price": entry_price,
                        "exit_price": price,
                        "quantity": qty,
                        "pnl": pnl,
                        "pnl_pct": None,
                        "opened_at": closed_at,
                        "closed_at": closed_at,
                    }
                )
                idx += 1
        trades.sort(key=lambda t: _as_utc_aware(t["closed_at"]), reverse=True)
        return trades[:limit]

    async def _exchange_daily_pnl(self) -> float:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        total = 0.0
        await self.exchange.connect()
        for symbol in self.config.symbols:
            try:
                items = await self.exchange.get_income_history("REALIZED_PNL", symbol=symbol, limit=200)
            except Exception:
                continue
            for item in items:
                ts_ms = int(item.get("time", 0))
                if not ts_ms:
                    continue
                ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
                if ts >= today:
                    total += safe_float(item.get("income"))
        return total

    async def get_merged_closed_trades(self, limit: int = 100) -> list[dict[str, Any]]:
        """Closed trades from DB (paper) plus Binance history (testnet/live)."""
        aid = self.account_manager.active_account_id
        db_account_id = aid
        db_rows: list[dict[str, Any]] = []
        try:
            async with get_async_session() as session:
                repo = TradeRepository(session)
                for t in await repo.get_closed_trades(limit=limit, account_id=db_account_id):
                    db_rows.append(
                        {
                            "id": t.id,
                            "symbol": t.symbol,
                            "side": t.side.value,
                            "status": t.status.value,
                            "strategy": t.strategy,
                            "entry_price": t.entry_price,
                            "exit_price": t.exit_price,
                            "quantity": t.quantity,
                            "pnl": t.pnl,
                            "pnl_pct": t.pnl_pct,
                            "opened_at": _as_utc_aware(t.opened_at),
                            "closed_at": _as_utc_aware(t.closed_at),
                        }
                    )
        except Exception as e:
            logger.error("db_closed_trades_failed", error=str(e))

        if self.config.is_paper:
            return db_rows

        # Prefer bot-recorded trades (correct strategy names) on testnet/live.
        if db_rows:
            db_rows.sort(key=lambda t: _as_utc_aware(t["closed_at"]), reverse=True)
            return db_rows[:limit]

        exchange_rows = await self._fetch_exchange_closed_trades(limit=limit)
        return exchange_rows

    def get_strategy_stats_from_trades(
        self, trades: list[dict[str, Any]]
    ) -> dict[str, dict[str, float]]:
        stats: dict[str, dict[str, float]] = {}
        for t in trades:
            name = t.get("strategy") or "unknown"
            pnl = float(t.get("pnl") or 0)
            bucket = stats.setdefault(
                name,
                {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "total_pnl": 0.0},
            )
            bucket["total_trades"] += 1
            bucket["total_pnl"] += pnl
            if pnl > 0:
                bucket["wins"] += 1
            elif pnl < 0:
                bucket["losses"] += 1
        for bucket in stats.values():
            total = int(bucket["total_trades"])
            wins = int(bucket["wins"])
            bucket["win_rate"] = (wins / total * 100) if total > 0 else 0.0
        return stats

    def get_strategy_settings(self) -> dict[str, Any]:
        aid = self.account_manager.active_account_id
        account = self.account_manager.active_account
        if aid is None or not self.account_manager.has_runtime(aid):
            return {
                "primary_timeframe": self.config.primary_timeframe,
                "active_strategies": [],
                "strategies": dict(self.config.strategies),
                "account_id": None,
                "account_name": None,
            }
        runtime = self.account_manager.get_runtime(aid)
        return {
            "primary_timeframe": self.config.primary_timeframe,
            "active_strategies": runtime.strategy_engine.active_strategies,
            "strategies": runtime.strategies_config,
            "account_id": aid,
            "account_name": account.name if account else None,
        }

    def apply_strategy_settings(self, updates: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Merge dashboard updates for the active account, persist, and reload its engine."""
        aid = self.account_manager.active_account_id
        if aid is None:
            raise RuntimeError("No active account")
        if not self.account_manager.has_runtime(aid):
            account = self.account_manager.active_account
            if account:
                self.account_manager.ensure_runtime(account)
            else:
                raise RuntimeError("No active account")
        runtime = self.account_manager.get_runtime(aid)
        merged = dict(runtime.strategies_config)
        yaml_names = set(self.config.strategies.keys())
        for name, patch in updates.items():
            if name not in yaml_names:
                continue
            current = merged.get(name, dict(self.config.strategies.get(name, {})))
            merged[name] = {**current, **patch}
        runtime.strategies_config = merged
        save_account_strategy(aid, {name: merged[name] for name in yaml_names if name in merged})
        runtime.strategy_engine.reload(merged)
        logger.info("strategy_settings_applied", account_id=aid, updates=list(updates.keys()))
        return self.get_strategy_settings()

    async def get_status(self) -> dict[str, Any]:
        """Return current bot status for API."""
        if self._running_accounts:
            alive = self._running and any(not task.done() for task in self._tasks)
            if not alive:
                await self._ensure_engine_running()
        if not self.config.is_paper:
            try:
                await self.sync_exchange_state()
            except Exception as e:
                logger.error("exchange_balance_sync_failed", error=str(e))

        balance = self.paper_trader.balance if self.config.is_paper else self._balance
        equity = balance
        unrealized = 0.0
        if self.config.is_paper:
            equity, unrealized = self.get_paper_equity()
        else:
            equity = self._equity if self._equity > 0 else balance
            unrealized = self._unrealized_pnl

        active_open = len(self.paper_trader.positions) if self.config.is_paper else self._exchange_open_positions
        total_open = 0
        if self.config.is_paper:
            for aid in self._running_accounts:
                if self.account_manager.has_runtime(aid):
                    total_open += len(self.account_manager.get_runtime(aid).paper_trader.positions)
        else:
            total_open = self._exchange_open_positions

        return {
            "running": len(self._running_accounts) > 0,
            "engine_running": self._running,
            "mode": self.settings.trading_mode.value,
            "balance": balance,
            "equity": equity,
            "total_assets": self._total_assets if not self.config.is_paper else equity,
            "unrealized_pnl": unrealized,
            "symbols": self.config.symbols,
            "strategies": self.strategy_engine.active_strategies,
            "open_positions": active_open,
            "total_open_positions": total_open,
            "running_accounts": self._running_accounts_payload(),
            "risk": {
                **self.risk_manager.get_settings(),
                "open_positions": active_open,
            },
            "account": self.account_manager.to_dict(
                running_account_ids=self._running_accounts,
                live_balance=None if self.config.is_paper else self._total_assets,
            ),
            "recent_signals": [
                {
                    "symbol": s.symbol,
                    "action": s.action.value,
                    "strategy": s.strategy,
                    "price": s.price,
                    "confidence": s.confidence,
                }
                for s in self._signals[-10:]
            ],
            "strategy_scan": {
                sym: self.strategy_engine.diagnose(sym, self.market_data)
                for sym in self.config.symbols
            },
        }
