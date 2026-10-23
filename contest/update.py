"""``--mode update``: weekly status during the contest.

* realised price-only EUR returns since the period-1 price date (the contest
  basis: USD names bought at that day's EUR/USD and valued at today's),
  for my holding, the tracked all-in candidates and every single stock
  that is ahead of my lead name;
* earnings reactions in the next 7 calendar days for those names;
* P(win) conditional on the path so far: the remaining period-1 days and
  period 2 are simulated, the realised part is fixed for me and for the
  whole field (opponents' portfolios are drawn as in period 1).
"""
from __future__ import annotations

import dataclasses
import json
import logging

import numpy as np
import pandas as pd

from . import config, report, sim
from .pipeline import _load

log = logging.getLogger(__name__)
TRACKED = ("CRWV", "MRNA", "NBIS", "ALAB", "SNDK")


def _pct(x, d=1):
    return "" if pd.isna(x) else f"{100 * x:+.{d}f}%"


def _holding(inp) -> tuple[str, np.ndarray]:
    path = config.OUTPUT_DIR / "period1" / "submission_shares.csv"
    if path.exists():
        h = pd.read_csv(path)
        w = np.zeros(inp.n)
        for r in h.itertuples():
            if r.ticker in inp.tickers:
                w[inp.ix(r.ticker)] = r.shares
        return " + ".join(f"{int(r.shares)}x {r.ticker}" for r in h.itertuples()), w
    w = np.zeros(inp.n)
    w[inp.ix("CRWV")] = 202
    return "202x CRWV", w


