"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type SeriesMarker,
  type UTCTimestamp,
} from "lightweight-charts";
import { fetchApi } from "@/lib/api";
import { chartLocalization, chartTickMarkFormatter, formatCountdown, formatPakistanClock, getMsUntilCandleClose, getNextCandleCloseMs } from "@/lib/timezone";
import { toTradingViewSymbol } from "@/lib/tradingview";
import { TradingViewChart } from "@/components/TradingViewChart";

interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface TradeMarker {
  time: number;
  type: string;
  side: string;
  price: number;
  strategy: string;
  pnl?: number | null;
}

interface PriceLineData {
  price: number;
  color: string;
  title: string;
  style?: string;
}

interface Position {
  id: string;
  symbol: string;
  side: string;
  entry_price: number;
  stop_loss?: number | null;
  take_profit?: number | null;
  unrealized_pnl: number;
}

interface TradingChartProps {
  symbols: string[];
  positions: Position[];
  defaultSymbol?: string;
}

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h"];
const CHART_SOURCES = [
  { id: "bot", label: "Bot Chart" },
  { id: "tradingview", label: "TradingView" },
] as const;
type ChartSource = (typeof CHART_SOURCES)[number]["id"];
const VISIBLE_BAR_OPTIONS = [30, 50, 80] as const;
const DEFAULT_VISIBLE_BARS = 50;
const SCROLL_STEP = 15;

function showRecentBars(chart: IChartApi, candleCount: number, visibleBars: number) {
  if (candleCount <= 0) return;
  const bars = Math.min(visibleBars, candleCount);
  chart.timeScale().setVisibleLogicalRange({
    from: candleCount - bars,
    to: candleCount + 0.5,
  });
}

function shiftVisibleRange(chart: IChartApi, delta: number) {
  const range = chart.timeScale().getVisibleLogicalRange();
  if (!range) return;
  chart.timeScale().setVisibleLogicalRange({
    from: range.from + delta,
    to: range.to + delta,
  });
}

function snapToCandleTime(time: number, candles: Candle[]): number {
  if (!candles.length) return time;
  const times = candles.map((c) => c.time);
  if (time >= times[times.length - 1]) return times[times.length - 1];
  if (time <= times[0]) return times[0];
  let nearest = times[0];
  let minDiff = Math.abs(time - nearest);
  for (const t of times) {
    const diff = Math.abs(t - time);
    if (diff < minDiff) {
      minDiff = diff;
      nearest = t;
    }
  }
  return nearest;
}

function buildPositionMarkers(positions: Position[], candles: Candle[]): TradeMarker[] {
  if (!candles.length) return [];
  const lastCandleTime = candles[candles.length - 1].time;
  return positions.map((p) => ({
    time: lastCandleTime,
    type: "entry",
    side: p.side,
    price: p.entry_price,
    strategy: "manual",
    pnl: null,
  }));
}

function getTradeBSLabel(marker: TradeMarker): string {
  const isLong = marker.side.toUpperCase() === "LONG";
  if (marker.type === "entry") {
    return isLong ? "B" : "S";
  }
  return isLong ? "S" : "B";
}

function mergeTradeMarkers(
  apiMarkers: TradeMarker[],
  openPositions: Position[],
  candles: Candle[]
): TradeMarker[] {
  if (openPositions.length === 0) {
    return apiMarkers;
  }

  const openEntryPrices = new Set(
    openPositions.map((p) => Math.round(p.entry_price * 100) / 100)
  );

  const historical = apiMarkers.filter((m) => {
    if (m.type === "exit") return true;
    const price = Math.round(m.price * 100) / 100;
    return !openEntryPrices.has(price);
  });

  return [...historical, ...buildPositionMarkers(openPositions, candles)];
}

const MARKER_SIZE = 0.35;

function markerColor(label: string): string {
  return label === "B" ? "#22c55e" : "#ef4444";
}

function formatPnl(pnl: number): string {
  const sign = pnl >= 0 ? "+" : "";
  return `${sign}${pnl.toFixed(1)}`;
}

