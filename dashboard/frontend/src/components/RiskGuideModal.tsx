"use client";

import { useEffect } from "react";
import { RISK_GLOSSARY, RISK_PNL_TABLE, RISK_SAVE_NOTE, RISK_TRADES_TABLE } from "@/lib/riskFieldHelp";

interface RiskGuideModalProps {
  open: boolean;
  onClose: () => void;
  accountName?: string;
  children: React.ReactNode;
}

export function RiskGuideModal({ open, onClose, accountName, children }: RiskGuideModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="risk-modal-title">
      <div className="modal-backdrop" onClick={onClose} aria-hidden="true" />
      <div className="modal-panel risk-modal">
        <header className="modal-header">
          <div>
            <h2 id="risk-modal-title">Risk protection guide</h2>
            {accountName && (
              <p className="modal-subtitle">Settings for: <strong>{accountName}</strong></p>
            )}
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        <div className="modal-body risk-modal-body">
          <section className="risk-modal-guide">
            <h3>What the banner means</h3>
            <p>
              Example: <em>Risk protection · Demo Practice · 1/22 positions open</em>
            </p>
            <ul className="risk-modal-list">
              <li>
                <strong>Account name</strong> — limits apply to the account you are viewing.
                Switch accounts in the panel below to edit another profile.
              </li>
              <li>
                <strong>1/22 positions</strong> — one open trade, maximum 22 allowed at once
                on this account.
              </li>
            </ul>

            <h3>Quick limits</h3>
            <table className="risk-modal-table">
              <thead>
                <tr>
                  <th>Label</th>
                  <th>What it does</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Max positions</td>
                  <td>Total open trades allowed at once (all symbols).</td>
                </tr>
                <tr>
                  <td>Per symbol</td>
                  <td>Max open trades on one pair (e.g. only 1 BTCUSDT).</td>
                </tr>
                <tr>
                  <td>Daily loss %</td>
                  <td>Blocks new trades if today&apos;s loss (closed + floating) exceeds this % of equity.</td>
                </tr>
                <tr>
                  <td>Unrealized cap %</td>
                  <td>Blocks new entries when floating loss is too large. Open trades stay open.</td>
                </tr>
                <tr>
                  <td>Emergency %</td>
                  <td>Auto-closes all positions on this account when floating loss hits this level.</td>
                </tr>
                <tr>
                  <td>Exposure %</td>
                  <td>
                    Max position size as % of equity. On $100 at 40% → ~$40 max (~0.0006 BTC).
                    Raise this for small accounts if manual trades are blocked.
                  </td>
                </tr>
              </tbody>
            </table>

            <h3>Start / stop accounts</h3>
            <ul className="risk-modal-list">
              <li>
                <strong>Start</strong> — auto-trading on that account only (others can run in parallel).
              </li>
              <li>
                <strong>Stop</strong> — stops auto-trading for that account only.
              </li>
              <li>
                <strong>Stop All Accounts</strong> — stops every account and the engine.
              </li>
            </ul>
            <p className="risk-modal-note">
              After an API restart, all accounts stop — press Start again for each account you want.
            </p>

            <h3>Glossary (R:R, ATR, etc.)</h3>
            <table className="risk-modal-table">
              <thead>
                <tr>
                  <th>Term</th>
                  <th>Meaning</th>
                </tr>
              </thead>
              <tbody>
                {RISK_GLOSSARY.map((row) => (
                  <tr key={row.term}>
                    <td><strong>{row.term}</strong></td>
                    <td>{row.meaning}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="risk-modal-note">
              <strong>Your settings example:</strong> Take profit R:R <em>2</em> with ATR stop <em>2</em> means
              stop is 2× ATR away, target is twice that distance (4× ATR). Break-even R:R <em>1</em> moves
              stop to entry after price moves one stop-distance in profit.
            </p>

            <div className="risk-impact-callout">
              <strong>Does saving these limits change my PnL or trade count?</strong>
              <p>{RISK_SAVE_NOTE}</p>
            </div>

            <h3 className="risk-impact-heading pnl">Does this affect PnL?</h3>
            <p className="risk-modal-intro">
              These control how <strong>big each win or loss</strong> can be and when positions close.
            </p>
            <table className="risk-modal-table risk-impact-table">
              <thead>
                <tr>
                  <th>Setting</th>
                  <th>Effect on profit &amp; loss</th>
                </tr>
              </thead>
              <tbody>
                {RISK_PNL_TABLE.map((row) => (
                  <tr key={row.setting}>
                    <td><strong>{row.setting}</strong></td>
                    <td>{row.effect}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <h3 className="risk-impact-heading trades">Does this affect number of trades?</h3>
            <p className="risk-modal-intro">
              These control <strong>how many trades open</strong> and how often the bot can enter again.
            </p>
            <table className="risk-modal-table risk-impact-table">
              <thead>
                <tr>
                  <th>Setting</th>
                  <th>Effect on trade count</th>
                </tr>
              </thead>
              <tbody>
                {RISK_TRADES_TABLE.map((row) => (
                  <tr key={row.setting}>
                    <td><strong>{row.setting}</strong></td>
                    <td>{row.effect}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="risk-tips-box">
              <strong>Quick tips</strong>
              <ul className="risk-modal-list">
                <li>Want <strong>bigger/smaller PnL per trade</strong> → change Risk per trade % or Max exposure %.</li>
                <li>Want <strong>more trades</strong> → raise max positions or lower cooldowns (more risk).</li>
                <li>Want <strong>fewer trades / safer</strong> → lower daily loss %, raise cooldowns, keep per symbol at 1.</li>
              </ul>
            </div>
          </section>

          <section className="risk-modal-edit">
            <h3>Edit limits for this account</h3>
            {children}
          </section>
        </div>
      </div>
    </div>
  );
}
