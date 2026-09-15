# Yahoo Finance Proxy

A tiny Express server that fetches data from Yahoo Finance's undocumented
chart API server-side (where CORS doesn't apply) and re-serves it with CORS
headers so your React app can call it directly from the browser.

## Endpoints

- `GET /api/quote/:symbol` — current price snapshot
  e.g. `/api/quote/HEB.TO`
- `GET /api/history/:symbol?range=1mo&interval=1d` — historical candles
  e.g. `/api/history/HEB.TO?range=1mo&interval=1d`

Note: for TSX-listed stocks, Yahoo's symbol format is `TICKER.TO`
(e.g. `HEB.TO`), not `HEB:TSX`.

## Deploy to Render.com

### Option A: Blueprint (fastest)
1. Push this folder to a GitHub repo.
2. In Render, click **New > Blueprint**, point it at the repo. It will
   read `render.yaml` and set everything up automatically.

### Option B: Manual
1. Push this folder to a GitHub repo.
2. In Render, click **New > Web Service**, connect the repo.
3. Settings:
   - Environment: **Node**
   - Build command: `npm install`
   - Start command: `npm start`
   - Plan: Free is fine to start
4. Deploy. Render gives you a URL like
   `https://yahoo-finance-proxy.onrender.com`.

Note: on Render's free plan the service spins down after inactivity, so
the first request after idling can take 20-50 seconds to wake up.

## Local testing

```bash
npm install
npm start
# then visit http://localhost:3000/api/quote/HEB.TO
```

## Using it from your React app

```typescript
const PROXY_URL = "https://yahoo-finance-proxy.onrender.com"; // your Render URL

const TICKER = "HEB.TO"; // Yahoo format, not "HEB:TSX"
const DISPLAY_NAME = "HEB.TO";

const BUY_PRICE = 37.74;
const AMOUNT_INVESTED = 160;
const BUY_DATE = "2026-09-08";

async function getQuote() {
  const res = await fetch(`${PROXY_URL}/api/quote/${TICKER}`);
  if (!res.ok) throw new Error("Failed to fetch quote");
  return res.json();
  // { symbol, currency, exchangeName, regularMarketPrice, previousClose, regularMarketTime, marketState }
}
```

A minimal React hook:

```tsx
import { useEffect, useState } from "react";

interface Quote {
  symbol: string;
  currency: string;
  regularMarketPrice: number;
  previousClose: number;
  marketState: string;
}

function useQuote(symbol: string, pollMs = 60000) {
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchQuote() {
      try {
        const res = await fetch(`${PROXY_URL}/api/quote/${symbol}`);
        if (!res.ok) throw new Error(`${res.status}`);
        const data = await res.json();
        if (!cancelled) setQuote(data);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    }

    fetchQuote();
    const id = setInterval(fetchQuote, pollMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [symbol, pollMs]);

  return { quote, error };
}
```

Then compute your position's P/L:

```tsx
const shares = AMOUNT_INVESTED / BUY_PRICE;
const currentValue = quote ? shares * quote.regularMarketPrice : null;
const pnl = currentValue !== null ? currentValue - AMOUNT_INVESTED : null;
const pnlPct = pnl !== null ? (pnl / AMOUNT_INVESTED) * 100 : null;
```