function getMarkerText(marker: TradeMarker): string {
  const label = getTradeBSLabel(marker);
  if (marker.type === "exit" && marker.pnl != null && !Number.isNaN(marker.pnl)) {
    return `${label} ${formatPnl(marker.pnl)}`;
  }
  return label;
}

function getMarkerColor(marker: TradeMarker, label: string): string {
  if (marker.type === "exit" && marker.pnl != null && !Number.isNaN(marker.pnl)) {
    return marker.pnl >= 0 ? "#22c55e" : "#ef4444";
  }
  return markerColor(label);
}

function toChartMarkers(markers: TradeMarker[], candles: Candle[]): SeriesMarker<UTCTimestamp>[] {
  const candleTimeSet = new Set(candles.map((c) => c.time));
  const sorted = [...markers].sort((a, b) => a.time - b.time);

  type PreparedMarker = {
    marker: TradeMarker;
    time: UTCTimestamp;
    index: number;
  };

  const prepared: PreparedMarker[] = sorted.map((m, index) => {
    let time = snapToCandleTime(m.time, candles) as UTCTimestamp;
    if (!candleTimeSet.has(time) && candles.length > 0) {
      time = candles[candles.length - 1].time as UTCTimestamp;
    }
    return { marker: m, time, index };
  });

  const byCandle = new Map<number, PreparedMarker[]>();
  for (const item of prepared) {
    const key = item.time as number;
    const group = byCandle.get(key) ?? [];
    group.push(item);
    byCandle.set(key, group);
  }

  const chartMarkers = prepared.map((item) => {
    const group = byCandle.get(item.time as number) ?? [item];
    const lineIndex = group.indexOf(item);
    const label = getTradeBSLabel(item.marker);

    return {
      time: item.time,
      position: lineIndex === 0 ? "inBar" : "aboveBar",
      color: getMarkerColor(item.marker, label),
      shape: "circle",
      text: getMarkerText(item.marker),
      size: MARKER_SIZE,
      id: `trade-${item.index}-${item.time}-${label}-${lineIndex}`,
    } as SeriesMarker<UTCTimestamp>;
  });

  return chartMarkers.sort((a, b) => {
    const timeDiff = (a.time as number) - (b.time as number);
    if (timeDiff !== 0) return timeDiff;
    const positionOrder = (position: SeriesMarker<UTCTimestamp>["position"]) =>
      position === "inBar" ? 0 : 1;
    return positionOrder(a.position) - positionOrder(b.position);
  });
}

