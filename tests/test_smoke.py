"""End-to-end smoke test on a synthetic cache (no network).

    python -m pytest tests -q      or      python tests/test_smoke.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contest import cli, config, sim  # noqa: E402

TICKERS = ["NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "PLTR", "AMD", "NFLX",
           "MSTR", "MU", "SPCX", "APP", "RKLB", "ITX.MC", "SAN.MC", "IBE.MC", "BBVA.MC",
           "TEF.MC", "REP.MC", "IDR.MC", "GRF.MC", "SLR.MC", "ASML.AS", "MC.PA", "RHM.DE",
           "RACE.MI", "SAP.DE", "NDA-FI.HE"]


def make_cache(root: Path, end: dt.date = dt.date(2026, 10, 22), seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    cache = root / "cache"
    cache.mkdir(parents=True)
    dates = pd.bdate_range(end - dt.timedelta(days=3 * 365 + 45), end)
    n = len(dates)
    mkt = rng.standard_t(5, n) * 0.008
    close, adj, divs = {}, {}, {}
    uni = []
    for k, t in enumerate(TICKERS):
        vol = 0.012 + 0.03 * rng.random()
        r = 0.8 * mkt + vol * rng.standard_t(4, n) / np.sqrt(2)
        # earnings jumps every ~63 days
        for d in range(20 + k % 60, n, 63):
            r[d] += rng.choice([-1, 1]) * 4 * vol
        p = 50 * np.exp(np.cumsum(r)) * (1 + 3 * rng.random())
        if t == "SPCX":
            p[: n - 90] = np.nan
        dv = np.zeros(n)
        if t.endswith(".MC"):
            dv[dates.get_indexer(pd.bdate_range(end - dt.timedelta(days=362), periods=1))] = 0.01 * p[-1]
        close[t], adj[t], divs[t] = p, p, dv
        usd = "." not in t
        uni.append({"ticker": t, "name": t, "index": "NDX" if usd else "SX5E",
                    "currency": "USD" if usd else "EUR", "sector": "", "popularity": 1})
    close["EURUSD=X"] = 1.10 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    adj["EURUSD=X"] = close["EURUSD=X"]
    divs["EURUSD=X"] = np.zeros(n)
    for name, d in (("close", close), ("adjclose", adj), ("dividends", divs), ("splits", {k: np.zeros(n) for k in close})):
        pd.DataFrame(d, index=dates.rename("date")).to_csv(cache / f"{name}.csv.gz")
    pd.DataFrame(uni).to_csv(cache / "universe.csv", index=False)
    meta = {}
    for k, t in enumerate(TICKERS):
        tz = "America/New_York"
        past = [pd.Timestamp(dates[d]).tz_localize(tz) + pd.Timedelta(hours=7 if "." in t else 16)
                for d in range(20 + k % 60, n, 63)]
        nxt = pd.Timestamp(dt.date(2026, 10, 27) + dt.timedelta(days=(k * 3) % 50)).tz_localize(tz) + pd.Timedelta(hours=16)
        meta[t] = {"ticker": t, "errors": {}, "info": {"isEarningsDateEstimate": False},
                   "calendar": {"Earnings Date": [str(nxt.date())]},
                   "earnings_dates": [{"ts": x.isoformat()} for x in past + [nxt]]}
    (cache / "meta.json").write_text(json.dumps(meta))
    (cache / "nasdaq_earnings.json").write_text(json.dumps(
        {"2026-10-29": [{"symbol": "NVDA", "time": "time-after-hours"}]}))
    (cache / "nasdaq_dividends.json").write_text("{}")
    (cache / "fetch_report.json").write_text(json.dumps({"universe": {}, "failed_downloads": []}))
    return cache


def test_period1_and_period2():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cache = make_cache(tmp)
        common = ["--cache", str(cache), "--scenarios", "2000", "--validate-scenarios", "2000"]
        cli.main(["--mode", "period1", "--out", str(tmp / "p1")] + common)
        res = pd.read_csv(tmp / "p1" / "candidates_ranked.csv")
        assert len(res) > len(TICKERS)
        assert res["p_win_4w"].between(0, 1).all()
        # P(win) over all distinct entrants cannot exceed 1 and singles must cover the universe
        assert set(TICKERS) <= set(res["candidate"])
        assert (tmp / "p1" / "report.md").read_text().startswith("# Stock contest")
        shares = pd.read_csv(tmp / "p1" / "submission_shares.csv")
        assert (shares["value_eur"].sum() <= config.CAPITAL_EUR + 1e-6)
        cli.main(["--mode", "period2", "--my-return", "5%", "--dry-run", "--out", str(tmp / "p2")] + common)
        assert (tmp / "p2" / "rule_of_thumb_test.csv").exists()


def test_whole_shares_and_ties():
    price = np.array([95.0, 2600.0, 40.0])
    s, cash = sim.whole_shares(np.array([0.5, 0.5, 0.0]), price)
    assert s[2] == 0 and cash < 95.0 and (s @ price + cash) == config.CAPITAL_EUR
    # identical portfolio to one opponent -> tie split 50/50
    R = np.array([[1.10]])
    top = np.full((1, sim.TOPK), 0.9)
    top[0, 0] = 1.10
    win, top5 = sim._win_top5(R, top, exact_ties=True)
    assert abs(win[0] - 0.5) < 1e-12 and top5[0] == 1.0


def test_v2_field_and_modes():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cache = make_cache(tmp)
        common = ["--cache", str(cache)]
        # v2 field knobs all on, quick period 1
        cli.main(["--mode", "period1", "--quick", "--scenarios", "1500", "--validate-scenarios", "1500",
                  "--savvy", "2", "--momentum-share", "0.1", "--fad-prob", "0.5", "--allin-vol-pow", "2",
                  "--p2-loser-allin", "1", "--cluster-corr", "0.3", "--z-clip", "6",
                  "--out", str(tmp / "p1")] + common)
        val = pd.read_csv(tmp / "p1" / "shortlist_validated.csv")
        assert val["p_win_8w_policy"].between(0, 1).all() and "policy_8w" in val
        cli.main(["--mode", "robust", "--worlds", "2", "--world-scenarios", "300", "--val-worlds", "4",
                  "--out", str(tmp / "rob")] + common)
        rv = pd.read_csv(tmp / "rob" / "shortlist_validated.csv")
        assert rv["p_win"].between(0, 1).all()
        assert (tmp / "rob" / "decomposition.csv").exists()
        cli.main(["--mode", "validate", "--out", str(tmp / "val")] + common)
        assert (tmp / "val" / "vol_forecasters.csv").exists()


def test_field_type_probs_and_volvol_neutral():
    mix = config.FieldMix(n_savvy=3, momentum_share=0.1)
    p = mix.type_probs()
    assert abs(p.sum() - 1) < 1e-12 and abs(p[3] - 3 / mix.n_opponents) < 1e-12
    # variance-neutral vol multipliers: E[m^2] = 1
    rng = np.random.default_rng(0)
    vm = 0.3
    m = np.exp(vm * rng.standard_normal(400_000) - vm ** 2)
    assert abs(np.mean(m ** 2) - 1) < 0.01


if __name__ == "__main__":
    test_whole_shares_and_ties()
    test_period1_and_period2()
    print("ok")
