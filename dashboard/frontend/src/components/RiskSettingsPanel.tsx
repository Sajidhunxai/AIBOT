"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchApi, postApi, putApi } from "@/lib/api";
import { RiskGuideModal } from "@/components/RiskGuideModal";
import { RISK_FIELD_HELP, RISK_FIELD_IMPACT, RISK_IMPACT_LABELS, type RiskImpact } from "@/lib/riskFieldHelp";

interface RiskSettings {
  risk_per_trade_pct: number;
  max_concurrent_positions: number;
  max_positions_per_symbol: number;
  max_daily_loss_pct: number;
  max_drawdown_pct: number;
  max_unrealized_loss_pct: number;
  emergency_close_unrealized_loss_pct: number;
  max_total_exposure_pct: number;
  signal_cooldown_minutes: number;
  cooldown_after_loss_minutes: number;
  block_duplicate_side: boolean;
  use_equity_for_limits: boolean;
  atr_stop_multiplier: number;
  take_profit_rr: number;
  trailing_stop_atr_multiplier: number;
  break_even_trigger_rr: number;
  position_size_method: string;
  trading_halted: boolean;
  halt_reason: string;
  open_positions: number;
  account_id?: number;
  account_name?: string;
}

type RiskForm = Omit<RiskSettings, "trading_halted" | "halt_reason" | "open_positions">;

const DEFAULT_FORM: RiskForm = {
  risk_per_trade_pct: 1,
  max_concurrent_positions: 4,
  max_positions_per_symbol: 1,
  max_daily_loss_pct: 3,
  max_drawdown_pct: 10,
  max_unrealized_loss_pct: 5,
  emergency_close_unrealized_loss_pct: 8,
  max_total_exposure_pct: 40,
  signal_cooldown_minutes: 15,
  cooldown_after_loss_minutes: 30,
  block_duplicate_side: true,
  use_equity_for_limits: true,
  atr_stop_multiplier: 2,
  take_profit_rr: 2,
  trailing_stop_atr_multiplier: 1.5,
  break_even_trigger_rr: 1,
  position_size_method: "fixed_risk",
};

function toForm(data: RiskSettings): RiskForm {
  return {
    risk_per_trade_pct: data.risk_per_trade_pct,
    max_concurrent_positions: data.max_concurrent_positions,
    max_positions_per_symbol: data.max_positions_per_symbol,
    max_daily_loss_pct: data.max_daily_loss_pct,
    max_drawdown_pct: data.max_drawdown_pct,
    max_unrealized_loss_pct: data.max_unrealized_loss_pct,
    emergency_close_unrealized_loss_pct: data.emergency_close_unrealized_loss_pct,
    max_total_exposure_pct: data.max_total_exposure_pct,
    signal_cooldown_minutes: data.signal_cooldown_minutes,
    cooldown_after_loss_minutes: data.cooldown_after_loss_minutes,
    block_duplicate_side: data.block_duplicate_side,
    use_equity_for_limits: data.use_equity_for_limits,
    atr_stop_multiplier: data.atr_stop_multiplier,
    take_profit_rr: data.take_profit_rr,
    trailing_stop_atr_multiplier: data.trailing_stop_atr_multiplier,
    break_even_trigger_rr: data.break_even_trigger_rr,
    position_size_method: data.position_size_method,
  };
}

const RISK_HELP: Record<string, string> = {
  max_positions: "Maximum open trades at once on this account.",
  per_symbol: "Max open trades on one symbol.",
  daily_loss: "Blocks new trades if today's loss exceeds this % of equity.",
  unrealized: "Blocks new entries when floating loss exceeds this %.",
  emergency: "Auto-closes all positions when floating loss hits this %.",
  exposure: "Max position size as % of equity.",
};

function ImpactTag({ impact }: { impact: RiskImpact }) {
  return <span className={`risk-impact-tag risk-impact-tag-${impact}`}>{RISK_IMPACT_LABELS[impact]}</span>;
}

function Field({
  id,
  label,
  helpKey,
  children,
}: {
  id: string;
  label: string;
  helpKey: keyof typeof RISK_FIELD_HELP;
  children: React.ReactNode;
}) {
  const impact = RISK_FIELD_IMPACT[helpKey];
  return (
    <label htmlFor={id} className="risk-field">
      <span className="risk-field-label-row">
        <span className="risk-field-label">{label}</span>
        {impact && <ImpactTag impact={impact} />}
      </span>
      {children}
      <span className="risk-field-hint">{RISK_FIELD_HELP[helpKey]}</span>
    </label>
  );
}

