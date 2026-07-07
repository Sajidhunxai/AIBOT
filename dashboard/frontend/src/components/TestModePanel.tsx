"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, StatBox } from "@/components/Card";
import { fetchApi, postApi } from "@/lib/api";
import { formatPakistanDate } from "@/lib/timezone";

interface TestSession {
  account_id?: number | null;
  account_name?: string | null;
  mode: string;
  started_at: string;
  days_running: number;
  starting_balance: number;
  current_equity: number;
  return_pct: number;
  session_pnl: number;
  max_drawdown_pct: number;
  closed_trades: number;
  win_rate: number;
  profit_factor: number;
  auto_initialized?: boolean;
}

function formatPct(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function TestModePanel() {
  const [session, setSession] = useState<TestSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchApi<TestSession>("/test-session");
      setSession(data);
      setError(null);
    } catch (e) {
      setSession(null);
      setError(e instanceof Error ? e.message : "Failed to load test session");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = setInterval(load, 15000);
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

  const handleReset = async () => {
    if (
      !confirm(
        "Reset the test baseline to your current equity? Return % and drawdown will restart from now. Closed trade history is kept.",
      )
    ) {
      return;
    }
    setResetting(true);
    setError(null);
    try {
      const data = await postApi<TestSession>("/test-session/reset");
      setSession(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reset failed");
    } finally {
      setResetting(false);
    }
  };

  if (loading && !session) {
    return (
      <Card title="Test Mode" className="test-mode-card">
        <p className="empty">Loading test metrics…</p>
      </Card>
    );
  }

  if (error && !session) {
    return (
      <Card title="Test Mode" className="test-mode-card">
        <p className="empty">{error}</p>
      </Card>
    );
  }

  if (!session) return null;

  const accountLabel = session.account_name ? ` · ${session.account_name}` : "";
  const startDate = formatPakistanDate(session.started_at);
  const returnColor = session.return_pct >= 0 ? "#22c55e" : "#ef4444";
  const pnlColor = session.session_pnl >= 0 ? "#22c55e" : "#ef4444";

  return (
    <Card title={`Test Mode${accountLabel}`} className="test-mode-card">
      <div className="test-mode-header">
        <p className="test-mode-intro">
          Track bot performance from a fixed baseline without changing trades or risk settings.
          {session.mode !== "paper" && (
            <> Metrics use your Binance {session.mode} wallet equity (balance + open PnL).</>
          )}
        </p>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => void handleReset()}
          disabled={resetting}
        >
          {resetting ? "Resetting…" : "Reset baseline"}
        </button>
      </div>

      {session.auto_initialized && (
        <p className="risk-hint test-mode-hint">
          Baseline set automatically on first view. Click &ldquo;Reset baseline&rdquo; when you want
          to start a fresh evaluation period.
        </p>
      )}

      <div className="grid grid-4 test-mode-stats">
        <StatBox label="Started" value={startDate} />
        <StatBox label="Days running" value={String(session.days_running)} />
        <StatBox
          label="Return"
          value={formatPct(session.return_pct)}
          color={returnColor}
        />
        <StatBox
          label="Max drawdown"
          value={`${session.max_drawdown_pct.toFixed(2)}%`}
          color={session.max_drawdown_pct > 5 ? "#ef4444" : "#e2e8f0"}
        />
      </div>

      <div className="grid grid-4 test-mode-stats">
        <StatBox
          label="Starting equity"
          value={`$${session.starting_balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
        />
        <StatBox
          label="Current equity"
          value={`$${session.current_equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
        />
        <StatBox
          label="Session PnL (closed)"
          value={`$${session.session_pnl.toFixed(2)}`}
          color={pnlColor}
        />
        <StatBox label="Closed trades" value={String(session.closed_trades)} />
      </div>

      <div className="grid grid-2 test-mode-stats">
        <StatBox label="Win rate" value={`${session.win_rate.toFixed(1)}%`} />
        <StatBox
          label="Profit factor"
          value={session.profit_factor > 0 ? session.profit_factor.toFixed(2) : "—"}
        />
      </div>
    </Card>
  );
}
