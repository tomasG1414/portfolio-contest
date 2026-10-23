"""``--mode robust``: period-1 ranking averaged over model uncertainty.

Every "world" draws one set of return-model and field parameters from the
priors below, builds its own inputs, simulates ``--world-scenarios`` return
scenarios and one opponent field, and scores all candidates (singles, pairs
of the high-vol names, benchmarks) on common random numbers. Candidates are
ranked on P(win) averaged over worlds (each candidate's period-2 policy is
picked on the average), then the shortlist is re-scored on fresh worlds,
which also gives the per-world spread and a variance decomposition: which
uncertain parameter moves P(win) of the leaders, and the gap between them.

The priors encode "we do not know": no crowding data, no leaderboard.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import math
import time

import numpy as np
import pandas as pd

from . import config, report, sim
from .pipeline import _load

log = logging.getLogger(__name__)

VOL_TARGETS = ("blend", "ewma", "60d", "1y")
VOL_TARGET_P = (0.40, 0.25, 0.15, 0.20)
BLOCKS = (3, 5, 10)

# name: (description, sampler) -- sampler(rng) -> value
PRIORS = {
    # return model
    "iv_weight":           ("weight on option-implied variance (US)", lambda r: r.uniform(0.0, 1.0)),
    "vol_target":          ("vol forecaster", lambda r: r.choice(len(VOL_TARGETS), p=VOL_TARGET_P)),
    "z_clip":              ("clip on bootstrap residuals (sigmas)", lambda r: r.uniform(6.0, 12.0)),
    "volvol_mkt":          ("vol-of-vol, market-wide (lognormal sd)", lambda r: r.uniform(0.05, 0.30)),
    "volvol_idio":         ("vol-of-vol, per stock", lambda r: r.uniform(0.0, 0.20)),
    "cluster_corr":        ("extra AI-infra cluster correlation", lambda r: r.uniform(0.0, 0.5)),
    "earn_implied_weight": ("weight on option-implied earnings moves", lambda r: r.uniform(0.0, 1.0)),
    "tail_skew_weight":    ("call-skew tilt of US vols", lambda r: r.uniform(0.0, 1.0)),
    "block":               ("bootstrap block length (days)", lambda r: r.choice(len(BLOCKS))),
    # field
    "allin":               ("share of all-in opponents", lambda r: r.uniform(0.05, 0.30)),
    "allin_vol_pow":       ("all-in sampling ~ pop x vol^k", lambda r: r.uniform(1.0, 3.0)),
    "n_savvy":             ("expected savvy max-vol opponents", lambda r: r.uniform(0.0, 4.0)),
    "momentum_share":      ("share of momentum buyers", lambda r: r.uniform(0.0, 0.15)),
    "fad_prob":            ("chance a high-vol name becomes a fad (x3)", lambda r: r.uniform(0.0, 0.6)),
    "pop_noise":           ("per-name popularity noise (lognormal sd)", lambda r: r.uniform(0.2, 0.6)),
    "p2_loser_allin":      ("trailing re-pickers who go all-in", lambda r: r.uniform(0.0, 1.0)),
    "p_rebalance":         ("opponents who re-pick on Nov 22", lambda r: r.uniform(0.3, 0.8)),
    "n_entrants":          ("entrants incl. me", lambda r: int(r.integers(160, 201))),
}


def draw_world(rng, cfg: config.SimConfig, mix: config.FieldMix):
    th = {k: f(rng) for k, (_, f) in PRIORS.items()}
    c = dataclasses.replace(cfg, iv_weight=th["iv_weight"], vol_target=VOL_TARGETS[th["vol_target"]],
                            z_clip=th["z_clip"], volvol_mkt=th["volvol_mkt"], volvol_idio=th["volvol_idio"],
                            cluster_corr=th["cluster_corr"], earn_implied_weight=th["earn_implied_weight"],
                            tail_skew_weight=th["tail_skew_weight"], block=BLOCKS[th["block"]])
    m = dataclasses.replace(mix.with_allin(th["allin"]), allin_vol_pow=th["allin_vol_pow"],
                            n_savvy=th["n_savvy"], momentum_share=th["momentum_share"],
                            fad_prob=th["fad_prob"], pop_noise=th["pop_noise"],
                            p2_loser_allin=th["p2_loser_allin"], p_rebalance=th["p_rebalance"],
                            n_opponents=th["n_entrants"] - 1)
    th["vol_target"] = VOL_TARGETS[th["vol_target"]]
    th["block"] = BLOCKS[th["block"]]
    return c, m, th


def _world(feat, extras, cfg, mix, cs, S, seed, extra_stats=False):
    inp = sim.prepare_inputs(feat, extras, cfg)
    rng = np.random.default_rng(seed)
    G1 = sim.simulate_period(inp, 1, config.P1_DAYS, S, rng, cfg.block, cfg.earnings_prior_n)
    G2 = sim.simulate_period(inp, 2, config.P2_DAYS, S, rng, cfg.block, cfg.earnings_prior_n)
    field = sim.simulate_field(inp, G1, G2, mix, np.random.default_rng(seed + 1),
                               n_worlds=1, pool_size=8_000)
    res = sim.evaluate(cs, G1, G2, field, inp.cons_w, chase2=sim.chaser_returns(inp, G1, G2),
                       extra_stats=extra_stats)
    return res, field


def _metric_cols(df):
    return [c for c in df.columns if c.startswith("p_win_") and c != "p_win_8w_policy"]


def run_robust(a, cfg: config.SimConfig, mix: config.FieldMix):
    out = a.out or (config.OUTPUT_DIR / "period1" / "robust")
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    md, prices, feat, extras = _load(a, cfg)
    inp0 = sim.prepare_inputs(feat, extras, cfg)
    feat["sim_vol_p1"] = np.nan
    G1q = sim.simulate_period(inp0, 1, config.P1_DAYS, 4000, np.random.default_rng(cfg.seed), cfg.block)
    top_vol = list(np.argsort(-sim.stock_period_vol(G1q, config.P1_DAYS))[:config.TOP_VOL_FOR_PAIRS])
    targets = sim.single_targets(inp0) + sim.benchmark_targets(inp0) + sim.pair_targets(inp0, top_vol)
    cs = sim.CandidateSet.build(inp0, targets)
    log.info("robust search: %d candidates x %d worlds x %d scenarios", len(cs), a.worlds, a.world_scenarios)

    # ---- search ------------------------------------------------------------
    rng = np.random.default_rng(cfg.seed + 5000)
    acc, thetas = None, []
    for w in range(a.worlds):
        c, m, th = draw_world(rng, cfg, mix)
        res, _ = _world(feat, extras, c, m, cs, a.world_scenarios, cfg.seed + 10 * w)
        cols = _metric_cols(res)
        acc = res[cols].to_numpy() if acc is None else acc + res[cols].to_numpy()
        thetas.append(th)
        if (w + 1) % 8 == 0:
            log.info("  search world %d/%d (%.0fs)", w + 1, a.worlds, time.time() - t0)
    avg = pd.DataFrame(acc / a.worlds, columns=cols)
    avg.insert(0, "candidate", cs.labels)
    avg.insert(1, "kind", cs.kinds)
    pol_cols = ["p_win_8w_hold"] + [c for c in cols if c.startswith("p_win_8w_cons@") or c.startswith("p_win_8w_chase@")]
    best = avg[pol_cols].to_numpy().argmax(axis=1)
    avg["policy_8w"] = [pol_cols[b][len("p_win_8w_"):] for b in best]
    avg["p_win_8w_policy"] = avg[pol_cols].to_numpy().max(axis=1)
    avg = avg.sort_values("p_win_8w_policy", ascending=False).reset_index(drop=True)
    avg.insert(0, "rank", np.arange(1, len(avg) + 1))
    avg.to_csv(out / "candidates_averaged.csv", index=False, float_format="%.6g")

    # ---- validation on fresh worlds ---------------------------------------
    short = list(avg[avg["kind"] != "benchmark"]["candidate"].head(30))
    short += [t for t in ("CRWV", "MRNA", "NBIS", "ALAB", "LITE", "SNDK 20% + CRWV 80%") if t in cs.labels]
    short += [l for l, k in zip(cs.labels, cs.kinds) if k == "benchmark"]
    short = list(dict.fromkeys(short))
    css = cs.subset([cs.labels.index(l) for l in short])
    pol = avg.set_index("candidate")["policy_8w"]
    rngv = np.random.default_rng(cfg.seed + 7000)
    per_world, vth, stats = [], [], []
    for w in range(a.val_worlds):
        c, m, th = draw_world(rngv, cfg, mix)
        res, field = _world(feat, extras, c, m, css, a.world_scenarios, cfg.seed + 100_000 + 10 * w,
                            extra_stats=True)
        res = res.set_index("candidate")
        pw = {l: res.at[l, f"p_win_8w_{pol[l]}"] if pol[l] != "hold" else res.at[l, "p_win_8w_hold"]
              for l in short}
        per_world.append(pw)
        stats.append(res[["p_win_4w", "p_win_8w_hold", "p_win_8w_switch", "p_top5_4w",
                          "ret_median_4w", "ret_p10_4w", "ret_p90_4w", "vol_ann"]])
        vth.append({**th, "field_max8_median": float(np.median(field.field_max8))})
        if (w + 1) % 20 == 0:
            log.info("  validation world %d/%d (%.0fs)", w + 1, a.val_worlds, time.time() - t0)
    PW = pd.DataFrame(per_world)
    TH = pd.DataFrame(vth)
    st = sum(stats) / len(stats)
    val = pd.DataFrame({"candidate": short,
                        "kind": [css.kinds[css.labels.index(l)] for l in short],
                        "policy_8w": [pol[l] for l in short],
                        "p_win": PW.mean().to_numpy(),
                        "se": (PW.std() / math.sqrt(len(PW))).to_numpy(),
                        "p_win_world_p10": PW.quantile(0.10).to_numpy(),
                        "p_win_world_p90": PW.quantile(0.90).to_numpy()})
    val = val.join(st, on="candidate")
    ranks = PW.rank(axis=1, ascending=False)
    val["share_worlds_best"] = [(ranks[l] == 1).mean() for l in short]
    val["mean_rank"] = [ranks[l].mean() for l in short]
    val = val.sort_values("p_win", ascending=False).reset_index(drop=True)
    val.insert(0, "rank", np.arange(1, len(val) + 1))
    val["holdings"] = [report.holdings_str(css, css.labels.index(l), inp0) for l in val["candidate"]]
    val.to_csv(out / "shortlist_validated.csv", index=False, float_format="%.6g")
    PW.assign(**{f"theta_{k}": v for k, v in TH.items()}).to_csv(out / "worlds.csv", index=False,
                                                                 float_format="%.6g")

    # ---- variance decomposition -------------------------------------------
    leaders = [l for l in val[val["kind"] != "benchmark"]["candidate"].head(3)]
    targets_dec = {l: PW[l] for l in leaders}
    if len(leaders) >= 2:
        targets_dec[f"{leaders[0]} - {leaders[1]}"] = PW[leaders[0]] - PW[leaders[1]]
    dec = decompose(TH.drop(columns=["field_max8_median"]), targets_dec)
    dec.to_csv(out / "decomposition.csv", index=False, float_format="%.6g")

    pick = val[val["kind"] != "benchmark"].iloc[0]
    summary = {"pick": pick["candidate"], "p_win": float(pick["p_win"]), "se": float(pick["se"]),
               "policy_8w": pick["policy_8w"], "worlds_search": a.worlds, "worlds_validation": a.val_worlds,
               "scenarios_per_world": a.world_scenarios, "price_date": str(prices.asof.date()),
               "runtime_s": round(time.time() - t0)}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    (out / "report.md").write_text(robust_markdown(val, dec, TH, prices, summary, avg))
    print(json.dumps(summary, indent=1))
    print(f"wrote {out}/report.md")
    return val, dec


def decompose(TH: pd.DataFrame, targets: dict) -> pd.DataFrame:
    """Linear (first-order) variance decomposition of per-world P(win).

    Regress the target on standardised parameters (vol forecaster one-hot);
    each parameter's share = beta^2 var(x) / var(fit). Per-world Monte Carlo
    noise is not attributable, so shares are of the *explained* variance and
    R^2 says how much of the spread the parameters explain at all."""
    X = TH.copy()
    X = pd.get_dummies(X, columns=["vol_target"], drop_first=True, dtype=float)
    X = X.astype(float)
    Xs = (X - X.mean()) / X.std().replace(0, 1)
    A = np.column_stack([np.ones(len(Xs)), Xs.to_numpy()])
    rows = []
    for name, y in targets.items():
        y = np.asarray(y, float)
        beta, *_ = np.linalg.lstsq(A, y, rcond=None)
        fit = A @ beta
        r2 = 1 - np.var(y - fit) / np.var(y) if np.var(y) > 0 else np.nan
        contrib = beta[1:] ** 2
        # group the vol-target dummies
        groups = {}
        for col, cval, b in zip(Xs.columns, contrib, beta[1:]):
            g = "vol_target" if col.startswith("vol_target_") else col
            groups.setdefault(g, [0.0, 0.0])
            groups[g][0] += cval
            groups[g][1] += b
        tot = sum(v[0] for v in groups.values()) or 1.0
        for g, (cv, b) in groups.items():
            rows.append({"target": name, "parameter": g, "share_of_explained": cv / tot,
                         "effect_per_sd": b, "r2": r2})
    return pd.DataFrame(rows).sort_values(["target", "share_of_explained"], ascending=[True, False])


def _pct(x, d=2):
    return "" if pd.isna(x) else f"{100 * x:.{d}f}%"


def robust_markdown(val, dec, TH, prices, sm, avg) -> str:
    L = [f"# Period 1 - model-uncertainty run (prices {prices.asof.date()})", "",
         "P(win at Dec 18) averaged over parameter worlds: every world draws the return model and the "
         "opponent field from the priors below (no crowding data, no leaderboard). Each portfolio keeps one "
         "period-2 policy, picked on the search worlds: `hold`, or switch to the consensus (`cons`) or to "
         "the chaser basket (`chase`, the period-1 best performers among the names most likely held "
         "all-in) when my own score is at least the threshold.", "",
         f"Search: {sm['worlds_search']} worlds; validation: {sm['worlds_validation']} fresh worlds; "
         f"{sm['scenarios_per_world']} scenarios per world.", "",
         f"**Pick: {sm['pick']}** - P(win) {_pct(sm['p_win'])} (+/- {_pct(sm['se'])} s.e.), period-2 policy "
         f"`{sm['policy_8w']}`.", "", "## Shortlist (fresh worlds)", ""]
    t = val.head(20)
    L.append(report._md_table(pd.DataFrame({
        "#": t["rank"], "portfolio": t["candidate"], "P(win) Dec18": t["p_win"].map(_pct),
        "s.e.": t["se"].map(_pct), "worst 10% of worlds": t["p_win_world_p10"].map(_pct),
        "best 10%": t["p_win_world_p90"].map(_pct), "best in worlds": t["share_worlds_best"].map(lambda x: _pct(x, 0)),
        "P(lead) Nov20": t["p_win_4w"].map(_pct), "oracle switch": t["p_win_8w_switch"].map(_pct),
        "policy": t["policy_8w"], "vol": t["vol_ann"].map(lambda x: _pct(x, 0))})))
    b = val[val["kind"] == "benchmark"]
    L += ["", "Benchmarks: " + "; ".join(f"{r.candidate} {_pct(r.p_win)}" for r in b.itertuples()), "",
          "`worst/best 10% of worlds` = P(win) in the 10th / 90th percentile world (includes ~"
          f"{_pct(float(np.sqrt(0.15 * 0.85 / sm['scenarios_per_world'])), 1)} per-world Monte Carlo noise). "
          "`best in worlds` = share of worlds where it has the highest P(win) in the shortlist "
          "(noisy per world, read as relative). `oracle switch` = the v1 metric (switch only when actually leading).",
          "", "## What drives the uncertainty", "",
          "First-order decomposition of per-world P(win): share of the explained variance and the effect of a "
          "one-s.d. move in the parameter (percentage points).", ""]
    for tgt, d in dec.groupby("target", sort=False):
        d = d.head(6)
        L += [f"**{tgt}** (R^2 {d['r2'].iloc[0]:.2f}): " + "; ".join(
            f"{r.parameter} {r.share_of_explained:.0%} ({100 * r.effect_per_sd:+.1f}pp)" for r in d.itertuples()), ""]
    L += ["## Priors", "", report._md_table(pd.DataFrame(
        [{"parameter": k, "meaning": d, "range in validation worlds":
          (f"{TH[k].min():.2f} - {TH[k].max():.2f}" if pd.api.types.is_numeric_dtype(TH[k])
           else ", ".join(f"{v} {c / len(TH):.0%}" for v, c in TH[k].value_counts().items()))}
         for k, (d, _) in PRIORS.items()]))]
    return "\n".join(L) + "\n"