function RiskEditForm({
  form,
  update,
  saving,
  halted,
  onSave,
  onResume,
}: {
  form: RiskForm;
  update: <K extends keyof RiskForm>(key: K, value: RiskForm[K]) => void;
  saving: boolean;
  halted: boolean;
  onSave: () => void;
  onResume: () => void;
}) {
  return (
    <>
      <div className="risk-form-grid">
        <Field id="risk_per_trade_pct" label="Risk per trade (%)" helpKey="risk_per_trade_pct">
          <input
            id="risk_per_trade_pct"
            type="number"
            step="0.1"
            value={form.risk_per_trade_pct}
            onChange={(e) => update("risk_per_trade_pct", parseFloat(e.target.value))}
          />
        </Field>
        <Field id="max_concurrent_positions" label="Max open positions" helpKey="max_concurrent_positions">
          <input
            id="max_concurrent_positions"
            type="number"
            min={1}
            value={form.max_concurrent_positions}
            onChange={(e) => update("max_concurrent_positions", parseInt(e.target.value, 10))}
          />
        </Field>
        <Field id="max_positions_per_symbol" label="Max per symbol" helpKey="max_positions_per_symbol">
          <input
            id="max_positions_per_symbol"
            type="number"
            min={1}
            value={form.max_positions_per_symbol}
            onChange={(e) => update("max_positions_per_symbol", parseInt(e.target.value, 10))}
          />
        </Field>
        <Field id="max_daily_loss_pct" label="Daily loss cap (%)" helpKey="max_daily_loss_pct">
          <input
            id="max_daily_loss_pct"
            type="number"
            step="0.5"
            value={form.max_daily_loss_pct}
            onChange={(e) => update("max_daily_loss_pct", parseFloat(e.target.value))}
          />
        </Field>
        <Field id="max_drawdown_pct" label="Max drawdown (%)" helpKey="max_drawdown_pct">
          <input
            id="max_drawdown_pct"
            type="number"
            step="0.5"
            value={form.max_drawdown_pct}
            onChange={(e) => update("max_drawdown_pct", parseFloat(e.target.value))}
          />
        </Field>
        <Field id="max_unrealized_loss_pct" label="Unrealized loss cap (%)" helpKey="max_unrealized_loss_pct">
          <input
            id="max_unrealized_loss_pct"
            type="number"
            step="0.5"
            value={form.max_unrealized_loss_pct}
            onChange={(e) => update("max_unrealized_loss_pct", parseFloat(e.target.value))}
          />
        </Field>
        <Field
          id="emergency_close_unrealized_loss_pct"
          label="Emergency close (%)"
          helpKey="emergency_close_unrealized_loss_pct"
        >
          <input
            id="emergency_close_unrealized_loss_pct"
            type="number"
            step="0.5"
            value={form.emergency_close_unrealized_loss_pct}
            onChange={(e) =>
              update("emergency_close_unrealized_loss_pct", parseFloat(e.target.value))
            }
          />
        </Field>
        <Field id="max_total_exposure_pct" label="Max exposure (%)" helpKey="max_total_exposure_pct">
          <input
            id="max_total_exposure_pct"
            type="number"
            step="1"
            value={form.max_total_exposure_pct}
            onChange={(e) => update("max_total_exposure_pct", parseFloat(e.target.value))}
          />
        </Field>
        <Field id="signal_cooldown_minutes" label="Signal cooldown (min)" helpKey="signal_cooldown_minutes">
          <input
            id="signal_cooldown_minutes"
            type="number"
            min={0}
            value={form.signal_cooldown_minutes}
            onChange={(e) => update("signal_cooldown_minutes", parseInt(e.target.value, 10))}
          />
        </Field>
        <Field
          id="cooldown_after_loss_minutes"
          label="Cooldown after loss (min)"
          helpKey="cooldown_after_loss_minutes"
        >
          <input
            id="cooldown_after_loss_minutes"
            type="number"
            min={0}
            value={form.cooldown_after_loss_minutes}
            onChange={(e) => update("cooldown_after_loss_minutes", parseInt(e.target.value, 10))}
          />
        </Field>
        <Field id="atr_stop_multiplier" label="ATR stop multiplier" helpKey="atr_stop_multiplier">
          <input
            id="atr_stop_multiplier"
            type="number"
            step="0.1"
            value={form.atr_stop_multiplier}
            onChange={(e) => update("atr_stop_multiplier", parseFloat(e.target.value))}
          />
        </Field>
        <Field id="take_profit_rr" label="Take profit R:R" helpKey="take_profit_rr">
          <input
            id="take_profit_rr"
            type="number"
            step="0.1"
            value={form.take_profit_rr}
            onChange={(e) => update("take_profit_rr", parseFloat(e.target.value))}
          />
        </Field>
        <Field
          id="trailing_stop_atr_multiplier"
          label="Trailing ATR mult."
          helpKey="trailing_stop_atr_multiplier"
        >
          <input
            id="trailing_stop_atr_multiplier"
            type="number"
            step="0.1"
            value={form.trailing_stop_atr_multiplier}
            onChange={(e) => update("trailing_stop_atr_multiplier", parseFloat(e.target.value))}
          />
        </Field>
        <Field id="break_even_trigger_rr" label="Break-even R:R" helpKey="break_even_trigger_rr">
          <input
            id="break_even_trigger_rr"
            type="number"
            step="0.1"
            value={form.break_even_trigger_rr}
            onChange={(e) => update("break_even_trigger_rr", parseFloat(e.target.value))}
          />
        </Field>
      </div>

      <div className="risk-form-checks">
        <label className="checkbox-label risk-field">
          <div className="risk-checkbox-row">
            <input
              type="checkbox"
              checked={form.block_duplicate_side}
              onChange={(e) => update("block_duplicate_side", e.target.checked)}
            />
            <span>Block duplicate side (no stacking LONG on LONG)</span>
            <ImpactTag impact="trades" />
          </div>
          <span className="risk-field-hint">{RISK_FIELD_HELP.block_duplicate_side}</span>
        </label>
        <label className="checkbox-label risk-field">
          <div className="risk-checkbox-row">
            <input
              type="checkbox"
              checked={form.use_equity_for_limits}
              onChange={(e) => update("use_equity_for_limits", e.target.checked)}
            />
            <span>Use equity (balance + open PnL) for loss limits</span>
            <ImpactTag impact="protect" />
          </div>
          <span className="risk-field-hint">{RISK_FIELD_HELP.use_equity_for_limits}</span>
        </label>
      </div>

      <div className="risk-form-actions">
        <button type="button" className="btn btn-submit long" onClick={onSave} disabled={saving}>
          {saving ? "Saving…" : "Save risk limits"}
        </button>
        {halted && (
          <button type="button" className="chart-nav-btn" onClick={onResume}>
            Resume trading
          </button>
        )}
      </div>
    </>
  );
}

