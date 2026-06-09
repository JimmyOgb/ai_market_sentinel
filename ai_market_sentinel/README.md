# AI Market Sentinel — GenLayer

A decentralised market-alert contract deployed on **GenLayer Studionet**. Users register a crypto asset, and a plain-English intent; a pool of validator nodes fetches live market data, runs multi-LLM consensus, and writes a final `TRIGGERED` or `PENDING` verdict back on-chain.

---

## Live links

| Resource | URL |
|---|---|
| Frontend (Netlify) | https://fancy-tulumba-3c9942.netlify.app/ |
| GenLayer Studio | https://studio.genlayer.com/?import-contract=0xfC1961C1029f48e560DdE8bc20b037c852e320fe |

---

## Repository layout

```
ai_market_sentinel/
├── contracts/
│   └── ai_market_sentinel.py   # GenLayer intelligent contract
├── frontend/
│   └── index.html              # Single-file frontend (Binance WS + simulated GenVM)
├── .github/
│   └── workflows/
│       └── deploy.yml          # Auto-deploy frontend to Netlify on push to main
├── .gitignore
└── README.md
```

---

## How it works

### Contract (`contracts/ai_market_sentinel.py`)

The contract stores all state in a single `TreeMap` with prefixed string keys.

| Key pattern | Value |
|---|---|
| `owner` | Contract deployer address |
| `counter` | Total alerts created (stringified integer) |
| `meta:{id}` | JSON — owner, asset, intent |
| `status:{id}` | `"Active"` · `"Triggered"` · `"Cancelled"` |
| `history:{id}` | Last consensus verdict JSON |

**Public write methods**

- `create_intelligent_alert(asset, natural_language_intent)` — registers a new alert, returns its integer ID.
- `process_sentinel_check(alert_id)` — non-deterministic: fetches live market data from two public feeds (CoinGecko Trending + Messari RSS), runs `exec_prompt` on each validator node, and reaches consensus using `get_eq_principle` on a constrained `TRIGGERED` / `PENDING` token. Returns `True` if triggered.
- `cancel_alert(alert_id)` — owner-only soft-delete; sets status to `"Cancelled"`.

**Public view methods**

- `inspect_alert_state(alert_id)` — returns status + full history string.
- `get_alert_meta(alert_id)` — returns raw metadata JSON string.
- `get_total_alerts()` — returns counter as string.
- `get_owner()` — returns contract owner address.

### Consensus design

`process_sentinel_check` uses **`gl.eq_principle.get_eq_principle`** with a comparative equivalence description:

> *"Responses are equivalent if they both contain the same verdict token: both say TRIGGERED, or both say PENDING."*

The inner closure returns **only** the constrained token `"TRIGGERED"` or `"PENDING"` — not free-form prose — so validators running different LLMs can reach genuine consensus on a two-token vocabulary. The full reasoning line is printed to the validator log for debugging but does not participate in the consensus hash.

### Data sources (no API key required)

| Feed | URL | Format |
|---|---|---|
| CoinGecko Trending | `https://api.coingecko.com/api/v3/search/trending` | JSON |
| Messari News RSS | `https://messari.io/rss/news.xml` | XML / text |

Both are fetched inside the non-deterministic closure so every validator independently fetches the same URLs, ensuring the consensus comparison is fair.

### Frontend (`frontend/index.html`)

Single self-contained HTML file. No build step required — open in a browser or serve statically.

- **Binance WebSocket** (`wss://data-stream.binance.vision`) — live price feed for BTC, ETH, SOL, BNB, AVAX, XRP, ADA, DOGE, MATIC, ARB with real-time flash animations.
- **Simulated GenVM terminal** — mirrors the on-chain execution flow: shows both data-source URLs, the per-validator PROCESSING → RESPONDED sequence, the `get_eq_principle` consensus step, and writes the constrained verdict token to the history state key.
- All four contract methods are wired to UI panels: Create Alert, Run Sentinel, Inspect Alert, Cancel Alert.

---

## Running locally

No dependencies. Just open the frontend:

```bash
# Clone
git clone https://github.com/JimmyOgb/ai_market_sentinel
cd ai_market_sentinel

# Open in browser (macOS)
open frontend/index.html

# Or serve with any static server
npx serve frontend
```

To deploy the contract to GenLayer Studio:

1. Open https://studio.genlayer.com
2. Import `contracts/ai_market_sentinel.py`
3. Deploy to Studionet
4. Copy the contract address into `frontend/index.html` if wiring to a real RPC

---

## Deploying the frontend

The `.github/workflows/deploy.yml` workflow publishes `frontend/` to Netlify automatically on every push to `main`. Set the following repository secrets:

| Secret | Value |
|---|---|
| `NETLIFY_AUTH_TOKEN` | Your Netlify personal access token |
| `NETLIFY_SITE_ID` | Site ID from Netlify dashboard |

---

## Key fixes (v2)

| Issue (reviewer) | Fix |
|---|---|
| `gl.eq_principle.strict_eq()` on free-form LLM text cannot reach genuine multi-validator consensus | Switched to `gl.eq_principle.get_eq_principle()` with a comparative description; inner closure returns only the constrained token `TRIGGERED` or `PENDING` |
| CryptoPanic news URL returned HTTP 404 without an API key, so AI evaluated an error page | Replaced with two public, no-auth-required feeds: CoinGecko Trending (JSON) + Messari RSS (XML) |
| Repo contained only a README; no contract or frontend source committed; README described features that didn't match the deployed app | Both source files are now committed; README accurately documents the actual contract methods, state layout, data sources, and frontend behaviour |
| Metadata built via string concatenation — injection risk if asset/intent contained quotes | Replaced with `json.dumps({...})` throughout |
