"""Orchestration for ``--mode period1`` and ``--mode period2``.

Kept apart from the CLI so the steps can be called from a notebook too.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import math

import numpy as np
import pandas as pd

from . import config, data, report, sim

log = logging.getLogger(__name__)

WIN_COLS = ("p_win_4w", "p_win_8w_hold", "p_win_8w_switch", "p_win_8w_policy")


def _ev(cs, G1, G2, field, inp, **kw):
    """sim.evaluate with the chaser basket for the realistic period-2 policies."""
    return sim.evaluate(cs, G1, G2, field, inp.cons_w, chase2=sim.chaser_returns(inp, G1, G2), **kw)


def _fix_policy(val: pd.DataFrame, chosen: pd.Series, suffix: str = "") -> pd.Series:
    """P(win) of each candidate under the policy picked on the *search*
    scenarios (removes the selection bias of taking the max again)."""
    out = []
    for _, r in val.iterrows():
        pol = chosen.get(r["candidate"], "hold")
        out.append(r[f"p_win_8w_{pol}{suffix}"] if f"p_win_8w_{pol}{suffix}" in r else r[f"p_win_8w_policy{suffix}"])
    return pd.Series(out, index=val.index, dtype=float)


def _load(a, cfg: config.SimConfig, asof=None):
    md = data.load_market_data(a.cache)
    prices = data.build_prices(md, asof or a.asof)
    feat, extras = data.compute_features(md, prices, cfg.ewma_lambda)
    return md, prices, feat, extras


def _mixes(mix: config.FieldMix, allins) -> dict:
    """Base mixture plus the sensitivity variants, keyed by all-in share."""
    out = {round(mix.allin, 4): mix}
    for x in allins:
        out.setdefault(round(x, 4), mix.with_allin(x))
    return dict(sorted(out.items()))


def _candidates_stage1(inp: sim.SimInputs, vol1: np.ndarray):
    top_vol = list(np.argsort(-vol1)[:config.TOP_VOL_FOR_PAIRS])
    targets = sim.single_targets(inp) + sim.benchmark_targets(inp) + sim.pair_targets(inp, top_vol)
    return sim.CandidateSet.build(inp, targets), top_vol


def _candidates_triples(inp, res: pd.DataFrame, cs: sim.CandidateSet, top_vol, rank_by):
    pairs = res[res["kind"] == "pair"].nlargest(config.N_PAIRS_FOR_TRIPLES, rank_by)
    singles = res[res["kind"] == "single"].nlargest(20, rank_by)["candidate"].tolist()
    thirds = sorted(set(top_vol) | {inp.ix(t) for t in singles})
    base = []
    for lab in pairs["candidate"]:
        j = cs.labels.index(lab)
        # use the *target* weights implied by the label (not the rounded ones)
        w = np.zeros(inp.n)
        for part in lab.split(" + "):
            t, pct = part.rsplit(" ", 1)
            w[inp.ix(t)] = float(pct.rstrip("%")) / 100
        base.append(w / w.sum())
    return sim.CandidateSet.build(inp, sim.triple_targets(inp, base, thirds))


def _concat(a: sim.CandidateSet, b: sim.CandidateSet) -> sim.CandidateSet:
    return sim.CandidateSet(a.labels + b.labels, a.kinds + b.kinds, np.vstack([a.W, b.W]),
                            np.concatenate([a.cash, b.cash]), np.vstack([a.shares, b.shares]))


def _holdings(cs: sim.CandidateSet, j: int, inp: sim.SimInputs, feat: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for i in np.flatnonzero(cs.shares[j]):
        t = inp.tickers[i]
        f = feat.loc[t]
        rows.append({"ticker": t, "name": f["name"], "shares": int(cs.shares[j, i]),
                     "price_local": f["price_local"], "currency": f["currency"],
                     "price_eur": f["price_eur"], "value_eur": cs.shares[j, i] * f["price_eur"],
                     "weight": cs.W[j, i], "last_close": f["last_date"]})
    return pd.DataFrame(rows)


def run_period1(a, cfg: config.SimConfig, mix: config.FieldMix):
    out = a.out or (config.OUTPUT_DIR / "period1")
    out.mkdir(parents=True, exist_ok=True)
    md, prices, feat, extras = _load(a, cfg)
    log.info("universe %d names, prices to %s", len(feat), prices.asof.date())
    inp = sim.prepare_inputs(feat, extras, cfg)
    rank_by = a.rank_by
    quick = getattr(a, "quick", False)
    allins = [] if quick else [float(x) for x in a.sensitivity.split(",") if x]
    mixes = _mixes(mix, allins)
    base_key = round(mix.allin, 4)

    # ---- search set A ---------------------------------------------------
    rng = np.random.default_rng(cfg.seed)
    G1 = sim.simulate_period(inp, 1, config.P1_DAYS, cfg.n_scenarios, rng, cfg.block, cfg.earnings_prior_n)
    G2 = sim.simulate_period(inp, 2, config.P2_DAYS, cfg.n_scenarios, rng, cfg.block, cfg.earnings_prior_n)
    feat["sim_vol_p1"] = sim.stock_period_vol(G1, config.P1_DAYS)
    feat["sim_vol_p2"] = sim.stock_period_vol(G2, config.P2_DAYS)
    feat["target_vol"] = inp.vol_ann
    feat["iv_scale"] = inp.iv_scale
    log.info("simulated %d scenarios; drawing fields for mixtures %s", cfg.n_scenarios, list(mixes))
    fields = {k: sim.simulate_field(inp, G1, G2, m, np.random.default_rng(cfg.seed + 101 + i))
              for i, (k, m) in enumerate(mixes.items())}
    cs, top_vol = _candidates_stage1(inp, feat["sim_vol_p1"].to_numpy())
    log.info("scoring %d singles/pairs/benchmarks", len(cs))
    res = _ev(cs, G1, G2, fields[base_key], inp)
    cs3 = _candidates_triples(inp, res, cs, top_vol, rank_by)
    res3 = _ev(cs3, G1, G2, fields[base_key], inp)
    cs_all = _concat(cs, cs3)
    res = pd.concat([res, res3], ignore_index=True)
    for k, f in fields.items():
        if k == base_key:
            continue
        log.info("re-scoring %d candidates under all-in %.0f%%", len(cs_all), 100 * k)
        alt = _ev(cs_all, G1, G2, f, inp)
        alt["p_win_8w_policy"] = _fix_policy(alt, res.set_index("candidate")["policy_8w"])
        for c in WIN_COLS:
            res[f"{c}@allin{k:.0%}"] = alt[c].to_numpy()
    for c in WIN_COLS:
        res[f"{c}@allin{base_key:.0%}"] = res[c]
    res = res.sort_values(rank_by, ascending=False).reset_index(drop=True)
    res.insert(0, "rank", np.arange(1, len(res) + 1))

    # ---- shortlist, re-scored on fresh scenarios (selection-bias check) --
    short = list(res["candidate"].head(config.SHORTLIST_SIZE))
    for k in mixes:
        if k != base_key:
            short += list(res.nlargest(10, f"{rank_by}@allin{k:.0%}")["candidate"])
    short += [l for l, kd in zip(cs_all.labels, cs_all.kinds) if kd == "benchmark"]
    short = list(dict.fromkeys(short))
    rows = [cs_all.labels.index(l) for l in short]
    css = cs_all.subset(rows)
    rngv = np.random.default_rng(cfg.seed + 1)
    G1v = sim.simulate_period(inp, 1, config.P1_DAYS, cfg.n_validate, rngv, cfg.block, cfg.earnings_prior_n)
    G2v = sim.simulate_period(inp, 2, config.P2_DAYS, cfg.n_validate, rngv, cfg.block, cfg.earnings_prior_n)
    log.info("validating %d shortlisted candidates on %d fresh scenarios", len(css), cfg.n_validate)
    fields_v = {k: sim.simulate_field(inp, G1v, G2v, m, np.random.default_rng(cfg.seed + 202 + i))
                for i, (k, m) in enumerate(mixes.items())}
    chosen = res.set_index("candidate")["policy_8w"]
    val = _ev(css, G1v, G2v, fields_v[base_key], inp)
    val["policy_8w"] = val["candidate"].map(chosen).fillna("hold")
    val["p_win_8w_policy"] = _fix_policy(val, chosen)
    for k, f in fields_v.items():
        alt = val if k == base_key else _ev(css, G1v, G2v, f, inp)
        if k != base_key:
            alt["p_win_8w_policy"] = _fix_policy(alt, chosen)
        for c in WIN_COLS:
            val[f"{c}@allin{k:.0%}"] = alt[c].to_numpy()
    ov = sim.overlap_metrics(css, G1v, fields_v[base_key])
    val = val.merge(ov, on="candidate")
    # vol-model sensitivity: the other choice of US vol (with / without IV calibration)
    alt_label = None
    if not quick:
        alt_cfg = dataclasses.replace(cfg, use_iv=not cfg.use_iv)
        alt_label = "realised vol only" if cfg.use_iv else "IV-calibrated"
        inp_a = sim.prepare_inputs(feat, extras, alt_cfg)
        rnga = np.random.default_rng(cfg.seed + 2)
        G1a = sim.simulate_period(inp_a, 1, config.P1_DAYS, cfg.n_validate, rnga, cfg.block, cfg.earnings_prior_n)
        G2a = sim.simulate_period(inp_a, 2, config.P2_DAYS, cfg.n_validate, rnga, cfg.block, cfg.earnings_prior_n)
        fa = sim.simulate_field(inp_a, G1a, G2a, mix, np.random.default_rng(cfg.seed + 303))
        va = _ev(css, G1a, G2a, fa, inp_a)
        va["p_win_8w_policy"] = _fix_policy(va, chosen)
        val[f"{rank_by}@volmodel"] = va[rank_by].to_numpy()
        val["rank@volmodel"] = val[f"{rank_by}@volmodel"].rank(ascending=False, method="min").astype(int)
    # robustness: worst ratio to the best P(win) in each mixture
    ratios = []
    for k in mixes:
        col = f"{rank_by}@allin{k:.0%}"
        val[f"rank@allin{k:.0%}"] = val[col].rank(ascending=False, method="min").astype(int)
        ratios.append(val[col] / val[col].max())
    val["robustness"] = np.min(np.vstack(ratios), axis=0)
    val["worst_rank"] = val[[f"rank@allin{k:.0%}" for k in mixes]].max(axis=1)
    val = val.sort_values(rank_by, ascending=False).reset_index(drop=True)
    val.insert(0, "rank", np.arange(1, len(val) + 1))
    val["holdings"] = [report.holdings_str(css, css.labels.index(l), inp) for l in val["candidate"]]
    val["flags"] = [report.flags_str(css, css.labels.index(l), inp, feat) for l in val["candidate"]]

    # crowding sensitivity: what if the field likes my lead names more than assumed?
    crowd = {}
    leads = []
    for l in val[val["kind"] != "benchmark"]["candidate"].head(10):
        jj = css.labels.index(l)
        t = inp.tickers[int(np.argmax(css.W[jj]))]
        if t not in leads:
            leads.append(t)
    top8 = css.subset([css.labels.index(l) for l in val[val["kind"] != "benchmark"]["candidate"].head(8)])
    for t in ([] if quick else leads[:3]):
        pop = inp.popularity.copy()
        pop[inp.ix(t)] *= 3
        fc = sim.simulate_field(dataclasses.replace(inp, popularity=pop), G1v, G2v, mix,
                                np.random.default_rng(cfg.seed + 404))
        ec = _ev(top8, G1v, G2v, fc, inp)
        ec["p_win_8w_policy"] = _fix_policy(ec, chosen)
        crowd[t] = ec.set_index("candidate")[rank_by]
    crowd = pd.DataFrame(crowd)
    if len(crowd):
        crowd.insert(0, "base", val.set_index("candidate").loc[crowd.index, rank_by])

    # ---- pick the submission --------------------------------------------
    pick = val.iloc[0]
    robust = val[(val["kind"] != "benchmark")].sort_values(["worst_rank", rank_by],
                                                           ascending=[True, False]).iloc[0]
    j = css.labels.index(pick["candidate"])
    hold = _holdings(css, j, inp, feat)
    jr = css.labels.index(robust["candidate"])
    hold_r = _holdings(css, jr, inp, feat)

    # ---- write ----------------------------------------------------------
    res.to_csv(out / "candidates_ranked.csv", index=False, float_format="%.6g")
    val.to_csv(out / "shortlist_validated.csv", index=False, float_format="%.6g")
    feat.to_csv(out / "stock_features.csv", float_format="%.6g")
    hold.to_csv(out / "submission_shares.csv", index=False, float_format="%.6g")
    fb = fields_v[base_key]
    report.plot_pwin_vs_vol(res, out / "pwin_vs_vol.png", rank_by, highlight=list(val["candidate"].head(5)),
                            n_entrants=mix.n_opponents + 1)
    best_R1 = G1v @ css.W[j] + css.cash[j]
    best_R8 = (G1v * G2v) @ css.W[j] + css.cash[j]
    report.plot_winning_score(fb.field_max1, fb.field_max8, out / "winning_score_hist.png",
                              mine=(pick["candidate"], best_R1, best_R8))
    ctx = dict(md=md, prices=prices, feat=feat, inp=inp, res=res, val=val, mixes=mixes,
               base_key=base_key, rank_by=rank_by, pick=pick, hold=hold, robust=robust,
               hold_r=hold_r, field=fb, cfg=cfg, mix=mix, n_cands=len(cs_all), alt_label=alt_label, crowd=crowd)
    (out / "report.md").write_text(report.period1_markdown(ctx))
    summary = {"pick": pick["candidate"], "rank_by": rank_by, rank_by: float(pick[rank_by]),
               "policy_8w": str(pick.get("policy_8w", "")),
               "p_win_4w": float(pick["p_win_4w"]), "robust_pick": robust["candidate"],
               "price_date": str(prices.asof.date()), "field": mix.label(),
               "n_entrants": mix.n_opponents + 1,
               "field_max_4w_median": float(np.median(fb.field_max1)),
               "field_max_8w_median": float(np.median(fb.field_max8)),
               "shares": {r.ticker: int(r.shares) for r in hold.itertuples()}}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    print(f"wrote {out}/report.md")
    return ctx


# ==========================================================================
# Period 2 (Nov 22): realised period-1 returns, optimise the rebalance
# ==========================================================================
def _evaluate_final(cs: sim.CandidateSet, G2: np.ndarray, top8: np.ndarray, my_gross: float,
                    cons_w: np.ndarray, chunk: int = 256) -> pd.DataFrame:
    cons2 = G2 @ cons_w
    n_names = (cs.W > 0).sum(axis=1)
    out = []
    for c0 in range(0, len(cs), chunk):
        c1 = min(len(cs), c0 + chunk)
        R2 = cs.W[c0:c1] @ G2.T + cs.cash[c0:c1, None]
        R = my_gross * R2
        win, t5 = sim._win_top5(R, top8, exact_ties=False)
        q = np.percentile(R2, [10, 50, 90], axis=1)
        vol = np.log(R2).std(axis=1) * math.sqrt(252 / config.P2_DAYS)
        for j in range(c1 - c0):
            out.append({"candidate": cs.labels[c0 + j], "kind": cs.kinds[c0 + j],
                        "n_names": int(n_names[c0 + j]), "cash_pct": cs.cash[c0 + j],
                        "p_win": win[j], "p_top5": t5[j], "vol_ann": vol[j],
                        "corr_consensus": float(np.corrcoef(R2[j], cons2)[0, 1]) if R2[j].std() > 0 else np.nan,
                        "ret_p10_p2": q[0, j] - 1, "ret_median_p2": q[1, j] - 1,
                        "ret_p90_p2": q[2, j] - 1})
    return pd.DataFrame(out)


def run_period2(a, cfg: config.SimConfig, mix: config.FieldMix, my_return: float):
    out = a.out or (config.OUTPUT_DIR / "period2")
    out.mkdir(parents=True, exist_ok=True)
    md, prices, feat, extras = _load(a, cfg)
    my_gross = 1.0 + my_return
    have_p1_end = prices.asof >= pd.Timestamp(config.P1_END)
    p1_prices = prices.close_eur.loc[:pd.Timestamp(config.P1_PRICE_DATE)].iloc[-1]
    inp2 = sim.prepare_inputs(feat, extras, cfg, periods=(2,))
    # opponents bought in period 1 at the Oct 23 close
    inp1 = dataclasses.replace(inp2, price_eur=p1_prices.reindex(inp2.tickers).to_numpy(float))
    S = cfg.n_scenarios
    rng = np.random.default_rng(cfg.seed + 7)
    if a.dry_run or not have_p1_end:
        if not a.dry_run:
            raise SystemExit(f"prices only go to {prices.asof.date()}; re-fetch after the "
                             f"{config.P1_END} close or pass --dry-run to test")
        g1 = sim.simulate_period(inp2, 1, config.P1_DAYS, 1, rng, cfg.block)[0]
        source = "DRY RUN: one simulated period-1 outcome (not real data)"
    else:
        g1 = data.realized_gross(prices, config.P1_PRICE_DATE, config.P1_END).reindex(inp2.tickers).to_numpy()
        source = f"realised closes {config.P1_PRICE_DATE} -> {config.P1_END}"
    g1 = np.nan_to_num(g1, nan=1.0)
    G1 = np.tile(g1, (S, 1))
    G2 = sim.simulate_period(inp2, 2, config.P2_DAYS, S, rng, cfg.block, cfg.earnings_prior_n)
    field = sim.simulate_field(inp1, G1, G2, mix, np.random.default_rng(cfg.seed + 303), pool_inp=inp2)
    feat["sim_vol_p2"] = sim.stock_period_vol(G2, config.P2_DAYS)
    feat["realized_p1"] = g1 - 1

    # candidates (period-2 sizing at the latest close)
    vol2 = feat["sim_vol_p2"].to_numpy()
    top_vol = list(np.argsort(-vol2)[:config.TOP_VOL_FOR_PAIRS])
    targets = sim.single_targets(inp2) + sim.benchmark_targets(inp2) + sim.pair_targets(inp2, top_vol)
    # "cover the chasers": period 1's best performers among the names most
    # likely held all-in (what the opponents who can still catch me hold)
    likely = np.argsort(-(inp2.popularity * inp2.vol_ann))[:40]
    best3 = likely[np.argsort(-g1[likely])[:3]]
    wch = np.zeros(inp2.n)
    wch[best3] = 1 / 3
    targets.append(("Chasers: " + ", ".join(inp2.tickers[i] for i in best3), "benchmark", wch))
    cs = sim.CandidateSet.build(inp2, targets)
    res = _evaluate_final(cs, G2, field.top8, my_gross, inp2.cons_w)
    cs3 = _candidates_triples(inp2, res.assign(p_win_8w_switch=res["p_win"]), cs, top_vol, "p_win")
    cs_all = _concat(cs, cs3)
    res = pd.concat([res, _evaluate_final(cs3, G2, field.top8, my_gross, inp2.cons_w)],
                    ignore_index=True).sort_values("p_win", ascending=False).reset_index(drop=True)
    res.insert(0, "rank", np.arange(1, len(res) + 1))

    # rule-of-thumb test: is de-risking right when ahead, concentration when behind?
    fmax = field.field_max1
    grid = {"actual": my_gross}
    for q in (0.10, 0.50, 0.90):
        grid[f"field-max q{int(q * 100)}"] = float(np.quantile(fmax, q))
    grid["field-max q50 +5%"] = float(np.quantile(fmax, 0.5)) * 1.05
    test_rows = []
    short = res.head(150)["candidate"].tolist() + \
        [l for l, k in zip(cs_all.labels, cs_all.kinds) if k in ("single", "benchmark")]
    css = cs_all.subset([cs_all.labels.index(l) for l in dict.fromkeys(short)])
    for name, g in grid.items():
        r = _evaluate_final(css, G2, field.top8, g, inp2.cons_w)
        def best_of(mask):
            d = r[mask].nlargest(1, "p_win")
            return (d["candidate"].iloc[0], d["p_win"].iloc[0]) if len(d) else (None, np.nan)
        # strategies: stay concentrated (1-2 names, high vol) vs de-risk
        # toward the consensus (baskets that track it) vs de-risk to low vol
        conc = best_of((r["n_names"] <= 2) & (r["vol_ann"] >= 0.6))
        cons_like = best_of(r["corr_consensus"] >= 0.8)
        low = best_of(r["vol_ann"] <= 0.25)
        best = r.nlargest(1, "p_win").iloc[0]
        test_rows.append({"my_score_after_p1": g, "scenario": name,
                          "p_leading_now": float((g > fmax).mean()),
                          "best": best["candidate"], "p_win_best": best["p_win"],
                          "best_concentrated": conc[0], "p_win_concentrated": conc[1],
                          "best_consensus_like": cons_like[0], "p_win_consensus_like": cons_like[1],
                          "best_low_vol": low[0], "p_win_low_vol": low[1],
                          "p_win_consensus_basket": r.loc[r["candidate"] == "Consensus basket", "p_win"].iloc[0],
                          "rule_says": "de-risk" if g > np.median(fmax) else "concentrate",
                          "model_says": ("concentrate" if conc[1] >= max(cons_like[1], low[1]) else "de-risk")})
    rule = pd.DataFrame(test_rows)
    pick = res.iloc[0]
    j = cs_all.labels.index(pick["candidate"])
    hold = _holdings(cs_all, j, inp2, feat)
    res["holdings"] = ""
    res.loc[:199, "holdings"] = [report.holdings_str(cs_all, cs_all.labels.index(l), inp2)
                                 for l in res["candidate"].head(200)]
    res.to_csv(out / "candidates_ranked.csv", index=False, float_format="%.6g")
    rule.to_csv(out / "rule_of_thumb_test.csv", index=False, float_format="%.6g")
    hold.to_csv(out / "submission_shares.csv", index=False, float_format="%.6g")
    feat.to_csv(out / "stock_features.csv", float_format="%.6g")
    report.plot_winning_score(field.field_max1, field.field_max8, out / "winning_score_hist.png",
                              mine=None, my_now=my_gross)
    ctx = dict(prices=prices, feat=feat, res=res, rule=rule, pick=pick, hold=hold, field=field,
               my_gross=my_gross, source=source, mix=mix, cfg=cfg, inp=inp2, cs=cs_all, md=md)
    (out / "report.md").write_text(report.period2_markdown(ctx))
    print(rule.to_string(index=False))
    print(f"pick: {pick['candidate']}  P(win)={pick['p_win']:.2%}")
    print(f"wrote {out}/report.md")
    return ctx


# ==========================================================================
# Stress tests: full period-1 searches under alternative fields, in parallel
# ==========================================================================
STRESS_VARIANTS = {
    "base": [],
    "participants 60": ["--participants", "60"],
    "participants 120": ["--participants", "120"],
    "participants 200": ["--participants", "200"],
    "30% non-Spanish EU": ["--foreign-share", "0.3"],
    "50% non-Spanish EU": ["--foreign-share", "0.5"],
    "hype names x2": ["--group-mult", "hype=2"],
    "Spanish bias x2": ["--group-mult", "spain=2"],
    "US mega-caps x2": ["--group-mult", "us_mega=2"],
    "group noise 50%": ["--group-noise", "0.5"],
    "combo: 120, 30% EU, hype x2": ["--participants", "120", "--foreign-share", "0.3",
                                     "--group-mult", "hype=2"],
    # v2: field behaviour
    "all-in ~ pop x vol^2": ["--allin-vol-pow", "2"],
    "all-in ~ pop x vol^3": ["--allin-vol-pow", "3"],
    "3 savvy max-vol opponents": ["--savvy", "3"],
    "10% momentum buyers": ["--momentum-share", "0.10"],
    "fads (50% of worlds)": ["--fad-prob", "0.5"],
    "trailing re-pickers go all-in": ["--p2-loser-allin", "1.0"],
    "popularity noise 50%": ["--pop-noise", "0.5"],
    # v2: return model
    "no vol-of-vol": ["--volvol", "0,0"],
    "vol-of-vol 30/30": ["--volvol", "0.3,0.3"],
    "residual clip 6 sigma": ["--z-clip", "6"],
    "AI cluster corr +0.4": ["--cluster-corr", "0.4"],
    "IV weight 1.0": ["--iv-weight", "1.0"],
    "call-skew tilt": ["--tail-skew-weight", "1.0"],
    "pessimistic combo": ["--allin-vol-pow", "2", "--savvy", "1", "--p2-loser-allin", "1.0",
                          "--volvol", "0.3,0.3", "--fad-prob", "0.5"],
}
TRACKED = ("CRWV", "MRNA", "NBIS", "SNDK 20% + CRWV 80%")


def _stress_worker(argv):
    from . import cli
    cli.main(argv)
    return argv


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name).strip("_").lower()


def run_stress(a, argv_common: list[str], workers: int = 4):
    """Run every variant as a quick full search (search + validation, no
    secondary sensitivities), ``workers`` processes at a time with one BLAS
    thread each, then tabulate picks and the tracked portfolios."""
    import os
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing as mp
    out = a.out or (config.OUTPUT_DIR / "period1" / "stress")
    out.mkdir(parents=True, exist_ok=True)
    for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[k] = "1"
    jobs = {name: ["--mode", "period1", "--quick", "--out", str(out / _slug(name))] + argv_common + extra
            for name, extra in STRESS_VARIANTS.items()}
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        list(ex.map(_stress_worker, jobs.values()))
    rows = []
    for name in jobs:
        d = out / _slug(name)
        sm = json.loads((d / "summary.json").read_text())
        res = pd.read_csv(d / "candidates_ranked.csv").set_index("candidate")
        rb = sm.get("rank_by", "p_win_8w_switch")
        row = {"variant": name, "entrants": sm["n_entrants"], "pick": sm["pick"],
               "P(win) pick": sm[rb], "random entrant": 1 / sm["n_entrants"],
               "winning score median": sm["field_max_8w_median"]}
        for t in TRACKED:
            if t in res.index:
                row[f"{t} P(win)"] = res.at[t, rb]
                row[f"{t} rank"] = int(res.at[t, "rank"])
        rows.append(row)
    tab = pd.DataFrame(rows)
    tab.to_csv(out / "summary.csv", index=False, float_format="%.6g")
    (out / "summary.md").write_text(report.stress_markdown(tab))
    print(tab.to_string(index=False))
    print(f"wrote {out}/summary.md")
    return tab
