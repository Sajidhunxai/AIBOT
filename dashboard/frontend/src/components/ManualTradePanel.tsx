"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchApi, postApi } from "@/lib/api";

const SYMBOLS = ["BTCUSDT", "ETHUSDT"];
const QTY_STEP: Record<string, number> = {
  BTCUSDT: 0.0001,
  ETHUSDT: 0.001,
};

function floorToStep(value: number, step: number): number {
  if (step <= 0) return value;
  return Math.floor(value / step) * step;
}

function formatQty(value: number, step: number): string {
  const decimals = Math.max(0, -Math.floor(Math.log10(step)));
  return value.toFixed(decimals);
}

function buildPresets(symbol: string, maxQty: number): string[] {
  const step = QTY_STEP[symbol] ?? 0.001;
  const candidates =
    symbol === "BTCUSDT"
      ? [0.0001, 0.0002, 0.0005, 0.001, 0.005, 0.01]
      : [0.001, 0.01, 0.05, 0.1, 0.5];
  const within = candidates.filter((q) => q <= maxQty + step * 0.01);
  if (within.length > 0) {
    return within.slice(-4).map((q) => formatQty(q, step));
  }
  if (maxQty >= step) {
    return [formatQty(floorToStep(maxQty, step), step)];
  }
  return [];
}

type RiskSettings = {
  max_total_exposure_pct: number;
  use_equity_for_limits: boolean;
};

type StatusSnapshot = {
  equity: number;
  balance: number;
  account?: { current_balance?: number };
};

type PositionRow = {
  symbol: string;
  quantity: number;
  entry_price: number;
  account_id?: number;
};

