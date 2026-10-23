"""Eligible universe (IBEX 35 + Euro Stoxx 50 + Nasdaq-100) and the
"consensus" popularity model of what business/marketing students would hold.

Scraping only happens in ``--mode fetch``; every other mode reads the cached
CSV written by the fetch so the analysis is reproducible offline.
"""
from __future__ import annotations

import io
import logging

import pandas as pd

from . import config

log = logging.getLogger(__name__)

UA = {"User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
      "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
      "Accept-Language": "en-US,en;q=0.9"}

WIKI = {
    "IBEX": "https://en.wikipedia.org/wiki/IBEX_35",
    "SX5E": "https://en.wikipedia.org/wiki/EURO_STOXX_50",
    "NDX": "https://en.wikipedia.org/wiki/Nasdaq-100",
}
NASDAQ100_API = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
EXPECTED_COUNT = {"IBEX": (34, 36), "SX5E": (49, 51), "NDX": (99, 103)}


# --------------------------------------------------------------------------
# Popularity model ("consensus basket")
# --------------------------------------------------------------------------
# Relative likelihood that a business/marketing student in a Spanish contest
# puts the name in a portfolio. Scale is arbitrary (only ratios matter).
# Names not listed get BASE_POPULARITY. The consensus basket is every name
# with popularity >= CONSENSUS_MIN, weighted by popularity.
POPULARITY = {
    # US mega-cap tech / AI / hype
    "NVDA": 10, "TSLA": 8, "AAPL": 8, "SPCX": 7, "MSFT": 7, "AMZN": 7,
    "GOOGL": 6, "META": 6, "PLTR": 6, "AMD": 5, "NFLX": 4, "AVGO": 3,
    "MSTR": 3, "MU": 3, "INTC": 2.5, "ARM": 2, "COST": 2, "WMT": 2,
    "RKLB": 2, "CRWV": 2, "SNDK": 2, "TTWO": 2, "APP": 2,
    "SBUX": 1.5, "PYPL": 1.5, "ABNB": 1.5, "SHOP": 1.5, "MELI": 1.5,
    "CRWD": 1.5, "NBIS": 1.5, "PEP": 1.2, "BKNG": 1.2, "ADBE": 1.2,
    "QCOM": 1.2, "PANW": 1.0, "DASH": 1.0, "PDD": 1.0,
    "MRNA": 2.5,   # 7x in a year (+177% on Aug 19 2026): news-driven hype

    "CSCO": 1.0, "GOOG": 1.0, "TMUS": 0.8, "LITE": 0.8, "ALAB": 0.8,
    "AMAT": 0.8, "LRCX": 0.8, "MRVL": 0.8, "MAR": 0.8, "DDOG": 0.8,
    # Spanish blue chips (home bias)
    "ITX.MC": 7, "SAN.MC": 7, "IBE.MC": 5, "BBVA.MC": 5, "TEF.MC": 4,
    "REP.MC": 4, "IDR.MC": 4, "CABK.MC": 3, "IAG.MC": 3, "AENA.MC": 2.5,
    "FER.MC": 2, "SAB.MC": 2, "AMS.MC": 1.5, "ACS.MC": 1.5, "GRF.MC": 1.5,
    "PUIG.MC": 1.5, "SLR.MC": 1.5, "ELE.MC": 1.0, "NTGY.MC": 1.0,
    "RED.MC": 1.0, "MAP.MC": 1.0, "CLNX.MC": 1.0, "ANA.MC": 1.0,
    "ANE.MC": 1.0, "BKT.MC": 1.0, "MTS.MC": 0.8,
    # Euro Stoxx brands and themes
    "ASML.AS": 5, "MC.PA": 4, "RHM.DE": 3.5, "RACE.MI": 3, "OR.PA": 2.5,
    "SAP.DE": 2.5, "AIR.PA": 2.5, "ADS.DE": 2.5, "RMS.PA": 2, "BMW.DE": 2,
    "SIE.DE": 1.5, "VOW3.DE": 1.5, "MBG.DE": 1.5, "ENR.DE": 1.5,
    "TTE.PA": 1.0, "ALV.DE": 1.0, "SAN.PA": 1.0, "ABI.BR": 1.0, "EL.PA": 1.0,
    "SU.PA": 1.0, "IFX.DE": 1.0, "ADYEN.AS": 1.0, "UCG.MI": 1.0,
    "BNP.PA": 1.0, "DTE.DE": 1.0, "ENEL.MI": 1.0, "SAF.PA": 0.8,
}
BASE_POPULARITY = 0.3
CONSENSUS_MIN = 3.0


def popularity_vector(tickers: list[str]) -> pd.Series:
    return pd.Series({t: float(POPULARITY.get(t, BASE_POPULARITY)) for t in tickers})


