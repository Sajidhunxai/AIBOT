"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchApi, putApi } from "@/lib/api";

interface LeverageSettings {
  default: number;
  max_leverage: number;
  per_symbol: Record<string, number>;
  resolved_per_symbol: Record<string, number>;
  symbols: string[];
  mode: string;
  account_id?: number;
  account_name?: string;
}

export function LeverageSettingsPanel() {
  const [settings, setSettings] = useState<LeverageSettings | null>(null);
  const [defaultLev, setDefaultLev] = useState(10);
  const [perSymbol, setPerSymbol] = useState<Record<string, number>>({});
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"ok" | "error">("ok");

  const load = useCallback(async () => {
    try {
      const data = await fetchApi<LeverageSettings>("/leverage/settings");
      setSettings(data);
      setDefaultLev(data.default);
      setPerSymbol({ ...data.per_symbol });
    } catch {
      setSettings(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const onSwitch = () => {
      setLoading(true);
      void load();
    };
    window.addEventListener("account-switched", onSwitch);
    return () => window.removeEventListener("account-switched", onSwitch);
  }, [load]);

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    setMessage("");
    try {
      const payload: { default: number; per_symbol: Record<string, number> } = {
        default: defaultLev,
        per_symbol: {},
      };
      for (const symbol of settings.symbols) {
        const value = perSymbol[symbol] ?? defaultLev;
        if (value !== defaultLev) {
          payload.per_symbol[symbol] = value;
        }
      }
      const data = await putApi<LeverageSettings>("/leverage/settings", payload);
      setSettings(data);
      setDefaultLev(data.default);
      setPerSymbol({ ...data.per_symbol });
      setMessageType("ok");
      setMessage(
        settings.mode === "paper"
          ? "Leverage saved for this account (paper mode)."
          : "Leverage saved and applied on Binance.",
      );
      setOpen(false);
    } catch (e) {
      setMessageType("error");
      setMessage(e instanceof Error ? e.message : "Failed to save leverage");
    } finally {
      setSaving(false);
    }
  };

  if (loading && !settings) {
    return <div className="leverage-banner">Loading leverage settings…</div>;
  }

  if (!settings) return null;

  const maxLev = settings.max_leverage;
  const accountLabel = settings.account_name ? ` · ${settings.account_name}` : "";

  return (
    <>
      <div className="leverage-banner">
        <div className="leverage-banner-header">
          <div className="leverage-banner-title">
            Leverage{accountLabel}
          </div>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => setOpen(true)}>
            Edit leverage
          </button>
        </div>
        <div className="leverage-banner-grid">
          <span>Default: {settings.default}x</span>
          {settings.symbols.map((symbol) => (
            <span key={symbol}>
              {symbol}: {settings.resolved_per_symbol[symbol] ?? settings.default}x
            </span>
          ))}
        </div>
        {settings.mode !== "paper" && (
          <p className="risk-hint">
            On testnet/live, leverage is set on Binance per symbol when you save or start trading.
            All dashboard accounts share one testnet wallet — the last saved leverage applies on the exchange.
          </p>
        )}
        {message && !open && <p className={`trade-feedback ${messageType}`}>{message}</p>}
      </div>

      {open && (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-backdrop" onClick={() => setOpen(false)} aria-hidden="true" />
          <div className="modal-panel leverage-modal">
            <header className="modal-header">
              <div>
                <h2>Edit leverage{accountLabel}</h2>
                <p className="modal-subtitle">
                  Sets margin multiplier for new positions. Size still follows risk % and stop distance.
                </p>
              </div>
              <button type="button" className="modal-close" onClick={() => setOpen(false)} aria-label="Close">
                ×
              </button>
            </header>
            <div className="modal-body">
              <label className="risk-field" htmlFor="leverage_default">
                <span className="risk-field-label">Default leverage</span>
                <input
                  id="leverage_default"
                  type="number"
                  min={1}
                  max={maxLev}
                  value={defaultLev}
                  onChange={(e) => setDefaultLev(parseInt(e.target.value, 10) || 1)}
                />
                <span className="risk-field-hint">Used for symbols without an override (1–{maxLev}x).</span>
              </label>
              <div className="leverage-symbol-grid">
                {settings.symbols.map((symbol) => (
                  <label key={symbol} className="risk-field" htmlFor={`lev_${symbol}`}>
                    <span className="risk-field-label">{symbol}</span>
                    <input
                      id={`lev_${symbol}`}
                      type="number"
                      min={1}
                      max={maxLev}
                      value={perSymbol[symbol] ?? defaultLev}
                      onChange={(e) =>
                        setPerSymbol((prev) => ({
                          ...prev,
                          [symbol]: parseInt(e.target.value, 10) || 1,
                        }))
                      }
                    />
                  </label>
                ))}
              </div>
              <div className="risk-form-actions">
                <button type="button" className="btn btn-submit long" onClick={() => void save()} disabled={saving}>
                  {saving ? "Saving…" : "Save leverage"}
                </button>
              </div>
              {message && <p className={`trade-feedback ${messageType}`}>{message}</p>}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
