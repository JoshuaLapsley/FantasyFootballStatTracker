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
 * Data behaviour:
 *  Data comes from your own Render proxy (not Yahoo or Twelve Data
 *  directly from the browser, which get blocked by CORS or require a
 *  client-exposed API key). On mount, and whenever you hit "Refresh", this
 *  makes two calls to the proxy:
 *    1. /api/history/:symbol?range=1mo&interval=60m — hourly candles used
 *       to draw the chart from your fill time to now.
 *    2. /api/quote/:symbol — the current live price, used for the
 *       headline "worth right now" number (more current than the last
 *       hourly candle, which can be up to ~an hour stale).
 *  There is no polling and no fabricated/simulated price data. If either
 *  fetch fails, the UI says so plainly instead of making up numbers, and
 *  gives you a manual "Retry" button.
 */

// ---------- Position config ----------
// Your Render proxy — see README from the yahoo-proxy project for the
// server code. Swap this for your actual Render URL if it changes.
const PROXY_URL = "https://fantasyfootballstattracker.onrender.com";

// Yahoo's format for TSX-listed stocks is "TICKER.TO", not "TICKER:TSX".
const TICKER = "HEB.TO";
const DISPLAY_NAME = "HEB.TO";

const BUY_PRICE = 34.74;
const AMOUNT_INVESTED = 160;
const SHARES = AMOUNT_INVESTED / BUY_PRICE;

// Fill time: fixed at September 8, 2026, 3:45 PM, America/Toronto.
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

type ProxyCandle = {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

type ProxyHistoryResponse = {
  symbol: string;
  candles: ProxyCandle[];
};

type ProxyQuoteResponse = {
  symbol: string;
  currency: string;
  exchangeName: string;
  regularMarketPrice: number;
  previousClose: number;
  regularMarketTime: number; // unix seconds
  marketState: string;
};

// Fetches hourly history + the live quote from your own proxy (not Yahoo
// directly, which blocks browser CORS requests).
async function fetchFromProxy(): Promise<{
  points: PricePoint[];
  latest: number;
  latestTime: number;
} | null> {
  try {
    const [historyRes, quoteRes] = await Promise.all([
      fetch(`${PROXY_URL}/api/history/${TICKER}?range=1mo&interval=60m`),
      fetch(`${PROXY_URL}/api/quote/${TICKER}`),
    ]);

    if (!historyRes.ok) {
      console.error("Proxy history request failed:", historyRes.status);
      return null;
    }

    const historyData: ProxyHistoryResponse = await historyRes.json();
    const candles = historyData?.candles ?? [];

    const points: PricePoint[] = candles
      .map((c) => ({ t: new Date(c.date).getTime(), price: c.close }))
      .filter(
        (p): p is PricePoint =>
          p.price !== null &&
          !Number.isNaN(p.t) &&
          p.t >= FILL_TIME.getTime()
      )
      .sort((a, b) => a.t - b.t);

    if (!points.length) return null;

    // Anchor the chart to the actual fill price at the fill time. Without
    // this, the line starts at whatever the first hourly candle happened
    // to close at (mid-candle from your actual buy), not your real cost
    // basis, which reads as "wrong" even though the market data is correct.
    if (points[0].t > FILL_TIME.getTime()) {
      points.unshift({ t: FILL_TIME.getTime(), price: BUY_PRICE });
    }

    // Prefer the live quote for the "current" price/time (more up to date
    // than the last hourly candle), but fall back to the last candle if
    // the quote request failed for some reason.
    let latest = points[points.length - 1].price;
    let latestTime = Date.now();

    if (quoteRes.ok) {
      const quoteData: ProxyQuoteResponse = await quoteRes.json();
      if (typeof quoteData.regularMarketPrice === "number") {
        latest = quoteData.regularMarketPrice;
        latestTime = quoteData.regularMarketTime
          ? quoteData.regularMarketTime * 1000
          : Date.now();
      }
    }

    // Add the live quote as the final chart point so the line extends
    // right up to "now" rather than stopping at the last hourly candle.
    const lastCandle = points[points.length - 1];
    if (latest !== lastCandle.price) {
      points.push({ t: latestTime, price: latest });
    }

    return { points, latest, latestTime };
  } catch (err) {
    console.error("Proxy fetch failed:", err);
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
    const real = await fetchFromProxy();

    if (real && real.points.length > 1) {
      setHistory(real.points);
      setLastUpdated(real.latestTime);
      setState("loaded");
    } else {
      setHistory(null);
      setLastUpdated(Date.now());
      setState("error");
    }
  }

  // Fetch on mount. No polling — click "Refresh" to pull the latest data.
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
            <span className="ticker">Treasurer Pot Tracker</span>
            <span className="exchange">Your treasurer has put the pot into HEB.TO</span>
          </div>
          <div className="status-pill status-live">
            <span className="status-dot" />
            Live
          </div>
        </header>

        <div className="pot-block">
          <div className="pot-label">The $160 pot is now worth</div>
          <div className="pot-value">{formatMoney(potValue)}</div>
          <div className={`delta-badge ${isUp ? "up" : "down"}`}>
            {isUp ? "+" : ""}
            {formatMoney(gainDollars)} ({isUp ? "+" : ""}
            {gainPercent.toFixed(2)}%) {isUp ? "profit" : "loss"}
          </div>
        </div>

        <div className="updated-line">
          Data last retrieved {formatClock(lastUpdated)} &middot;{" "}
          {history.length} hourly points since fill{" "}
        </div>

        <div className="chart-wrap">
          <svg
            viewBox={`0 0 ${chart.width} ${chart.height}`}
            preserveAspectRatio="none"
            className="chart-svg"
          >
            {/* Y-axis gridlines + labels */}
            {chart.yTicks.map((tick, i) => (
              <g key={`y-${i}`}>
                <line
                  x1={chart.padLeft}
                  y1={tick.y}
                  x2={chart.width - chart.padRight}
                  y2={tick.y}
                  className="grid-line"
                />
                <text
                  x={chart.padLeft - 8}
                  y={tick.y}
                  className="axis-label y-label"
                >
                  {formatMoney(tick.price)}
                </text>
              </g>
            ))}

            {/* X-axis ticks + labels */}
            {chart.xTicks.map((tick, i) => (
              <text
                key={`x-${i}`}
                x={tick.x}
                y={chart.height - 6}
                className="axis-label x-label"
              >
                {tick.label}
              </text>
            ))}

            {/* Axis lines */}
            <line
              x1={chart.padLeft}
              y1={chart.padTop}
              x2={chart.padLeft}
              y2={chart.height - chart.padBottom}
              className="axis-line"
            />
            <line
              x1={chart.padLeft}
              y1={chart.height - chart.padBottom}
              x2={chart.width - chart.padRight}
              y2={chart.height - chart.padBottom}
              className="axis-line"
            />

            {/* Buy price reference line */}
            <line
              x1={chart.padLeft}
              y1={chart.buyLineY}
              x2={chart.width - chart.padRight}
              y2={chart.buyLineY}
              className="buy-line"
            />
            <text
              x={chart.width - chart.padRight - 6}
              y={chart.buyLineY - 6}
              textAnchor="end"
              className="buy-label"
            >
              Buy {formatMoney(BUY_PRICE)}
            </text>

            <polyline points={chart.areaPoints} className={`chart-area ${isUp ? "up" : "down"}`} />
            <polyline points={chart.linePoints} className={`chart-line ${isUp ? "up" : "down"}`} />
            <circle
              cx={chart.lastX}
              cy={chart.lastY}
              r={5}
              className={`chart-dot ${isUp ? "up" : "down"}`}
            />
          </svg>
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
            <dt>Net profit/loss</dt>
            <dd className={isUp ? "text-up" : "text-down"}>
              {isUp ? "+" : ""}
              {formatMoney(gainDollars)}
            </dd>
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
        </dl>
      </div>
    </div>
  );
}

