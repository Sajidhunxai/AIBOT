"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchApi, putApi } from "@/lib/api";
import {
  EMA_CROSS_GUIDE,
  STRATEGY_FIELDS,
  STRATEGY_GUIDES,
  STRATEGY_META,
  type StrategyFieldDef,
} from "@/lib/strategyFieldHelp";

type StrategiesData = {
  primary_timeframe: string;
  active_strategies: string[];
  strategies: Record<string, Record<string, unknown>>;
  account_id?: number | null;
  account_name?: string | null;
};

export function StrategySettingsPanel() {
  const [data, setData] = useState<StrategiesData | null>(null);
  const [form, setForm] = useState<Record<string, Record<string, unknown>>>({});
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<string | null>("ema_cross_rsi");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"ok" | "error">("ok");

  const load = useCallback(async () => {
    try {
      const res = await fetchApi<StrategiesData>("/strategies/settings");
      setData(res);
      setForm(JSON.parse(JSON.stringify(res.strategies)) as Record<string, Record<string, unknown>>);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const onAccountSwitched = () => {
      setLoading(true);
      void load();
    };
    window.addEventListener("account-switched", onAccountSwitched);
    return () => window.removeEventListener("account-switched", onAccountSwitched);
  }, [load]);

  const updateField = (strategy: string, key: string, value: unknown) => {
    setForm((prev) => ({
      ...prev,
      [strategy]: { ...prev[strategy], [key]: value },
    }));
  };

  const save = async () => {
    setSaving(true);
    setMessage("");
    try {
      const res = await putApi<StrategiesData>("/strategies/settings", { strategies: form });
      setData(res);
      setForm(JSON.parse(JSON.stringify(res.strategies)) as Record<string, Record<string, unknown>>);
      setMessageType("ok");
      setMessage("Strategy settings saved for this account — active on next signal scan.");
    } catch (e) {
      setMessageType("error");
      setMessage(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const renderField = (strategy: string, field: StrategyFieldDef) => {
    const value = form[strategy]?.[field.key];
    const hintTitle = field.helpDetail ? `${field.help}\n\n${field.helpDetail}` : field.help;
    if (field.type === "boolean") {
      return (
        <label key={field.key} className="checkbox-label risk-field">
          <div className="risk-checkbox-row">
            <input
              type="checkbox"
              checked={Boolean(value)}
              onChange={(e) => updateField(strategy, field.key, e.target.checked)}
            />
            <span title={hintTitle}>{field.label}</span>
          </div>
          <span className="risk-field-hint">{field.help}</span>
          {field.helpDetail && <p className="risk-field-detail">{field.helpDetail}</p>}
        </label>
      );
    }
    if (field.type === "select") {
      return (
        <label key={field.key} className="risk-field">
          <span className="risk-field-label" title={hintTitle}>
            {field.label}
          </span>
          <select
            value={String(value ?? field.options?.[0] ?? "")}
            onChange={(e) => updateField(strategy, field.key, e.target.value)}
          >
            {(field.options ?? []).map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
          <span className="risk-field-hint">{field.help}</span>
          {field.helpDetail && <p className="risk-field-detail">{field.helpDetail}</p>}
        </label>
      );
    }
    return (
      <label key={field.key} className="risk-field">
        <span className="risk-field-label" title={hintTitle}>
          {field.label}
        </span>
        <input
          type="number"
          step={field.step ?? 1}
          min={field.min}
          value={Number(value ?? 0)}
          onChange={(e) => updateField(strategy, field.key, parseFloat(e.target.value))}
        />
        <span className="risk-field-hint">{field.help}</span>
        {field.helpDetail && <p className="risk-field-detail">{field.helpDetail}</p>}
      </label>
    );
  };

  const renderStrategyGuide = (name: string) => {
    const guide = STRATEGY_GUIDES[name];
    if (!guide) return null;
    return (
      <div className="strategy-inline-guide">
        <p>{guide.summary}</p>
        <p><strong>LONG when:</strong></p>
        <ul className="risk-modal-list">
          {guide.longWhen.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <p><strong>SHORT when:</strong></p>
        <ul className="risk-modal-list">
          {guide.shortWhen.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        {guide.tuningTips.length > 0 && (
          <>
            <p><strong>Tuning tips:</strong></p>
            <ul className="risk-modal-list">
              {guide.tuningTips.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </>
        )}
        {guide.note && <p className="risk-modal-note">{guide.note}</p>}
      </div>
    );
  };

  if (loading && !data) {
    return <div className="risk-banner">Loading strategy settings…</div>;
  }

  const active = data?.active_strategies ?? [];

  return (
    <>
      <div className="risk-banner strategy-banner">
        <div className="risk-banner-header">
          <div className="risk-banner-title">
            Auto-trade strategies
            {data?.account_name && (
              <span className="risk-account-tag"> · {data.account_name}</span>
            )}
            <span className="risk-open-count">
              · {active.length} active on {data?.primary_timeframe ?? "15m"}
            </span>
          </div>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => setOpen(true)}>
            Strategy settings
          </button>
        </div>
        <div className="risk-banner-grid">
          {Object.keys(STRATEGY_META).map((name) => (
            <span key={name} title={STRATEGY_META[name].summary}>
              {STRATEGY_META[name].title}: {active.includes(name) ? "ON" : "off"}
            </span>
          ))}
        </div>
        <p className="risk-hint">
          Per-account strategy settings (like risk). Switch account to edit another profile — saved to{" "}
          <code>{"data/accounts/{id}_strategy.json"}</code>.
        </p>
      </div>

      {open && (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-backdrop" onClick={() => setOpen(false)} aria-hidden="true" />
          <div className="modal-panel risk-modal">
            <header className="modal-header">
              <div>
                <h2>Strategy settings</h2>
                <p className="modal-subtitle">
                  {data?.account_name ? (
                    <>
                      Account: <strong>{data.account_name}</strong>
                      {" · "}
                    </>
                  ) : null}
                  Primary timeframe: <strong>{data?.primary_timeframe}</strong> — strategies run on candle close
                </p>
              </div>
              <button type="button" className="modal-close" onClick={() => setOpen(false)} aria-label="Close">
                ✕
              </button>
            </header>
            <div className="modal-body risk-modal-body">
              <section className="risk-modal-guide">
                <h3>EMA Cross + RSI — how signals are decided</h3>
                <p>{STRATEGY_META.ema_cross_rsi.summary}</p>
                <p><strong>LONG when:</strong></p>
                <ul className="risk-modal-list">
                  {EMA_CROSS_GUIDE.longRules.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
                <p><strong>SHORT when:</strong></p>
                <ul className="risk-modal-list">
                  {EMA_CROSS_GUIDE.shortRules.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
                <p className="risk-modal-note">{EMA_CROSS_GUIDE.stops}</p>
              </section>

              {Object.keys(STRATEGY_META).map((name) => {
                const meta = STRATEGY_META[name];
                const fields = STRATEGY_FIELDS[name] ?? [];
                const isOpen = expanded === name;
                const enabled = Boolean(form[name]?.enabled);
                return (
                  <section key={name} className="strategy-settings-section">
                    <button
                      type="button"
                      className="strategy-section-toggle"
                      onClick={() => setExpanded(isOpen ? null : name)}
                    >
                      <span>
                        {meta.title} <span className={enabled ? "strat-on" : "strat-off"}>{enabled ? "ON" : "off"}</span>
                      </span>
                      <span>{isOpen ? "▲" : "▼"}</span>
                    </button>
                    {isOpen && (
                      <div className="strategy-section-body">
                        <p className="risk-modal-intro">{meta.summary}</p>
                        {renderStrategyGuide(name)}
                        <div className="risk-form-grid">{fields.map((f) => renderField(name, f))}</div>
                      </div>
                    )}
                  </section>
                );
              })}

              <div className="risk-form-actions">
                <button type="button" className="btn btn-submit long" onClick={() => void save()} disabled={saving}>
                  {saving ? "Saving…" : "Save strategy settings"}
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
