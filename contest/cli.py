"""Command line interface.

    python -m contest --mode fetch                     # network: refresh data/cache
    python -m contest --mode period1                   # Oct 25 submission
    python -m contest --mode period2 --my-return 0.083 # Nov 22 rebalance (+8.3%)
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import logging
import sys
import time
from pathlib import Path

from . import config

log = logging.getLogger("contest")


def _parse_return(s: str | None) -> float | None:
    """'0.083', '8.3%' -> 0.083 (simple return over period 1)."""
    if s is None:
        return None
    s = s.strip()
    return float(s[:-1]) / 100 if s.endswith("%") else float(s)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m contest", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["fetch", "period1", "period2", "stress", "robust", "validate", "update"], required=True)
    p.add_argument("--cache", type=Path, default=config.CACHE_DIR)
    p.add_argument("--out", type=Path, default=None, help="output directory")
    p.add_argument("--end", type=dt.date.fromisoformat, default=None,
                   help="fetch: last price date to download (default: today)")
    p.add_argument("--asof", type=dt.date.fromisoformat, default=None,
                   help="period1/2: ignore prices after this date")
    p.add_argument("--scenarios", type=int, default=config.SimConfig.n_scenarios)
    p.add_argument("--validate-scenarios", type=int, default=config.SimConfig.n_validate)
    p.add_argument("--seed", type=int, default=config.SimConfig.seed)
    p.add_argument("--block", type=int, default=config.SimConfig.block)
    p.add_argument("--vol-target", choices=["ewma", "60d", "1y", "blend"],
                   default=config.SimConfig.vol_target)
    p.add_argument("--no-iv", action="store_true",
                   help="do not calibrate US vols to option-implied variance")
    p.add_argument("--iv-weight", type=float, default=config.SimConfig.iv_weight)
    p.add_argument("--mix", type=str, default=None,
                   help="field mixture 'diversified,moderate,allin', e.g. 0.6,0.25,0.15")
    p.add_argument("--sensitivity", type=str,
                   default=",".join(str(a) for a in config.SENSITIVITY_ALLIN),
                   help="all-in shares for the sensitivity runs")
    p.add_argument("--p-rebalance", type=float, default=config.FieldMix.p_rebalance)
    p.add_argument("--chase", type=float, default=config.FieldMix.chase)
    p.add_argument("--pop-noise", type=float, default=config.FieldMix.pop_noise,
                   help="lognormal sigma of popularity uncertainty (0 = take weights as exact)")
    p.add_argument("--participants", type=int, default=config.N_OPPONENTS + 1,
                   help="number of entrants including me")
    p.add_argument("--foreign-share", type=float, default=0.0,
                   help="share of opponents with the non-Spanish European profile")
    p.add_argument("--group-mult", type=str, default="",
                   help="popularity stress per group, e.g. hype=2,spain=0.5 "
                        "(groups: us_mega, hype, spain, europe)")
    p.add_argument("--group-noise", type=float, default=0.0,
                   help="lognormal sigma of a shared popularity factor per group")
    # v2 return model
    p.add_argument("--z-clip", type=float, default=config.SimConfig.z_clip)
    p.add_argument("--volvol", type=str, default=f"{config.SimConfig.volvol_mkt},{config.SimConfig.volvol_idio}",
                   help="vol-of-vol 'market,idio' lognormal sds, e.g. 0.15,0.10 (0,0 = off)")
    p.add_argument("--cluster-corr", type=float, default=config.SimConfig.cluster_corr)
    p.add_argument("--earn-implied-weight", type=float, default=config.SimConfig.earn_implied_weight)
    p.add_argument("--earn-sign-prior", type=int, default=config.SimConfig.earn_sign_prior)
    p.add_argument("--tail-skew-weight", type=float, default=config.SimConfig.tail_skew_weight)
    p.add_argument("--no-thanksgiving", action="store_true")
    # v2 field
    p.add_argument("--allin-vol-pow", type=float, default=config.FieldMix.allin_vol_pow)
    p.add_argument("--savvy", type=float, default=config.FieldMix.n_savvy,
                   help="expected number of opponents all-in on max-vol names")
    p.add_argument("--momentum-share", type=float, default=config.FieldMix.momentum_share)
    p.add_argument("--fad-prob", type=float, default=config.FieldMix.fad_prob)
    p.add_argument("--fad-mult", type=float, default=config.FieldMix.fad_mult)
    p.add_argument("--p2-loser-allin", type=float, default=config.FieldMix.p2_loser_allin)
    # robust mode
    p.add_argument("--worlds", type=int, default=48, help="robust: parameter worlds in the search")
    p.add_argument("--world-scenarios", type=int, default=500)
    p.add_argument("--val-worlds", type=int, default=160)
    p.add_argument("--quick", action="store_true",
                   help="period1: skip the secondary sensitivities (used by --mode stress)")
    p.add_argument("--workers", type=int, default=4, help="stress: parallel processes")
    p.add_argument("--stress-only", type=lambda x: x.split(";"), default=None,
                   help="stress: re-run only these variants (';'-separated names), rebuild the summary")
    p.add_argument("--rank-by", default="p_win_8w_policy",
                   help="metric used to rank candidates")
    p.add_argument("--my-return", type=str, default=None,
                   help="period2: my realised period-1 return, e.g. 0.083 or 8.3%%")
    p.add_argument("--dry-run", action="store_true",
                   help="period2 before Nov 20: use one simulated period-1 outcome "
                        "in place of realised returns (for testing only)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _mix_from_args(a) -> config.FieldMix:
    gm = tuple((g.split("=")[0], float(g.split("=")[1])) for g in a.group_mult.split(",") if g)
    mix = config.FieldMix(p_rebalance=a.p_rebalance, chase=a.chase, pop_noise=a.pop_noise,
                          n_opponents=a.participants - 1, foreign_share=a.foreign_share,
                          group_mult=gm, group_noise=a.group_noise,
                          allin_vol_pow=a.allin_vol_pow, n_savvy=a.savvy,
                          momentum_share=a.momentum_share, fad_prob=a.fad_prob,
                          fad_mult=a.fad_mult, p2_loser_allin=a.p2_loser_allin)
    if a.mix:
        d, m, x = (float(v) for v in a.mix.split(","))
        tot = d + m + x
        mix = dataclasses.replace(mix, diversified=d / tot, moderate=m / tot, allin=x / tot)
    return mix


def _sim_cfg(a) -> config.SimConfig:
    return config.SimConfig(n_scenarios=a.scenarios, n_validate=a.validate_scenarios,
                            seed=a.seed, block=a.block, vol_target=a.vol_target,
                            use_iv=not a.no_iv, iv_weight=a.iv_weight, z_clip=a.z_clip,
                            volvol_mkt=float(a.volvol.split(",")[0]),
                            volvol_idio=float(a.volvol.split(",")[1]),
                            cluster_corr=a.cluster_corr, earn_implied_weight=a.earn_implied_weight,
                            earn_sign_prior=a.earn_sign_prior, tail_skew_weight=a.tail_skew_weight,
                            thanksgiving=not a.no_thanksgiving)


def main(argv=None):
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose or a.mode == "fetch" else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    t0 = time.time()
    if a.mode == "fetch":
        from . import data
        rep = data.fetch_all(a.cache, end=a.end)
        print(json.dumps({k: rep[k] for k in ("last_price_date", "n_tickers", "failed_downloads",
                                              "stale_tickers")}, indent=1))
        for idx, r in rep["universe"].items():
            print(f"{idx}: {r['source']} ({r['count']}) +{r['added_vs_snapshot']} -{r['removed_vs_snapshot']}")
    elif a.mode == "stress":
        from .pipeline import run_stress
        common = ["--cache", str(a.cache), "--scenarios", str(a.scenarios),
                  "--validate-scenarios", str(a.validate_scenarios), "--seed", str(a.seed),
                  "--vol-target", a.vol_target, "--pop-noise", str(a.pop_noise)]
        if a.asof:
            common += ["--asof", a.asof.isoformat()]
        if a.no_iv:
            common += ["--no-iv"]
        run_stress(a, common, workers=a.workers)
    elif a.mode == "robust":
        from .robust import run_robust
        run_robust(a, _sim_cfg(a), _mix_from_args(a))
    elif a.mode == "update":
        from .update import run_update
        run_update(a, _sim_cfg(a), _mix_from_args(a))
    elif a.mode == "validate":
        from .validate import run_validate
        run_validate(a, _sim_cfg(a))
    elif a.mode == "period1":
        from .pipeline import run_period1
        run_period1(a, _sim_cfg(a), _mix_from_args(a))
    else:
        from .pipeline import run_period2
        if a.my_return is None:
            sys.exit("--mode period2 needs --my-return (e.g. 0.083 or 8.3%)")
        run_period2(a, _sim_cfg(a), _mix_from_args(a), _parse_return(a.my_return))
    log.info("done in %.0fs", time.time() - t0)
    print(f"[done in {time.time() - t0:.0f}s]")