export function RiskSettingsPanel() {
  const router = useRouter();
  const [status, setStatus] = useState<RiskSettings | null>(null);
  const [form, setForm] = useState<RiskForm>(DEFAULT_FORM);
  const [modalOpen, setModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"ok" | "error">("ok");

  const load = useCallback(async () => {
    try {
      const data = await fetchApi<RiskSettings>("/risk/settings");
      setStatus(data);
      setForm(toForm(data));
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = setInterval(load, 10000);
    const onAccountSwitched = () => {
      setLoading(true);
      void load();
    };
    window.addEventListener("account-switched", onAccountSwitched);
    return () => {
      clearInterval(interval);
      window.removeEventListener("account-switched", onAccountSwitched);
    };
  }, [load]);

  const update = <K extends keyof RiskForm>(key: K, value: RiskForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const save = async () => {
    setSaving(true);
    setMessage("");
    try {
      const data = await putApi<RiskSettings>("/risk/settings", form);
      setStatus(data);
      setForm(toForm(data));
      setMessageType("ok");
      setMessage("Risk limits saved for this account.");
      router.refresh();
    } catch (e) {
      setMessageType("error");
      setMessage(e instanceof Error ? e.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const resume = async () => {
    try {
      await postApi("/controls/resume-risk");
      await load();
      setMessageType("ok");
      setMessage("Trading resumed.");
    } catch (e) {
      setMessageType("error");
      setMessage(e instanceof Error ? e.message : "Resume failed");
    }
  };

  if (loading && !status) {
    return <div className="risk-banner">Loading risk settings…</div>;
  }

  const halted = status?.trading_halted;
  const open = status?.open_positions ?? 0;
  const maxOpen = status?.max_concurrent_positions ?? form.max_concurrent_positions;

  return (
    <>
      <div className={`risk-banner ${halted ? "risk-halted" : open >= maxOpen ? "risk-warn" : ""}`}>
        <div className="risk-banner-header">
          <div className="risk-banner-title">
            {halted ? "Trading halted" : "Risk protection"}
            {status?.account_name && (
              <span className="risk-account-tag"> · {status.account_name}</span>
            )}
            {status && (
              <span className="risk-open-count">
                · {open}/{maxOpen} positions open
              </span>
            )}
          </div>
          <div className="risk-banner-actions">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => setModalOpen(true)}
            >
              Guide &amp; edit limits
            </button>
          </div>
        </div>

        {status && (
          <div className="risk-banner-grid">
            <span title={RISK_HELP.max_positions}>Max positions: {status.max_concurrent_positions}</span>
            <span title={RISK_HELP.per_symbol}>Per symbol: {status.max_positions_per_symbol}</span>
            <span title={RISK_HELP.daily_loss}>Daily loss: {status.max_daily_loss_pct}%</span>
            <span title={RISK_HELP.unrealized}>Unrealized cap: {status.max_unrealized_loss_pct}%</span>
            <span title={RISK_HELP.emergency}>
              Emergency: {status.emergency_close_unrealized_loss_pct}%
            </span>
            <span title={RISK_HELP.exposure}>Exposure: {status.max_total_exposure_pct}%</span>
          </div>
        )}

        {halted && status?.halt_reason && (
          <p className="risk-halt-reason">Reason: {status.halt_reason.replace(/_/g, " ")}</p>
        )}
        {message && !modalOpen && <p className={`trade-feedback ${messageType}`}>{message}</p>}
        <p className="risk-hint">
          Click <strong>Guide &amp; edit limits</strong> to read explanations and change settings in a popup.
        </p>
      </div>

      <RiskGuideModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        accountName={status?.account_name}
      >
        <RiskEditForm
          form={form}
          update={update}
          saving={saving}
          halted={!!halted}
          onSave={() => void save()}
          onResume={() => void resume()}
        />
        {message && modalOpen && <p className={`trade-feedback ${messageType}`}>{message}</p>}
      </RiskGuideModal>
    </>
  );
}
