"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchApi, postApi, putApi } from "@/lib/api";

interface Account {
  id: number;
  name: string;
  account_type: string;
  paper_balance: number;
  current_balance: number;
  is_active: boolean;
  is_trading: boolean;
  notes: string | null;
}

export function AccountPanel() {
  const router = useRouter();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<"demo" | "live">("demo");
  const [newBalance, setNewBalance] = useState("10000");
  const [customBalance, setCustomBalance] = useState("10000");
  const [resetBalance, setResetBalance] = useState("");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"ok" | "error">("ok");
  const [tradingMode, setTradingMode] = useState<"paper" | "testnet" | "live">("paper");

  const load = useCallback(async () => {
    try {
      const [status, list] = await Promise.all([
        fetchApi<{ running_accounts?: { id: number }[]; mode?: string }>("/status"),
        fetchApi<Account[]>("/accounts"),
      ]);
      setTradingMode((status.mode as "paper" | "testnet" | "live") ?? "paper");
      const runningIds = new Set(status.running_accounts?.map((a) => a.id) ?? []);
      const merged = list.map((a) => ({
        ...a,
        is_trading: a.is_trading || runningIds.has(a.id),
      }));
      setAccounts(merged);
      const active = merged.find((a) => a.is_active);
      setActiveId(active?.id ?? merged[0]?.id ?? null);
      if (active) setCustomBalance(String(active.current_balance ?? active.paper_balance));
    } catch {
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = setInterval(() => void load(), 5000);
    const refresh = () => void load();
    window.addEventListener("account-switched", refresh);
    window.addEventListener("bot-status-changed", refresh);
    return () => {
      clearInterval(interval);
      window.removeEventListener("account-switched", refresh);
      window.removeEventListener("bot-status-changed", refresh);
    };
  }, [load]);

  const showMsg = (text: string, type: "ok" | "error" = "ok") => {
    setMessageType(type);
    setMessage(text);
    setTimeout(() => setMessage(""), 5000);
  };

  const createAccount = async () => {
    if (!newName.trim()) return;
    try {
      await postApi("/accounts", {
        name: newName.trim(),
        account_type: newType,
        paper_balance: newType === "demo" ? parseFloat(newBalance) : undefined,
      });
      setNewName("");
      await load();
      router.refresh();
      showMsg(`Account "${newName}" created.`);
    } catch (e) {
      showMsg(e instanceof Error ? e.message : "Create failed", "error");
    }
  };

  const switchAccount = async (id: number, start = false) => {
    try {
      const result = await postApi<{
        message: string;
        started: boolean;
        running: boolean;
      }>(`/accounts/${id}/activate`, { start });
      setActiveId(id);
      await load();
      router.refresh();
      if (result.started) {
        window.dispatchEvent(new CustomEvent("trade-placed"));
      }
      window.dispatchEvent(new CustomEvent("account-switched"));
      window.dispatchEvent(new CustomEvent("bot-status-changed"));
      showMsg(result.message, "ok");
    } catch (e) {
      showMsg(e instanceof Error ? e.message : "Switch failed", "error");
    }
  };

  const toggleTrading = async (id: number, isTrading: boolean) => {
    if (isTrading) {
      await stopAccount(id);
    } else {
      await switchAccount(id, true);
    }
  };

  const stopAccount = async (id: number) => {
    try {
      const result = await postApi<{ message: string }>(`/accounts/${id}/stop`);
      await load();
      router.refresh();
      window.dispatchEvent(new CustomEvent("account-switched"));
      window.dispatchEvent(new CustomEvent("bot-status-changed"));
      showMsg(result.message, "ok");
    } catch (e) {
      showMsg(e instanceof Error ? e.message : "Stop failed", "error");
    }
  };

  const applyBalance = async () => {
    if (!activeId) return;
    const bal = parseFloat(customBalance);
    if (!bal || bal <= 0) return;
    try {
      await putApi(`/accounts/${activeId}/balance`, { balance: bal });
      await load();
      router.refresh();
      showMsg(`Demo balance set to $${bal.toLocaleString()}.`);
    } catch (e) {
      showMsg(e instanceof Error ? e.message : "Balance update failed", "error");
    }
  };

  const resetDemo = async () => {
    if (!activeId) return;
    const active = accounts.find((a) => a.id === activeId);
    if (!active || active.account_type !== "demo") {
      showMsg("Only demo accounts can be reset.", "error");
      return;
    }
    if (
      !confirm(
        "Reset this demo account? Clears open positions, trade history, and signals."
      )
    ) {
      return;
    }
    try {
      const bal = resetBalance ? parseFloat(resetBalance) : undefined;
      const result = await postApi<{ message: string }>(`/accounts/${activeId}/reset-demo`, {
        balance: bal,
        clear_history: true,
        close_positions: true,
      });
      await load();
      router.refresh();
      window.dispatchEvent(new CustomEvent("trade-placed"));
      showMsg(result.message);
    } catch (e) {
      showMsg(e instanceof Error ? e.message : "Reset failed", "error");
    }
  };

  const active = accounts.find((a) => a.id === activeId);

  if (loading) {
    return <div className="account-panel">Loading accounts…</div>;
  }

  return (
    <div className="account-panel">
      <div className="account-panel-header">
        <h3>Trading account</h3>
        <p className="account-hint">
          {tradingMode === "paper" ? (
            <>
              Run <strong>multiple accounts in parallel</strong>. Switch &amp; Start adds trading on
              the selected account without stopping others. Each account keeps its own balance and
              risk limits.
            </>
          ) : (
            <>
              <strong>{tradingMode.toUpperCase()} mode</strong> — balance is fetched live from your
              Binance Futures wallet (shared across dashboard profiles). Risk and strategy settings
              remain per account.
            </>
          )}
        </p>
      </div>

      <div className="account-row">
        <label>
          View / focus account
          <select
            value={activeId ?? ""}
            onChange={(e) => void switchAccount(parseInt(e.target.value, 10), false)}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({a.account_type.toUpperCase()})
                {a.is_trading ? " · trading" : ""}
                {a.is_active ? " · viewing" : ""}
              </option>
            ))}
          </select>
        </label>
        {active && (
          <>
            <span className="account-balance-badge">
              {tradingMode === "paper"
                ? `$${(active.current_balance ?? active.paper_balance).toLocaleString()} demo`
                : `$${(active.current_balance ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })} Binance ${tradingMode}`}
            </span>
            <button
              type="button"
              className={`btn btn-sm ${active.is_trading ? "btn-danger" : "btn-primary"}`}
              onClick={() => void toggleTrading(active.id, active.is_trading)}
            >
              {active.is_trading ? "Stop" : "Start"}
            </button>
          </>
        )}
      </div>

      <div className="account-list">
        <h4>Start / stop each account</h4>
        <p className="account-hint">
          Each row runs independently. <strong>Stop</strong> halts auto-trading for that account only.
          Use <strong>Guide &amp; edit limits</strong> on the risk banner for help.
        </p>
        <ul className="account-list-rows">
          {accounts.map((a) => (
            <li key={a.id} className={`account-list-item ${a.is_active ? "active" : ""}`}>
              <div className="account-list-meta">
                <strong>{a.name}</strong>
                <span className="account-list-type">{a.account_type}</span>
                {a.is_trading && <span className="account-list-badge trading">trading</span>}
                {a.is_active && <span className="account-list-badge viewing">viewing</span>}
                {(tradingMode === "paper" ? a.account_type === "demo" : true) && (
                  <span className="account-list-balance">
                    ${(a.current_balance ?? a.paper_balance).toLocaleString(undefined, {
                      minimumFractionDigits: tradingMode === "paper" ? 0 : 2,
                    })}
                    {tradingMode !== "paper" ? ` ${tradingMode}` : ""}
                  </span>
                )}
              </div>
              <div className="account-list-actions">
                {!a.is_active && (
                  <button
                    type="button"
                    className="chart-nav-btn"
                    onClick={() => void switchAccount(a.id, false)}
                  >
                    View
                  </button>
                )}
                <button
                  type="button"
                  className={`btn btn-sm ${a.is_trading ? "btn-danger" : "btn-primary"}`}
                  onClick={() => void toggleTrading(a.id, a.is_trading)}
                >
                  {a.is_trading ? "Stop" : "Start"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {active?.account_type === "demo" && tradingMode === "paper" && (
        <div className="account-row">
          <label>
            Custom demo balance (USDT)
            <input
              type="number"
              min={100}
              step={100}
              value={customBalance}
              onChange={(e) => setCustomBalance(e.target.value)}
            />
          </label>
          <button type="button" className="chart-nav-btn" onClick={() => void applyBalance()}>
            Set balance
          </button>
        </div>
      )}

      <div className="account-row account-reset-row">
        <label>
          Reset balance (optional)
          <input
            type="number"
            placeholder="Keep current"
            value={resetBalance}
            onChange={(e) => setResetBalance(e.target.value)}
          />
        </label>
        <button type="button" className="btn btn-danger btn-sm" onClick={() => void resetDemo()}>
          Clean demo data
        </button>
      </div>

      <div className="account-create">
        <h4>Create account</h4>
        <div className="account-create-grid">
          <input
            type="text"
            placeholder="Account name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <select value={newType} onChange={(e) => setNewType(e.target.value as "demo" | "live")}>
            <option value="demo">Demo (paper)</option>
            <option value="live">Live (real)</option>
          </select>
          {newType === "demo" && (
            <input
              type="number"
              min={100}
              value={newBalance}
              onChange={(e) => setNewBalance(e.target.value)}
              placeholder="Starting balance"
            />
          )}
          <button type="button" className="btn btn-submit long" onClick={() => void createAccount()}>
            Create
          </button>
        </div>
      </div>

      {message && <p className={`trade-feedback ${messageType}`}>{message}</p>}
    </div>
  );
}
