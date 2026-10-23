"""Data module: download (fetch mode), cache loading, EUR returns and
per-stock features (vols, implied vol, earnings, ex-dividends, consensus beta).

Network access is confined to ``fetch_all``; it writes everything the
analysis needs under ``data/cache`` so the period-1 / period-2 runs are
offline and reproducible.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, universe

log = logging.getLogger(__name__)

INFO_KEYS = ("currency", "longName", "shortName", "exchange", "quoteType",
             "marketCap", "beta", "sector", "industry", "regularMarketPrice",
             "previousClose", "exDividendDate", "dividendRate", "dividendYield",
             "lastDividendValue", "lastDividendDate", "earningsTimestamp",
             "earningsTimestampStart", "earningsTimestampEnd",
             "isEarningsDateEstimate", "earningsCallTimestampStart")

EXCHANGE_TZ = {".MC": "Europe/Madrid", ".PA": "Europe/Paris", ".DE": "Europe/Berlin",
               ".AS": "Europe/Amsterdam", ".MI": "Europe/Rome", ".BR": "Europe/Brussels",
               ".HE": "Europe/Helsinki", ".IR": "Europe/Dublin", ".LS": "Europe/Lisbon"}


def exchange_tz(ticker: str) -> str:
    for suf, tz in EXCHANGE_TZ.items():
        if ticker.endswith(suf):
            return tz
    return "America/New_York"


def is_us(ticker: str) -> bool:
    return exchange_tz(ticker) == "America/New_York"


# ==========================================================================
# 1. Fetch (network)
# ==========================================================================
def _retry(fn, tries=3, wait=2.0):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # yfinance raises many types (rate limits, parse errors)
            if i == tries - 1:
                raise
            log.info("retry after %s", e)
            time.sleep(wait * (2 ** i))


def _download_prices(tickers: list[str], start: dt.date, end: dt.date | None):
    import yfinance as yf
    kw = dict(start=start.isoformat(), end=(end + dt.timedelta(days=1)).isoformat() if end else None,
              auto_adjust=False, actions=True, group_by="column", threads=True,
              progress=False, interval="1d")
    df = yf.download(tickers, **kw)
    fields = {}
    for f in ("Close", "Adj Close", "Dividends", "Stock Splits"):
        fields[f] = df[f].reindex(columns=tickers) if f in df.columns.get_level_values(0) \
            else pd.DataFrame(index=df.index, columns=tickers, dtype=float)
    # Retry tickers that came back empty, one by one.
    missing = [t for t in tickers if fields["Close"][t].dropna().empty]
    for t in missing:
        try:
            d1 = _retry(lambda: yf.download(t, **{**kw, "threads": False}))
            if d1 is not None and not d1.empty:
                for f in fields:
                    if f in d1.columns.get_level_values(0):
                        col = d1[f]
                        col = col.iloc[:, 0] if isinstance(col, pd.DataFrame) else col
                        fields[f] = fields[f].reindex(fields[f].index.union(col.index))
                        fields[f][t] = col
        except Exception as e:
            log.warning("download failed for %s: %s", t, e)
    for f in fields:
        fields[f].index = pd.to_datetime(fields[f].index).tz_localize(None).normalize()
        fields[f].index.name = "date"
    return fields


def _bs_price(s, k, t, r, vol, call):
    from scipy.stats import norm
    d1 = (math.log(s / k) + (r + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    if call:
        return s * norm.cdf(d1) - k * math.exp(-r * t) * norm.cdf(d2)
    return k * math.exp(-r * t) * norm.cdf(-d2) - s * norm.cdf(-d1)


def _implied_vol(price, s, k, t, r, call):
    from scipy.optimize import brentq
    intrinsic = max(0.0, (s - k) if call else (k - s))
    if not price or price <= intrinsic + 1e-6 or t <= 0:
        return None
    try:
        return brentq(lambda v: _bs_price(s, k, t, r, v, call) - price, 1e-3, 6.0, xtol=1e-5)
    except Exception:
        return None


def _atm_iv(tk, expiry: str, spot: float, asof: dt.date) -> dict | None:
    """ATM implied vol for one expiry: own Black-Scholes inversion of mid
    prices for the strikes bracketing spot, with Yahoo's IV as a fallback."""
    chain = tk.option_chain(expiry)
    t = max((dt.date.fromisoformat(expiry) - asof).days, 1) / 365.0
    ivs, yivs = [], []
    for df, call in ((chain.calls, True), (chain.puts, False)):
        if df is None or df.empty:
            continue
        df = df.assign(dist=(df["strike"] - spot).abs()).nsmallest(4, "dist")
        for _, row in df.iterrows():
            bid, ask = row.get("bid", 0) or 0, row.get("ask", 0) or 0
            mid = 0.5 * (bid + ask) if bid > 0 and ask > 0 else (row.get("lastPrice") or 0)
            iv = _implied_vol(float(mid), spot, float(row["strike"]), t, 0.04, call)
            if iv and 0.03 < iv < 4:
                ivs.append(iv)
            y = row.get("impliedVolatility")
            if y and 0.03 < y < 4:
                yivs.append(float(y))
    if not ivs and not yivs:
        return None
    return {"expiry": expiry, "iv": float(np.median(ivs)) if ivs else None,
            "iv_yahoo": float(np.median(yivs)) if yivs else None, "t_years": t}