def run_update(a, cfg: config.SimConfig, mix: config.FieldMix):
    out = a.out or (config.OUTPUT_DIR / "updates")
    out.mkdir(parents=True, exist_ok=True)
    md, prices, feat, extras = _load(a, cfg)
    asof = prices.asof
    p0 = prices.close_eur.loc[:pd.Timestamp(config.P1_PRICE_DATE)].iloc[-1]
    pt = prices.close_eur.ffill().iloc[-1]
    g = (pt / p0)
    wk = prices.close_eur.ffill().loc[:asof - pd.Timedelta(days=6)].iloc[-1]
    g_week = pt / wk
    inp = sim.prepare_inputs(feat, extras, cfg)
    label, shares = _holding(inp)
    w = shares * p0.reindex(inp.tickers).to_numpy() / config.CAPITAL_EUR
    cash = 1 - w.sum()
    gv = g.reindex(inp.tickers).fillna(1.0).to_numpy()
    my = float(w @ gv + cash)
    lead = inp.tickers[int(np.argmax(w))]

    # table: tracked + every single stock ahead of the lead name
    ahead = g[g > g[lead]].sort_values(ascending=False)
    names = list(dict.fromkeys([lead] + [t for t in TRACKED if t in g.index] + list(ahead.index)))
    tab = pd.DataFrame({"ticker": names,
                        "name": [feat.at[t, "name"] for t in names],
                        "since Oct 23": [g[t] - 1 for t in names],
                        "last week": [g_week[t] - 1 for t in names],
                        "popularity": [feat.at[t, "popularity"] for t in names],
                        "next earnings": [feat.at[t, "earn_reaction"] for t in names]})
    # earnings in the next 7 days (tracked, ahead, and the consensus names)
    cal = feat[(pd.to_datetime(feat["earn_reaction"], errors="coerce") > asof) &
               (pd.to_datetime(feat["earn_reaction"], errors="coerce") <= asof + pd.Timedelta(days=7))]
    cal = cal[cal.index.isin(names) | cal["in_consensus"]][["name", "earn_reaction", "earn_timing",
                                                            "earn_status", "earn_move_mean_abs"]]

    # conditional P(win)
    days1 = pd.bdate_range(config.P1_START, config.P1_END)
    elapsed = int((days1 <= asof).sum())
    pw = None
    if elapsed < len(days1):
        h1 = len(days1) - elapsed
        earn1 = [(i, k - elapsed, own, prob) for i, k, own, prob in inp.earn.get(1, []) if k >= elapsed]
        # ex-dividends already in the realised prices: keep only future ones
        ex1 = feat["exdiv_p1_date"]
        ex_future = np.array([1.0 if (isinstance(d, str) and pd.Timestamp(d.split(",")[-1]) > asof) else 0.0
                              for d in ex1.reindex(inp.tickers)])
        inp_r = dataclasses.replace(inp, earn={1: earn1, 2: inp.earn.get(2, [])},
                                    exdiv={1: inp.exdiv[1] * ex_future, 2: inp.exdiv[2]})
        S = cfg.n_scenarios
        rng = np.random.default_rng(cfg.seed + 77)
        G1r = sim.simulate_period(inp_r, 1, h1, S, rng, cfg.block, cfg.earnings_prior_n)
        G2 = sim.simulate_period(inp_r, 2, config.P2_DAYS, S, rng, cfg.block, cfg.earnings_prior_n)
        G1 = gv[None, :] * G1r
        inp_p0 = dataclasses.replace(inp, price_eur=p0.reindex(inp.tickers).to_numpy(float))
        field = sim.simulate_field(inp_p0, G1, G2, mix, np.random.default_rng(cfg.seed + 78))
        cs = sim.CandidateSet(labels=[label], kinds=["mine"], W=w[None, :], cash=np.array([cash]),
                              shares=shares[None, :])
        res = sim.evaluate(cs, G1, G2, field, inp.cons_w,
                           chase2=sim.chaser_returns(inp, G1, G2)).iloc[0]
        pw = {"p_lead_nov20": float(res["p_win_4w"]), "p_win_dec18_hold": float(res["p_win_8w_hold"]),
              "p_win_dec18_best_policy": float(res["p_win_8w_policy"]), "policy": res["policy_8w"],
              "p_top5_nov20": float(res["p_top5_4w"]), "days_left_p1": h1}
        # what the leader probably has right now: best opponent on realised returns only
        f_now = sim.simulate_field(inp_p0, np.tile(gv, (2000, 1)), np.ones((2000, inp.n)), mix,
                                   np.random.default_rng(cfg.seed + 79))
        pw["field_leader_now_median"] = float(np.median(f_now.field_max1))
        pw["field_leader_now_p10_p90"] = [float(np.quantile(f_now.field_max1, q)) for q in (0.1, 0.9)]
        pw["p_leading_now"] = float((my > f_now.field_max1 + sim.TIE_TOL).mean())
        pw["random_entrant"] = 1 / (mix.n_opponents + 1)

    L = [f"# Contest update - prices {asof.date()}", "",
         f"**My portfolio ({label}): {_pct(my - 1)} since the {config.P1_PRICE_DATE} close.**", ""]
    if pw:
        L += [f"- Estimated leader's score right now: median {_pct(pw['field_leader_now_median'] - 1)} "
              f"(10-90%: {_pct(pw['field_leader_now_p10_p90'][0] - 1)} to {_pct(pw['field_leader_now_p10_p90'][1] - 1)}); "
              f"P(I am leading now) {pw['p_leading_now']:.0%}.",
              f"- P(lead at Nov 20) {pw['p_lead_nov20']:.1%}, P(top 5 at Nov 20) {pw['p_top5_nov20']:.1%}, "
              f"P(win Dec 18) {pw['p_win_dec18_best_policy']:.1%} with policy `{pw['policy']}` "
              f"({pw['p_win_dec18_hold']:.1%} holding); random entrant {pw['random_entrant']:.1%}. "
              f"{pw['days_left_p1']} trading days left in period 1.", ""]
    else:
        L += ["Period 1 is over: conditional P(win) for period 2 needs the Nov 22 portfolio (not set up yet).", ""]
    t = tab.copy()
    t["since Oct 23"] = t["since Oct 23"].map(_pct)
    t["last week"] = t["last week"].map(_pct)
    L += ["## My lead name, the other all-in candidates, and every single stock ahead of it", "",
          report._md_table(t), ""]
    if len(cal):
        c = cal.reset_index()
        c["earn_move_mean_abs"] = c["earn_move_mean_abs"].map(lambda x: "" if pd.isna(x) else f"{100 * x:.1f}%")
        L += ["## Earnings in the next 7 days", "",
              report._md_table(c.rename(columns={"earn_move_mean_abs": "avg |move|"})), ""]
    md_text = "\n".join(L)
    (out / f"{asof.date()}.md").write_text(md_text)
    (out / f"{asof.date()}.json").write_text(json.dumps(
        {"asof": str(asof.date()), "portfolio": label, "my_return": my - 1, "conditional": pw,
         "table": tab.assign(**{"next earnings": tab["next earnings"].astype(str)}).to_dict("records")},
        indent=1, default=str))
    print(md_text)
    return md_text
