#!/usr/bin/env python3
"""Breakout Rider: a long-only cbBTC trend bot for make.fun's 24h BTC race.

Strategy (all decisions on 1-minute bar closes, fills land at the next open):
  * Enter long with the full cash balance when the market shows a real
    breakout: the 60-minute return is at least +0.6%, the 15-minute return
    is also positive (momentum alignment), and the close sits above its
    90-bar average (trend filter). A 60-bar cooldown after every full exit
    keeps the bot out of whipsaw chop.
  * While long, bank half the position at +2.0% and let the rest ride with
    a 2.0% trailing stop from the peak close. A hard stop at -2.0% from the
    entry cost caps every losing trade. No cross-down or time-based exit:
    on 1-minute bars those only churn fees (about 26 bps a round trip).
  * In a falling market the breakout rule simply never fires, so the bot
    holds cash and loses nothing -- on a race window that falls, losing
    the least is what wins.

The bot is fully deterministic: no randomness, no wall clock, no network,
no files. Every decision comes from the bars the harness sends, in
integer micro-USDC and raw price units. One reply per batch, echoing seq.
"""

import json
import sys

SYMBOL = "CBBTC"

# --- strategy parameters (round, robust numbers; tuned lightly on the dev
# window, checked on both halves and on a mirrored falling window) ---
LOOKBACK = 60          # minutes for the breakout return
ENTRY_RET = 0.006      # +0.6% over LOOKBACK to enter: the replay showed the
                       # +1.2% bar entered the dev window's only real move
                       # 113 bars late (bar 204 vs 91, $59,873 vs $59,177);
                       # +0.6% still fires exactly once on the dev window,
                       # so no whipsaw is added
ALIGN_N = 15           # short window that must also be rising
TREND_N = 90           # close must be above this average
TAKE_HALF = 0.020      # bank half the position at +2.0%
TRAIL = 0.020          # trailing stop: 2.0% off the peak close
STOP = 0.020           # hard stop: -2.0% from entry cost
MIN_GAIN_FOR_TRAIL = 0.003   # trail only arms once the trade is +0.3%
COOLDOWN = 60          # bars to wait after a full exit
MAX_SLIPPAGE_BPS = 100  # 1%: rejects fills that gap far past the close


def main():
    closes = []          # raw integer closes of CBBTC, in arrival order
    price_scale = 5      # overridden by hello
    qty_scale = 8
    quote_scale = 6
    warmup = 0

    cash = 0             # micro-USDC, from the account snapshot
    pos_qty = 0          # base units (raw integer), from the account
    pos_cost = 0         # micro-USDC cost of the open position
    entry_price = 0.0    # raw price units of the current entry
    peak = 0.0           # highest raw close seen since entry
    half_taken = False
    cool = 0             # cooldown bars remaining
    order_no = 0         # unique client ids

    def pnl_ratio():
        if pos_qty <= 0 or entry_price <= 0:
            return 0.0
        return closes[-1] / entry_price - 1.0

    def sma(n):
        window = closes[-n:]
        return sum(window) / len(window)

    def reply(seq, orders):
        sys.stdout.write(json.dumps(
            {"type": "reply", "seq": seq, "orders": orders},
            separators=(",", ":")) + "\n")
        sys.stdout.flush()

    def next_id(prefix):
        nonlocal order_no
        order_no += 1
        return "%s%d" % (prefix, order_no)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        kind = msg.get("type")

        if kind == "hello":
            for s in msg.get("symbols", []):
                if s.get("symbol") == SYMBOL:
                    price_scale = int(s.get("price_scale", 5))
                    qty_scale = int(s.get("qty_scale", 8))
            quote_scale = int(msg.get("capital", {}).get("quote_scale", 6))
            warmup = int(msg.get("warmup_bars", 0) or 0)
            continue

        if kind == "done":
            break

        if kind != "batch":
            continue

        seq = msg["seq"]
        account = msg.get("account", {})
        cash = int(account.get("cash_quote_units", "0") or 0)
        pos_qty = 0
        pos_cost = 0
        for p in account.get("positions", []) or []:
            if p.get("symbol") == SYMBOL:
                pos_qty = int(p.get("qty", "0") or 0)
                pos_cost = int(p.get("cost_quote_units", "0") or 0)

        # Record this bar's close before deciding.
        bar = None
        for b in msg.get("bars", []) or []:
            if b.get("symbol") == SYMBOL:
                bar = b
                break
        if bar is not None:
            closes.append(int(bar["c"]))

        # Learn the entry price from our own buy fills (they arrive one
        # bar after the decision, priced at the fill open).
        for f in msg.get("fills", []) or []:
            if f.get("symbol") != SYMBOL or f.get("status") != "filled":
                continue
            if f.get("side") == "buy":
                entry_price = float(f["price"])
                peak = entry_price
                half_taken = False

        orders = []
        n = len(closes)

        if cool > 0:
            cool -= 1

        if bar is not None and n > warmup:
            if pos_qty <= 0:
                # Flat: look for a breakout entry.
                if cool <= 0 and n > LOOKBACK and n > TREND_N:
                    ret60 = closes[-1] / closes[-1 - LOOKBACK] - 1.0
                    ret15 = closes[-1] / closes[-1 - ALIGN_N] - 1.0
                    if (ret60 >= ENTRY_RET and ret15 > 0
                            and closes[-1] > sma(TREND_N)
                            and cash > 0):
                        orders.append({
                            "side": "buy",
                            "client_id": next_id("b"),
                            "symbol": SYMBOL,
                            "notional_quote_units": str(cash),
                            "max_slippage_bps": MAX_SLIPPAGE_BPS,
                        })
            else:
                # Long: manage the position.
                if entry_price <= 0 and pos_cost > 0 and pos_qty > 0:
                    # Fallback if a buy fill was missed: rebuild the
                    # entry price from the account's cost basis.
                    entry_price = (
                        pos_cost * 10 ** (qty_scale + price_scale - quote_scale)
                        / pos_qty)
                    peak = max(peak, entry_price)
                if closes:
                    peak = max(peak, closes[-1])
                pnl = pnl_ratio()
                if TAKE_HALF is not None and not half_taken and pnl >= TAKE_HALF:
                    half = pos_qty // 2
                    if half > 0:
                        orders.append({
                            "side": "sell",
                            "client_id": next_id("s"),
                            "symbol": SYMBOL,
                            "qty": str(half),
                            "max_slippage_bps": MAX_SLIPPAGE_BPS,
                        })
                        half_taken = True
                elif pnl <= -STOP or (
                        pnl > MIN_GAIN_FOR_TRAIL
                        and peak > 0
                        and (peak - closes[-1]) / peak >= TRAIL):
                    orders.append({
                        "side": "sell",
                        "client_id": next_id("s"),
                        "symbol": SYMBOL,
                        "qty": str(pos_qty),
                        "max_slippage_bps": MAX_SLIPPAGE_BPS,
                    })
                    cool = COOLDOWN

        reply(seq, orders)

    return 0


if __name__ == "__main__":
    sys.exit(main())