def _ticker_meta(ticker: str, asof: dt.date) -> dict:
    import yfinance as yf
    tk = yf.Ticker(ticker)
    m: dict = {"ticker": ticker, "errors": {}}
    try:
        info = _retry(tk.get_info)
        m["info"] = {k: info.get(k) for k in INFO_KEYS}
    except Exception as e:
        m["errors"]["info"] = str(e)
        m["info"] = {}
    try:
        cal = _retry(lambda: tk.calendar) or {}
        m["calendar"] = json.loads(json.dumps(cal, default=str))
    except Exception as e:
        m["errors"]["calendar"] = str(e)
    try:
        ed = _retry(lambda: tk.get_earnings_dates(limit=24))
        rows = []
        if ed is not None:
            if "Event Type" in ed.columns:
                ed = ed[ed["Event Type"].astype(str).str.contains("Earn", case=False)]
            for ts, r in ed.iterrows():
                rows.append({"ts": pd.Timestamp(ts).isoformat(),
                             "eps_est": _num(r.get("EPS Estimate")),
                             "eps_rep": _num(r.get("Reported EPS")),
                             "surprise": _num(r.get("Surprise(%)"))})
        m["earnings_dates"] = rows
    except Exception as e:
        m["errors"]["earnings_dates"] = str(e)
    if is_us(ticker):
        try:
            spot = m["info"].get("regularMarketPrice") or m["info"].get("previousClose")
            exps = list(_retry(lambda: tk.options) or [])
            m["iv"] = {}
            for label, target in (("p1", config.P1_END), ("p2", config.P2_END)):
                cands = [e for e in exps if dt.date.fromisoformat(e) >= target]
                if spot and cands:
                    res = _atm_iv(tk, cands[0], float(spot), asof)
                    if res:
                        m["iv"][label] = res
        except Exception as e:
            m["errors"]["options"] = str(e)
    return m


def _num(x):
    try:
        x = float(x)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def _nasdaq_json(url: str):
    import requests
    r = requests.get(url, headers=universe.UA, timeout=30)
    r.raise_for_status()
    return r.json()


def _fetch_nasdaq_earnings(start: dt.date, end: dt.date) -> dict:
    """Second earnings-date source for US names: Nasdaq's earnings calendar."""
    out = {}
    for d in pd.bdate_range(start, end):
        ds = d.date().isoformat()
        try:
            js = _retry(lambda: _nasdaq_json(f"https://api.nasdaq.com/api/calendar/earnings?date={ds}"))
            rows = ((js.get("data") or {}).get("rows")) or []
            out[ds] = [{"symbol": r.get("symbol"), "time": r.get("time"),
                        "fiscalQuarterEnding": r.get("fiscalQuarterEnding")} for r in rows]
        except Exception as e:
            out[ds] = {"error": str(e)}
        time.sleep(0.3)
    return out


def _fetch_nasdaq_dividends(tickers: list[str]) -> dict:
    """Declared (incl. upcoming) dividends for US names from Nasdaq."""
    out = {}
    for t in tickers:
        try:
            js = _retry(lambda: _nasdaq_json(
                f"https://api.nasdaq.com/api/quote/{t}/dividends?assetclass=stocks"))
            rows = ((((js.get("data") or {}).get("dividends")) or {}).get("rows")) or []
            out[t] = rows[:8]
        except Exception as e:
            out[t] = {"error": str(e)}
        time.sleep(0.2)
    return out