def consensus_weights(tickers: list[str]) -> pd.Series:
    """Popularity-weighted basket of the names students most likely hold."""
    pop = popularity_vector(tickers)
    members = pop[pop >= CONSENSUS_MIN]
    return members / members.sum()


# --------------------------------------------------------------------------
# Constituent scraping (network; fetch mode only)
# --------------------------------------------------------------------------
def _get(url: str, timeout: int = 30):
    import requests
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r


def _wiki_table(url: str, must_have: set[str]) -> pd.DataFrame:
    tables = pd.read_html(io.StringIO(_get(url).text))
    for t in tables:
        cols = {str(c).strip() for c in t.columns}
        if must_have <= cols:
            return t
    raise ValueError(f"no table with columns {must_have} at {url}")


def _scrape_ibex() -> pd.DataFrame:
    t = _wiki_table(WIKI["IBEX"], {"Ticker", "Company"})
    t = t[t["Ticker"].astype(str).str.endswith(".MC")]
    return pd.DataFrame({"ticker": t["Ticker"].str.strip(), "name": t["Company"],
                         "index": "IBEX", "currency": "EUR",
                         "sector": t.get("Sector", "")})


def _scrape_sx5e() -> pd.DataFrame:
    t = _wiki_table(WIKI["SX5E"], {"Ticker", "Name"})
    t = t[t["Ticker"].astype(str).str.contains(r"\.")]
    tick = t["Ticker"].str.strip().replace(config.TICKER_FIXES)
    return pd.DataFrame({"ticker": tick, "name": t["Name"], "index": "SX5E",
                         "currency": "EUR", "sector": t.get("Sector", "")})


def _scrape_ndx() -> pd.DataFrame:
    try:
        rows = _get(NASDAQ100_API).json()["data"]["data"]["rows"]
        df = pd.DataFrame(rows)
        return pd.DataFrame({"ticker": df["symbol"].str.strip(),
                             "name": df["companyName"], "index": "NDX",
                             "currency": "USD", "sector": ""})
    except Exception as e:  # fall back to Wikipedia
        log.warning("Nasdaq API failed (%s); trying Wikipedia", e)
    for cols in ({"Ticker", "Company"}, {"Symbol", "Company"}):
        try:
            t = _wiki_table(WIKI["NDX"], cols)
            col = "Ticker" if "Ticker" in t.columns else "Symbol"
            return pd.DataFrame({"ticker": t[col].str.replace(".", "-", regex=False),
                                 "name": t["Company"], "index": "NDX",
                                 "currency": "USD", "sector": t.get("GICS Sector", "")})
        except Exception:
            continue
    raise ValueError("could not scrape Nasdaq-100")


def scrape_constituents() -> tuple[pd.DataFrame, dict]:
    """Scrape the three indices, falling back to the checked-in snapshot.

    Returns the raw (non-deduplicated) rows and a report of which source was
    used and how it differs from the snapshot.
    """
    snap = pd.read_csv(config.SNAPSHOT_CSV)
    out, report = [], {}
    for idx, fn in (("IBEX", _scrape_ibex), ("SX5E", _scrape_sx5e), ("NDX", _scrape_ndx)):
        snap_i = snap[snap["index"] == idx]
        try:
            df = fn()
            lo, hi = EXPECTED_COUNT[idx]
            if not lo <= len(df) <= hi:
                raise ValueError(f"{len(df)} rows scraped, expected {lo}-{hi}")
            src = "scraped"
        except Exception as e:
            log.warning("%s scrape failed (%s); using snapshot", idx, e)
            df, src = snap_i.copy(), f"snapshot (scrape failed: {e})"
        added = sorted(set(df["ticker"]) - set(snap_i["ticker"]))
        removed = sorted(set(snap_i["ticker"]) - set(df["ticker"]))
        report[idx] = {"source": src, "count": int(len(df)),
                       "added_vs_snapshot": added, "removed_vs_snapshot": removed}
        out.append(df)
    return pd.concat(out, ignore_index=True), report


def build_universe(raw: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate: one row per Yahoo ticker, EUR listing kept for cross-listings."""
    raw = raw.copy()
    raw["ticker"] = raw["ticker"].replace(config.TICKER_FIXES)
    # Cross-listed USD lines -> fold into the EUR line's index membership.
    for usd, eur in config.CROSS_LISTINGS.items():
        if usd in set(raw["ticker"]) and eur in set(raw["ticker"]):
            raw.loc[raw["ticker"] == usd, "ticker"] = eur
    uni = (raw.groupby("ticker", sort=False)
              .agg(name=("name", "first"),
                   index=("index", lambda s: "+".join(sorted(set(s)))),
                   currency=("currency", lambda s: "EUR" if "EUR" in set(s) else "USD"),
                   sector=("sector", "first"))
              .reset_index())
    uni["popularity"] = uni["ticker"].map(lambda t: POPULARITY.get(t, BASE_POPULARITY))
    return uni
