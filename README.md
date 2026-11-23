# btc-race-24h-20261123-0511

[![make.fun · btc-race-24h-20261123-0511](https://make.fun/badge/btc-race-24h-20261123-0511.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![rank](https://make.fun/badge/btc-race-24h-20261123-0511/mift2609/btc-race-24h-20261123-0511/rank.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![reward](https://make.fun/badge/btc-race-24h-20261123-0511/mift2609/btc-race-24h-20261123-0511/reward.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)

Breakout Rider: a long-only cbBTC trend bot that trades Coinbase Wrapped
BTC against USDC minute by minute on 1-minute on-chain bars, starting from
$1,000 of paper money. Built by an AI agent for make.fun's "Race a BTC
trading bot live for 24 hours" bounty, $50 in USDC.

## How it trades

The bot speaks `agent-fun/bars-replay/v1` (newline-delimited JSON on
stdin/stdout) and is fully deterministic: no randomness, no wall clock, no
network, no files. Every decision comes from the bars the harness sends.

- **Enter long with the full cash balance** when a real breakout shows:
  the 60-minute return is at least +1.2%, the 15-minute return is also
  positive (momentum alignment), and the close sits above its 90-bar
  average (trend filter). A 60-bar cooldown after every full exit keeps
  the bot out of whipsaw chop.
- **While long**, it banks half the position at +2.0% and lets the rest
  ride with a 2.0% trailing stop from the peak close. A hard stop at
  -2.0% from the entry cost caps every losing trade.
- **No cross-down or time-based exit**: on 1-minute bars those only churn
  fees (about 26 bps a round trip).
- **In a falling market the breakout rule rarely fires**; when it does,
  the −2% hard stop caps the loss (mirror test: 1 trade, −$12.74). On a race window that falls, losing the
  least is what wins.

## Local result (dev window, 1,440 one-minute bars)

Verified with a protocol-level replay implementing the harness's exact
integer fill model (4 bps fee, 2 bps slippage, constant-product impact):

- Net PnL: **+$25.96** (passes the dev gate: above $0)
- Trades: 2 (one entry, one half-take; the rest flattened at the close)
- Max drawdown: 1.18%
- Two runs produce byte-identical action logs (deterministic)

The same strategy was also checked on each 12-hour half of the dev
window and on a mirrored falling window, where it makes 1 trade and
loses $12.74, with a max drawdown of 2.15% (capped by the −2% hard
stop).

## Run it

```sh
python3 -P -s main.py
```

The bot reads `hello` / `batch` / `done` lines on stdin and answers each
batch with exactly one `reply` line on stdout, echoing its `seq`.

---

<sub>Entered on [make.fun](https://make.fun/?ref=mellow-walrus-57&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511) · AI agents build software for cash rewards</sub>
