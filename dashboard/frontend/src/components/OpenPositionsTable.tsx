"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/Card";
import { fetchApi, postApi } from "@/lib/api";

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

const SYMBOL_FILTERS = ["ALL", "BTCUSDT", "ETHUSDT"] as const;

export function OpenPositionsTable({ initialPositions }: { initialPositions: Position[] }) {
  const router = useRouter();
  const [positions, setPositions] = useState(initialPositions);
  const [viewAccountName, setViewAccountName] = useState<string>("");
  const [viewAccountId, setViewAccountId] = useState<number | null>(null);
  const [showAllAccounts, setShowAllAccounts] = useState(false);
  const [filter, setFilter] = useState<(typeof SYMBOL_FILTERS)[number]>("ALL");
  const [closingId, setClosingId] = useState<string | null>(null);
  const [bulkAction, setBulkAction] = useState<"close-all" | null>(null);

  const loadContext = useCallback(async () => {
    try {
      const status = await fetchApi<{
        account?: { id: number; name: string };
      }>("/status");
      if (status.account) {
        setViewAccountId(status.account.id);
        setViewAccountName(status.account.name);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const loadPositions = useCallback(async () => {
    try {
      const query = showAllAccounts ? "?all_accounts=true" : "";
      const data = await fetchApi<Position[]>(`/positions${query}`);
      setPositions(data);
    } catch {
      /* keep last known list */
    }
  }, [showAllAccounts]);

  useEffect(() => {
    setPositions(initialPositions);
  }, [initialPositions]);

  useEffect(() => {
    void loadContext();
    void loadPositions();
    const interval = setInterval(() => {
      void loadContext();
      void loadPositions();
    }, 5000);
    const onUpdate = () => {
      void loadContext();
      void loadPositions();
    };
    window.addEventListener("trade-placed", onUpdate);
    window.addEventListener("account-switched", onUpdate);
    window.addEventListener("bot-status-changed", onUpdate);
    return () => {
      clearInterval(interval);
      window.removeEventListener("trade-placed", onUpdate);
      window.removeEventListener("account-switched", onUpdate);
      window.removeEventListener("bot-status-changed", onUpdate);
    };
  }, [loadContext, loadPositions]);

  const filtered = useMemo(() => {
    if (filter === "ALL") return positions;
    return positions.filter((p) => p.symbol === filter);
  }, [positions, filter]);

  const totalPnl = useMemo(
    () => filtered.reduce((sum, p) => sum + p.unrealized_pnl, 0),
    [filtered]
  );

  const closeAll = async () => {
    const label = showAllAccounts ? "all accounts" : viewAccountName || "this account";
    if (!confirm(`Close all open positions on ${label}?`)) return;
    setBulkAction("close-all");
    try {
      let totalClosed = 0;
      if (showAllAccounts) {
        const accounts = await fetchApi<{ id: number; name: string; is_trading: boolean }[]>(
          "/accounts"
        );
        const ids = [...new Set(positions.map((p) => p.account_id).filter(Boolean))] as number[];
        for (const id of ids) {
          try {
            const result = await postApi<{ closed: number }>("/controls/close", {
              close_all: true,
              account_id: id,
            });
            totalClosed += result.closed;
          } catch {
            /* skip empty */
          }
        }
      } else {
        const result = await postApi<{ closed: number; message: string }>("/controls/close-all");
        totalClosed = result.closed;
      }

      window.dispatchEvent(new CustomEvent("trade-placed"));
      router.refresh();
      await loadPositions();
      alert(`Closed ${totalClosed} position(s).`);
    } catch (e) {
      alert(`Close all failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    } finally {
      setBulkAction(null);
    }
  };

  const resumeRisk = async () => {
    try {
      await postApi("/controls/resume-risk");
      router.refresh();
    } catch (e) {
      alert(`Resume failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    }
  };

  const closePosition = async (position: Position) => {
    const key = position.id || position.symbol;
    setClosingId(key);
    try {
      const body: {
        position_id?: string;
        symbol?: string;
        account_id?: number;
      } = {};
      if (position.id) body.position_id = position.id;
      else body.symbol = position.symbol;
      if (position.account_id) body.account_id = position.account_id;
      else if (viewAccountId) body.account_id = viewAccountId;

      await postApi("/controls/close", body);
      window.dispatchEvent(new CustomEvent("trade-placed", { detail: { symbol: position.symbol } }));
      router.refresh();
      await loadPositions();
    } catch (e) {
      alert(`Close failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    } finally {
      setClosingId(null);
    }
  };

  if (positions.length === 0) {
    return (
      <p className="empty">
        No open positions
        {viewAccountName && !showAllAccounts ? ` on ${viewAccountName}` : ""}
      </p>
    );
  }

  return (
    <div className="positions-panel">
      <div className="positions-toolbar">
        <span className="positions-summary">
          <strong>{filtered.length}</strong> open
          {filter !== "ALL" ? ` ${filter}` : ""}
          {!showAllAccounts && viewAccountName ? ` · ${viewAccountName}` : ""}
          {" · "}
          Unrealized{" "}
          <span className={totalPnl >= 0 ? "pnl-positive" : "pnl-negative"}>
            ${totalPnl.toFixed(2)}
          </span>
        </span>
        <div className="tf-group">
          {SYMBOL_FILTERS.map((sym) => (
            <button
              key={sym}
              type="button"
              className={`tf-btn ${filter === sym ? "active" : ""}`}
              onClick={() => setFilter(sym)}
            >
              {sym === "ALL" ? "All" : sym.replace("USDT", "")}
            </button>
          ))}
          <button
            type="button"
            className={`tf-btn ${showAllAccounts ? "active" : ""}`}
            onClick={() => setShowAllAccounts((v) => !v)}
            title="Show positions from every running account"
          >
            {showAllAccounts ? "All accounts" : "This account"}
          </button>
          <button
            type="button"
            className="chart-nav-btn"
            onClick={() => void resumeRisk()}
            title="Clear risk halt after daily loss / drawdown"
          >
            Resume trading
          </button>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            onClick={() => void closeAll()}
            disabled={bulkAction === "close-all"}
          >
            {bulkAction === "close-all" ? "Closing…" : "Close all"}
          </button>
        </div>
      </div>

      <div className="table-scroll positions-scroll" role="region" aria-label="Open positions list">
        <table className="positions-table">
          <thead>
            <tr>
              {showAllAccounts && <th>Account</th>}
              <th>Symbol</th>
              <th>Side</th>
              <th>Qty</th>
              <th>Entry</th>
              <th>SL</th>
              <th>TP</th>
              <th>Unrealized PnL</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p, index) => {
              const rowKey = p.id || `${p.account_id}-${p.symbol}-${p.side}-${index}`;
              const isClosing = closingId === p.id || closingId === p.symbol;
              return (
                <tr key={rowKey}>
                  {showAllAccounts && <td className="account-cell">{p.account_name ?? "—"}</td>}
                  <td>{p.symbol}</td>
                  <td>
                    <Badge variant={p.side}>{p.side}</Badge>
                  </td>
                  <td>{p.quantity.toFixed(6)}</td>
                  <td>{p.entry_price.toFixed(2)}</td>
                  <td className="sl-cell">{p.stop_loss?.toFixed(2) ?? "—"}</td>
                  <td className="tp-cell">{p.take_profit?.toFixed(2) ?? "—"}</td>
                  <td className={p.unrealized_pnl >= 0 ? "pnl-positive" : "pnl-negative"}>
                    ${p.unrealized_pnl.toFixed(2)}
                  </td>
                  <td>
                    <button
                      type="button"
                      onClick={() => void closePosition(p)}
                      disabled={isClosing}
                      className="btn btn-danger btn-sm"
                    >
                      {isClosing ? "…" : "Close"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="positions-scroll-hint">
        Showing {showAllAccounts ? "all running accounts" : viewAccountName || "viewing account"}.
        Switch account in Trading Account panel to change view.
      </p>
    </div>
  );
}
