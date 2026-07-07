/** Strategy field definitions and help for the dashboard settings UI. */

export type StrategyFieldType = "boolean" | "number" | "select";

export interface StrategyFieldDef {
  key: string;
  label: string;
  type: StrategyFieldType;
  options?: string[];
  step?: number;
  min?: number;
  max?: number;
  help: string;
  /** Longer explanation — shown below the field and on label hover. */
  helpDetail?: string;
}

export interface StrategyGuide {
  summary: string;
  longWhen: string[];
  shortWhen: string[];
  tuningTips: string[];
  note?: string;
}

export const STRATEGY_GUIDES: Record<string, StrategyGuide> = {
  scalping: {
    summary:
      "Looks for quick mean-reversion bounces: price stretches to a Bollinger Band edge while short EMAs agree on direction, RSI is stretched, and volume is active.",
    longWhen: [
      "Fast EMA (5) is above slow EMA (13) — short-term bias is up",
      "Price is at or below the lower Bollinger Band (oversold stretch)",
      "RSI is below 35 (pullback in an up-bias)",
      "Current candle volume ≥ min volume ratio × 20-candle average",
    ],
    shortWhen: [
      "Fast EMA is below slow EMA — short-term bias is down",
      "Price is at or above the upper Bollinger Band (overbought stretch)",
      "RSI is above 65",
      "Volume filter passes (same as LONG)",
    ],
    tuningTips: [
      "Lower min volume ratio (e.g. 1.0) = more signals; raise (e.g. 1.5) = only high-volume moves",
      "Tighter EMAs (3/8) react faster; wider (8/21) are calmer",
      "Narrower BB std (1.5) = bands closer to price, more touches; wider (2.5) = fewer band hits",
    ],
    note:
      "Despite the name, this runs on your bot’s primary timeframe (15m). It fires less often than on 1m/5m charts. Stops ≈ 1.5× ATR, targets ≈ 2× ATR.",
  },
  breakout: {
    summary:
      "Trades when price breaks above the recent range high (LONG) or below the range low (SHORT), with enough volume to confirm the move.",
    longWhen: [
      "Close breaks above the highest high of the last N candles (lookback)",
      "Volume on this candle ≥ volume multiplier × average volume in that range",
    ],
    shortWhen: [
      "Close breaks below the lowest low of the last N candles",
      "Volume confirmation (same rule as LONG)",
    ],
    tuningTips: [
      "Lookback 20 on 15m ≈ 5 hours of range; smaller = more breaks, more false signals",
      "Volume multiplier 1.0 = at least average volume; 1.5 = needs a volume spike",
    ],
    note: "Stop uses nearest support/resistance or 2× ATR; target ≈ 3× ATR.",
  },
};

export const STRATEGY_META: Record<
  string,
  { title: string; summary: string }
> = {
  ema_cross_rsi: {
    title: "EMA Cross + RSI",
    summary:
      "LONG when fast EMA > slow EMA (trend mode) and RSI is between filters. SHORT when fast < slow. Evaluated on each 15m candle close.",
  },
  trend_following: {
    title: "Trend Following",
    summary: "Trades with EMA + ADX trend strength + Supertrend direction.",
  },
  scalping: {
    title: "Scalping",
    summary:
      "Short-term bounce trades: EMA bias + RSI stretch + Bollinger Band touch + volume filter. Scans every 15m candle close.",
  },
  breakout: {
    title: "Breakout",
    summary: "Enters when price breaks recent high/low with volume confirmation.",
  },
  mean_reversion: {
    title: "Mean Reversion",
    summary: "Fades extremes using Bollinger Bands + RSI in low-ADX markets.",
  },
};

export function formatStrategyName(strategy: string): string {
  if (strategy === "manual") return "Manual";
  if (strategy === "binance_fill" || strategy === "exchange") return "Testnet fill";
  return STRATEGY_META[strategy]?.title ?? strategy.replace(/_/g, " ");
}

