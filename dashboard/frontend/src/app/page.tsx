import { Card, Badge } from "@/components/Card";
import { BotControls } from "@/components/BotControls";
import { AccountPanel } from "@/components/AccountPanel";
import { OpenPositionsTable } from "@/components/OpenPositionsTable";
import { RiskSettingsPanel } from "@/components/RiskSettingsPanel";
import { LeverageSettingsPanel } from "@/components/LeverageSettingsPanel";
import { StrategySettingsPanel } from "@/components/StrategySettingsPanel";
import { AccountDashboardPanel } from "@/components/AccountDashboardPanel";
import { TestModePanel } from "@/components/TestModePanel";
import { ManualTradePanel } from "@/components/ManualTradePanel";
import { TradingChart } from "@/components/TradingChart";
import { fetchApi } from "@/lib/api";

interface BotStatus {
  running: boolean;
  mode: string;
  balance: number;
  symbols: string[];
  strategies: string[];
  open_positions: number;
  account?: { name: string };
  running_accounts?: { id: number; name: string }[];
}

interface Position {
  id: string;
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  unrealized_pnl: number;
  stop_loss?: number | null;
  take_profit?: number | null;
  strategy: string;
  account_id?: number | null;
  account_name?: string | null;
}

interface LogEntry {
  id: number;
  level: string;
  logger_name: string;
  message: string;
}

async function getDashboardData() {
  try {
    const [status, positions, logs] = await Promise.all([
      fetchApi<BotStatus>("/status"),
      fetchApi<Position[]>("/positions"),
      fetchApi<LogEntry[]>("/logs?limit=30"),
    ]);
    return { status, positions, logs, error: null };
  } catch (e) {
    return {
      status: null,
      positions: [],
      logs: [],
      error: e instanceof Error ? e.message : "Failed to connect to API",
    };
  }
}

export default async function DashboardPage() {
  const { status, positions, logs, error } = await getDashboardData();

  return (
    <>
      <div className="dashboard-header">
        <h1>Trading Dashboard</h1>
        {status && (
          <div className="header-status">
            <div>
              <span className={`status-dot ${status.running ? "running" : "stopped"}`} />
              {status.running ? "Running" : "Stopped"} &middot; {status.mode.toUpperCase()}
              {status.running_accounts && status.running_accounts.length > 0 ? (
                <> - {status.running_accounts.map((a) => a.name).join(", ")}</>
              ) : status.account?.name ? (
                ` - ${status.account.name}`
              ) : (
                ""
              )}
            </div>
            <BotControls running={status.running} />
          </div>
        )}
      </div>

      {error && (
        <Card title="Connection Error">
          <p className="empty">{error} — Start the API with: python -m core.main api</p>
        </Card>
      )}

      <Card title="Trading Account" className="account-card">
        <AccountPanel />
      </Card>

      <RiskSettingsPanel />

      <LeverageSettingsPanel />

      <StrategySettingsPanel />

      <AccountDashboardPanel />

      <TestModePanel />

      <Card title="Live Chart — TradingView / Bot (PKT)" className="chart-card">
        <TradingChart
          symbols={status?.symbols ?? ["BTCUSDT", "ETHUSDT"]}
          positions={positions}
          defaultSymbol={status?.symbols?.[0] ?? "BTCUSDT"}
        />
      </Card>

      <div className="grid grid-2" style={{ marginBottom: "1.5rem" }}>
        <Card title={`Open Positions${status?.account?.name ? ` · ${status.account.name}` : ""}`}>
          <OpenPositionsTable initialPositions={positions} />
        </Card>

        <Card title="Logs">
          <div style={{ maxHeight: 320, overflowY: "auto" }}>
            {logs.length > 0 ? (
              logs.map((l) => (
                <div
                  key={l.id}
                  className={`log-entry log-${l.level.toLowerCase()}`}
                >
                  [{l.level}] {l.message}
                </div>
              ))
            ) : (
              <p className="empty">No logs available</p>
            )}
          </div>
        </Card>
      </div>

      <Card title="Quick Trade — Manual Entry">
        <ManualTradePanel />
      </Card>
    </>
  );
}
