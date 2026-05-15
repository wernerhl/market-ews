# Market Early Warning System

22-indicator dashboard monitoring credit, volatility, breadth, macro, and AI-specific risk factors. Auto-updates via GitHub Actions, deploys to GitHub Pages.

## Quick Start

```bash
# 1. Clone and enter
git clone https://github.com/YOUR_USER/market-ews.git
cd market-ews

# 2. Get a free FRED API key
#    → https://fred.stlouisfed.org/docs/api/api_key.html

# 3. Run locally
pip install fredapi yfinance pandas
python scripts/fetch_data.py --fred-key YOUR_KEY

# 4. Open index.html — it reads from data/indicators.json
```

## Deploy to GitHub Pages

1. Push to GitHub
2. Go to **Settings → Secrets → Actions** → add `FRED_API_KEY`
3. Go to **Settings → Pages** → Source: **GitHub Actions**
4. The workflow runs automatically on weekday market close (5:30 PM ET)
5. Trigger manually: **Actions → Update Market EWS → Run workflow**

## Indicators

| Tier | Name | Source | Frequency |
|------|------|--------|-----------|
| 1 | HY OAS Spread | FRED | Daily |
| 1 | MOVE Index | FRED/Yahoo | Realtime |
| 1 | 2s10s Yield Curve | FRED | Realtime |
| 1 | SOFR-FF Spread | FRED | Daily |
| 2 | VVIX/VIX Ratio | Yahoo | Realtime |
| 2 | VIX Term Structure | Yahoo | Realtime |
| 2 | Put/Call Ratio | CBOE | Realtime |
| 2 | Dark Pool Short Vol | FINRA | Daily |
| 3 | % Above 200-DMA | Yahoo | Realtime |
| 3 | SOX/SPX Ratio | Yahoo | Realtime |
| 3 | Net New Highs | Yahoo | Realtime |
| 3 | Defensives/Cyclicals | Yahoo | Realtime |
| 4 | Dollar Index (DXY) | Yahoo | Realtime |
| 4 | Oil 60d Velocity | Yahoo | Realtime |
| 4 | Initial Claims 4wk | FRED | Weekly |
| 4 | ISM Manufacturing | FRED | Monthly |
| 4 | Fed Balance Sheet | FRED | Weekly |
| 5 | Hyperscaler Capex | Manual | Quarterly |
| 5 | NVDA Lead Times | Manual | Qualitative |
| 5 | AI Lab Revenue | Manual | Qualitative |
| 5 | Taiwan Strait Risk | Manual | Qualitative |

## Manual Indicators

Edit `data/manual.json` to update qualitative assessments (Tier 5). Status values: `green`, `yellow`, `red`.

## Architecture

```
Cron (weekdays 5:30pm ET)
  → scripts/fetch_data.py
    → FRED API (credit, yields, claims, fed BS)
    → Yahoo Finance (VIX, VVIX, DXY, SOX, SPX, oil, sectors)
    → FINRA (dark pool short volume)
    → Compute signals (ratios, velocity, thresholds)
  → data/indicators.json (frontend reads this)
  → data/history/YYYY-MM-DD.json (sparkline history)
  → GitHub Pages deploy
```

## Cost

Zero. FRED API is free. Yahoo Finance is free. GitHub Actions and Pages are free for public repos.