def fetch_all(cache_dir: Path = config.CACHE_DIR, end: dt.date | None = None,
              workers: int = 4) -> dict:
    """Download everything the analysis needs and write it to ``cache_dir``."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    asof = end or today
    # One extra year beyond the 2y bootstrap sample: more past earnings
    # reactions for the move distribution and a warm EWMA.
    start = asof - dt.timedelta(days=365 * (config.HISTORY_YEARS + 1) + config.HISTORY_BUFFER_DAYS)
    raw, uni_report = universe.scrape_constituents()
    uni = universe.build_universe(raw)
    uni.to_csv(cache_dir / "universe.csv", index=False)
    tickers = uni["ticker"].tolist()

    log.info("downloading prices for %d tickers + FX", len(tickers))
    px = _download_prices(tickers + [config.FX_TICKER], start, end)
    for f, name in (("Close", "close"), ("Adj Close", "adjclose"),
                    ("Dividends", "dividends"), ("Stock Splits", "splits")):
        px[f].to_csv(cache_dir / f"{name}.csv.gz", float_format="%.6f")
    failed = [t for t in tickers + [config.FX_TICKER] if px["Close"][t].dropna().empty]

    log.info("fetching per-ticker metadata (earnings, dividends, options)")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        metas = list(ex.map(lambda t: _ticker_meta(t, asof), tickers))
    meta = {m["ticker"]: m for m in metas}
    (cache_dir / "meta.json").write_text(json.dumps(meta, indent=1, default=str))

    us = [t for t in tickers if is_us(t)]
    log.info("fetching Nasdaq earnings calendar + dividends (second source)")
    ncal = _fetch_nasdaq_earnings(asof - dt.timedelta(days=3), config.P2_END + dt.timedelta(days=3))
    (cache_dir / "nasdaq_earnings.json").write_text(json.dumps(ncal, indent=1))
    ndiv = _fetch_nasdaq_dividends(us)
    (cache_dir / "nasdaq_dividends.json").write_text(json.dumps(ndiv, indent=1))

    last = px["Close"].dropna(how="all").index.max()
    report = {
        "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "last_price_date": str(last.date()) if pd.notna(last) else None,
        "universe": uni_report, "n_tickers": len(tickers),
        "failed_downloads": failed,
        "stale_tickers": [t for t in tickers if t not in failed and
                          px["Close"][t].dropna().index.max() < last - pd.Timedelta(days=4)],
        "meta_errors": {t: m["errors"] for t, m in meta.items() if m["errors"]},
        "nasdaq_calendar_errors": [d for d, v in ncal.items() if isinstance(v, dict)],
        "nasdaq_dividend_errors": [t for t, v in ndiv.items() if isinstance(v, dict)],
    }
    (cache_dir / "fetch_report.json").write_text(json.dumps(report, indent=1))
    return report


# ==========================================================================
# 2. Cache loading and EUR prices / returns
# ==========================================================================
@dataclass
class MarketData:
    universe: pd.DataFrame            # index: ticker
    close: pd.DataFrame               # local ccy, split-adjusted, NOT dividend-adjusted
    adj: pd.DataFrame                 # local ccy, total-return adjusted
    dividends: pd.DataFrame           # local ccy cash dividends on ex-dates
    fx: pd.Series                     # USD per EUR
    meta: dict
    nasdaq_cal: dict
    nasdaq_div: dict
    fetch_report: dict
    failed: list = field(default_factory=list)


def _read_wide(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index).normalize()
    return df.apply(pd.to_numeric, errors="coerce")


def load_market_data(cache_dir: Path = config.CACHE_DIR) -> MarketData:
    uni = pd.read_csv(cache_dir / "universe.csv").set_index("ticker")
    close = _read_wide(cache_dir / "close.csv.gz")
    adj = _read_wide(cache_dir / "adjclose.csv.gz")
    divs = _read_wide(cache_dir / "dividends.csv.gz").fillna(0.0)
    fx = close[config.FX_TICKER].dropna()
    rd = lambda n, d: json.loads((cache_dir / n).read_text()) if (cache_dir / n).exists() else d
    report = rd("fetch_report.json", {})
    failed = [t for t in uni.index if t not in close.columns or close[t].dropna().empty]
    keep = [t for t in uni.index if t not in failed]
    return MarketData(universe=uni.loc[keep], close=close[keep], adj=adj[keep],
                      dividends=divs.reindex(columns=keep).fillna(0.0), fx=fx,
                      meta=rd("meta.json", {}), nasdaq_cal=rd("nasdaq_earnings.json", {}),
                      nasdaq_div=rd("nasdaq_dividends.json", {}), fetch_report=report,
                      failed=failed)


def _clean_spikes(px: pd.DataFrame, thresh: float = 0.35) -> pd.DataFrame:
    """Remove one-day Yahoo glitches: a jump that fully reverses next day."""
    lr = np.log(px).diff()
    spike = (lr.abs() > thresh) & (lr.shift(-1).abs() > thresh) & \
            (np.sign(lr) != np.sign(lr.shift(-1))) & ((lr + lr.shift(-1)).abs() < thresh / 3)
    return px.mask(spike).ffill(limit=1)


@dataclass
class Prices:
    dates: pd.DatetimeIndex
    close_eur: pd.DataFrame          # price-only, EUR
    close_local: pd.DataFrame
    ret_eur: pd.DataFrame            # daily total-return log returns, EUR
    fx: pd.Series
    asof: pd.Timestamp


def build_prices(md: MarketData, asof: dt.date | None = None) -> Prices:
    """Align all listings on one weekday calendar and convert to EUR.

    Holidays are forward-filled (zero return). USD names are converted at
    the EURUSD=X close of the same day.
    """
    close = md.close.copy()
    adj = md.adj.copy()
    if asof is not None:
        close, adj = close.loc[:pd.Timestamp(asof)], adj.loc[:pd.Timestamp(asof)]
    idx = close.index[close.index.dayofweek < 5]
    idx = idx[close.loc[idx].notna().sum(axis=1) > 0.3 * close.shape[1]]
    close = _clean_spikes(close.loc[idx]).ffill(limit=5)
    adj = _clean_spikes(adj.reindex(idx)).ffill(limit=5)
    adj = adj.fillna(close)
    fx = md.fx.reindex(idx).ffill().bfill()
    usd = [t for t in close.columns if md.universe.loc[t, "currency"] == "USD"]
    close_eur, adj_eur = close.copy(), adj.copy()
    close_eur[usd] = close[usd].div(fx, axis=0)
    adj_eur[usd] = adj[usd].div(fx, axis=0)
    ret = np.log(adj_eur).diff()
    return Prices(dates=idx, close_eur=close_eur, close_local=close, ret_eur=ret.iloc[1:],
                  fx=fx, asof=idx.max())


def realized_gross(prices: Prices, d0: dt.date, d1: dt.date) -> pd.Series:
    """Price-only EUR gross return between two closes (contest scoring)."""
    p0 = prices.close_eur.loc[:pd.Timestamp(d0)].iloc[-1]
    p1 = prices.close_eur.loc[:pd.Timestamp(d1)].iloc[-1]
    return p1 / p0


# ==========================================================================
# 3. Features
# ==========================================================================
def ewma_vol(r: pd.DataFrame, lam: float) -> pd.DataFrame:
    """Daily EWMA vol using information up to t-1 (RiskMetrics recursion)."""
    v = r.pow(2).ewm(alpha=1 - lam, adjust=False, ignore_na=True).mean()
    seed = r.iloc[:30].var()
    v = v.fillna(seed)
    return np.sqrt(v.shift(1).fillna(seed))


def _trading_on_or_after(days: pd.DatetimeIndex, d: pd.Timestamp) -> pd.Timestamp | None:
    pos = days.searchsorted(d)
    return days[pos] if pos < len(days) else None


def _future_bdays(asof: pd.Timestamp, until: dt.date) -> pd.DatetimeIndex:
    return pd.bdate_range(asof + pd.Timedelta(days=1), pd.Timestamp(until) + pd.Timedelta(days=10))


def _timing_from_local_hour(ts_local: pd.Timestamp, us: bool) -> str:
    h = ts_local.hour + ts_local.minute / 60
    if us and ts_local.hour == 0 and ts_local.minute == 0:
        return "unknown"
    if h < (9.5 if us else 9.0):
        return "BMO"
    # Yahoo's calendar shifts future US times by an hour across DST (a 4 PM
    # release shows as 3 PM EST), so 3 PM already counts as after the close.
    if h >= (15.0 if us else 17.5):
        return "AMC"
    return "DMH"   # during market hours: reaction the same day


def _reaction_day(announce: pd.Timestamp, timing: str, cal: pd.DatetimeIndex) -> pd.Timestamp | None:
    d = announce.normalize()
    if timing == "AMC":
        return _trading_on_or_after(cal, d + pd.Timedelta(days=1))
    return _trading_on_or_after(cal, d)


def _period_of(day: pd.Timestamp | None) -> int:
    if day is None:
        return 0
    d = day.date()
    if config.P1_START <= d <= config.P1_END:
        return 1
    if config.P2_START <= d <= config.P2_END:
        return 2
    return 0


def _nasdaq_lookup(ncal: dict) -> dict:
    """symbol -> list of (date, timing) from the Nasdaq calendar."""
    out: dict = {}
    tmap = {"time-pre-market": "BMO", "time-after-hours": "AMC"}
    for ds, rows in ncal.items():
        if not isinstance(rows, list):
            continue
        for r in rows:
            if r.get("symbol"):
                out.setdefault(r["symbol"], []).append(
                    (pd.Timestamp(ds), tmap.get(r.get("time"), "unknown")))
    return out


def _load_overrides(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path, comment="#", dtype=str).fillna("")
    return pd.DataFrame()


def earnings_table(md: MarketData, prices: Prices) -> tuple[pd.DataFrame, dict]:
    """Next earnings event per stock + history of earnings-reaction days.

    Sources, in order of precedence: manual overrides (verified against
    company IR pages), Yahoo earnings calendar (with time of day), Yahoo
    quote calendar, Yahoo quote summary timestamps. Nasdaq's calendar is the
    independent second source for US names.
    """
    asof = prices.asof
    hist_cal = prices.dates
    fut_cal = hist_cal.append(_future_bdays(asof, config.P2_END))
    nas = _nasdaq_lookup(md.nasdaq_cal)
    ovr = _load_overrides(config.EARNINGS_OVERRIDES_CSV)
    rows, history = [], {}
    for t in md.universe.index:
        m = md.meta.get(t, {})
        us = is_us(t)
        tz = exchange_tz(t)
        past, future = [], []
        for e in m.get("earnings_dates", []) or []:
            ts = pd.Timestamp(e["ts"])
            ts = ts.tz_convert(tz) if ts.tzinfo else ts.tz_localize("America/New_York").tz_convert(tz)
            timing = _timing_from_local_hour(ts, us)
            naive = ts.tz_localize(None)
            (past if naive.normalize() <= asof else future).append((naive, timing))
        # Historical reaction days (for the earnings-move distribution).
        hd = []
        for ts, timing in past:
            if timing == "unknown":
                d0 = _trading_on_or_after(hist_cal, ts.normalize())
                d1 = _trading_on_or_after(hist_cal, ts.normalize() + pd.Timedelta(days=1))
                hd.append((d0, d1))
            else:
                hd.append((_reaction_day(ts, timing, hist_cal), None))
        history[t] = [(a, b) for a, b in hd if a is not None]

        # Candidate next dates from each source.
        src = {}
        fut = [(ts, tm) for ts, tm in future if ts.normalize() <= pd.Timestamp(config.P2_END) + pd.Timedelta(days=30)]
        if fut:
            src["yahoo_cal"] = min(fut)
        cal = m.get("calendar") or {}
        cdates = [pd.Timestamp(x) for x in (cal.get("Earnings Date") or []) if x]
        cdates = [d for d in cdates if d > asof - pd.Timedelta(days=1)]
        if cdates:
            src["yahoo_quote"] = (min(cdates), "unknown")
        info = m.get("info") or {}
        if info.get("earningsTimestamp"):
            ts = pd.Timestamp(info["earningsTimestamp"], unit="s", tz="UTC").tz_convert(tz)
            if ts.tz_localize(None).normalize() > asof - pd.Timedelta(days=1):
                src["yahoo_ts"] = (ts.tz_localize(None), _timing_from_local_hour(ts, us))
        nd = [x for x in nas.get(t, []) if x[0] > asof - pd.Timedelta(days=1)]
        if nd:
            src["nasdaq"] = min(nd)
        o = ovr[ovr["ticker"] == t] if not ovr.empty else ovr
        ovr_row = o.iloc[0] if len(o) else None
        if ovr_row is not None:
            src["override"] = (pd.Timestamp(ovr_row["date"]), ovr_row.get("timing") or "unknown")

        primary_key = next((k for k in ("override", "yahoo_cal", "yahoo_ts", "yahoo_quote", "nasdaq")
                            if k in src), None)
        row = {"ticker": t, "earn_date": None, "earn_timing": None, "earn_reaction": None,
               "earn_period": 0, "earn_status": "none", "earn_sources": "",
               "earn_alt_date": None, "earn_alt_reaction": None, "earn_alt_period": 0,
               "earn_p_primary": 1.0, "earn_n_hist": len(history[t]),
               "earn_last": max(past)[0].date() if past else None}
        if primary_key:
            d, timing = src[primary_key]
            if timing == "unknown":
                # borrow the time of day from another source on the same date
                for k, (d2, tm2) in src.items():
                    if tm2 != "unknown" and abs((d2.normalize() - d.normalize()).days) <= 1:
                        timing = tm2
                        break
            react_timing = timing if timing != "unknown" else ("AMC" if us else "BMO")
            react = _reaction_day(d, react_timing, fut_cal)
            others = {k: v[0].normalize() for k, v in src.items() if k != primary_key}
            agree = [k for k, v in others.items() if abs((v - d.normalize()).days) <= 1]
            conflict = [k for k, v in others.items() if abs((v - d.normalize()).days) > 1]
            if primary_key == "override":
                status = "manual (see overrides)"
            elif "nasdaq" in agree:
                status = "confirmed (2 sources)"
            elif conflict:
                status = "CONFLICT"
            elif info.get("isEarningsDateEstimate") is False and primary_key != "nasdaq":
                status = "yahoo-confirmed"
            else:
                status = "estimate/single source"
            row.update(earn_date=d.normalize().date(), earn_timing=timing, earn_reaction=react.date() if react is not None else None,
                       earn_period=_period_of(react), earn_status=status,
                       earn_sources=",".join(f"{k}:{v[0].date()}" for k, v in src.items()))
            # Date uncertainty: an unconfirmed date can fall in the other window.
            alt, p_primary = None, 1.0
            if ovr_row is not None and str(ovr_row.get("alt_date") or ""):
                alt = pd.Timestamp(ovr_row["alt_date"])
                p_primary = float(ovr_row.get("p_primary") or 0.5)
                row["earn_status"] = "unconfirmed (manual check)"
            elif conflict:
                alt, p_primary = others[conflict[0]], 0.5
            if alt is not None:
                alt_react = _reaction_day(alt, react_timing, fut_cal)
                alt_period = _period_of(alt_react)
                if alt_period == row["earn_period"]:
                    p_primary = 1.0
                    if row["earn_status"] == "CONFLICT":
                        row["earn_status"] = "sources differ, same window"
                row.update(earn_alt_date=alt.date(), earn_alt_reaction=alt_react.date() if alt_react is not None else None,
                           earn_alt_period=alt_period, earn_p_primary=p_primary)
            if timing == "unknown" and react is not None:
                row["earn_status"] += " (time unknown)"
        rows.append(row)
    return pd.DataFrame(rows).set_index("ticker"), history


def earnings_moves(prices: Prices, history: dict, ewma: pd.DataFrame) -> dict:
    """Empirical earnings-day log returns (EUR) and their multiple of the
    normal daily vol at the time, per stock."""
    r = prices.ret_eur
    out = {}
    for t, events in history.items():
        if t not in r.columns:
            continue
        moves, mults = [], []
        for d0, d1 in events:
            cands = [d for d in (d0, d1) if d is not None and d in r.index]
            if not cands:
                continue
            d = max(cands, key=lambda x: abs(r.at[x, t]) if pd.notna(r.at[x, t]) else -1)
            x = r.at[d, t]
            if pd.isna(x):
                continue
            moves.append(float(x))
            s = ewma.at[d, t] if d in ewma.index else np.nan
            if s and np.isfinite(s) and s > 0:
                mults.append(abs(float(x)) / float(s))
        out[t] = {"days": [d for d0, d1 in events for d in (d0, d1) if d is not None],
                  "moves": moves, "mults": mults}
    return out


def _divs_from_nasdaq(rows) -> list[tuple[pd.Timestamp, float]]:
    out = []
    if not isinstance(rows, list):
        return out
    for r in rows:
        try:
            d = pd.Timestamp(r.get("exOrEffDate"))
            a = float(str(r.get("amount", "")).replace("$", "").replace(",", ""))
            if pd.notna(d) and a > 0:
                out.append((d, a))
        except (ValueError, TypeError):
            continue
    return out


def exdiv_table(md: MarketData, prices: Prices) -> pd.DataFrame:
    """Expected ex-dividend events inside each holding period (price-only
    scoring makes these a pure negative).

    Confirmed = announced future ex-date (Yahoo calendar, Nasdaq for US, or a
    manual override). Estimated = same window last year (annual/semi-annual
    payers) or last ex-date + median spacing (quarterly payers).
    """
    ovr = _load_overrides(config.EXDIV_OVERRIDES_CSV)
    asof = prices.asof
    windows = {1: (config.P1_START, config.P1_END), 2: (config.P2_START, config.P2_END)}
    rows = []
    for t in md.universe.index:
        hist = md.dividends[t][md.dividends[t] > 0] if t in md.dividends else pd.Series(dtype=float)
        hist = hist.loc[:asof]
        last_amt = float(hist.iloc[-1]) if len(hist) else 0.0
        events: list[tuple[pd.Timestamp, float, str]] = []
        # confirmed sources
        cal = (md.meta.get(t, {}) or {}).get("calendar") or {}
        xd = cal.get("Ex-Dividend Date")
        if xd and pd.Timestamp(xd) > asof:
            events.append((pd.Timestamp(xd), last_amt, "yahoo"))
        info = (md.meta.get(t, {}) or {}).get("info") or {}
        if info.get("exDividendDate"):
            d = pd.Timestamp(info["exDividendDate"], unit="s").normalize()
            if d > asof and all(abs((d - e[0]).days) > 3 for e in events):
                events.append((d, last_amt, "yahoo"))
        for d, a in _divs_from_nasdaq(md.nasdaq_div.get(t)):
            if d > asof:
                events = [e for e in events if abs((d - e[0]).days) > 3]
                events.append((d, a, "nasdaq"))
        if not ovr.empty:
            for _, r in ovr[ovr["ticker"] == t].iterrows():
                d = pd.Timestamp(r["ex_date"])
                events = [e for e in events if abs((d - e[0]).days) > 5]
                events.append((d, float(r["amount"]), "manual"))
        row = {"ticker": t}
        for p, (a, b) in windows.items():
            a, b = pd.Timestamp(a), pd.Timestamp(b)
            conf = [(d, amt, s) for d, amt, s in events if a <= d <= b]
            est = []
            if not conf and len(hist):
                gaps = hist.index.to_series().diff().dt.days.dropna()
                quarterly = len(gaps) >= 3 and gaps.iloc[-4:].median() < 120
                if quarterly:
                    nxt = hist.index[-1] + pd.Timedelta(days=int(gaps.iloc[-4:].median()))
                    while nxt < a - pd.Timedelta(days=7):
                        nxt += pd.Timedelta(days=int(gaps.iloc[-4:].median()))
                    known_next = [d for d, _, _ in events if d > asof]
                    if a <= nxt <= b and not any(abs((nxt - k).days) < 45 for k in known_next):
                        est.append((nxt, last_amt, "est: quarterly cadence"))
                else:
                    ly = hist.loc[a - pd.Timedelta(days=371):b - pd.Timedelta(days=357)]
                    for d, amt in ly.items():
                        d2 = d + pd.Timedelta(days=364)
                        if a <= d2 <= b:
                            est.append((d2, float(amt), "est: same window last year"))
            ev = conf or est
            price = prices.close_local[t].dropna().iloc[-1]
            amt = sum(e[1] for e in ev)
            row[f"exdiv_p{p}_date"] = ", ".join(str(e[0].date()) for e in ev) or None
            row[f"exdiv_p{p}_amount"] = amt
            row[f"exdiv_p{p}_pct"] = amt / price if price else 0.0
            row[f"exdiv_p{p}_source"] = ", ".join(sorted({e[2] for e in ev})) or None
        rows.append(row)
    return pd.DataFrame(rows).set_index("ticker")


def compute_features(md: MarketData, prices: Prices, lam: float = 0.94) -> tuple[pd.DataFrame, dict]:
    """Per-stock feature table plus the earnings-move dictionary for the sim."""
    r = prices.ret_eur
    tickers = list(r.columns)
    one_y = r.iloc[-252:]
    ew = ewma_vol(r, lam)
    earn, history = earnings_table(md, prices)
    moves = earnings_moves(prices, history, ew)

    # Neutralise historical earnings days for "normal" vol (jumps are added
    # back explicitly in the simulation).
    cw = universe.consensus_weights(tickers)
    cons = (r[cw.index] * cw).sum(axis=1, min_count=1) / r[cw.index].notna().mul(cw).sum(axis=1)
    r_x = r.copy()
    beta = {}
    for t in tickers:
        y = one_y[t]
        ok = y.notna() & cons.loc[one_y.index].notna()
        c = cons.loc[one_y.index][ok]
        beta[t] = float(np.cov(y[ok], c)[0, 1] / c.var()) if ok.sum() > 60 else 1.0
        days = [d for d in moves.get(t, {}).get("days", []) if d in r_x.index]
        if days:
            r_x.loc[days, t] = beta[t] * cons.loc[days]
    # Robust "normal" vol: winsorise residual jumps (results we have no date
    # for, other news) at 4 sigma so one day cannot inflate the target vol.
    ew_raw = ewma_vol(r_x, lam)
    r_w = r_x.clip(lower=-4 * ew_raw, upper=4 * ew_raw)
    ew_x = ewma_vol(r_w, lam)
    corr = {t: float(one_y[t].corr(cons.loc[one_y.index])) for t in tickers}
    ex = exdiv_table(md, prices)

    ann = math.sqrt(252)
    f = pd.DataFrame(index=pd.Index(tickers, name="ticker"))
    f["name"] = md.universe.loc[tickers, "name"]
    f["index"] = md.universe.loc[tickers, "index"]
    f["currency"] = md.universe.loc[tickers, "currency"]
    f["popularity"] = universe.popularity_vector(tickers)
    f["in_consensus"] = f.index.isin(cw.index)
    last = prices.close_local.ffill().iloc[-1]
    f["last_date"] = [prices.close_local[t].last_valid_index().date() for t in tickers]
    f["price_local"] = last
    f["price_eur"] = prices.close_eur.ffill().iloc[-1]
    f["n_obs"] = r.notna().sum()
    f["vol20"] = r.iloc[-20:].std() * ann
    f["vol60"] = r.iloc[-60:].std() * ann
    f["vol1y"] = one_y.std() * ann
    f["vol60_ex_earn"] = r_w.iloc[-60:].std() * ann
    f["vol1y_ex_earn"] = r_w.iloc[-252:].std() * ann
    # next-day EWMA forecast (includes today's return)
    f["ewma_vol_ex_earn"] = np.sqrt(lam * ew_x.iloc[-1] ** 2 + (1 - lam) * r_w.iloc[-1].fillna(0) ** 2) * ann
    f["beta_cons"] = pd.Series(beta)
    f["corr_cons"] = pd.Series(corr)
    # ATM implied vol for the Nov 20 / Dec 18 expiries (own BS inversion of
    # mid prices; Yahoo's own IV field is often stale outside US hours).
    fetched = pd.Timestamp((md.fetch_report or {}).get("fetched_at_utc") or prices.asof)
    first_day = (fetched + pd.Timedelta(days=1)).normalize() if fetched.hour >= 20 else fetched.normalize()
    first_day = first_day.tz_localize(None) if first_day.tzinfo else first_day
    for p in ("p1", "p2"):
        ivd = [((md.meta.get(t, {}).get("iv") or {}).get(p) or {}) for t in tickers]
        f[f"iv_{p}"] = [d.get("iv") for d in ivd]
        f[f"iv_{p}_t"] = [d.get("t_years") for d in ivd]
        f[f"iv_{p}_bdays"] = [len(pd.bdate_range(first_day, d["expiry"])) if d.get("expiry") else None
                              for d in ivd]
    f = f.join(earn).join(ex)
    mv = {t: moves.get(t, {}).get("moves", []) for t in tickers}
    f["earn_move_n"] = [len(mv[t]) for t in tickers]
    f["earn_move_mean_abs"] = [float(np.mean(np.abs(mv[t]))) if mv[t] else np.nan for t in tickers]
    f["earn_move_max_abs"] = [float(np.max(np.abs(mv[t]))) if mv[t] else np.nan for t in tickers]
    f["short_history"] = f["n_obs"] < 250
    extras = {"moves": moves, "r_ex_earn": r_x, "ewma_ex_earn": ew_x, "consensus_daily": cons,
              "consensus_weights": cw}
    return f, extras
