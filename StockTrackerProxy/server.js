const express = require("express");
const cors = require("cors");

const app = express();
const PORT = process.env.PORT || 3000;

// Allow requests from any origin. If you want to lock this down to just
// your app's domain, replace "*" with e.g. "https://your-app.vercel.app"
app.use(cors({ origin: "*" }));

const YAHOO_BASE = "https://query1.finance.yahoo.com";

// Yahoo blocks requests that don't look like they came from a browser,
// so we set a realistic User-Agent on our outgoing requests.
const YAHOO_HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
  Accept: "application/json",
};

/**
 * GET /api/quote/:symbol
 * Returns current price + basic info for a single symbol.
 * Example: /api/quote/HEB.TO
 */
app.get("/api/quote/:symbol", async (req, res) => {
  const { symbol } = req.params;

  try {
    const url = `${YAHOO_BASE}/v8/finance/chart/${encodeURIComponent(
      symbol
    )}?interval=1d&range=5d`;

    const response = await fetch(url, { headers: YAHOO_HEADERS });

    if (!response.ok) {
      return res
        .status(response.status)
        .json({ error: `Yahoo responded with ${response.status}` });
    }

    const data = await response.json();
    const result = data?.chart?.result?.[0];

    if (!result) {
      return res.status(404).json({ error: "Symbol not found" });
    }

    const meta = result.meta;

    res.json({
      symbol: meta.symbol,
      currency: meta.currency,
      exchangeName: meta.exchangeName,
      regularMarketPrice: meta.regularMarketPrice,
      previousClose: meta.chartPreviousClose,
      regularMarketTime: meta.regularMarketTime,
      marketState: meta.marketState,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to fetch quote" });
  }
});

/**
 * GET /api/history/:symbol?range=1mo&interval=1d
 * Returns historical OHLC candles for a symbol.
 * Example: /api/history/HEB.TO?range=1mo&interval=1d
 */
app.get("/api/history/:symbol", async (req, res) => {
  const { symbol } = req.params;
  const { range = "1mo", interval = "1d" } = req.query;

  try {
    const url = `${YAHOO_BASE}/v8/finance/chart/${encodeURIComponent(
      symbol
    )}?interval=${encodeURIComponent(interval)}&range=${encodeURIComponent(
      range
    )}`;

    const response = await fetch(url, { headers: YAHOO_HEADERS });

    if (!response.ok) {
      return res
        .status(response.status)
        .json({ error: `Yahoo responded with ${response.status}` });
    }

    const data = await response.json();
    const result = data?.chart?.result?.[0];

    if (!result) {
      return res.status(404).json({ error: "Symbol not found" });
    }

    const timestamps = result.timestamp || [];
    const quote = result.indicators?.quote?.[0] || {};

    const candles = timestamps.map((t, i) => ({
      date: new Date(t * 1000).toISOString(),
      open: quote.open?.[i] ?? null,
      high: quote.high?.[i] ?? null,
      low: quote.low?.[i] ?? null,
      close: quote.close?.[i] ?? null,
      volume: quote.volume?.[i] ?? null,
    }));

    res.json({ symbol: result.meta.symbol, candles });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Failed to fetch history" });
  }
});

app.get("/", (req, res) => {
  res.send("Yahoo Finance proxy is running. Try /api/quote/HEB.TO");
});

app.listen(PORT, () => {
  console.log(`Server listening on port ${PORT}`);
});