// ---------- Chart geometry helpers ----------
function useMemoChart(history: PricePoint[]) {
  return useMemo(() => buildChartGeometry(history), [history]);
}

const Y_TICK_COUNT = 5;
const X_TICK_COUNT = 5;

function buildChartGeometry(history: PricePoint[]) {
  const width = 1000;
  const height = 320;

  // Room reserved for axis labels: left for price labels, bottom for date labels.
  const padLeft = 64;
  const padRight = 12;
  const padTop = 24;
  const padBottom = 26;

  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;

  const prices = history.map((p) => p.price);
  const min = Math.min(...prices, BUY_PRICE);
  const max = Math.max(...prices, BUY_PRICE);
  // Pad the price range slightly so the line/gridlines don't sit flush
  // against the top/bottom edge of the plot area.
  const rawRange = max - min || 1;
  const rangePad = rawRange * 0.08;
  const domainMin = min - rangePad;
  const domainMax = max + rangePad;
  const range = domainMax - domainMin || 1;

  const xStep = history.length > 1 ? plotWidth / (history.length - 1) : plotWidth;

  const toX = (i: number) => padLeft + i * xStep;
  const toY = (price: number) =>
    padTop + plotHeight - ((price - domainMin) / range) * plotHeight;

  const linePoints = history.map((p, i) => `${toX(i)},${toY(p.price)}`).join(" ");

  const areaPoints = `${padLeft},${height - padBottom} ${linePoints} ${
    width - padRight
  },${height - padBottom}`;

  const buyLineY = toY(BUY_PRICE);

  const lastX = toX(history.length - 1);
  const lastY = toY(history[history.length - 1].price);

  // Y-axis ticks: evenly spaced prices across the padded domain.
  const yTicks = Array.from({ length: Y_TICK_COUNT }, (_, i) => {
    const price = domainMin + (range * i) / (Y_TICK_COUNT - 1);
    return { price, y: toY(price) };
  }).reverse();

  // X-axis ticks: evenly spaced indices across the history array,
  // always including the first (fill) and last (now) points.
  const tickCount = Math.min(X_TICK_COUNT, history.length);
  const xTicks = Array.from({ length: tickCount }, (_, i) => {
    const idx =
      tickCount === 1
        ? 0
        : Math.round((i * (history.length - 1)) / (tickCount - 1));
    return { x: toX(idx), label: formatAxisTime(history[idx].t) };
  });

  return {
    width,
    height,
    padLeft,
    padRight,
    padTop,
    padBottom,
    linePoints,
    areaPoints,
    buyLineY,
    lastX,
    lastY,
    yTicks,
    xTicks,
  };
}
