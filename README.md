# Polybot — Polymarket copy-trading bot

Polybot finds consistently profitable wallets on [Polymarket](https://polymarket.com),
ranks them with a transparent scoring model, watches the best ones for new
trades, and **copies those trades** with built-in risk limits.

It defaults to **paper trading** (simulated fills, no money, no keys). Live
trading is opt-in and gated behind explicit confirmation plus credentials.

> Prediction markets are risky and copy-trading does not guarantee profit. Past
> wallet performance is not predictive. Use paper mode first, start small, and
> never risk funds you can't lose. This software is provided as-is, for
> educational and research purposes.

## How it works

```
 discover ──► score/rank ──► follow top-N ──► monitor ──► copy (paper|live)
   │              │                              │            │
 data API     win-rate, ROI,                poll /activity   risk caps +
 + holders    PnL, volume,                  for new trades   slippage guard
 + leaderboard recency                       (dedup'd)        CLOB order
```

1. **Discovery** (`polybot/discovery.py`) gathers candidate wallets from three
   sources: seed wallets you list, a best-effort leaderboard fetch, and the top
   holders of the most active markets.
2. **Scoring** (`polybot/scoring.py`) pulls each candidate's real
   activity/positions history and computes win-rate, ROI, realized+unrealized
   PnL, volume and recency, combined into a single weighted score. Hard filters
   (min trades/volume/win-rate, must be profitable, not idle) decide eligibility.
3. **Monitoring** (`polybot/monitor.py`) polls each followed wallet's `/activity`
   feed on an interval, using a per-wallet watermark + a seen-set so each trade
   fires exactly once.
4. **Copy execution** (`polybot/copytrader.py`) sizes each copy (proportional or
   fixed), checks live market price and slippage, then either records a simulated
   fill (paper) or places a marketable limit order on the CLOB (live).
5. **Risk** (`polybot/risk.py`) gates every signal: per-trade min/max, per-market
   and total exposure caps, max open positions, a daily loss limit, market
   allow/block lists, and a stale-signal cutoff.

State lives in a local SQLite file (`polybot.db`): ranked wallets, seen trades,
and every copy order.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .            # add ".[dev]" for tests, ".[live]" for live trading
cp config.example.yaml config.yaml
```

## Usage

```bash
# 1. Find and rank profitable wallets; auto-follow the top N (config: copy.follow_top_n)
polybot discover

# Inspect the ranking and who you're following
polybot wallets
polybot status

# Manually adjust the follow list
polybot track   0xWALLET...
polybot untrack 0xWALLET...

# 2a. Headless copy loop (paper by default)
polybot monitor

# 2b. Live monitoring terminal (TUI dashboard)
polybot dashboard

# Connectivity / credential sanity check
polybot check
```

All commands accept `--config PATH` and `--mode {paper,live}`. Add `-v` for
debug logging.

## Paper vs. live

| | Paper (default) | Live |
|---|---|---|
| Money | none | real USDC on Polygon |
| Keys | none | `.env` with `POLYMARKET_PRIVATE_KEY` |
| Dependency | base install | `pip install -e ".[live]"` (`py-clob-client`) |
| Fills | simulated at market price | real CLOB orders |

To go live:

```bash
cp .env.example .env        # fill in your key; NEVER commit it
pip install -e ".[live]"
polybot --mode live monitor # asks for confirmation before starting
```

Live mode refuses to start without a trading key, and every order still passes
through the same risk caps as paper mode.

## Configuration

Everything is in `config.yaml` (copied from `config.example.yaml`), grouped into
`discovery`, `scoring`, `copy`, `risk`, and `monitor` sections. Key knobs:

- `copy.sizing` — `proportional` (`scale` × source size) or `fixed` (`fixed_usdc`)
- `copy.min_trade_usdc` / `max_trade_usdc` — per-copy bounds
- `copy.max_slippage` — reject if the market moved too far from the source price
- `risk.max_total_exposure_usdc`, `max_position_per_market_usdc`,
  `max_open_positions`, `daily_loss_limit_usdc` — portfolio safety rails
- `scoring.weights` and `scoring.min_*` — how wallets are ranked and filtered

## Notes on the Polymarket APIs

- **Data API** (`data-api.polymarket.com`) — `/activity`, `/positions`,
  `/holders`, `/value`. Public, read-only. Field names have changed over time,
  so parsing is intentionally defensive.
- **Gamma API** (`gamma-api.polymarket.com`) — market/event metadata.
- **CLOB** (`clob.polymarket.com`) — prices (no auth) and order placement (auth,
  via `py-clob-client`).

These endpoints sit behind bot-protection and rate limiting; the HTTP layer
retries with backoff and the bot degrades gracefully when a call is blocked or
unreachable. If `polybot check` reports "no data", your network egress is likely
being filtered.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests cover scoring/filtering, risk sizing and caps, copy execution (paper +
live via a fake CLOB), and the monitor's dedup/watermark logic — all offline,
no network required.
```
polybot/
  clients/   data_api, gamma_api, clob, http
  config.py  models.py  store.py
  discovery.py  scoring.py  risk.py  copytrader.py  monitor.py
  dashboard.py  cli.py
tests/
```
