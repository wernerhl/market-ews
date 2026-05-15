"""
Market Early Warning System — Data Pipeline
Fetches indicators from FRED, Yahoo Finance, and FINRA.
Computes regime signals. Writes indicators.json for the frontend.

Usage:
    python scripts/fetch_data.py [--fred-key YOUR_KEY]

Environment:
    FRED_API_KEY — required for FRED data
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"
MANUAL_FILE = DATA_DIR / "manual.json"
OUTPUT_FILE = DATA_DIR / "indicators.json"

HISTORY_DIR.mkdir(parents=True, exist_ok=True)

# How many days of history to keep for sparklines
SPARKLINE_DAYS = 90


# ── FRED Fetcher ───────────────────────────────────────────────────────

def fetch_fred(api_key: str) -> dict:
    """Fetch indicators from FRED API."""
    try:
        from fredapi import Fred
    except ImportError:
        print("Installing fredapi...")
        os.system(f"{sys.executable} -m pip install fredapi -q")
        from fredapi import Fred

    fred = Fred(api_key=api_key)
    results = {}

    series_map = {
        "hy_oas": "BAMLH0A0HYM2",      # HY OAS spread
        "sofr": "SOFR",                  # SOFR rate
        "fed_funds": "EFFR",             # Effective Fed Funds
        "us02y": "DGS2",                 # 2-year treasury
        "us10y": "DGS10",               # 10-year treasury
        "claims": "IC4WSA",              # Initial claims 4-wk MA
        "fed_bs": "WALCL",              # Fed balance sheet
        "rrp": "RRPONTSYD",             # Reverse repo
    }

    for key, series_id in series_map.items():
        try:
            data = fred.get_series(series_id, observation_start=datetime.now() - timedelta(days=120))
            data = data.dropna()
            if len(data) > 0:
                results[key] = {
                    "value": round(float(data.iloc[-1]), 4),
                    "date": str(data.index[-1].date()),
                    "history": [round(float(v), 4) for v in data.values[-SPARKLINE_DAYS:]],
                }
        except Exception as e:
            print(f"  FRED {series_id}: {e}")

    # Compute derived FRED indicators
    if "us10y" in results and "us02y" in results:
        results["yield_curve"] = {
            "value": round(results["us10y"]["value"] - results["us02y"]["value"], 4),
            "date": results["us10y"]["date"],
        }

    if "sofr" in results and "fed_funds" in results:
        results["sofr_ff"] = {
            "value": round((results["sofr"]["value"] - results["fed_funds"]["value"]) * 100, 2),  # in bps
            "date": results["sofr"]["date"],
        }

    if "fed_bs" in results:
        results["fed_bs"]["value"] = round(results["fed_bs"]["value"] / 1e6, 2)  # Convert to $T
        results["fed_bs"]["history"] = [round(v / 1e6, 2) for v in results["fed_bs"].get("history", [])]

    return results


# ── Yahoo Finance Fetcher ──────────────────────────────────────────────

def fetch_yahoo() -> dict:
    """Fetch indicators from Yahoo Finance."""
    try:
        import yfinance as yf
    except ImportError:
        print("Installing yfinance...")
        os.system(f"{sys.executable} -m pip install yfinance -q")
        import yfinance as yf

    results = {}
    end = datetime.now()
    start = end - timedelta(days=130)

    tickers = {
        "vix": "^VIX",
        "vvix": "^VVIX",
        "vix3m": "^VIX3M",
        "dxy": "DX-Y.NYB",
        "oil": "CL=F",
        "sox": "^SOX",
        "spx": "^GSPC",
        "move": None,  # MOVE not directly on Yahoo; fallback to FRED
        # Sector ETFs for defensives/cyclicals ratio
        "xlu": "XLU",
        "xlp": "XLP",
        "xlk": "XLK",
        "xly": "XLY",
    }

    for key, ticker in tickers.items():
        if ticker is None:
            continue
        try:
            data = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if data is not None and len(data) > 0:
                closes = data["Close"].dropna()
                if hasattr(closes, 'values') and len(closes) > 0:
                    vals = closes.values.flatten().tolist()
                    results[key] = {
                        "value": round(float(vals[-1]), 4),
                        "date": str(data.index[-1].date()),
                        "history": [round(float(v), 4) for v in vals[-SPARKLINE_DAYS:]],
                    }
        except Exception as e:
            print(f"  Yahoo {ticker}: {e}")

    # Compute derived Yahoo indicators
    if "vix" in results and "vvix" in results:
        vix_val = results["vix"]["value"]
        vvix_val = results["vvix"]["value"]
        if vix_val > 0:
            results["vvix_vix"] = {
                "value": round(vvix_val / vix_val, 2),
                "date": results["vix"]["date"],
            }
            # Build ratio history
            vix_h = results["vix"]["history"]
            vvix_h = results["vvix"]["history"]
            min_len = min(len(vix_h), len(vvix_h))
            if min_len > 0:
                results["vvix_vix"]["history"] = [
                    round(vvix_h[i] / vix_h[i], 2) if vix_h[i] > 0 else 0
                    for i in range(min_len)
                ]

    if "vix" in results and "vix3m" in results:
        results["vix_term"] = {
            "value": round(results["vix"]["value"] - results["vix3m"]["value"], 2),
            "date": results["vix"]["date"],
        }
        vix_h = results["vix"]["history"]
        vix3m_h = results["vix3m"]["history"]
        min_len = min(len(vix_h), len(vix3m_h))
        if min_len > 0:
            results["vix_term"]["history"] = [
                round(vix_h[i] - vix3m_h[i], 2) for i in range(min_len)
            ]

    if "sox" in results and "spx" in results:
        results["sox_spx"] = {
            "value": round(results["sox"]["value"] / results["spx"]["value"], 4),
            "date": results["sox"]["date"],
        }
        sox_h = results["sox"]["history"]
        spx_h = results["spx"]["history"]
        min_len = min(len(sox_h), len(spx_h))
        if min_len > 0:
            results["sox_spx"]["history"] = [
                round(sox_h[i] / spx_h[i], 4) if spx_h[i] > 0 else 0
                for i in range(min_len)
            ]

    if "xlu" in results and "xlp" in results and "xlk" in results and "xly" in results:
        def_val = results["xlu"]["value"] + results["xlp"]["value"]
        cyc_val = results["xlk"]["value"] + results["xly"]["value"]
        if cyc_val > 0:
            results["def_cyc"] = {
                "value": round(def_val / cyc_val, 4),
                "date": results["xlu"]["date"],
            }

    # Oil 60-day velocity
    if "oil" in results and len(results["oil"].get("history", [])) >= 60:
        h = results["oil"]["history"]
        current = h[-1]
        sixty_ago = h[-60] if len(h) >= 60 else h[0]
        if sixty_ago > 0:
            results["oil_velocity"] = {
                "value": round(((current - sixty_ago) / sixty_ago) * 100, 1),
                "date": results["oil"]["date"],
                "history": [],
            }
            # Build rolling 60d velocity history
            for i in range(len(h)):
                if i >= 60 and h[i - 60] > 0:
                    results["oil_velocity"]["history"].append(
                        round(((h[i] - h[i - 60]) / h[i - 60]) * 100, 1)
                    )

    return results


# ── FINRA Dark Pool Fetcher ────────────────────────────────────────────

def fetch_finra() -> dict:
    """Fetch dark pool short volume from FINRA (SPY as proxy)."""
    import urllib.request

    results = {}
    # Try to get recent FINRA short volume data
    # FINRA publishes daily files at regsho.finra.org
    today = datetime.now()

    for days_back in range(0, 5):
        dt = today - timedelta(days=days_back)
        if dt.weekday() >= 5:  # skip weekends
            continue
        date_str = dt.strftime("%Y%m%d")
        url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date_str}.txt"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                lines = resp.read().decode("utf-8").strip().split("\n")
                for line in lines:
                    parts = line.split("|")
                    if len(parts) >= 5 and parts[1] == "SPY":
                        short_vol = int(parts[2])
                        total_vol = int(parts[4])
                        if total_vol > 0:
                            pct = round((short_vol / total_vol) * 100, 1)
                            results["dark_pool"] = {
                                "value": pct,
                                "date": dt.strftime("%Y-%m-%d"),
                            }
                            break
                if "dark_pool" in results:
                    break
        except Exception as e:
            continue

    return results


# ── Signal Computation ─────────────────────────────────────────────────

def compute_status(value, green_range, yellow_range):
    """Compute status: green, yellow, red, or grey."""
    if value is None:
        return "grey"
    if green_range[0] <= value <= green_range[1]:
        return "green"
    if yellow_range[0] <= value <= yellow_range[1]:
        return "yellow"
    return "red"


def build_indicators(fred_data: dict, yahoo_data: dict, finra_data: dict, manual_data: dict) -> list:
    """Assemble the full indicator list with values, history, and status."""

    def get(source, key, field="value"):
        d = source.get(key, {})
        return d.get(field) if d else None

    def hist(source, key):
        d = source.get(key, {})
        return d.get("history", []) if d else []

    indicators = [
        # ── TIER 1: Credit & Funding ──
        {
            "id": "hy", "name": "HY OAS", "sub": "Credit Spread", "tier": 1,
            "val": get(fred_data, "hy_oas"), "u": "bps",
            "h": hist(fred_data, "hy_oas"),
            "g": [0, 400], "y": [400, 500],
            "th": "<400 clear · 400-500 watch · >500 alert",
            "desc": "High-yield option-adjusted spread. Widens 2-4 weeks before equity markets crack. Most reliable single early warning indicator.",
            "tv": "FRED:BAMLH0A0HYM2", "freq": "daily",
        },
        {
            "id": "mv", "name": "MOVE", "sub": "Bond Vol", "tier": 1,
            "val": get(fred_data, "move") or get(yahoo_data, "move"), "u": "",
            "h": hist(fred_data, "move") or hist(yahoo_data, "move"),
            "g": [0, 100], "y": [100, 130],
            "th": "<100 clear · 100-130 watch · >130 alert",
            "desc": "Treasury volatility index. When MOVE spikes above 120 while VIX stays below 20, the bond market sees something equities haven't priced.",
            "tv": "TVC:MOVE", "freq": "realtime",
        },
        {
            "id": "yc", "name": "2s10s", "sub": "Yield Curve", "tier": 1,
            "val": get(fred_data, "yield_curve"), "u": "%",
            "h": [],  # computed; no direct history yet
            "g": [0.1, 3], "y": [-0.2, 0.1],
            "th": ">0.1 clear · flat watch · <-0.2 inverted",
            "desc": "Yield curve spread. 8-for-8 recession predictor since 1968. Watch the speed of steepening after inversion.",
            "tv": "US10Y-US02Y", "freq": "realtime",
        },
        {
            "id": "sf", "name": "SOFR-FF", "sub": "Funding", "tier": 1,
            "val": get(fred_data, "sofr_ff"), "u": "bps",
            "h": [],
            "g": [-5, 8], "y": [8, 15],
            "th": "<8 clear · 8-15 watch · >15 alert",
            "desc": "Overnight funding stress. Widening above 10bps outside quarter-end signals liquidity seizing.",
            "tv": "—", "freq": "daily",
        },
        # ── TIER 2: Volatility ──
        {
            "id": "vv", "name": "VVIX/VIX", "sub": "Vol of Vol", "tier": 2,
            "val": get(yahoo_data, "vvix_vix"), "u": "",
            "h": hist(yahoo_data, "vvix_vix"),
            "g": [4.7, 6], "y": [6, 7],
            "th": "4.7-6 clear · 6-7 watch · >7 panic · <4.7 complacent",
            "desc": "Vol-of-vol ratio. Below 4.7 = maximum complacency, buy protection. Above 7.0 = panic. Speed of transition matters more than level.",
            "tv": "VVIX/VIX", "freq": "realtime",
        },
        {
            "id": "vt", "name": "VIX Term", "sub": "Structure", "tier": 2,
            "val": get(yahoo_data, "vix_term"), "u": "",
            "h": hist(yahoo_data, "vix_term"),
            "g": [-20, -1], "y": [-1, 1],
            "th": "contango clear · flat watch · backwardation alert",
            "desc": "VIX minus VIX3M. Contango is normal. Sustained backwardation beyond 2-3 days = market pricing imminent event.",
            "tv": "VIX-VIX3M", "freq": "realtime",
        },
        {
            "id": "pc", "name": "Put/Call", "sub": "Sentiment", "tier": 2,
            "val": None, "u": "",  # needs CBOE data; placeholder
            "h": [],
            "g": [0.7, 1], "y": [1, 1.2],
            "th": "0.7-1.0 clear · >1.2 panic · <0.7 complacent",
            "desc": "CBOE total put/call ratio. Spike from below 0.8 to above 1.0 = regime change from complacency to fear.",
            "tv": "USI:PCC", "freq": "realtime",
        },
        {
            "id": "dp", "name": "Dark Pool", "sub": "Short Vol", "tier": 2,
            "val": get(finra_data, "dark_pool"), "u": "%",
            "h": [],
            "g": [0, 42], "y": [42, 48],
            "th": "<42 clear · 42-48 watch · >48 distribution",
            "desc": "FINRA dark pool short volume (SPY proxy). Above 45% for multiple consecutive days = institutions distributing.",
            "tv": "—", "freq": "daily",
        },
        # ── TIER 3: Breadth & Regime ──
        {
            "id": "sx", "name": "SOX/SPX", "sub": "Semi Relative", "tier": 3,
            "val": get(yahoo_data, "sox_spx"), "u": "",
            "h": hist(yahoo_data, "sox_spx"),
            "g": [0.65, 1], "y": [0.55, 0.65],
            "th": "rising clear · flat watch · diverging alert",
            "desc": "Semiconductor relative performance vs S&P 500. Breakdown while SPX rises = cycle peaking.",
            "tv": "SOX/SPX", "freq": "realtime",
        },
        {
            "id": "dc", "name": "Def/Cyc", "sub": "Rotation", "tier": 3,
            "val": get(yahoo_data, "def_cyc"), "u": "",
            "h": [],
            "g": [0, 0.45], "y": [0.45, 0.52],
            "th": "cyclicals lead clear · defensives lead alert",
            "desc": "Defensive (XLU+XLP) vs cyclical (XLK+XLY) ratio. Defensives outperforming for 4+ weeks while SPX rises = smart money rotating.",
            "tv": "(XLU+XLP)/(XLK+XLY)", "freq": "realtime",
        },
        # ── TIER 4: Macro ──
        {
            "id": "dx", "name": "DXY", "sub": "Dollar", "tier": 4,
            "val": get(yahoo_data, "dxy"), "u": "",
            "h": hist(yahoo_data, "dxy"),
            "g": [90, 105], "y": [105, 110],
            "th": "<105 clear · 105-110 watch · >110 stress",
            "desc": "Dollar index. Rapidly strengthening dollar = global liquidity drain for every EM borrower and multinational.",
            "tv": "TVC:DXY", "freq": "realtime",
        },
        {
            "id": "oi", "name": "Oil 60d", "sub": "Velocity", "tier": 4,
            "val": get(yahoo_data, "oil_velocity"), "u": "%",
            "h": hist(yahoo_data, "oil_velocity"),
            "g": [-30, 15], "y": [15, 30],
            "th": "<15% clear · 15-30% watch · >30% recession signal",
            "desc": "60-day rate of change in crude. Oil rising 30%+ in 60 days preceded 7 of 9 recessions.",
            "tv": "CL1!", "freq": "realtime",
        },
        {
            "id": "cl", "name": "Claims", "sub": "4wk MA", "tier": 4,
            "val": get(fred_data, "claims"), "u": "K",
            "h": hist(fred_data, "claims"),
            "g": [0, 250], "y": [250, 300],
            "th": "<250K clear · 250-300K watch · >300K recession",
            "desc": "Initial jobless claims 4-week MA. Rising 10%+ from cycle low = recession started. Every time since 1967. Zero false positives.",
            "tv": "FRED:IC4WSA", "freq": "weekly",
        },
        {
            "id": "fb", "name": "Fed B/S", "sub": "Liquidity", "tier": 4,
            "val": get(fred_data, "fed_bs"), "u": "$T",
            "h": hist(fred_data, "fed_bs"),
            "g": [6.5, 9], "y": [6, 6.5],
            "th": "stable clear · draining watch · depleted alert",
            "desc": "Federal Reserve balance sheet. QT drains liquidity with 3-6 month lag. RRP near zero = liquidity cushion gone.",
            "tv": "FRED:WALCL", "freq": "weekly",
        },
        # ── TIER 5: AI Stack ──
        {
            "id": "cx", "name": "Capex", "sub": "Hyperscaler", "tier": 5,
            "val": None, "u": "", "h": [],
            "g": [0, 0], "y": [0, 0],
            "th": "all raising clear · one flat watch · two+ cutting alert",
            "desc": manual_data.get("capex", {}).get("desc", "Quarterly hyperscaler capex commentary."),
            "tv": "—", "freq": "quarterly",
            "so": manual_data.get("capex", {}).get("status", "grey"),
        },
        {
            "id": "nl", "name": "NVDA Lead", "sub": "Supply/Demand", "tier": 5,
            "val": None, "u": "mo", "h": [],
            "g": [0, 0], "y": [0, 0],
            "th": ">6mo clear · 3-6mo watch · <3mo cycle peak",
            "desc": manual_data.get("nvda_lead", {}).get("desc", "GPU delivery lead time assessment."),
            "tv": "—", "freq": "qualitative",
            "so": manual_data.get("nvda_lead", {}).get("status", "grey"),
        },
        {
            "id": "ai", "name": "AI Labs", "sub": "Revenue", "tier": 5,
            "val": None, "u": "", "h": [],
            "g": [0, 0], "y": [0, 0],
            "th": "all growing clear · one miss watch · multiple alert",
            "desc": manual_data.get("ai_labs", {}).get("desc", "AI lab revenue and growth tracking."),
            "tv": "—", "freq": "qualitative",
            "so": manual_data.get("ai_labs", {}).get("status", "grey"),
        },
        {
            "id": "tw", "name": "Taiwan", "sub": "Strait Risk", "tier": 5,
            "val": None, "u": "", "h": [],
            "g": [0, 0], "y": [0, 0],
            "th": "routine clear · rhetoric watch · military alert",
            "desc": manual_data.get("taiwan", {}).get("desc", "Taiwan Strait geopolitical risk assessment."),
            "tv": "—", "freq": "qualitative",
            "so": manual_data.get("taiwan", {}).get("status", "grey"),
        },
    ]

    # Compute status for each indicator
    for ind in indicators:
        if "so" not in ind:
            ind["so"] = compute_status(ind["val"], ind["g"], ind["y"])

    return indicators


# ── History Management ─────────────────────────────────────────────────

def save_daily_snapshot(indicators: list):
    """Save today's values to history folder."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot = {}
    for ind in indicators:
        if ind["val"] is not None:
            snapshot[ind["id"]] = ind["val"]
    
    snapshot_file = HISTORY_DIR / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"  Saved snapshot: {snapshot_file}")

    # Cleanup: keep only last 120 days
    cutoff = datetime.now() - timedelta(days=120)
    for f in sorted(HISTORY_DIR.glob("*.json")):
        try:
            file_date = datetime.strptime(f.stem, "%Y-%m-%d")
            if file_date < cutoff:
                f.unlink()
                print(f"  Cleaned: {f.name}")
        except ValueError:
            pass


