"""``--mode validate``: checks of the return model against history and options.

1. Vol forecaster backtest: QLIKE of 20-day-ahead realised variance for the
   candidate forecasters (EWMA 0.90/0.94/0.97, 60d, 1y, blend, HAR), fitted /
   chosen on the first year, scored on the last year (out of sample).
2. Vol-of-vol: dispersion of log(realised / forecast) 20-day vol, split into a
   market-wide part (cross-sectional median per date) and a per-stock part,
   net of the sampling noise of a 20-day vol estimate (simulated from each
   stock's own standardised residuals).
3. Right-tail reliability: predicted vs realised frequency of 20-day moves
   beyond +20% / +40% / -20% (ex-earnings), filtered historical simulation
   with and without the vol-of-vol multipliers.
4. Options: risk-neutral P(S_T > x S0) from the Nov 20 / Dec 18 smiles vs the
   simulation, and option-implied vs historical earnings moves.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math

import numpy as np
import pandas as pd

from . import config, data, report, sim
from .pipeline import _load

log = logging.getLogger(__name__)
H = 20
ANN = 252


def _realised_var(r: pd.DataFrame) -> pd.DataFrame:
    """Annualised mean squared return over the next H days (index = origin)."""
    return (r ** 2).rolling(H).mean().shift(-H) * ANN


def forecasters(r_x: pd.DataFrame) -> dict:
    """Annualised variance forecasts known at the close of each day."""
    out = {}
    ew_raw = data.ewma_vol(r_x, 0.94)
    r_w = r_x.clip(lower=-4 * ew_raw, upper=4 * ew_raw)
    for lam in (0.90, 0.94, 0.97):
        ew = data.ewma_vol(r_w, lam)                 # info to t-1
        v = (lam * ew ** 2 + (1 - lam) * r_w.fillna(0) ** 2)  # include day t
        out[f"ewma{int(lam * 100)}"] = v * ANN
    out["60d"] = r_w.rolling(60).var() * ANN
    out["1y"] = r_w.rolling(252, min_periods=120).var() * ANN
    out["blend"] = (0.5 * (np.sqrt(out["ewma94"]) + np.sqrt(out["60d"]))) ** 2
    return out, r_w


def _har(r_w: pd.DataFrame, rv_fwd: pd.DataFrame, train, test) -> pd.DataFrame:
    """Pooled HAR in logs: log RV_fwd ~ log rv_5d + log rv_22d + log rv_66d + log rv_252d."""
    feats = {k: np.log((r_w ** 2).rolling(n, min_periods=max(3, n // 2)).mean() * ANN)
             for k, n in (("d5", 5), ("d22", 22), ("d66", 66), ("d252", 252))}
    def stack(idx):
        X = pd.concat({k: v.loc[idx].stack() for k, v in feats.items()}, axis=1)
        y = np.log(rv_fwd.loc[idx].stack()).rename("y")
        d = X.join(y, how="inner").replace([np.inf, -np.inf], np.nan).dropna()
        return d
    tr = stack(train)
    A = np.column_stack([np.ones(len(tr)), tr[list(feats)].to_numpy()])
    beta, *_ = np.linalg.lstsq(A, tr["y"].to_numpy(), rcond=None)
    resid_var = np.var(tr["y"].to_numpy() - A @ beta)
    out = {}
    for k in feats:
        out[k] = feats[k].loc[test]
    pred = beta[0] + sum(b * out[k] for b, k in zip(beta[1:], feats))
    # log-normal bias correction so it forecasts the variance, not its median
    return np.exp(pred + 0.5 * resid_var), beta


def qlike(rv, f):
    x = (rv / f).to_numpy().ravel()
    x = x[np.isfinite(x) & (x > 0)]
    return float(np.mean(x - np.log(x) - 1)), float(np.mean(np.log(x))), len(x)


def vol_backtest(prices, extras, feat):
    r_x = extras["r_ex_earn"]
    fc, r_w = forecasters(r_x)
    rv = _realised_var(r_x)
    origins = r_x.index[-504:-H:5]
    train, test = origins[: len(origins) // 2], origins[len(origins) // 2:]
    fc["har"], beta = _har(r_w, rv, train, test)
    hv = feat.index[feat["vol1y"] > 0.6]
    rows = []
    for k, f in fc.items():
        f_t = f.loc[test]
        q_all, bias, n = qlike(rv.loc[test], f_t)
        q_hv, bias_hv, n_hv = qlike(rv.loc[test, hv], f_t[hv])
        rows.append({"forecaster": k, "qlike_all": q_all, "bias_log_all": bias, "n": n,
                     "qlike_highvol": q_hv, "bias_log_highvol": bias_hv, "n_highvol": n_hv})
    tab = pd.DataFrame(rows).sort_values("qlike_all")
    return tab, {"har_beta": [float(b) for b in beta], "test_from": str(test[0].date()),
                 "test_to": str(test[-1].date()), "n_highvol_names": len(hv)}, fc, rv, test


def volvol_calibration(extras, fc, rv, test, rng):
    """sd of log(realised/forecast vol): market part, per-stock part net of
    the sampling noise of a 20-day vol estimate."""
    e = 0.5 * np.log(rv.loc[test] / fc["blend"].loc[test])
    e = e.replace([np.inf, -np.inf], np.nan)
    common = e.median(axis=1)
    idio = e.sub(common, axis=0)
    # sampling noise: 20-day vol estimates drawn from each stock's own standardised residuals
    z = (extras["r_ex_earn"] / extras["ewma_ex_earn"]).iloc[-504:]
    noise = []
    for t in z.columns:
        col = z[t].dropna().to_numpy()
        if len(col) < 100:
            continue
        col = np.clip(col, -12, 12)
        draws = rng.choice(col, size=(2000, H))
        noise.append(np.var(0.5 * np.log((draws ** 2).mean(axis=1))))
    nv = float(np.mean(noise))
    raw_idio = float(np.nanstd(idio.to_numpy()))
    return {"sd_total": float(np.nanstd(e.to_numpy())), "sd_market": float(common.std()),
            "sd_idio_raw": raw_idio, "sd_sampling_noise": math.sqrt(nv),
            "sd_idio_net": math.sqrt(max(raw_idio ** 2 - nv, 0.0)),
            "mean_log_ratio": float(np.nanmean(e.to_numpy()))}


def tail_reliability(extras, fc, test, rng, vv=(0.15, 0.10), n_draw=1500):
    """Predicted (FHS bootstrap of the stock's own past residuals x blend
    forecast) vs realised frequency of 20-day ex-earnings moves."""
    r_x = extras["r_ex_earn"]
    zfull = (r_x / extras["ewma_ex_earn"]).clip(-12, 12)
    fwd = r_x.rolling(H).sum().shift(-H)
    thr = {"up20": math.log(1.2), "up40": math.log(1.4), "down20": math.log(0.8),
           "abs30": ("abs", math.log(1.3))}
    rows = []
    sig = np.sqrt(fc["blend"] / ANN)
    for o in test[::2]:
        pos = r_x.index.get_loc(o)
        past = zfull.iloc[max(0, pos - 504):pos + 1]
        mkt = vv[0] * rng.standard_normal(n_draw) - vv[0] ** 2
        for t in r_x.columns:
            col = past[t].dropna().to_numpy()
            s, y = sig.at[o, t], fwd.at[o, t]
            if len(col) < 120 or not np.isfinite(s) or not np.isfinite(y):
                continue
            col = (col - col.mean()) / col.std()
            starts = rng.integers(0, len(col) - 5, size=(n_draw, 4))
            zs = sum(col[starts[:, b, None] + np.arange(5)].sum(axis=1) for b in range(4))
            base = s * zs
            withvv = base * np.exp(mkt + vv[1] * rng.standard_normal(n_draw) - vv[1] ** 2)
            row = {"origin": o, "ticker": t, "sigma_ann": s * math.sqrt(ANN)}
            for k, x in thr.items():
                if isinstance(x, tuple):     # two-sided: insensitive to drift
                    x = x[1]
                    row[f"{k}_real"] = float(abs(y) > x)
                    row[f"{k}_pred"] = float((np.abs(base) > x).mean())
                    row[f"{k}_pred_vv"] = float((np.abs(withvv) > x).mean())
                    continue
                hit = y > x if x > 0 else y < x
                row[f"{k}_real"] = float(hit)
                row[f"{k}_pred"] = float((base > x).mean() if x > 0 else (base < x).mean())
                row[f"{k}_pred_vv"] = float((withvv > x).mean() if x > 0 else (withvv < x).mean())
            rows.append(row)
    df = pd.DataFrame(rows)
    summ = []
    for grp, d in (("all", df), ("vol > 60%", df[df["sigma_ann"] > 0.6])):
        for k in thr:
            summ.append({"names": grp, "event": k, "n": len(d), "realised": d[f"{k}_real"].mean(),
                         "predicted": d[f"{k}_pred"].mean(), "predicted_volvol": d[f"{k}_pred_vv"].mean(),
                         "brier": ((d[f"{k}_pred"] - d[f"{k}_real"]) ** 2).mean(),
                         "brier_volvol": ((d[f"{k}_pred_vv"] - d[f"{k}_real"]) ** 2).mean()})
    return pd.DataFrame(summ), df


def rn_tail(chains: pd.DataFrame, ticker: str, expiry: str, t: float, xs=(1.2, 1.4, 1.6)) -> dict:
    """Risk-neutral P(S_T > x S0) = -dC/dK, with C(K) from the call smile
    (own BS inversion of mids, linear in strike), central differences."""
    c = chains[(chains["ticker"] == ticker) & (chains["expiry"] == expiry) & (chains["type"] == "C")]
    if c.empty or not t:
        return {}
    spot = float(c["spot"].iloc[0])
    pts = []
    for _, r in c.iterrows():
        k = float(r["strike"])
        if not 0.7 * spot <= k <= 2.2 * spot:
            continue
        bid, ask = r.get("bid") or 0, r.get("ask") or 0
        mid = 0.5 * (bid + ask) if bid > 0 and ask > 0 else (r.get("lastPrice") or 0)
        iv = data._implied_vol(float(mid), spot, k, t, 0.04, True) if mid else None
        if iv and 0.05 < iv < 5:
            pts.append((k, iv))
    if len(pts) < 4:
        return {}
    ks, ivs = np.array(pts).T
    out = {"spot": spot}
    for x in xs:
        K = x * spot
        if K > ks.max() or K < ks.min():
            out[f"rn_p{x:g}"] = np.nan
            continue
        h = 0.01 * spot
        cK = [data._bs_price(spot, kk, t, 0.04, float(np.interp(kk, ks, ivs)), True) for kk in (K - h, K + h)]
        out[f"rn_p{x:g}"] = float(-(cK[1] - cK[0]) / (2 * h) * math.exp(0.04 * t))
        out[f"iv_{x:g}"] = float(np.interp(K, ks, ivs))
    return out


def options_check(md, feat, extras, cfg, n=20000):
    if md.chains is None or md.chains.empty:
        return None, None
    inp = sim.prepare_inputs(feat, extras, cfg)
    rng = np.random.default_rng(cfg.seed)
    G1 = sim.simulate_period(inp, 1, config.P1_DAYS, n, rng, cfg.block, cfg.earnings_prior_n)
    G2 = sim.simulate_period(inp, 2, config.P2_DAYS, n, rng, cfg.block, cfg.earnings_prior_n)
    us = [t for t in feat.index if data.is_us(t)]
    names = feat.loc[us].assign(v=inp.vol_ann[[inp.ix(t) for t in us]]).nlargest(25, "v").index
    rows = []
    for t in names:
        i = inp.ix(t)
        for label, G in (("p1", G1[:, i]), ("p2", G1[:, i] * G2[:, i])):
            iv = (md.meta.get(t, {}).get("iv") or {}).get(label) or {}
            rn = rn_tail(md.chains, t, iv.get("expiry"), iv.get("t_years"))
            if not rn:
                continue
            row = {"ticker": t, "horizon": "Nov 20" if label == "p1" else "Dec 18", "atm_iv": iv.get("iv")}
            for x in (1.2, 1.4, 1.6):
                row[f"rn_p{x:g}"] = rn.get(f"rn_p{x:g}")
                row[f"sim_p{x:g}"] = float((G > x).mean())
                row[f"iv_{x:g}"] = rn.get(f"iv_{x:g}")
            rows.append(row)
    tab = pd.DataFrame(rows)
    earn = feat.loc[feat["earn_implied_move"].notna(), ["earn_reaction", "earn_implied_move",
                                                         "earn_move_mean_abs"]].copy()
    if len(earn):
        earn["hist_rms_move"] = [float(np.sqrt(np.mean(np.square(extras["moves"].get(t, {}).get("moves") or [np.nan]))))
                                 for t in earn.index]
        earn["earn_scale_used"] = [inp.earn_scale[inp.ix(t)] for t in earn.index]
        earn = earn.sort_values("earn_implied_move", ascending=False)
    return tab, earn


def _pct(x, d=1):
    return "" if pd.isna(x) else f"{100 * x:.{d}f}%"


def run_validate(a, cfg: config.SimConfig):
    out = a.out or (config.OUTPUT_DIR / "validation")
    out.mkdir(parents=True, exist_ok=True)
    md, prices, feat, extras = _load(a, cfg)
    rng = np.random.default_rng(cfg.seed)
    log.info("vol forecaster backtest")
    vb, info, fc, rv, test = vol_backtest(prices, extras, feat)
    vb.to_csv(out / "vol_forecasters.csv", index=False, float_format="%.6g")
    log.info("vol-of-vol calibration")
    vv = volvol_calibration(extras, fc, rv, test, rng)
    log.info("tail reliability")
    rel, rel_rows = tail_reliability(extras, fc, test, rng, vv=(cfg.volvol_mkt, cfg.volvol_idio))
    rel.to_csv(out / "tail_reliability.csv", index=False, float_format="%.6g")
    log.info("options check")
    opt, earn = options_check(md, feat, extras, cfg)
    if opt is not None:
        opt.to_csv(out / "options_tail.csv", index=False, float_format="%.6g")
        earn.to_csv(out / "earnings_implied.csv", float_format="%.6g")
    js = {"vol_backtest": info, "volvol": vv}
    (out / "summary.json").write_text(json.dumps(js, indent=1))

    L = [f"# Model validation (prices {prices.asof.date()})", "",
         f"## 1. Vol forecasters (20 days ahead, out of sample {info['test_from']} to {info['test_to']})", "",
         "QLIKE (lower is better) and mean log(realised/forecast) variance (bias, + = forecast too low). "
         f"High-vol = 1y vol > 60% ({info['n_highvol_names']} names). HAR fitted on the first year.", "",
         report._md_table(vb.assign(**{c: vb[c].map(lambda x: f"{x:.3f}") for c in
                                     ("qlike_all", "bias_log_all", "qlike_highvol", "bias_log_highvol")})), "",
         "## 2. Vol-of-vol", "",
         f"log(realised/forecast 20-day vol), blend forecaster: total sd {vv['sd_total']:.2f}, "
         f"market-wide sd {vv['sd_market']:.2f}, per-stock sd {vv['sd_idio_raw']:.2f} of which sampling noise "
         f"{vv['sd_sampling_noise']:.2f} -> per-stock vol-of-vol net of noise **{vv['sd_idio_net']:.2f}**; "
         f"mean {vv['mean_log_ratio']:+.2f}. Model default: market {cfg.volvol_mkt:.2f}, per-stock {cfg.volvol_idio:.2f}.", "",
         "## 3. Tail reliability (20-day moves, earnings days neutralised)", "",
         report._md_table(rel.assign(**{c: rel[c].map(lambda x: _pct(x, 2)) for c in
                                      ("realised", "predicted", "predicted_volvol")},
                                   **{c: rel[c].map(lambda x: f"{x:.4f}") for c in ("brier", "brier_volvol")})), ""]
    if opt is not None and len(opt):
        L += ["## 4. Options: risk-neutral vs simulated right tail", "",
              "P(price > x times today) at the period ends. Risk-neutral probabilities from the call smile "
              "(USD), simulation in EUR with the base settings; FX adds ~2% vol, negligible here.", ""]
        o = opt.copy()
        for x in (1.2, 1.4, 1.6):
            o[f"sim/rn {x:g}"] = (o[f"sim_p{x:g}"] / o[f"rn_p{x:g}"]).map(lambda v: "" if pd.isna(v) else f"{v:.2f}")
            o[f"rn_p{x:g}"] = o[f"rn_p{x:g}"].map(_pct)
            o[f"sim_p{x:g}"] = o[f"sim_p{x:g}"].map(_pct)
        o["atm_iv"] = o["atm_iv"].map(lambda v: _pct(v, 0))
        cols = ["ticker", "horizon", "atm_iv"] + [c for x in (1.2, 1.4, 1.6) for c in (f"rn_p{x:g}", f"sim_p{x:g}", f"sim/rn {x:g}")]
        L += [report._md_table(o[cols]), ""]
        if earn is not None and len(earn):
            e = earn.head(25).reset_index()
            L += ["Option-implied earnings moves (sd of the reaction-day log move) vs historical RMS move:", "",
                  report._md_table(pd.DataFrame({"ticker": e["ticker"], "reaction": e["earn_reaction"],
                                                 "implied": e["earn_implied_move"].map(_pct),
                                                 "historical RMS": e["hist_rms_move"].map(_pct),
                                                 "size scale used": e["earn_scale_used"].map(lambda v: f"{v:.2f}")})), ""]
    else:
        L += ["## 4. Options", "", "No option chains in the cache (fetch with the v2 fetcher).", ""]
    (out / "report.md").write_text("\n".join(L))
    print(f"wrote {out}/report.md")
