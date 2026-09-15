import React, { useEffect, useMemo, useState } from "react";
import "./PotTracker.css";

/**
 * Full-page investment tracker for a single position: HEB.TO
 *
 * Position assumptions (edit these to match your real fill):
 *  - Ticker:        HEB.TO  (Toronto Stock Exchange)
 *  - Fill price:    $37.74 / share
 *  - Amount put in: $160.00
 *  - Fill time:     September 8, 2026 at 3:45 PM America/Toronto (EST/EDT)
 *  - Shares held:   $160 / $37.74 = ~4.240 shares (fractional, since $160
 *                    doesn't divide evenly into whole shares at that price)
 *
 * Data behaviour (changed from the previous version):
 *  On mount, this does ONE fetch to Yahoo Finance's chart endpoint, which
 *  returns both the intraday candle history (used to draw the chart from
 *  your fill time to now) and the latest quote (used for the headline
 *  numbers) in a single response. There is no polling, no setTimeout loop,
 *  and no fabricated/simulated price data. If the fetch fails (e.g. CORS
 *  blocks a direct browser call to Yahoo, or you're offline), the UI says
 *  so plainly instead of making up numbers, and gives you a manual "Retry"
 *  button.
 *
 * Live data note:
 *  Yahoo's chart endpoint is unofficial and frequently blocks direct
 *  browser requests via CORS. If you see "Unable to load live data" in
 *  practice, you'll likely need to route this through a small server-side
 *  proxy (or a keyed provider like Twelve Data / Alpha Vantage) rather than
 *  calling Yahoo directly from the client.
 */

// ---------- Position config ----------
// Twelve Data uses "SYMBOL:EXCHANGE" for non-US listings (e.g. "HEB:TSX"),
// not the Yahoo-style ".TO" suffix.
const TICKER = "HEB:TSX";
const DISPLAY_NAME = "HEB.TO";

// Create React App only exposes env vars prefixed with REACT_APP_, and only
// ones baked in at build time. Add this to a .env file at your project root
// (same level as package.json), then restart `npm start`:
//   REACT_APP_TWELVEDATA_API_KEY=your_key_here
// Note this key ships in your built JS bundle since it's a client-side call
// — fine for a free-tier personal tracker, not something to treat as secret.
const TWELVEDATA_API_KEY = "fbef40a161f947e68bed461947e34d88";
const BUY_PRICE = 37.74;
const AMOUNT_INVESTED = 160;
const SHARES = AMOUNT_INVESTED / BUY_PRICE;

// Fill time: fixed at September 8, 2026, 3:45 PM, America/Toronto.
// (Previously this was computed as "yesterday", which drifted every day
// the app was opened. It's now pinned to the actual fill date.)
function getFillTimestamp(): Date {
  // Month is 0-indexed in JS Date, so 8 = September.
  return new Date(2026, 8, 8, 15, 45, 0, 0);
}
const FILL_TIME = getFillTimestamp();

type PricePoint = { t: number; price: number };