export const STRATEGY_FIELDS: Record<string, StrategyFieldDef[]> = {
  ema_cross_rsi: [
    {
      key: "enabled",
      label: "Enabled",
      type: "boolean",
      help: "Turn this strategy on or off for auto-trading.",
    },
    {
      key: "signal_mode",
      label: "Signal mode",
      type: "select",
      options: ["trend", "crossover"],
      help: "trend = signal while fast EMA above/below slow. crossover = only on the cross candle.",
    },
    { key: "fast_ema", label: "Fast EMA period", type: "number", min: 2, help: "Short EMA length (default 9)." },
    { key: "slow_ema", label: "Slow EMA period", type: "number", min: 3, help: "Long EMA length (default 21)." },
    { key: "rsi_period", label: "RSI period", type: "number", min: 2, help: "RSI lookback (default 14)." },
    {
      key: "rsi_filter_long_min",
      label: "RSI min for LONG",
      type: "number",
      min: 0,
      max: 100,
      help: "LONG only if RSI is above this (default 40).",
    },
    {
      key: "rsi_filter_short_max",
      label: "RSI max for SHORT",
      type: "number",
      min: 0,
      max: 100,
      help: "SHORT only if RSI is below this (default 60).",
    },
  ],
  trend_following: [
    { key: "enabled", label: "Enabled", type: "boolean", help: "Turn strategy on/off." },
    { key: "ema_period", label: "EMA period", type: "number", min: 5, help: "Trend EMA (default 50)." },
    { key: "adx_period", label: "ADX period", type: "number", min: 2, help: "ADX lookback." },
    {
      key: "adx_threshold",
      label: "ADX threshold",
      type: "number",
      min: 5,
      help: "Minimum ADX for a trend (default 25).",
    },
    { key: "supertrend_period", label: "Supertrend period", type: "number", min: 2, help: "Supertrend ATR period." },
    {
      key: "supertrend_multiplier",
      label: "Supertrend multiplier",
      type: "number",
      step: 0.1,
      min: 0.5,
      help: "Supertrend band width.",
    },
  ],
  scalping: [
    {
      key: "enabled",
      label: "Enabled",
      type: "boolean",
      help: "Turn this strategy on or off for auto-trading on this account.",
      helpDetail:
        "When ON, the bot checks for scalping signals at each 15m candle close (same as other strategies). It does not run every second.",
    },
    {
      key: "ema_fast",
      label: "Fast EMA",
      type: "number",
      min: 2,
      help: "Short EMA length (default 5).",
      helpDetail:
        "Reacts quickly to recent price. For LONG, fast EMA must be above slow EMA (up-bias). For SHORT, fast must be below slow. Lower = more sensitive, more signals.",
    },
    {
      key: "ema_slow",
      label: "Slow EMA",
      type: "number",
      min: 3,
      help: "Longer EMA length (default 13).",
      helpDetail:
        "Defines the short-term trend filter paired with fast EMA. Typical gap: fast 5 / slow 13. If slow is too close to fast, you get whipsaws; too far apart, fewer setups.",
    },
    {
      key: "rsi_period",
      label: "RSI period",
      type: "number",
      min: 2,
      help: "How many candles RSI uses (default 7).",
      helpDetail:
        "Shorter period (5–7) = RSI moves faster, catches quick pullbacks. LONG needs RSI < 35; SHORT needs RSI > 65 (fixed in code).",
    },
    {
      key: "bb_period",
      label: "BB period",
      type: "number",
      min: 5,
      help: "Bollinger Bands lookback (default 20).",
      helpDetail:
        "Number of candles used to calculate the middle band (SMA) and upper/lower bands. 20 on 15m ≈ 5 hours. LONG triggers near lower band; SHORT near upper band.",
    },
    {
      key: "bb_std",
      label: "BB std dev",
      type: "number",
      step: 0.1,
      min: 0.5,
      help: "Band width — default 2.0 standard deviations.",
      helpDetail:
        "Higher (e.g. 2.5) = wider bands, price reaches edges less often, fewer signals. Lower (e.g. 1.5) = tighter bands, more band touches, more signals (more noise).",
    },
    {
      key: "min_volume_ratio",
      label: "Min volume ratio",
      type: "number",
      step: 0.1,
      min: 0.5,
      help: "Volume must be at least this × the 20-candle average.",
      helpDetail:
        "Example: 1.0 = current candle volume must be at least the recent average (filters dead, low-volume bars). 1.2 = needs 20% above average. 0.8 = looser, more trades.",
    },
  ],
  breakout: [
    { key: "enabled", label: "Enabled", type: "boolean", help: "Turn strategy on/off." },
    {
      key: "lookback_period",
      label: "Lookback candles",
      type: "number",
      min: 5,
      help: "How many past candles define the range high and low.",
      helpDetail:
        "Default 20 on 15m ≈ 5 hours. The bot buys if price breaks above that range high (with volume); sells if price breaks below the range low. Smaller lookback = tighter range, more breakouts.",
    },
    {
      key: "volume_multiplier",
      label: "Volume multiplier",
      type: "number",
      step: 0.1,
      min: 1,
      help: "Breakout candle volume vs average in the lookback window.",
      helpDetail:
        "1.0 = at least average volume on the breakout candle. 1.5 = needs a clear volume spike. Lower = easier to trigger; higher = only strong breakouts.",
    },
    {
      key: "confirmation_candles",
      label: "Confirmation candles",
      type: "number",
      min: 0,
      help: "Extra bars to confirm (reserved; currently 1 bar logic in code).",
      helpDetail: "Kept for future use. Breakout mainly uses lookback + volume on the closing candle.",
    },
  ],
  mean_reversion: [
    { key: "enabled", label: "Enabled", type: "boolean", help: "Turn strategy on/off." },
    { key: "bb_period", label: "BB period", type: "number", min: 5, help: "Bollinger period." },
    { key: "bb_std", label: "BB std dev", type: "number", step: 0.1, min: 0.5, help: "Band width." },
    { key: "rsi_period", label: "RSI period", type: "number", min: 2, help: "RSI lookback." },
    { key: "rsi_oversold", label: "RSI oversold", type: "number", min: 0, max: 50, help: "Buy zone RSI." },
    { key: "rsi_overbought", label: "RSI overbought", type: "number", min: 50, max: 100, help: "Sell zone RSI." },
    { key: "adx_max", label: "ADX max", type: "number", min: 5, help: "Only trade when ADX below this (ranging market)." },
  ],
};

export const EMA_CROSS_GUIDE = {
  longRules: [
    "Fast EMA (9) above slow EMA (21) — or exact bullish cross in crossover mode",
    "RSI > rsi_filter_long_min (40) and RSI < 70",
    "Enough candle history loaded",
  ],
  shortRules: [
    "Fast EMA below slow EMA — or exact bearish cross in crossover mode",
    "RSI < rsi_filter_short_max (60) and RSI > 30",
  ],
  stops: "Stop ≈ 2× ATR from entry, take-profit ≈ 4× ATR (before risk manager adjustments).",
};
