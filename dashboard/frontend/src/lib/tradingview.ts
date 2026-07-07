import { PAKISTAN_TIMEZONE } from "@/lib/timezone";

const TIMEFRAME_TO_TV: Record<string, string> = {
  "1m": "1",
  "5m": "5",
  "15m": "15",
  "1h": "60",
  "4h": "240",
};

export function toTradingViewSymbol(symbol: string): string {
  const normalized = symbol.toUpperCase().replace(/[^A-Z0-9]/g, "");
  return `BINANCE:${normalized}.P`;
}

export function toTradingViewInterval(timeframe: string): string {
  return TIMEFRAME_TO_TV[timeframe] ?? "15";
}

export const TRADINGVIEW_WIDGET_SCRIPT =
  "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";

export function buildTradingViewConfig(symbol: string, timeframe: string) {
  return {
    autosize: true,
    symbol: toTradingViewSymbol(symbol),
    interval: toTradingViewInterval(timeframe),
    timezone: PAKISTAN_TIMEZONE,
    theme: "dark",
    style: "1",
    locale: "en",
    backgroundColor: "#0f172a",
    gridColor: "#1e293b",
    toolbar_bg: "#1e293b",
    enable_publishing: false,
    allow_symbol_change: false,
    hide_side_toolbar: false,
    hide_top_toolbar: false,
    hide_legend: false,
    save_image: false,
    calendar: false,
    withdateranges: true,
    support_host: "https://www.tradingview.com",
  };
}