export function ManualTradePanel() {
  const router = useRouter();
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [side, setSide] = useState<"LONG" | "SHORT">("LONG");
  const [quantity, setQuantity] = useState("0.001");
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const [autoSlTp, setAutoSlTp] = useState(true);
  const [price, setPrice] = useState(0);
  const [referenceCapital, setReferenceCapital] = useState(0);
  const [exposureCapPct, setExposureCapPct] = useState(40);
  const [openNotional, setOpenNotional] = useState(0);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"ok" | "error">("ok");

  const step = QTY_STEP[symbol] ?? 0.001;

  const maxAdditionalQty = useMemo(() => {
    if (price <= 0 || referenceCapital <= 0 || exposureCapPct <= 0) return 0;
    const capNotional = referenceCapital * (exposureCapPct / 100);
    const remaining = Math.max(0, capNotional - openNotional);
    return floorToStep(remaining / price, step);
  }, [price, referenceCapital, exposureCapPct, openNotional, step]);

  const qtyPresets = useMemo(
    () => buildPresets(symbol, maxAdditionalQty),
    [symbol, maxAdditionalQty],
  );

  const qtyNum = parseFloat(quantity) || 0;
  const tradeNotional = qtyNum * price;
  const projectedExposurePct =
    referenceCapital > 0 ? ((openNotional + tradeNotional) / referenceCapital) * 100 : 0;
  const overExposure = projectedExposurePct > exposureCapPct + 0.05;

  const loadContext = useCallback(
    async (resetQty = false) => {
      try {
        const [snap, status, risk, positions] = await Promise.all([
          fetchApi<{ price: number }>(`/market/snapshot?symbol=${symbol}`),
          fetchApi<StatusSnapshot>("/status"),
          fetchApi<RiskSettings>("/risk/settings"),
          fetchApi<PositionRow[]>("/positions"),
        ]);
        setPrice(snap.price);
        const capital = risk.use_equity_for_limits ? status.equity : status.balance;
        const ref =
          capital > 0 ? capital : status.account?.current_balance ?? status.balance;
        setReferenceCapital(ref);
        setExposureCapPct(risk.max_total_exposure_pct);
        const notional = positions
          .filter((p) => p.symbol === symbol)
          .reduce((sum, p) => sum + p.quantity * p.entry_price, 0);
        setOpenNotional(notional);

        if (resetQty && snap.price > 0 && ref > 0 && risk.max_total_exposure_pct > 0) {
          const capNotional = ref * (risk.max_total_exposure_pct / 100);
          const remaining = Math.max(0, capNotional - notional);
          const maxQty = floorToStep(remaining / snap.price, step);
          if (maxQty > 0) {
            const target = Math.min(maxQty, symbol === "BTCUSDT" ? 0.001 : 0.01);
            setQuantity(formatQty(target > 0 ? target : maxQty, step));
          }
        }
      } catch {
        setPrice(0);
      }
    },
    [symbol, step],
  );

  useEffect(() => {
    void loadContext(true);
    const onSwitch = () => void loadContext(true);
    window.addEventListener("account-switched", onSwitch);
    return () => window.removeEventListener("account-switched", onSwitch);
  }, [loadContext]);

  useEffect(() => {
    const id = window.setInterval(() => void loadContext(false), 15000);
    return () => window.clearInterval(id);
  }, [loadContext]);

  const applyPct = (field: "sl" | "tp", pct: number) => {
    if (price <= 0) return;
    const isLong = side === "LONG";
    if (field === "sl") {
      const sl = isLong ? price * (1 - pct / 100) : price * (1 + pct / 100);
      setStopLoss(sl.toFixed(2));
      setAutoSlTp(false);
    } else {
      const tp = isLong ? price * (1 + pct / 100) : price * (1 - pct / 100);
      setTakeProfit(tp.toFixed(2));
      setAutoSlTp(false);
    }
  };

  const submit = async () => {
    setLoading(true);
    setMessage("");
    try {
      const result = await postApi<{
        message: string;
        stop_loss: number;
        take_profit: number;
      }>("/controls/trade", {
        symbol,
        side: side === "LONG" ? "BUY" : "SELL",
        quantity: parseFloat(quantity),
        order_type: "MARKET",
        stop_loss: stopLoss ? parseFloat(stopLoss) : null,
        take_profit: takeProfit ? parseFloat(takeProfit) : null,
        auto_sl_tp: autoSlTp,
      });
      setMessageType("ok");
      setMessage(result.message);
      window.dispatchEvent(new CustomEvent("trade-placed", { detail: { symbol } }));
      router.refresh();
      setTimeout(() => setMessage(""), 4000);
    } catch (e) {
      setMessageType("error");
      setMessage(e instanceof Error ? e.message : "Trade failed");
    } finally {
      setLoading(false);
    }
  };

  const slPreview =
    autoSlTp && price > 0
      ? side === "LONG"
        ? `Auto (~${(price * 0.98).toFixed(0)})`
        : `Auto (~${(price * 1.02).toFixed(0)})`
      : stopLoss || "—";

  const tpPreview =
    autoSlTp && price > 0
      ? side === "LONG"
        ? `Auto (~${(price * 1.04).toFixed(0)})`
        : `Auto (~${(price * 0.96).toFixed(0)})`
      : takeProfit || "—";

  return (
    <div className="manual-trade">
      <div className="manual-trade-grid">
        {/* Symbol & price */}
        <div className="trade-field">
          <label>Symbol</label>
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            {SYMBOLS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          {price > 0 && (
            <span className="field-hint">
              Mark price: <strong>${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong>
            </span>
          )}
        </div>

        {/* Side toggle */}
        <div className="trade-field">
          <label>Direction</label>
          <div className="side-toggle">
            <button
              type="button"
              className={`side-btn long ${side === "LONG" ? "active" : ""}`}
              onClick={() => setSide("LONG")}
            >
              LONG ▲
            </button>
            <button
              type="button"
              className={`side-btn short ${side === "SHORT" ? "active" : ""}`}
              onClick={() => setSide("SHORT")}
            >
              SHORT ▼
            </button>
          </div>
        </div>

        {/* Quantity */}
        <div className="trade-field">
          <label>Quantity</label>
          <input
            type="number"
            step={step}
            min="0"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
          />
          {referenceCapital > 0 && price > 0 && (
            <span className={`field-hint ${overExposure ? "field-hint-warn" : ""}`}>
              Exposure: {projectedExposurePct.toFixed(1)}% / {exposureCapPct}% cap
              {maxAdditionalQty > 0 && ` · max qty ~${formatQty(maxAdditionalQty, step)}`}
            </span>
          )}
          <div className="preset-row">
            {qtyPresets.map((q) => (
              <button key={q} type="button" className="preset-btn" onClick={() => setQuantity(q)}>
                {q}
              </button>
            ))}
            {maxAdditionalQty > 0 && (
              <button
                type="button"
                className="preset-btn"
                onClick={() => setQuantity(formatQty(maxAdditionalQty, step))}
              >
                max
              </button>
            )}
          </div>
        </div>

        {/* Stop Loss */}
        <div className="trade-field">
          <label>Stop Loss</label>
          <input
            type="number"
            step="0.01"
            placeholder={autoSlTp ? "Auto (ATR-based)" : "Price"}
            value={stopLoss}
            onChange={(e) => {
              setStopLoss(e.target.value);
              setAutoSlTp(false);
            }}
            disabled={autoSlTp}
          />
          <div className="preset-row">
            {[1, 2, 3].map((p) => (
              <button key={p} type="button" className="preset-btn sl" onClick={() => applyPct("sl", p)}>
                -{p}%
              </button>
            ))}
          </div>
        </div>

        {/* Take Profit */}
        <div className="trade-field">
          <label>Take Profit</label>
          <input
            type="number"
            step="0.01"
            placeholder={autoSlTp ? "Auto (ATR-based)" : "Price"}
            value={takeProfit}
            onChange={(e) => {
              setTakeProfit(e.target.value);
              setAutoSlTp(false);
            }}
            disabled={autoSlTp}
          />
          <div className="preset-row">
            {[2, 4, 6].map((p) => (
              <button key={p} type="button" className="preset-btn tp" onClick={() => applyPct("tp", p)}>
                +{p}%
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="trade-options">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={autoSlTp}
            onChange={(e) => {
              setAutoSlTp(e.target.checked);
              if (e.target.checked) {
                setStopLoss("");
                setTakeProfit("");
              }
            }}
          />
          Auto SL/TP (ATR-based risk rules)
        </label>
        <div className="trade-summary">
          <span>SL: {slPreview}</span>
          <span>TP: {tpPreview}</span>
        </div>
      </div>

      <button
        type="button"
        onClick={submit}
        disabled={loading || !quantity || qtyNum <= 0 || overExposure}
        className={`btn btn-submit ${side === "LONG" ? "long" : "short"}`}
      >
        {loading ? "Placing…" : overExposure ? "Exposure too high" : `${side} ${symbol}`}
      </button>

      {message && (
        <p className={`trade-feedback ${messageType}`}>{message}</p>
      )}
    </div>
  );
}
