"""Position API routes."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from api.schemas.models import PositionResponse

router = APIRouter(prefix="/positions", tags=["positions"])


async def _load_exchange_trade_meta(bot: object) -> dict[tuple[str, str], dict[str, object]]:
    """Map exchange positions to SL/TP stored in DB (shared testnet/live wallet)."""
    meta: dict[tuple[str, str], dict[str, object]] = {}
    try:
        from database.repositories.trades import TradeRepository
        from database.session import get_async_session

        async with get_async_session() as session:
            repo = TradeRepository(session)
            for trade in await repo.get_open_trades():
                key = (trade.symbol, trade.side.value)
                aid = trade.account_id or 0
                meta[key] = {
                    "stop_loss": trade.stop_loss,
                    "take_profit": trade.take_profit,
                    "strategy": trade.strategy or "manual",
                    "account_id": aid,
                    "account_name": bot._account_names.get(aid, f"Account {aid}"),  # type: ignore[attr-defined]
                }
    except Exception:
        pass
    return meta


def _collect_paper_positions(bot: object, account_ids: set[int]) -> list[PositionResponse]:
    from utils.helpers import calculate_pnl

    positions: list[PositionResponse] = []
    for aid in sorted(account_ids):
        if not bot.account_manager.has_runtime(aid):  # type: ignore[attr-defined]
            continue
        trader = bot.account_manager.get_runtime(aid).paper_trader  # type: ignore[attr-defined]
        name = bot._account_names.get(aid, f"Account {aid}")  # type: ignore[attr-defined]
        for pos in trader.positions.values():
            price = bot.market_data.get_latest_price(pos.symbol)  # type: ignore[attr-defined]
            unrealized = calculate_pnl(pos.side, pos.entry_price, price, pos.quantity)
            positions.append(
                PositionResponse(
                    id=pos.id,
                    symbol=pos.symbol,
                    side=pos.side,
                    quantity=pos.quantity,
                    entry_price=pos.entry_price,
                    unrealized_pnl=unrealized,
                    leverage=pos.leverage,
                    stop_loss=pos.stop_loss,
                    take_profit=pos.take_profit,
                    strategy=pos.strategy,
                    account_id=aid,
                    account_name=name,
                )
            )
    return positions


async def _collect_exchange_positions(bot: object) -> list[PositionResponse]:
    await bot.exchange.connect()  # type: ignore[attr-defined]
    exchange_positions = await bot.exchange.get_positions()  # type: ignore[attr-defined]
    trade_meta = await _load_exchange_trade_meta(bot)

    positions: list[PositionResponse] = []
    for pos in exchange_positions:
        meta = trade_meta.get((pos.symbol, pos.side), {})
        stop_loss = meta.get("stop_loss")
        take_profit = meta.get("take_profit")
        strategy = meta.get("strategy", "exchange")
        aid = meta.get("account_id") or bot.account_manager.active_account_id  # type: ignore[attr-defined]
        name = meta.get("account_name") or (
            bot.account_manager.active_account.name  # type: ignore[attr-defined]
            if bot.account_manager.active_account  # type: ignore[attr-defined]
            else "Binance"
        )
        positions.append(
            PositionResponse(
                id=f"{pos.symbol}-{pos.side}",
                symbol=pos.symbol,
                side=pos.side,
                quantity=pos.quantity,
                entry_price=pos.entry_price,
                unrealized_pnl=pos.unrealized_pnl,
                leverage=pos.leverage,
                stop_loss=stop_loss,  # type: ignore[arg-type]
                take_profit=take_profit,  # type: ignore[arg-type]
                strategy=str(strategy),
                account_id=int(aid) if aid else None,
                account_name=str(name),
            )
        )
    return positions


@router.get("", response_model=list[PositionResponse])
async def get_positions(
    request: Request,
    all_accounts: bool = Query(False, description="Include open positions from every running account"),
    account_id: int | None = Query(None, description="View positions for a specific account"),
) -> list[PositionResponse]:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        return []

    if not bot.config.is_paper:
        return await _collect_exchange_positions(bot)

    active_id = bot.account_manager.active_account_id

    if account_id is not None:
        target_ids = {account_id}
    elif all_accounts:
        target_ids = set(bot.running_accounts)
        if active_id is not None:
            target_ids.add(active_id)
    elif active_id is not None:
        target_ids = {active_id}
    else:
        target_ids = set(bot.running_accounts)

    for aid in list(target_ids):
        if bot.account_manager.has_runtime(aid):
            continue
        account = await bot.account_manager.get_account(aid)
        if account:
            bot.account_manager.ensure_runtime(account)

    return _collect_paper_positions(bot, target_ids)
