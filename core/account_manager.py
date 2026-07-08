"""Per-account demo state, runtimes, and switching."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.account_runtime import AccountRuntime
from core.engine import StrategyEngine
from core.paper_trader import PaperTrader
from database.models import AccountType, TradingAccount
from database.repositories.accounts import AccountRepository
from database.repositories.signals import SignalRepository
from database.repositories.trades import TradeRepository
from database.session import get_async_session
from risk.manager import RiskManager
from utils.logger import get_logger
from utils.risk_settings import load_account_risk
from utils.strategy_settings import get_merged_strategies_for_account

logger = get_logger(__name__)

ACCOUNTS_DIR = Path("data/accounts")
DEFAULT_DEMO_NAME = "Demo Practice"


class AccountManager:
    """Manage demo/live profiles with isolated in-memory runtimes."""

    def __init__(
        self,
        risk_config: dict[str, Any],
        strategies_yaml: dict[str, Any],
        primary_timeframe: str = "15m",
        ai_filter: object | None = None,
        default_balance: float = 10000.0,
        slippage_pct: float = 0.02,
    ) -> None:
        self.risk_config = risk_config
        self.strategies_yaml = strategies_yaml
        self.primary_timeframe = primary_timeframe
        self.ai_filter = ai_filter
        self.default_balance = default_balance
        self.slippage_pct = slippage_pct
        self._runtimes: dict[int, AccountRuntime] = {}
        self._active_account: TradingAccount | None = None
        ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def active_account_id(self) -> int | None:
        return self._active_account.id if self._active_account else None

    @property
    def active_account(self) -> TradingAccount | None:
        return self._active_account

    @property
    def paper_trader(self) -> PaperTrader:
        if self._active_account is None:
            raise RuntimeError("No active account")
        return self.ensure_runtime(self._active_account).paper_trader

    @property
    def risk_manager(self) -> RiskManager:
        if self._active_account is None:
            raise RuntimeError("No active account")
        return self.ensure_runtime(self._active_account).risk_manager

    @property
    def strategy_engine(self) -> StrategyEngine:
        if self._active_account is None:
            raise RuntimeError("No active account")
        return self.ensure_runtime(self._active_account).strategy_engine

    def runtime_ids(self) -> list[int]:
        return list(self._runtimes.keys())

    def set_ai_filter(self, ai_filter: object | None) -> None:
        self.ai_filter = ai_filter
        for runtime in self._runtimes.values():
            runtime.strategy_engine.ai_filter = ai_filter  # type: ignore[assignment]

    def get_runtime(self, account_id: int) -> AccountRuntime:
        if account_id not in self._runtimes:
            raise KeyError(f"Runtime not loaded for account {account_id}")
        return self._runtimes[account_id]

    def has_runtime(self, account_id: int) -> bool:
        return account_id in self._runtimes

    def _state_path(self, account_id: int) -> Path:
        return ACCOUNTS_DIR / f"{account_id}.json"

    def read_paper_state(self, account_id: int) -> dict[str, Any]:
        path = self._state_path(account_id)
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def write_paper_state_file(self, account_id: int, data: dict[str, Any]) -> None:
        path = self._state_path(account_id)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_stored_balance(self, account_id: int) -> float | None:
        data = self.read_paper_state(account_id)
        if not data:
            return None
        return float(data.get("balance", 0))

    def _reconcile_demo_balance_for_trader(
        self, account: TradingAccount, trader: PaperTrader
    ) -> None:
        if account.account_type != AccountType.DEMO:
            return
        data = self.read_paper_state(account.id)
        has_activity = bool(data.get("positions")) or bool(data.get("closed_trades"))
        if has_activity or account.paper_balance <= 0:
            return
        if trader.balance != account.paper_balance:
            trader.balance = account.paper_balance
            trader.initial_balance = account.paper_balance
            self.write_paper_state_file(account.id, trader.export_state())

    def _load_state_into_trader(self, account: TradingAccount, trader: PaperTrader) -> None:
        data = self.read_paper_state(account.id)
        if data:
            trader.import_state(data)
            self._reconcile_demo_balance_for_trader(account, trader)
            return
        start_balance = (
            account.paper_balance
            if account.account_type == AccountType.DEMO
            else self.default_balance
        )
        trader.reset(start_balance)
        self.write_paper_state_file(account.id, trader.export_state())

    def _build_risk_for_trader(self, account_id: int, trader: PaperTrader) -> RiskManager:
        risk = RiskManager(self.risk_config)
        overrides = load_account_risk(account_id, migrate_global=(account_id == 1))
        if overrides:
            risk.apply_settings(overrides)
        risk.set_balance(trader.balance)
        risk._peak_equity = trader.balance
        risk._initial_balance = trader.balance
        return risk

    def _build_strategy_for_account(self, account_id: int) -> tuple[StrategyEngine, dict[str, Any]]:
        config = get_merged_strategies_for_account(self.strategies_yaml, account_id)
        engine = StrategyEngine(
            config,
            ai_filter=self.ai_filter,
            primary_timeframe=self.primary_timeframe,
        )
        return engine, config

    def reload_strategy_for_account(self, account_id: int) -> None:
        if account_id not in self._runtimes:
            return
        engine, config = self._build_strategy_for_account(account_id)
        runtime = self._runtimes[account_id]
        runtime.strategy_engine = engine
        runtime.strategies_config = config

    def ensure_runtime(self, account: TradingAccount) -> AccountRuntime:
        if account.id in self._runtimes:
            return self._runtimes[account.id]

        trader = PaperTrader(
            initial_balance=account.paper_balance or self.default_balance,
            slippage_pct=self.slippage_pct,
        )
        self._load_state_into_trader(account, trader)
        risk = self._build_risk_for_trader(account.id, trader)
        strategy_engine, strategies_config = self._build_strategy_for_account(account.id)
        runtime = AccountRuntime(
            account.id,
            trader,
            risk,
            strategy_engine,
            strategies_config,
        )
        self._runtimes[account.id] = runtime
        logger.info("account_runtime_loaded", account_id=account.id, balance=trader.balance)
        return runtime

    def save_runtime(self, account_id: int | None = None) -> None:
        aid = account_id or self.active_account_id
        if aid is None or aid not in self._runtimes:
            return
        trader = self._runtimes[aid].paper_trader
        self.write_paper_state_file(aid, trader.export_state())
        if self._active_account and self._active_account.id == aid:
            self._active_account.paper_balance = trader.balance

    def save_paper_state(self, account_id: int | None = None) -> None:
        self.save_runtime(account_id)

    def update_stored_balance(self, account_id: int, balance: float) -> None:
        data = self.read_paper_state(account_id)
        if not data:
            data = {
                "balance": balance,
                "initial_balance": balance,
                "positions": {},
                "closed_trades": [],
                "order_counter": 0,
            }
        else:
            data["balance"] = balance
            data["initial_balance"] = balance
        self.write_paper_state_file(account_id, data)
        if account_id in self._runtimes:
            self._runtimes[account_id].paper_trader.balance = balance
            self._runtimes[account_id].paper_trader.initial_balance = balance

    async def _sync_db_balance(self, account_id: int, balance: float) -> None:
        async with get_async_session() as session:
            account = await AccountRepository(session).update_balance(account_id, balance)
            if account and self._active_account and account.id == self._active_account.id:
                self._active_account.paper_balance = balance

    async def initialize(self) -> TradingAccount:
        async with get_async_session() as session:
            repo = AccountRepository(session)
            active = await repo.get_active()
            accounts = await repo.list_all()

            if not accounts:
                active = await repo.create(
                    name=DEFAULT_DEMO_NAME,
                    account_type=AccountType.DEMO,
                    paper_balance=self.default_balance,
                    activate=True,
                )
            elif active is None:
                active = accounts[0]
                await repo.set_active(active.id)

            self._active_account = active
            self.ensure_runtime(active)
            await self._sync_db_balance(active.id, self._runtimes[active.id].paper_trader.balance)
            logger.info(
                "account_loaded",
                account_id=active.id,
                name=active.name,
                type=active.account_type.value,
            )
            return active

    async def list_accounts(self) -> list[TradingAccount]:
        async with get_async_session() as session:
            return await AccountRepository(session).list_all()

    async def get_account(self, account_id: int) -> TradingAccount | None:
        async with get_async_session() as session:
            return await AccountRepository(session).get_by_id(account_id)

    async def create_account(
        self,
        name: str,
        account_type: str,
        paper_balance: float | None = None,
        notes: str | None = None,
    ) -> TradingAccount:
        balance = paper_balance if paper_balance is not None else self.default_balance
        atype = AccountType.LIVE if account_type.lower() == "live" else AccountType.DEMO
        async with get_async_session() as session:
            repo = AccountRepository(session)
            if await repo.get_by_name(name):
                raise ValueError(f"Account '{name}' already exists")
            account = await repo.create(
                name=name,
                account_type=atype,
                paper_balance=balance if atype == AccountType.DEMO else 0.0,
                notes=notes,
            )
        if atype == AccountType.DEMO:
            self.ensure_runtime(account)
        return account

    async def activate_account(self, account_id: int) -> TradingAccount:
        if self._active_account:
            self.save_runtime(self._active_account.id)
            old_rt = self._runtimes.get(self._active_account.id)
            if old_rt:
                await self._sync_db_balance(
                    self._active_account.id, old_rt.paper_trader.balance
                )

        async with get_async_session() as session:
            repo = AccountRepository(session)
            account = await repo.set_active(account_id)
            if account is None:
                raise ValueError("Account not found")

        self._active_account = account
        self.ensure_runtime(account)
        await self._sync_db_balance(account.id, self._runtimes[account.id].paper_trader.balance)
        logger.info(
            "account_activated",
            account_id=account.id,
            name=account.name,
            balance=self._runtimes[account.id].paper_trader.balance,
        )
        return account

    async def set_demo_balance(self, balance: float, account_id: int | None = None) -> TradingAccount:
        if balance <= 0:
            raise ValueError("Balance must be positive")
        aid = account_id or self.active_account_id
        if aid is None:
            raise ValueError("No active account")

        async with get_async_session() as session:
            repo = AccountRepository(session)
            account = await repo.update_balance(aid, balance)
            if account is None:
                raise ValueError("Account not found")

        if account.account_type != AccountType.DEMO:
            raise ValueError("Balance can only be set on demo accounts")

        self.update_stored_balance(aid, balance)
        if self._active_account and self._active_account.id == aid:
            self._active_account.paper_balance = balance

        return account

    async def reset_demo_account(
        self,
        account_id: int | None = None,
        balance: float | None = None,
        clear_history: bool = True,
    ) -> dict[str, Any]:
        aid = account_id or self.active_account_id
        if aid is None:
            raise ValueError("No active account")

        async with get_async_session() as session:
            repo = AccountRepository(session)
            account = await repo.get_by_id(aid)
            if account is None:
                raise ValueError("Account not found")
            if account.account_type != AccountType.DEMO:
                raise ValueError("Only demo accounts can be reset")

            reset_balance = balance if balance is not None else account.paper_balance
            account.paper_balance = reset_balance

            deleted_trades = 0
            deleted_signals = 0
            if clear_history:
                trade_repo = TradeRepository(session)
                signal_repo = SignalRepository(session)
                deleted_trades = await trade_repo.delete_demo_history(aid)
                deleted_signals = await signal_repo.delete_demo_history(aid)

        if aid in self._runtimes:
            self._runtimes[aid].paper_trader.reset(reset_balance)
            self.save_runtime(aid)
        else:
            path = self._state_path(aid)
            if path.exists():
                path.unlink()

        return {
            "account_id": aid,
            "balance": reset_balance,
            "deleted_trades": deleted_trades,
            "deleted_signals": deleted_signals,
        }

    def trader_balance(self, account_id: int) -> float:
        if account_id in self._runtimes:
            return self._runtimes[account_id].paper_trader.balance
        stored = self.get_stored_balance(account_id)
        return stored if stored is not None else 0.0

    def to_dict(
        self,
        account: TradingAccount | None = None,
        running_account_ids: set[int] | None = None,
        live_balance: float | None = None,
    ) -> dict[str, Any]:
        acc = account or self._active_account
        if acc is None:
            return {}
        if live_balance is not None:
            current_balance = live_balance
        else:
            current_balance = self.trader_balance(acc.id)
        return {
            "id": acc.id,
            "name": acc.name,
            "account_type": acc.account_type.value,
            "paper_balance": acc.paper_balance,
            "current_balance": current_balance,
            "is_active": acc.is_active,
            "is_trading": acc.id in (running_account_ids or set()),
            "notes": acc.notes,
        }
