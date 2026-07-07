# Risk protection guide

This explains the **Risk protection** banner on the dashboard and how limits apply per account.

## Per-account rules

Each trading account (Demo Practice, SAJI, HMISD, etc.) has **its own** risk file:

`data/accounts/{account_id}_risk.json`

When you switch accounts and click **Edit limits → Save**, only the **active (viewing)** account is updated. Other accounts keep their own settings.

---

## Banner labels

Example header:

```text
Risk protection · Demo Practice · 1/22 positions open
```

| Part | Meaning |
|------|---------|
| **Risk protection** | Auto-trading is governed by the rules below (not halted). |
| **Demo Practice** | Limits shown are for this account — switch accounts to edit another. |
| **1/22 positions open** | This account has **1** open trade out of **22** allowed (`max_concurrent_positions`). |

**Edit limits** — expand the form to change values and save for the active account.

---

## Quick summary row

| Label | Setting | What it does |
|-------|---------|--------------|
| **Max positions** | `max_concurrent_positions` | Maximum open trades **at once** on this account (all symbols combined). |
| **Per symbol** | `max_positions_per_symbol` | Max open trades on **one symbol** (e.g. only 1 BTCUSDT position). |
| **Daily loss** | `max_daily_loss_pct` | If **realized + unrealized** loss today exceeds this % of equity, **new trades are blocked** and trading may halt. |
| **Unrealized cap** | `max_unrealized_loss_pct` | Blocks **new** entries when floating (open) loss exceeds this % of equity. Existing positions stay open. |
| **Emergency** | `emergency_close_unrealized_loss_pct` | If floating loss hits this %, the bot **closes all open positions** on that account automatically. Must be ≥ unrealized cap. |
| **Exposure** | `max_total_exposure_pct` | Max total position size as % of equity. Example: 40% on $100 → ~$40 notional max (~0.0006 BTC at $65k). |

---

## Detailed settings (Edit limits)

### Position limits

- **Risk per trade (%)** — How much of balance/equity to risk on one trade when sizing from stop distance (`fixed_risk`).
- **Max open positions** — Hard cap on concurrent positions (your **22** allows many parallel trades).
- **Max per symbol** — Usually `1` so you do not stack multiple BTC longs.

### Loss limits

- **Daily loss cap (%)** — Stops trading for the day if total PnL (closed + open) is worse than this.
- **Max drawdown (%)** — Halt if equity falls this far from the session peak.
- **Unrealized loss cap (%)** — No new trades while floating loss is too large.
- **Emergency close (%)** — Force-close everything when floating loss is critical.

### Exposure & cooldowns

- **Max exposure (%)** — Sum of `(quantity × entry price)` for all open positions, as % of equity. Blocks manual and auto trades that would exceed it.
- **Signal cooldown (min)** — Minimum time between new auto entries on the **same symbol** after a position was opened.
- **Cooldown after loss (min)** — Pause new entries after a losing close.

### Stops & targets

- **ATR stop multiplier** — Stop distance = ATR × this value when auto SL/TP is used.
- **Take profit R:R** — Take-profit distance as a multiple of stop distance.
- **Trailing ATR mult.** — How tight trailing stops follow price.
- **Break-even R:R** — Move stop to entry after price moves this many R in profit.
- **Trailing ATR mult.** — How tight trailing stops follow price.

On **testnet/live**, when `update_exchange_trailing_sl` is enabled, the bot cancels the old Binance SL algo order and places a new one when break-even or trailing tightens the stop (checked every ~5 seconds).

### Checkboxes

- **Block duplicate side** — No second LONG on BTC if you already have a LONG there.
- **Use equity for limits** — Use balance + unrealized PnL (not just cash balance) when checking % limits.

---

## Trading halted

If the banner shows **Trading halted**, a hard rule was breached (e.g. daily loss or drawdown). Use **Resume trading** after you have reviewed the situation. Halt reason is shown under the banner.

---

## Stopping the bot per account

| Action | Effect |
|--------|--------|
| **Stop** (on one account in the account list) | Stops auto-trading for **that account only**. Open positions remain; stops/TP still monitored while engine runs. |
| **Stop All Accounts** (top controls) | Stops every account and shuts down the trading engine. |
| **Switch & Start** | Starts auto-trading on the selected account **without** stopping others. |

After an API restart, all accounts stop — use **Start** or **Switch & Start** again for each account you want running.

---

## Small balance example (SAJI $100)

With **Exposure: 40%**:

- Max notional ≈ **$40**
- At BTC ≈ $65,000 → max size ≈ **0.0006 BTC**
- Default manual preset **0.001 BTC** will be **blocked** until you lower quantity or raise exposure %.

Demo Practice ($10k) can use larger sizes because 40% ≈ $4,000 notional.

---

## Where settings are stored

| File | Contents |
|------|----------|
| `data/accounts/1_risk.json` | Risk limits for account 1 |
| `data/accounts/2_risk.json` | Risk limits for account 2 |
| `config/default.yaml` | Default values for **new** accounts |

Default in `config/default.yaml` is **4** max positions; your Demo account was saved with **22** via the dashboard.
