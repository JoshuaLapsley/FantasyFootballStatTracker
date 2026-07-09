import requests
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

url = "https://www.fantasypros.com/nfl/projections/rb.php?week=draft&scoring=PPR&year=2025"
resp = requests.get(url, headers=HEADERS, timeout=15)
html = resp.text

# 1. Show the context around every occurrence of "application/json"
for m in re.finditer(r'application/json', html):
    start = max(0, m.start() - 200)
    end = min(len(html), m.end() + 100)
    print("----- context -----")
    print(html[start:end])
    print()

# 2. Look for any URLs that look like API/data endpoints referenced anywhere in the page
api_like = re.findall(r'https?://[^\s"\'<>]*(?:api|json|data|projections)[^\s"\'<>]*', html, re.IGNORECASE)
print("Possible API-like URLs found:")
for u in sorted(set(api_like)):
    print(" ", u)

# 3. Look for any <script src="..."> pointing to app bundles (helps confirm it's a JS SPA-rendered table)
script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html)
print(f"\n{len(script_srcs)} external script tags found, first 10:")
for s in script_srcs[:10]:
    print(" ", s)