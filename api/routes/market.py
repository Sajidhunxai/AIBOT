"""Market data API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from datetime import UTC, datetime

from api.schemas.models import (
    CandleResponse,
    MarketSnapshotResponse,
    PriceLine,
    TradeMarker,
    TradeMarkersResponse,
)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/candles", response_model=list[CandleResponse])
async def get_candles(
    request: Request,
    symbol: str = Query(default="BTCUSDT"),
    timeframe: str = Query(default="15m"),
    limit: int = Query(default=200, ge=10, le=500),
) -> list[CandleResponse]:
    """Return OHLCV candles for charting."""
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    candles: list[CandleResponse] = []

    if bot._running:
        df = bot.market_data.get_candles(symbol, timeframe)
        if not df.empty:
            subset = df.tail(limit)
            for _, row in subset.iterrows():
                candles.append(_row_to_candle(row))

    if not candles:
        await bot.exchange.connect()
        raw = await bot.exchange.get_klines(symbol, timeframe, limit=limit)
        for row in raw:
            candles.append(
                CandleResponse(
                    time=int(row["open_time"].timestamp()),
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                )
            )

    return candles


@router.get("/snapshot", response_model=MarketSnapshotResponse)
async def get_market_snapshot(
    request: Request,
    symbol: str = Query(default="BTCUSDT"),
) -> MarketSnapshotResponse:
    """Return latest price and 24h change."""
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    price = 0.0
    if bot._running:
        price = bot.market_data.get_latest_price(symbol)

    if price <= 0:
        await bot.exchange.connect()
        ticker = await bot.exchange.get_ticker(symbol)
        price = ticker.price

    return MarketSnapshotResponse(
        symbol=symbol,
        price=price,
        funding_rate=bot.market_data.get_funding_rate(symbol) if bot._running else 0.0,
        open_interest=bot.market_data.get_open_interest(symbol) if bot._running else 0.0,
    )


async def _candle_open_times(
    bot: object,
    symbol: str,
    timeframe: str,
    limit: int = 200,
) -> list[int]:
    """Return candle open times (unix seconds) for aligning trade markers."""
    times: list[int] = []

    if getattr(bot, "_running", False):
        df = bot.market_data.get_candles(symbol, timeframe)  # type: ignore[attr-defined]
        if not df.empty:
            subset = df.tail(limit)
            for _, row in subset.iterrows():
                times.append(_row_to_candle(row).time)

    if not times:
        await bot.exchange.connect()  # type: ignore[attr-defined]
        raw = await bot.exchange.get_klines(symbol, timeframe, limit=limit)  # type: ignore[attr-defined]
        for row in raw:
            times.append(int(row["open_time"].timestamp()))

    return sorted(times)


def _align_to_candle(ts: int, candle_times: list[int]) -> int:
    """Snap a unix timestamp to the nearest candle open time on the chart."""
    if not candle_times:
        return ts
    if ts >= candle_times[-1]:
        return candle_times[-1]
    if ts <= candle_times[0]:
        return candle_times[0]
    nearest = candle_times[0]
    min_diff = abs(ts - nearest)
    for t in candle_times:
        diff = abs(ts - t)
        if diff < min_diff:
            min_diff = diff
            nearest = t
    return nearest


@router.get("/trade-markers", response_model=TradeMarkersResponse)
async def get_trade_markers(
    request: Request,
    symbol: str = Query(default="BTCUSDT"),
    timeframe: str = Query(default="15m"),
) -> TradeMarkersResponse:
    """Return entry/exit markers and SL/TP lines for chart overlay."""
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    account_id = bot.account_manager.active_account_id
    trader = bot.paper_trader
    candle_times = await _candle_open_times(bot, symbol, timeframe)
    markers: list[TradeMarker] = []
    price_lines: list[PriceLine] = []
    seen: set[str] = set()

    if bot.config.is_paper:
        for pos in trader.positions.values():
            if pos.symbol != symbol:
                continue
            ts = _align_to_candle(int(pos.opened_at.timestamp()), candle_times)
            markers.append(
                TradeMarker(
                    time=ts,
                    type="entry",
                    side=pos.side,
                    price=pos.entry_price,
                    strategy=pos.strategy,
                )
            )
            if pos.stop_loss:
                price_lines.append(
                    PriceLine(price=pos.stop_loss, color="#ef4444", title="Stop Loss")
                )
            if pos.take_profit:
                price_lines.append(
                    PriceLine(price=pos.take_profit, color="#22c55e", title="Take Profit")
                )
            price_lines.append(
                PriceLine(price=pos.entry_price, color="#3b82f6", title="Entry", style="solid")
            )

        for trade in trader.closed_trades:
            if trade.get("symbol") != symbol:
                continue
            key = f"{trade.get('opened_at')}-{trade.get('closed_at')}"
            if key in seen:
                continue
            seen.add(key)

            opened = trade.get("opened_at")
            closed = trade.get("closed_at")
            if opened:
                markers.append(
                    TradeMarker(
                        time=_align_to_candle(_parse_ts(opened), candle_times),
                        type="entry",
                        side=str(trade.get("side", "LONG")),
                        price=float(trade.get("entry_price", 0)),
                        strategy=str(trade.get("strategy", "")),
                    )
                )
            if closed:
                markers.append(
                    TradeMarker(
                        time=_align_to_candle(_parse_ts(closed), candle_times),
                        type="exit",
                        side=str(trade.get("side", "LONG")),
                        price=float(trade.get("exit_price", 0)),
                        strategy=str(trade.get("strategy", "")),
                        pnl=float(trade.get("pnl", 0)),
                    )
                )
    else:
        from api.routes.positions import _load_exchange_trade_meta

        trade_meta = await _load_exchange_trade_meta(bot)
        await bot.exchange.connect()
        for pos in await bot.exchange.get_positions():
            if pos.symbol != symbol:
                continue
            ts = (
                _align_to_candle(int(pos.opened_at.timestamp()), candle_times)
                if pos.opened_at
                else candle_times[-1] if candle_times else int(datetime.now(UTC).timestamp())
            )
            key = f"ex-{pos.symbol}-{pos.side}"
            if key in seen:
                continue
            seen.add(key)
            meta = trade_meta.get((pos.symbol, pos.side), {})
            strategy = str(meta.get("strategy", "exchange"))
            markers.append(
                TradeMarker(
                    time=ts,
                    type="entry",
                    side=pos.side,
                    price=pos.entry_price,
                    strategy=strategy,
                )
            )
            stop_loss = meta.get("stop_loss")
            take_profit = meta.get("take_profit")
            if stop_loss:
                price_lines.append(
                    PriceLine(price=float(stop_loss), color="#ef4444", title="Stop Loss")
                )
            if take_profit:
                price_lines.append(
                    PriceLine(price=float(take_profit), color="#22c55e", title="Take Profit")
                )
            price_lines.append(
                PriceLine(price=pos.entry_price, color="#3b82f6", title="Entry", style="solid")
            )

    try:
        merged_closed = await bot.get_merged_closed_trades(limit=50)
        for row in merged_closed:
            if row["symbol"] != symbol:
                continue
            key = f"hist-{row['id']}-{row.get('closed_at')}"
            if key in seen:
                continue
            seen.add(key)
            opened = row.get("opened_at")
            if opened:
                ts = int(opened.timestamp()) if hasattr(opened, "timestamp") else _parse_ts(opened)
                markers.append(
                    TradeMarker(
                        time=_align_to_candle(ts, candle_times),
                        type="entry",
                        side=str(row.get("side", "LONG")),
                        price=float(row.get("entry_price", 0)),
                        strategy=str(row.get("strategy", "")),
                    )
                )
            closed = row.get("closed_at")
            exit_price = row.get("exit_price")
            if closed and exit_price:
                ts = int(closed.timestamp()) if hasattr(closed, "timestamp") else _parse_ts(closed)
                markers.append(
                    TradeMarker(
                        time=_align_to_candle(ts, candle_times),
                        type="exit",
                        side=str(row.get("side", "LONG")),
                        price=float(exit_price),
                        strategy=str(row.get("strategy", "")),
                        pnl=float(row["pnl"]) if row.get("pnl") is not None else None,
                    )
                )

    except Exception:
        pass

    markers.sort(key=lambda m: m.time)
    if len(markers) > 40:
        markers = markers[-40:]

    return TradeMarkersResponse(markers=markers, price_lines=price_lines)


def _parse_ts(value: str | datetime) -> int:
    if isinstance(value, datetime):
        return int(value.timestamp())
    return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())


def _row_to_candle(row: object) -> CandleResponse:
    import pandas as pd

    r = row  # pandas Series
    open_time = r["open_time"]  # type: ignore[index]
    if hasattr(open_time, "timestamp"):
        ts = int(open_time.timestamp())
    else:
        ts = int(pd.Timestamp(open_time).timestamp())

    return CandleResponse(
        time=ts,
        open=float(r["open"]),  # type: ignore[index]
        high=float(r["high"]),  # type: ignore[index]
        low=float(r["low"]),  # type: ignore[index]
        close=float(r["close"]),  # type: ignore[index]
        volume=float(r["volume"]),  # type: ignore[index]
    )
