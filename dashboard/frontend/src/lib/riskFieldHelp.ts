/** Plain-language help for each risk setting field. */

export const RISK_FIELD_HELP: Record<string, string> = {
  risk_per_trade_pct:
    "How much of your account you risk on one trade if the stop-loss hits. 1% on $10,000 = $100 max loss per trade.",
  max_concurrent_positions:
    "Maximum number of open trades at the same time on this account (all symbols combined).",
  max_positions_per_symbol:
    "Maximum open trades on one pair. 1 = only one BTCUSDT (or ETH) position at a time.",
  max_daily_loss_pct:
    "If today's total loss (closed trades + floating PnL) exceeds this % of equity, new trades are blocked.",
  max_drawdown_pct:
    "If equity falls this % below its recent peak, trading halts until you resume.",
  max_unrealized_loss_pct:
    "Blocks new entries when open (floating) loss is larger than this % of equity.",
  emergency_close_unrealized_loss_pct:
    "If floating loss reaches this %, the bot closes all open positions on this account immediately.",
  max_total_exposure_pct:
    "Cap on total position size as % of equity. 40% on $100 ≈ $40 max notional (~0.0006 BTC).",
  signal_cooldown_minutes:
    "After opening on a symbol, wait this many minutes before another auto entry on the same symbol.",
  cooldown_after_loss_minutes:
    "After a losing close, wait this long before allowing new auto entries.",
  atr_stop_multiplier:
    "ATR = Average True Range (how much price typically moves). Stop is placed this many × ATR away from entry. 2 = wider stop in volatile markets.",
  take_profit_rr:
    "R:R = Risk:Reward. 2 means take-profit is 2× as far as the stop. Risk $50 to make → target $100 profit.",
  trailing_stop_atr_multiplier:
    "Trailing stop follows price at this many × ATR behind it, locking in profit as price moves your way.",
  break_even_trigger_rr:
    "When price moves this many R in profit (1R = distance to stop), stop moves to entry so you cannot lose on that trade.",
  block_duplicate_side:
    "If ON: cannot open another LONG while already LONG on the same symbol (no stacking).",
  use_equity_for_limits:
    "If ON: % limits use balance + open PnL. If OFF: uses cash balance only.",
};

export const RISK_GLOSSARY: { term: string; meaning: string }[] = [
  { term: "R / 1R", meaning: "One “unit of risk” = distance from entry to stop-loss. If stop is $100 away, 1R = $100." },
  { term: "R:R (Risk:Reward)", meaning: "Ratio of stop distance to target distance. R:R 2 → target is twice as far as the stop." },
  { term: "ATR", meaning: "Average True Range — average recent price swing size. Used for dynamic stop distance." },
  { term: "Equity", meaning: "Balance + unrealized PnL from open positions." },
  { term: "Exposure", meaning: "Total size of open positions (quantity × price), as % of equity." },
  { term: "Unrealized / floating PnL", meaning: "Profit or loss on trades that are still open, not yet closed." },
  { term: "Drawdown", meaning: "How far equity has fallen from its highest point in this session." },
];

export type RiskImpact = "pnl" | "trades" | "both" | "protect";

export const RISK_FIELD_IMPACT: Record<string, RiskImpact> = {
  risk_per_trade_pct: "pnl",
  max_concurrent_positions: "trades",
  max_positions_per_symbol: "trades",
  max_daily_loss_pct: "both",
  max_drawdown_pct: "trades",
  max_unrealized_loss_pct: "trades",
  emergency_close_unrealized_loss_pct: "pnl",
  max_total_exposure_pct: "pnl",
  signal_cooldown_minutes: "trades",
  cooldown_after_loss_minutes: "trades",
  atr_stop_multiplier: "pnl",
  take_profit_rr: "pnl",
  trailing_stop_atr_multiplier: "pnl",
  break_even_trigger_rr: "pnl",
  block_duplicate_side: "trades",
  use_equity_for_limits: "protect",
};

export const RISK_IMPACT_LABELS: Record<RiskImpact, string> = {
  pnl: "Affects PnL",
  trades: "Affects # trades",
  both: "PnL + trades",
  protect: "How limits are measured",
};

export const RISK_PNL_TABLE: { setting: string; effect: string }[] = [
  {
    setting: "Risk per trade %",
    effect: "Main sizing knob. Higher % → bigger wins AND losses per trade. 1% on $10k ≈ $100 risk per trade.",
  },
  {
    setting: "Max exposure %",
    effect: "Caps position size. On $100 at 40% → ~$40 max → small PnL per trade on small accounts.",
  },
  {
    setting: "ATR stop multiplier",
    effect: "Wider stop → smaller size (with fixed risk) but less likely to stop out early.",
  },
  {
    setting: "Take profit R:R",
    effect: "Target distance vs stop. R:R 2 → when TP hits, profit ≈ 2× what you risked.",
  },
  {
    setting: "Trailing ATR / Break-even R:R",
    effect: "Changes when and how stops move → can lock profit or exit at scratch instead of a loss.",
  },
  {
    setting: "Emergency close %",
    effect: "Forces all positions closed → realized PnL changes immediately when triggered.",
  },
  {
    setting: "Daily loss / drawdown / unrealized caps",
    effect: "Do not change open-trade math. They block NEW trades so you stop adding losses.",
  },
];

export const RISK_TRADES_TABLE: { setting: string; effect: string }[] = [
  {
    setting: "Max open positions",
    effect: "Hard cap on concurrent trades. 22 = up to 22 open at once.",
  },
  {
    setting: "Max per symbol",
    effect: "1 = only one BTC and one ETH position at a time — no stacking.",
  },
  {
    setting: "Signal cooldown (min)",
    effect: "Fewer auto entries on the same symbol after a recent open.",
  },
  {
    setting: "Cooldown after loss (min)",
    effect: "Pauses new auto trades after a losing close.",
  },
  {
    setting: "Daily loss % / Max drawdown %",
    effect: "Stops or halts new trades when limits hit → fewer trades for the rest of the session/day.",
  },
  {
    setting: "Block duplicate side",
    effect: "No second LONG on the same symbol → fewer duplicate entries.",
  },
];

export const RISK_SAVE_NOTE =
  "Saving does NOT change closed trade history or balance from past trades. New values apply to the next trade, manual entry, or stop update.";
