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
    p.add_argument("--mode", choices=["fetch", "period1", "period2"], required=True)
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
    p.add_argument("--rank-by", default="p_win_8w_switch",
                   help="metric used to rank candidates")
    p.add_argument("--my-return", type=str, default=None,
                   help="period2: my realised period-1 return, e.g. 0.083 or 8.3%%")
    p.add_argument("--dry-run", action="store_true",
                   help="period2 before Nov 20: use one simulated period-1 outcome "
                        "in place of realised returns (for testing only)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _mix_from_args(a) -> config.FieldMix:
    mix = config.FieldMix(p_rebalance=a.p_rebalance, chase=a.chase, pop_noise=a.pop_noise)
    if a.mix:
        d, m, x = (float(v) for v in a.mix.split(","))
        tot = d + m + x
        mix = dataclasses.replace(mix, diversified=d / tot, moderate=m / tot, allin=x / tot)
    return mix


def _sim_cfg(a) -> config.SimConfig:
    return config.SimConfig(n_scenarios=a.scenarios, n_validate=a.validate_scenarios,
                            seed=a.seed, block=a.block, vol_target=a.vol_target,
                            use_iv=not a.no_iv, iv_weight=a.iv_weight)


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