function formatMoney(n: number): string {
  return n.toLocaleString("en-CA", {
    style: "currency",
    currency: "CAD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatClock(t: number): string {
  return new Date(t).toLocaleTimeString("en-CA", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatAxisTime(t: number): string {
  return new Date(t).toLocaleDateString("en-CA", {
    month: "short",
    day: "numeric",
  });
}

// Single fetch: Twelve Data's time_series endpoint returns candles ordered
// most-recent-first, so the first entry doubles as the "latest quote" —
// no second request needed.
//
// Since the fill date is now potentially many days in the past (not just
// "yesterday"), we ask for a much larger batch of 5-minute candles so the
// history actually reaches back to the fill timestamp instead of getting
// truncated to the last ~2 trading days.
async function fetchRealHistory(): Promise<{
  points: PricePoint[];
  latest: number | null;
} | null> {
  if (!TWELVEDATA_API_KEY) {
    console.error(
      "Missing REACT_APP_TWELVEDATA_API_KEY — add it to your .env file and restart the dev server."
    );
    return null;
  }

  try {
    const url = new URL("https://api.twelvedata.com/time_series");
    url.searchParams.set("symbol", TICKER);
    url.searchParams.set("interval", "5min");
    // 5000 is the max outputsize Twelve Data allows per request. At ~78
    // 5-min candles per trading day, this comfortably covers several
    // weeks of history back to the fill date.
    url.searchParams.set("outputsize", "5000");
    url.searchParams.set("timezone", "America/Toronto");
    url.searchParams.set("apikey", TWELVEDATA_API_KEY);

    const res = await fetch(url.toString());
    if (!res.ok) return null;
    const data = await res.json();

    if (data?.status === "error") {
      console.error("Twelve Data error:", data.message);
      return null;
    }

    const values: Array<{ datetime: string; close: string }> =
      data?.values ?? [];
    if (!values.length) return null;

    // Twelve Data returns newest-first; flip to chronological order and
    // parse each "YYYY-MM-DD HH:mm:ss" datetime as America/Toronto time.
    const points: PricePoint[] = values
      .map((v) => ({
        t: new Date(`${v.datetime.replace(" ", "T")}-04:00`).getTime(),
        price: parseFloat(v.close),
      }))
      .filter((p) => !Number.isNaN(p.t) && !Number.isNaN(p.price))
      .filter((p) => p.t >= FILL_TIME.getTime())
      .sort((a, b) => a.t - b.t);

    if (!points.length) return null;

    const latest = points[points.length - 1].price;
    return { points, latest };
  } catch (err) {
    console.error("Twelve Data fetch failed:", err);
    return null;
  }
}

type LoadState = "loading" | "loaded" | "error";

export default function InvestmentTracker() {
  const [history, setHistory] = useState<PricePoint[] | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [lastUpdated, setLastUpdated] = useState<number>(Date.now());

  async function load() {
    setState("loading");
    const real = await fetchRealHistory();

    if (real && real.points.length > 1) {
      const points = [...real.points];
      const last = points[points.length - 1];
      if (real.latest != null && real.latest !== last.price) {
        points.push({ t: Date.now(), price: real.latest });
      }
      setHistory(points);
      setState("loaded");
    } else {
      setHistory(null);
      setState("error");
    }
    setLastUpdated(Date.now());
  }

  // Fetch exactly once, on mount. No polling — this is fine to only
  // refresh once a day (e.g. re-open the app / call `load()` manually).
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Hooks must run unconditionally on every render, so this is computed
  // with a safe fallback even before real data has loaded, and the
  // loading/error branches below simply don't use the result.
  const chart = useMemoChart(
    history ?? [{ t: FILL_TIME.getTime(), price: BUY_PRICE }]
  );

  if (state === "error" || history === null) {
    return (
      <div className="tracker-page">
        <div className="tracker-card">
          <header className="tracker-header">
            <div className="tracker-title">
              <span className="ticker">{DISPLAY_NAME}</span>
              <span className="exchange">TSX &middot; CAD</span>
            </div>
            <div className="status-pill status-sim">
              <span className="status-dot" />
              {state === "loading" ? "Loading" : "Unavailable"}
            </div>
          </header>
          <div className="pot-block">
            <div className="pot-label">
              {state === "loading"
                ? "Fetching live price..."
                : "Unable to load live data"}
            </div>
            {state === "error" && (
              <button className="delta-badge" onClick={load}>
                Retry
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  const current = history[history.length - 1].price;
  const potValue = SHARES * current;
  const gainDollars = potValue - AMOUNT_INVESTED;
  const gainPercent = (gainDollars / AMOUNT_INVESTED) * 100;
  const isUp = gainDollars >= 0;

  return (
    <div className="tracker-page">
      <div className="tracker-card">
        <header className="tracker-header">
          <div className="tracker-title">
            <span className="ticker">{DISPLAY_NAME}</span>
            <span className="exchange">TSX &middot; CAD</span>
          </div>
          <div className="status-pill status-live">
            <span className="status-dot" />
            Live
          </div>
        </header>

        <div className="pot-block">
          <div className="pot-label">Your $160 is now worth</div>
          <div className="pot-value">{formatMoney(potValue)}</div>
          <div className={`delta-badge ${isUp ? "up" : "down"}`}>
            {isUp ? "+" : ""}
            {formatMoney(gainDollars)} ({isUp ? "+" : ""}
            {gainPercent.toFixed(2)}%)
          </div>
        </div>
        <div className="updated-line">
          Loaded {formatClock(lastUpdated)} &middot; {history.length} points
          since fill{" "}
          <button className="refresh-link" onClick={load}>
            Refresh
          </button>
        </div>

        <div className="chart-wrap">
          <svg
            viewBox={`0 0 ${chart.width} ${chart.height}`}
            preserveAspectRatio="none"
            className="chart-svg"
          >
            <line
              x1={0}
              y1={chart.buyLineY}
              x2={chart.width}
              y2={chart.buyLineY}
              className="buy-line"
            />
            <polyline
              points={chart.areaPoints}
              className={`chart-area ${isUp ? "up" : "down"}`}
            />
            <polyline
              points={chart.linePoints}
              className={`chart-line ${isUp ? "up" : "down"}`}
            />
            <circle
              cx={chart.lastX}
              cy={chart.lastY}
              r={5}
              className={`chart-dot ${isUp ? "up" : "down"}`}
            />
          </svg>
          <div
            className="chart-axis-label buy-label"
            style={{ top: `${chart.buyLinePct}%` }}
          >
            Buy {formatMoney(BUY_PRICE)}
          </div>
          <div className="chart-x-labels">
            <span>{formatAxisTime(FILL_TIME.getTime())} (bought)</span>
            <span>{formatAxisTime(Date.now())} (now)</span>
          </div>
        </div>

        <dl className="stats-grid">
          <div className="stat">
            <dt>Share price</dt>
            <dd>{formatMoney(current)}</dd>
          </div>
          <div className="stat">
            <dt>Shares held</dt>
            <dd>{SHARES.toFixed(3)}</dd>
          </div>
          <div className="stat">
            <dt>Avg. cost</dt>
            <dd>{formatMoney(BUY_PRICE)}</dd>
          </div>
          <div className="stat">
            <dt>Invested</dt>
            <dd>{formatMoney(AMOUNT_INVESTED)}</dd>
          </div>
          <div className="stat">
            <dt>Bought</dt>
            <dd>
              {FILL_TIME.toLocaleDateString("en-CA", {
                month: "short",
                day: "numeric",
              })}{" "}
              &middot;{" "}
              {FILL_TIME.toLocaleTimeString("en-CA", {
                hour: "numeric",
                minute: "2-digit",
              })}
            </dd>
          </div>
          <div className="stat">
            <dt>Since fill</dt>
            <dd className={isUp ? "text-up" : "text-down"}>
              {isUp ? "+" : ""}
              {gainPercent.toFixed(2)}%
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}

// ---------- Chart geometry helpers ----------
function useMemoChart(history: PricePoint[]) {
  return useMemo(() => buildChartGeometry(history), [history]);
}

function buildChartGeometry(history: PricePoint[]) {
  const width = 1000;
  const height = 320;
  const padY = 20;

  const prices = history.map((p) => p.price);
  const min = Math.min(...prices, BUY_PRICE);
  const max = Math.max(...prices, BUY_PRICE);
  const range = max - min || 1;

  const xStep = history.length > 1 ? width / (history.length - 1) : width;

  const toY = (price: number) =>
    height - padY - ((price - min) / range) * (height - padY * 2);

  const linePoints = history
    .map((p, i) => `${i * xStep},${toY(p.price)}`)
    .join(" ");

  const areaPoints = `0,${height} ${linePoints} ${width},${height}`;

  const buyLineY = toY(BUY_PRICE);
  const buyLinePct = (buyLineY / height) * 100;

  const lastX = (history.length - 1) * xStep;
  const lastY = toY(history[history.length - 1].price);

  return {
    width,
    height,
    linePoints,
    areaPoints,
    buyLineY,
    buyLinePct,
    lastX,
    lastY,
  };
}