export function TradingChart({
  symbols,
  positions,
  defaultSymbol = "BTCUSDT",
}: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const candleCountRef = useRef(0);
  const resetViewRef = useRef(true);
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [timeframe, setTimeframe] = useState("15m");
  const [chartSource, setChartSource] = useState<ChartSource>("tradingview");
  const [visibleBars, setVisibleBars] = useState<number>(DEFAULT_VISIBLE_BARS);
  const [price, setPrice] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [markerCount, setMarkerCount] = useState(0);
  const [candleCountdown, setCandleCountdown] = useState("00:00");
  const [candleCloseAt, setCandleCloseAt] = useState("");
  const [openPositions, setOpenPositions] = useState<Position[]>(
    positions.filter((p) => p.symbol === defaultSymbol)
  );

  const clearPriceLines = () => {
    if (seriesRef.current) {
      priceLinesRef.current.forEach((line) => seriesRef.current?.removePriceLine(line));
    }
    priceLinesRef.current = [];
  };

  const applyPriceLines = (lines: PriceLineData[]) => {
    if (!seriesRef.current) return;
    clearPriceLines();
    lines.forEach((line) => {
      const pl = seriesRef.current!.createPriceLine({
        price: line.price,
        color: line.color,
        lineWidth: 2,
        lineStyle: line.style === "solid" ? 0 : 2,
        axisLabelVisible: true,
        title: line.title,
      });
      priceLinesRef.current.push(pl);
    });
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (chartSource === "tradingview") {
        const snapshot = await fetchApi<{ price: number }>(`/market/snapshot?symbol=${symbol}`);
        setPrice(snapshot.price);
        return;
      }

      const [candles, snapshot, tradeData, livePositions] = await Promise.all([
        fetchApi<Candle[]>(`/market/candles?symbol=${symbol}&timeframe=${timeframe}&limit=200`),
        fetchApi<{ price: number }>(`/market/snapshot?symbol=${symbol}`),
        fetchApi<{ markers: TradeMarker[]; price_lines: PriceLineData[] }>(
          `/market/trade-markers?symbol=${symbol}&timeframe=${timeframe}`
        ),
        fetchApi<Position[]>(`/positions`).catch(() => [] as Position[]),
      ]);

      setOpenPositions(livePositions.filter((p) => p.symbol === symbol));

      if (!seriesRef.current || candles.length === 0) {
        setPrice(snapshot.price);
        return;
      }

      const savedRange = resetViewRef.current
        ? null
        : chartRef.current?.timeScale().getVisibleLogicalRange();

      seriesRef.current.setData(
        candles.map((c) => ({
          time: c.time as UTCTimestamp,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }))
      );
      candleCountRef.current = candles.length;

      const symbolPositions = livePositions.filter((p) => p.symbol === symbol);
      const markers = mergeTradeMarkers(tradeData.markers, symbolPositions, candles);

      const chartMarkers = toChartMarkers(markers, candles);
      seriesRef.current.setMarkers(chartMarkers);
      setMarkerCount(chartMarkers.length);

      const priceLines =
        tradeData.price_lines.length > 0
          ? tradeData.price_lines
          : symbolPositions.flatMap((p) => {
              const lines: PriceLineData[] = [
                { price: p.entry_price, color: "#3b82f6", title: "Entry", style: "solid" },
              ];
              if (p.stop_loss) {
                lines.push({ price: p.stop_loss, color: "#ef4444", title: "Stop Loss" });
              }
              if (p.take_profit) {
                lines.push({ price: p.take_profit, color: "#22c55e", title: "Take Profit" });
              }
              return lines;
            });

      applyPriceLines(priceLines);

      const chart = chartRef.current;
      if (chart) {
        if (resetViewRef.current) {
          showRecentBars(chart, candles.length, visibleBars);
          resetViewRef.current = false;
        } else if (savedRange) {
          chart.timeScale().setVisibleLogicalRange(savedRange);
        }
      }

      setPrice(snapshot.price);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load chart");
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe, visibleBars, chartSource]);

  const goOlder = () => {
    if (chartRef.current) shiftVisibleRange(chartRef.current, -SCROLL_STEP);
  };

  const goNewer = () => {
    if (chartRef.current) shiftVisibleRange(chartRef.current, SCROLL_STEP);
  };

  const goLatest = () => {
    if (chartRef.current) {
      showRecentBars(chartRef.current, candleCountRef.current, visibleBars);
    }
  };

  useEffect(() => {
    resetViewRef.current = true;
  }, [symbol, timeframe, visibleBars]);

  useEffect(() => {
    if (chartSource !== "bot" || !containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "#0f172a" },
        textColor: "#94a3b8",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      width: containerRef.current.clientWidth,
      height: 420,
      localization: chartLocalization(),
      timeScale: {
        borderColor: "#334155",
        timeVisible: true,
        tickMarkFormatter: chartTickMarkFormatter(),
      },
      rightPriceScale: { borderColor: "#334155" },
      crosshair: { mode: 1 },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const onResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      clearPriceLines();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [chartSource]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    const interval = setInterval(loadData, 10000);
    const onTradePlaced = () => {
      void loadData();
    };
    const onAccountSwitched = () => {
      resetViewRef.current = true;
      void loadData();
    };
    window.addEventListener("trade-placed", onTradePlaced);
    window.addEventListener("account-switched", onAccountSwitched);
    return () => {
      clearInterval(interval);
      window.removeEventListener("trade-placed", onTradePlaced);
      window.removeEventListener("account-switched", onAccountSwitched);
    };
  }, [loadData]);

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setCandleCountdown(formatCountdown(getMsUntilCandleClose(timeframe, now)));
      setCandleCloseAt(formatPakistanClock(getNextCandleCloseMs(timeframe, now)));
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [timeframe]);

  const symbolPositions = openPositions.filter((p) => p.symbol === symbol);

  return (
    <div className="trading-chart">
      <div className="chart-toolbar">
        <div className="chart-toolbar-left">
          <div className="tf-group chart-source-toggle" title="Chart provider">
            {CHART_SOURCES.map((source) => (
              <button
                key={source.id}
                type="button"
                className={`tf-btn ${chartSource === source.id ? "active" : ""}`}
                onClick={() => setChartSource(source.id)}
              >
                {source.label}
              </button>
            ))}
          </div>
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            {symbols.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <div className="tf-group">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                className={`tf-btn ${timeframe === tf ? "active" : ""}`}
                onClick={() => setTimeframe(tf)}
              >
                {tf}
              </button>
            ))}
          </div>
          {chartSource === "bot" && (
            <>
              <div className="chart-nav" title="Scroll through chart history">
                <button type="button" className="chart-nav-btn" onClick={goOlder}>
                  ◀ Older
                </button>
                <button type="button" className="chart-nav-btn chart-nav-latest" onClick={goLatest}>
                  Latest
                </button>
                <button type="button" className="chart-nav-btn" onClick={goNewer}>
                  Newer ▶
                </button>
              </div>
              <div className="tf-group" title="Candles visible on screen">
                {VISIBLE_BAR_OPTIONS.map((n) => (
                  <button
                    key={n}
                    type="button"
                    className={`tf-btn ${visibleBars === n ? "active" : ""}`}
                    onClick={() => setVisibleBars(n)}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
        <div className="chart-price">
          <span
            className="candle-countdown"
            title={`${timeframe} candle closes at ${candleCloseAt} PKT`}
          >
            Closes in <strong>{candleCountdown}</strong>
          </span>
          {price > 0 && (
            <span>
              {symbol}{" "}
              <strong>${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong>
            </span>
          )}
          {markerCount > 0 && chartSource === "bot" && (
            <span className="chart-markers-badge">{markerCount} trade markers</span>
          )}
          {loading && <span className="chart-loading">Updating…</span>}
        </div>
      </div>

      {error && <p className="empty">{error}</p>}
      <p className="chart-scroll-hint">
        {chartSource === "tradingview" ? (
          <>
            TradingView chart — live Binance Futures ({toTradingViewSymbol(symbol)}). Times in PKT
            (UTC+5). Use TradingView tools for indicators and drawing.
          </>
        ) : (
          <>
            Showing last {visibleBars} candles — drag chart or use ◀ ▶ to browse trade history.
            Times shown in PKT (UTC+5).
          </>
        )}
      </p>
      {chartSource === "tradingview" ? (
        <TradingViewChart symbol={symbol} timeframe={timeframe} />
      ) : (
        <div ref={containerRef} className="chart-container" />
      )}

      {chartSource === "bot" && (
        <div className="chart-legend chart-legend-trades">
        <span className="legend-item">
          <span className="pnl-positive">B</span> Buy — on candle (green)
        </span>
        <span className="legend-item">
          <span className="pnl-negative">S</span> Sell — on candle (red)
        </span>
        <span className="legend-item">
          Close shows <span className="pnl-positive">+PnL</span> /{" "}
          <span className="pnl-negative">-PnL</span>
        </span>
        <span className="legend-item">Multiple trades on one candle stack above</span>
        <span className="legend-item sl-cell">— SL line</span>
        <span className="legend-item tp-cell">— TP line</span>
        <span className="legend-item" style={{ color: "#3b82f6" }}>
          — Entry line
        </span>
        </div>
      )}

      {chartSource === "bot" && symbolPositions.length > 0 && (
        <div className="chart-legend">
          {symbolPositions.map((p, i) => (
            <span key={p.id || `${p.symbol}-${i}`} className="legend-item">
              <span className={p.side === "LONG" ? "pnl-positive" : "pnl-negative"}>
                {p.side}
              </span>{" "}
              @ {p.entry_price.toFixed(2)}
              {p.stop_loss ? ` · SL ${p.stop_loss.toFixed(0)}` : ""}
              {p.take_profit ? ` · TP ${p.take_profit.toFixed(0)}` : ""}
              {" · "}PnL ${p.unrealized_pnl.toFixed(2)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
