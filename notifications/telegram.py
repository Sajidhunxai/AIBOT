"""Telegram notification service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)


class TelegramNotifier:
    """Send trading notifications via Telegram."""

    def __init__(
        self,
        token: str = "",
        chat_id: str = "",
        enabled: bool = False,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.token = token
        self.chat_id = chat_id
        self.enabled = enabled and bool(token) and bool(chat_id)
        self.config = config or {}
        self._bot: Any = None

    async def _get_bot(self) -> Any:
        if self._bot is None and self.enabled:
            from telegram import Bot

            self._bot = Bot(token=self.token)
        return self._bot

    async def send_message(self, text: str) -> None:
        if not self.enabled:
            return
        try:
            bot = await self._get_bot()
            if bot:
                await bot.send_message(chat_id=self.chat_id, text=text, parse_mode="HTML")
        except Exception as e:
            logger.error("telegram_send_failed", error=str(e))

    async def notify_entry(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        strategy: str,
    ) -> None:
        if not self.config.get("notify_on_entry", True):
            return
        emoji = "🟢" if side == "LONG" else "🔴"
        text = (
            f"{emoji} <b>ENTRY</b>\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"Price: {price:.4f}\n"
            f"Qty: {quantity:.6f}\n"
            f"Strategy: {strategy}"
        )
        await self.send_message(text)

    async def notify_exit(
        self,
        symbol: str,
        side: str,
        price: float,
        pnl: float,
        reason: str,
    ) -> None:
        if not self.config.get("notify_on_exit", True):
            return
        emoji = "✅" if pnl >= 0 else "❌"
        text = (
            f"{emoji} <b>EXIT</b>\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"Price: {price:.4f}\n"
            f"PnL: ${pnl:.2f}\n"
            f"Reason: {reason}"
        )
        await self.send_message(text)

    async def send_error(self, error: str) -> None:
        if not self.config.get("notify_on_error", True):
            return
        text = f"⚠️ <b>ERROR</b>\n{error}"
        await self.send_message(text)

    async def send_daily_report(
        self,
        balance: float,
        win_rate: float,
        total_trades: int,
    ) -> None:
        text = (
            f"📊 <b>Daily Report</b>\n"
            f"Date: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
            f"Balance: ${balance:.2f}\n"
            f"Win Rate: {win_rate:.1f}%\n"
            f"Trades: {total_trades}"
        )
        await self.send_message(text)

    async def send_weekly_report(
        self,
        balance: float,
        win_rate: float,
        total_pnl: float,
        total_trades: int,
    ) -> None:
        text = (
            f"📈 <b>Weekly Report</b>\n"
            f"Week ending: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
            f"Balance: ${balance:.2f}\n"
            f"Win Rate: {win_rate:.1f}%\n"
            f"Total PnL: ${total_pnl:.2f}\n"
            f"Trades: {total_trades}"
        )
        await self.send_message(text)
