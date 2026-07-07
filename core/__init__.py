"""Core trading bot module."""

from core.bot import TradingBot
from core.engine import StrategyEngine
from core.main import main
from core.paper_trader import PaperTrader
from core.state import BotState, StateManager

__all__ = [
    "TradingBot",
    "StrategyEngine",
    "PaperTrader",
    "BotState",
    "StateManager",
    "main",
]