def load_history_into_indicators(indicators: list):
    """Load historical snapshots and populate sparkline data where API history is missing."""
    files = sorted(HISTORY_DIR.glob("*.json"))[-SPARKLINE_DAYS:]
    if not files:
        return

    history_data = {}
    for f in files:
        try:
            with open(f) as fh:
                day = json.load(fh)
                for k, v in day.items():
                    history_data.setdefault(k, []).append(v)
        except Exception:
            pass

    for ind in indicators:
        if not ind["h"] and ind["id"] in history_data:
            ind["h"] = history_data[ind["id"]]


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Market EWS Data Pipeline")
    parser.add_argument("--fred-key", default=os.environ.get("FRED_API_KEY", ""), help="FRED API key")
    args = parser.parse_args()

    print("=" * 50)
    print(f"Market EWS Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # Load manual data
    manual_data = {}
    if MANUAL_FILE.exists():
        with open(MANUAL_FILE) as f:
            manual_data = json.load(f)
        print(f"✓ Loaded manual data: {len(manual_data)} entries")

    # Fetch FRED data
    fred_data = {}
    if args.fred_key:
        print("\nFetching FRED data...")
        fred_data = fetch_fred(args.fred_key)
        print(f"✓ FRED: {len(fred_data)} series")
    else:
        print("\n⚠ No FRED API key — skipping FRED data")

    # Fetch Yahoo data
    print("\nFetching Yahoo Finance data...")
    yahoo_data = fetch_yahoo()
    print(f"✓ Yahoo: {len(yahoo_data)} series")

    # Fetch FINRA data
    print("\nFetching FINRA dark pool data...")
    finra_data = fetch_finra()
    print(f"✓ FINRA: {len(finra_data)} series")

    # Build indicators
    print("\nBuilding indicators...")
    indicators = build_indicators(fred_data, yahoo_data, finra_data, manual_data)

    # Load history and fill gaps
    load_history_into_indicators(indicators)

    # Save daily snapshot
    save_daily_snapshot(indicators)

    # Compute summary
    status_counts = {"green": 0, "yellow": 0, "red": 0, "grey": 0}
    for ind in indicators:
        status_counts[ind["so"]] = status_counts.get(ind["so"], 0) + 1

    total = status_counts["green"] + status_counts["yellow"] + status_counts["red"]
    score = round(((status_counts["green"] * 2 + status_counts["yellow"]) / (total * 2)) * 100) if total > 0 else 50

    # Write output
    output = {
        "updated": datetime.now().isoformat(),
        "score": score,
        "counts": status_counts,
        "indicators": indicators,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n{'=' * 50}")
    print(f"Score: {score}/100")
    print(f"Green: {status_counts['green']} | Yellow: {status_counts['yellow']} | Red: {status_counts['red']} | Grey: {status_counts['grey']}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
