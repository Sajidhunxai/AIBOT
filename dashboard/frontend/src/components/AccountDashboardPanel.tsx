"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, StatBox, Badge } from "@/components/Card";
import { EquityChart } from "@/components/EquityChart";
import { fetchApi } from "@/lib/api";
import { formatStrategyName } from "@/lib/strategyFieldHelp";
import { formatPakistanClock } from "@/lib/timezone";

interface Performance {
  balance: number;
  equity: number;
  total_assets?: number;
  unrealized_pnl?: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  open_positions: number;
  daily_pnl: number;
  strategy_stats: Record<string, { total_trades: number; win_rate: number; total_pnl: number }>;
  account_id?: number | null;
  account_name?: string | null;
}

interface Trade {
  id: number;
  symbol: string;
  side: string;
  strategy: string;
  entry_price: number;
  exit_price: number | null;
  pnl: number | null;
}

interface Signal {
  id: number;
  symbol: string;
  strategy: string;
  action: string;
  confidence: number;
  created_at: string | null;
}

function buildEquityData(
  trades: Trade[],
  startBalance: number,
): { index: number; equity: number }[] {
  const chronological = [...trades].reverse();
  return chronological.reduce<{ index: number; equity: number }[]>((acc, t, i) => {
    const prev = acc.length ? acc[acc.length - 1].equity : startBalance;
    acc.push({ index: i + 1, equity: prev + (t.pnl ?? 0) });
    return acc;
  }, []);
}

export function AccountDashboardPanel() {
  const [performance, setPerformance] = useState<Performance | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [tradingMode, setTradingMode] = useState("paper");

  const load = useCallback(async () => {
    try {
      const [perf, tradeData, signalData, status] = await Promise.all([
        fetchApi<Performance>("/performance"),
        fetchApi<Trade[]>("/trades/closed?limit=50"),
        fetchApi<Signal[]>("/signals?limit=20"),
        fetchApi<{ mode?: string }>("/status"),
      ]);
      setPerformance(perf);
      setTrades(tradeData);
      setSignals(signalData);
      setTradingMode(status.mode ?? "paper");
    } catch {
      setPerformance(null);
      setTrades([]);
      setSignals([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = setInterval(load, 10000);
    const onSwitch = () => {
      setLoading(true);
      void load();
    };
    window.addEventListener("account-switched", onSwitch);
    return () => {
      clearInterval(interval);
      window.removeEventListener("account-switched", onSwitch);
    };
  }, [load]);

  const accountLabel = performance?.account_name ? ` · ${performance.account_name}` : "";
  const totalHistoricalPnl = trades.reduce((sum, t) => sum + (t.pnl ?? 0), 0);
  const equityStart =
    tradingMode === "paper"
      ? (performance?.balance ?? 10000)
      : Math.max(0, (performance?.balance ?? 0) - totalHistoricalPnl);
  const equityData = buildEquityData(trades, equityStart);

  if (loading && !performance) {
    return <p className="empty">Loading account data…</p>;
  }

  return (
    <>
      <div className="grid grid-4" style={{ marginBottom: "1.5rem" }}>
        <Card title={`Total Assets${accountLabel}`}>
          <StatBox
            label={
              tradingMode === "paper"
                ? "USDT — updates on close"
                : `Binance ${tradingMode} (matches mobile app)`
            }
            value={`$${(performance?.total_assets ?? performance?.equity ?? performance?.balance ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
          />
        </Card>
        <Card title={`Futures Wallet${accountLabel}`}>
          <StatBox
            label="USD wallet balance (excl. BTC collateral)"
            value={`$${(performance?.balance ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
          />
        </Card>
        <Card title={`Equity (Margin)${accountLabel}`}>
          <StatBox
            label="Wallet + open PnL (API margin balance)"
            value={`$${(performance?.equity ?? performance?.balance ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
            color={
              (performance?.equity ?? 0) >= (performance?.balance ?? 0) ? "#22c55e" : "#ef4444"
            }
          />
        </Card>
        <Card title={`Daily PnL${accountLabel}`}>
          <StatBox
            label="Today"
            value={`$${(performance?.daily_pnl ?? 0).toFixed(2)}`}
            color={(performance?.daily_pnl ?? 0) >= 0 ? "#22c55e" : "#ef4444"}
          />
        </Card>
        <Card title={`Open Positions${accountLabel}`}>
          <StatBox label="Active" value={String(performance?.open_positions ?? 0)} />
        </Card>
      </div>

      <div className="grid grid-2" style={{ marginBottom: "1.5rem" }}>
        <Card title={`Equity Curve${accountLabel}`}>
          <EquityChart data={equityData} />
          {tradingMode !== "paper" && trades.length === 0 && (
            <p className="risk-hint">No closed PnL on Binance yet — equity curve fills after your first closed trade.</p>
          )}
        </Card>
        <Card title={`Strategy Performance${accountLabel}`}>
          {performance?.strategy_stats && Object.keys(performance.strategy_stats).length > 0 ? (
            Object.entries(performance.strategy_stats).map(([name, stats]) => (
              <div key={name} className="strategy-stat">
                <span>{formatStrategyName(name)}</span>
                <span>
                  {stats.total_trades} trades &middot; {stats.win_rate.toFixed(0)}% WR &middot;{" "}
                  <span className={stats.total_pnl >= 0 ? "pnl-positive" : "pnl-negative"}>
                    ${stats.total_pnl.toFixed(2)}
                  </span>
                </span>
              </div>
            ))
          ) : (
            <p className="empty">No strategy data yet</p>
          )}
        </Card>
      </div>

      <div className="grid grid-2" style={{ marginBottom: "1.5rem" }}>
        <Card title={`Recent Signals${accountLabel}`}>
          {signals.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Symbol</th>
                  <th>Action</th>
                  <th>Strategy</th>
                  <th>Conf.</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s) => (
                  <tr key={s.id}>
                    <td>{s.created_at ? formatPakistanClock(s.created_at) : "-"}</td>
                    <td>{s.symbol}</td>
                    <td>
                      <Badge variant={s.action.toLowerCase()}>{s.action}</Badge>
                    </td>
                    <td>{s.strategy}</td>
                    <td>{(s.confidence * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="empty">No signals yet</p>
          )}
        </Card>

        <Card title={`Closed Trades${accountLabel}`}>
          {trades.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Entry</th>
                  <th>Exit</th>
                  <th>PnL</th>
                  <th>Strategy</th>
                </tr>
              </thead>
              <tbody>
                {trades.slice(0, 15).map((t) => (
                  <tr key={t.id}>
                    <td>{t.symbol}</td>
                    <td>
                      <Badge variant={t.side}>{t.side}</Badge>
                    </td>
                    <td>{t.entry_price.toFixed(2)}</td>
                    <td>{t.exit_price?.toFixed(2) ?? "-"}</td>
                    <td className={(t.pnl ?? 0) >= 0 ? "pnl-positive" : "pnl-negative"}>
                      ${(t.pnl ?? 0).toFixed(2)}
                    </td>
                    <td>{formatStrategyName(t.strategy)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="empty">No closed trades</p>
          )}
        </Card>
      </div>
    </>
  );
}
