"""Simulation module.

* ``prepare_inputs``    filtered-historical-simulation residuals, target vols,
                        drifts, earnings jumps and ex-dividend drops.
* ``simulate_period``   block bootstrap of joint daily EUR returns.
* ``simulate_field``    179 opponents drawn from the archetype mixture.
* ``CandidateSet`` / ``evaluate``   my whole-share portfolios and their
                        win / top-5 probabilities against the field.

All return arrays are gross, price-only, EUR: ``G[s, i]`` is stock i's
end/start price ratio in scenario s, which is exactly what the contest scores.
"""
from __future__ import annotations

import dataclasses
import itertools
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config, universe

TOPK = 32          # opponents' best scores kept per scenario (ties + top-5)
TIE_TOL = 1e-9


# ==========================================================================
# Inputs
# ==========================================================================
@dataclass
class SimInputs:
    tickers: list
    Z: np.ndarray          # (T, N) standardised daily residuals, unit variance
    sigma_d: np.ndarray    # (N,) target daily vol (ex-earnings)
    mu_d: np.ndarray       # (N,) daily log drift
    price_eur: np.ndarray  # (N,) latest close in EUR (whole-share sizing)
    popularity: np.ndarray
    vol_ann: np.ndarray    # (N,) target annual vol (field all-in sampling)
    earn: dict             # period -> list of (i, day offset, own mults)
    pooled_mults: np.ndarray
    exdiv: dict            # period -> (N,) fraction of price lost to ex-div
    cons_w: np.ndarray     # (N,) consensus basket weights
    iv_scale: np.ndarray | None = None   # vol multiplier from the IV calibration
    popularity_eu: np.ndarray | None = None  # non-Spanish European students
    groups: dict | None = None               # popularity group -> positions
    # v2
    earn_pup: np.ndarray | None = None       # (N,) P(earnings move is up), shrunk to 0.5
    earn_scale: np.ndarray | None = None     # (N,) multiplier on drawn earnings-move multiples
    h2_scale: np.ndarray | None = None       # (N,) period-2 trading days / P2_DAYS (Thanksgiving)
    cluster: np.ndarray | None = None        # (N,) bool, AI-infra cluster
    cluster_corr: float = 0.0
    volvol: tuple = (0.0, 0.0)               # (market, idio) lognormal sd of vol multipliers
    mom: np.ndarray | None = None            # (N,) z-score of the 3-month log return

    @property
    def n(self) -> int:
        return len(self.tickers)

    def ix(self, ticker: str) -> int:
        return self.tickers.index(ticker)


def _period_days(period: int) -> pd.DatetimeIndex:
    a, b = ((config.P1_START, config.P1_END) if period == 1 else (config.P2_START, config.P2_END))
    return pd.bdate_range(a, b)


def target_vol(feat: pd.DataFrame, how: str, floor: float, cap: float) -> pd.Series:
    ew, v60, v1y = feat["ewma_vol_ex_earn"], feat["vol60_ex_earn"], feat["vol1y_ex_earn"]
    v = {"ewma": ew, "60d": v60, "1y": v1y, "blend": 0.5 * (ew + v60)}[how]
    v = v.fillna(v60).fillna(v1y).fillna(feat["vol20"])
    return v.clip(floor, cap)


def prepare_inputs(feat: pd.DataFrame, extras: dict, cfg: config.SimConfig,
                   periods=(1, 2), rng: np.random.Generator | None = None) -> SimInputs:
    """Build the bootstrap pool and per-stock parameters.

    Residuals follow filtered historical simulation: each stock's daily EUR
    return (earnings days neutralised) is divided by its own EWMA vol at the
    time, so the pool has unit variance and the *current* vol can be
    re-imposed. Rows are kept whole (same calendar day for all stocks) so the
    cross-section and FX co-movement survive the bootstrap.
    """
    rng = rng or np.random.default_rng(cfg.seed)
    tickers = list(feat.index)
    n_days = 252 * config.HISTORY_YEARS
    r = extras["r_ex_earn"][tickers].iloc[-n_days:]
    s = extras["ewma_ex_earn"][tickers].reindex(r.index)
    Z = (r / s).to_numpy(dtype=float)
    Z[~np.isfinite(Z)] = np.nan
    Z = np.clip(Z, -cfg.z_clip, cfg.z_clip)

    # Market factor for filling short histories.
    cw = extras["consensus_weights"].reindex(tickers).fillna(0.0).to_numpy()
    zc = np.nansum(np.nan_to_num(Z) * cw, axis=1)
    zc = (zc - zc.mean()) / zc.std()
    for i in range(Z.shape[1]):
        col = Z[:, i]
        ok = np.isfinite(col)
        if ok.sum() >= 2:
            col[ok] = (col[ok] - col[ok].mean()) / (col[ok].std() or 1.0)
        if ok.all():
            continue
        # Short history (recent IPO): keep the market co-movement estimated on
        # the days we have, draw the idiosyncratic part from its own residuals.
        if ok.sum() >= 40:
            rho = float(np.corrcoef(col[ok], zc[ok])[0, 1])
            idio = col[ok] - rho * zc[ok]
        else:
            rho = 0.5
            idio = rng.standard_t(4, size=500)
        idio = (idio - idio.mean()) / max(idio.std(), 1e-9)
        eps = rng.choice(idio, size=(~ok).sum())
        col[~ok] = rho * zc[~ok] + math.sqrt(max(1 - rho ** 2, 0.0)) * eps
        Z[:, i] = col

    vol = target_vol(feat, cfg.vol_target, cfg.vol_floor, cfg.vol_cap)
    sigma_d = vol.to_numpy() / math.sqrt(252)

    pooled = np.concatenate([np.asarray(m["mults"], float) for m in extras["moves"].values()
                             if m.get("mults")] or [np.array([2.5])])
    pooled = pooled[np.isfinite(pooled)]
    earn = {}
    for p in periods:
        days = _period_days(p)
        lst = []
        for i, t in enumerate(tickers):
            own = np.asarray(extras["moves"].get(t, {}).get("mults", []), float)
            own = own[np.isfinite(own)]
            p_primary = float(feat.at[t, "earn_p_primary"]) if "earn_p_primary" in feat else 1.0
            # (period column, reaction column, probability the event is there)
            for pc, rc, prob in (("earn_period", "earn_reaction", p_primary),
                                 ("earn_alt_period", "earn_alt_reaction", 1.0 - p_primary)):
                if pc not in feat or prob <= 0:
                    continue
                ep, rd = feat.at[t, pc], feat.at[t, rc]
                if pd.isna(ep) or int(ep) != p or pd.isna(rd) or rd is None:
                    continue
                k = days.searchsorted(pd.Timestamp(rd))
                if 0 <= k < len(days):
                    lst.append((i, int(k), own, prob))
        earn[p] = lst
    earn_pup, earn_scale = _earnings_shape(feat, extras, tickers, sigma_d, pooled, cfg)
    iv_scale = np.ones(len(tickers))
    if cfg.use_iv:
        iv_scale = _iv_scale(feat, sigma_d, earn, pooled, periods[0], cfg, earn_scale)
        sigma_d = sigma_d * iv_scale
    if cfg.tail_skew_weight and "skew_130_p2" in feat:
        sk = feat["skew_130_p2"].to_numpy(float)
        ok = np.isfinite(sk) & (sk > 0)
        if ok.sum() >= 10:
            tilt = np.ones(len(tickers))
            tilt[ok] = (sk[ok] / np.median(sk[ok])) ** cfg.tail_skew_weight
            sigma_d = sigma_d * tilt
            iv_scale = iv_scale * tilt
    vol = pd.Series(sigma_d * math.sqrt(252), index=tickers)
    beta = feat["beta_cons"].fillna(1.0).clip(0.0, 2.5).to_numpy()
    mu_a = cfg.rf + beta * cfg.erp
    mu_d = mu_a / 252 - 0.5 * sigma_d ** 2
    exdiv = {p: feat[f"exdiv_p{p}_pct"].fillna(0.0).clip(0, 0.2).to_numpy() for p in periods}
    return SimInputs(tickers=tickers, Z=Z, sigma_d=sigma_d, mu_d=mu_d,
                     price_eur=feat["price_eur"].to_numpy(float),
                     popularity=feat["popularity"].to_numpy(float),
                     vol_ann=vol.to_numpy(), earn=earn, pooled_mults=pooled,
                     exdiv=exdiv, cons_w=cw / cw.sum(), iv_scale=iv_scale,
                     popularity_eu=universe.popularity_vector_eu(tickers).to_numpy(float),
                     groups={g: np.asarray(v, int) for g, v in universe.group_members(tickers).items()},
                     earn_pup=earn_pup, earn_scale=earn_scale,
                     h2_scale=np.array([(config.US_P2_DAYS if (cfg.thanksgiving and "." not in t)
                                         else config.P2_DAYS) / config.P2_DAYS for t in tickers]),
                     cluster=np.isin(tickers, config.AI_CLUSTER), cluster_corr=cfg.cluster_corr,
                     volvol=(cfg.volvol_mkt, cfg.volvol_idio), mom=_momentum_z(feat))


def _momentum_z(feat: pd.DataFrame) -> np.ndarray:
    """What a "buy the recent winners" student sees: average of the 3-month
    and 1-year return z-scores (log), clipped at -2/+3 s.d."""
    zs = []
    for c in ("ret_3m", "ret_1y"):
        if c in feat:
            x = np.log1p(feat[c].astype(float))
            x = x.fillna(x.median())
            zs.append((x - x.mean()) / (x.std() or 1.0))
    if not zs:
        return np.zeros(len(feat))
    return np.clip(sum(zs) / len(zs), -2.0, 3.0).to_numpy()


def _earnings_shape(feat, extras, tickers, sigma_d, pooled, cfg):
    """Up-probability of earnings moves (own history shrunk to 50/50) and a
    per-stock scale on the move size that blends the historical moves with
    the option-implied event move (cross-section only: implied event
    variance is rescaled by the median historical/implied ratio)."""
    n = len(tickers)
    pup = np.full(n, 0.5)
    scale = np.ones(n)
    prior = cfg.earn_sign_prior
    hist_m2 = np.full(n, np.nan)
    for i, t in enumerate(tickers):
        mv = np.asarray(extras["moves"].get(t, {}).get("moves", []), float)
        mv = mv[np.isfinite(mv)]
        if len(mv):
            pup[i] = ((mv > 0).sum() + 0.5 * prior) / (len(mv) + prior)
        own = np.asarray(extras["moves"].get(t, {}).get("mults", []), float)
        own = own[np.isfinite(own)]
        k = len(own)
        hist_m2[i] = ((k * np.mean(own ** 2) if k else 0.0) + cfg.earnings_prior_n * np.mean(pooled ** 2)) \
            / (k + cfg.earnings_prior_n)
    if cfg.earn_implied_weight > 0 and "earn_implied_move" in feat:
        imp = feat["earn_implied_move"].to_numpy(float)          # sd of the event log move
        imp_m2 = (imp / sigma_d) ** 2
        ok = np.isfinite(imp_m2) & (imp_m2 > 0) & np.isfinite(hist_m2)
        if ok.sum() >= 5:
            k = np.median(hist_m2[ok] / imp_m2[ok])
            w = cfg.earn_implied_weight
            target = (1 - w) * hist_m2[ok] + w * k * imp_m2[ok]
            scale[ok] = np.sqrt(target / hist_m2[ok])
    return pup, scale


def _iv_scale(feat, sigma_d, earn, pooled, period, cfg, earn_scale=None) -> np.ndarray:
    """Scale factors that move each US stock's simulated period variance
    (diffusion + earnings jump) toward the variance implied by its ATM
    options for the expiry that ends the period (Nov 20 / Dec 18 are the
    monthly expiries, so the match is exact).

    Only the cross-section is taken from the options market: IV is first
    rescaled by the median model/IV ratio across US names, so the average
    level stays model-based and EU names (no options in Yahoo) are not
    disadvantaged by the variance risk premium.
    """
    H = config.P1_DAYS if period == 1 else config.P2_DAYS
    prior = cfg.earnings_prior_n
    jump_m2 = np.zeros(len(sigma_d))       # prob x (E[mult^2] - 1), per stock
    for i, _, own, prob in earn.get(period, []):
        n = len(own)
        em2 = (n * np.mean(own ** 2) if n else 0.0) + prior * np.mean(pooled ** 2)
        es = 1.0 if earn_scale is None else earn_scale[i] ** 2
        jump_m2[i] += prob * (es * em2 / (n + prior) - 1.0)
    model_var = sigma_d ** 2 * (H + jump_m2)
    iv = feat[f"iv_p{period}"].to_numpy(float)
    t = feat.get(f"iv_p{period}_t", pd.Series(np.nan, index=feat.index)).to_numpy(float)
    nb = feat.get(f"iv_p{period}_bdays", pd.Series(np.nan, index=feat.index)).to_numpy(float)
    ok = np.isfinite(iv) & (iv > 0.05) & np.isfinite(t) & np.isfinite(nb) & (nb > 0)
    scale = np.ones(len(sigma_d))
    if ok.sum() < 10:
        return scale
    iv_var = iv ** 2 * t * H / nb
    k = np.median(model_var[ok] / iv_var[ok])
    target = (1 - cfg.iv_weight) * model_var + cfg.iv_weight * k * iv_var
    scale[ok] = np.sqrt(target[ok] / model_var[ok])
    return scale


# ==========================================================================
# Return simulation
# ==========================================================================
def simulate_period(inp: SimInputs, period: int, horizon: int, n_scen: int,
                    rng: np.random.Generator, block: int = 5, prior_n: int = 4,
                    with_earnings: bool = True, return_log: bool = False):
    """Block-bootstrap ``horizon`` days of joint returns for ``n_scen`` scenarios.

    Returns gross price-only EUR returns (S, N): exp(sum of daily log TR
    returns) x (1 - ex-dividend drop in the window).
    """
    Z = inp.Z
    T, N = Z.shape
    nb = math.ceil(horizon / block)
    lens = [block] * (nb - 1) + [horizon - block * (nb - 1)]
    starts = rng.integers(0, T - block + 1, size=(n_scen, nb))
    C = np.vstack([np.zeros((1, N)), np.cumsum(Z, axis=0)])
    zsum = np.zeros((n_scen, N))
    for b, ln in enumerate(lens):
        zsum += C[starts[:, b] + ln] - C[starts[:, b]]
    sig = inp.sigma_d
    mu = inp.mu_d
    if period == 2 and inp.h2_scale is not None:
        # fewer trading days (US Thanksgiving): shrink the diffusive variance
        sig = sig * np.sqrt(inp.h2_scale)
        mu = mu * inp.h2_scale
    if inp.cluster_corr > 0 and inp.cluster is not None and inp.cluster.any():
        c = inp.cluster_corr
        f = rng.standard_normal(n_scen)[:, None] * math.sqrt(horizon)
        zsum[:, inp.cluster] = math.sqrt(1 - c) * zsum[:, inp.cluster] + math.sqrt(c) * f
    L = horizon * mu + sig * zsum
    if with_earnings:
        prior = prior_n
        for i, k, own, prob in inp.earn.get(period, []):
            b, o = divmod(k, block)
            t = starts[:, b] + o
            # drop that day's diffusive move, add an earnings jump scaled to
            # the stock's current vol (own history shrunk to the pooled one)
            n_own = len(own)
            use_own = rng.random(n_scen) < n_own / (n_own + prior) if n_own else np.zeros(n_scen, bool)
            m = rng.choice(inp.pooled_mults, size=n_scen)
            if n_own:
                m = np.where(use_own, rng.choice(own, size=n_scen), m)
            if inp.earn_scale is not None:
                m = m * inp.earn_scale[i]
            pup = 0.5 if inp.earn_pup is None else inp.earn_pup[i]
            sign = np.where(rng.random(n_scen) < pup, 1.0, -1.0)
            jump = sign * m * inp.sigma_d[i]
            jump -= np.log(np.mean(np.exp(jump)))  # skew allowed, arithmetic mean kept
            here = rng.random(n_scen) < prob       # uncertain date: maybe other window
            L[:, i] += np.where(here, jump - inp.sigma_d[i] * Z[t, i], 0.0)
    vm, vi = inp.volvol
    if vm > 0 or vi > 0:
        # vol uncertainty: scale each scenario's shocks by variance-neutral
        # lognormal multipliers (market-wide x per-stock)
        mult = np.exp(vm * rng.standard_normal((n_scen, 1)) - vm ** 2) * \
            np.exp(vi * rng.standard_normal((n_scen, N)) - vi ** 2)
        drift = horizon * mu
        L = drift + (L - drift) * mult
    G = np.exp(L) * (1.0 - inp.exdiv.get(period, 0.0))
    return (G, L) if return_log else G


# ==========================================================================
# Opponent field
# ==========================================================================
def _draw_portfolios(rng, n_rows: int, logq: np.ndarray, k_lo: int, k_hi: int,
                     alpha: float, price: np.ndarray, kmax: int = 15):
    """Sample ``n_rows`` portfolios: k names without replacement with
    probability ~ exp(logq) (Gumbel top-k), Dirichlet weights, whole shares.
    ``logq`` is (N,) or (n_rows, N). Returns padded (idx, eff_weight)."""
    N = logq.shape[-1]
    keys = logq + rng.gumbel(size=(n_rows, N))
    top = np.argpartition(-keys, k_hi - 1, axis=1)[:, :k_hi]
    order = np.argsort(-np.take_along_axis(keys, top, axis=1), axis=1)
    idx = np.take_along_axis(top, order, axis=1)
    k = rng.integers(k_lo, k_hi + 1, size=n_rows)
    mask = np.arange(k_hi)[None, :] < k[:, None]
    w = rng.gamma(alpha, size=(n_rows, k_hi)) * mask
    w /= w.sum(axis=1, keepdims=True)
    px = price[idx]
    shares = np.floor(config.CAPITAL_EUR * w / px)
    eff = shares * px / config.CAPITAL_EUR
    pad = kmax - k_hi
    if pad > 0:
        idx = np.pad(idx, ((0, 0), (0, pad)))
        eff = np.pad(eff, ((0, 0), (0, pad)))
    return idx.astype(np.int32), eff


N_TYPES = 5   # diversified, moderate, all-in, savvy (max vol), momentum


def _type_specs(inp: SimInputs, mix: config.FieldMix):
    pop = inp.popularity
    lv = np.log(inp.vol_ann)
    mom = inp.mom if inp.mom is not None else np.zeros(inp.n)
    return [
        (np.log(pop), mix.div_k[0], mix.div_k[1]),
        (mix.mod_pop_power * np.log(pop), mix.mod_k[0], mix.mod_k[1]),
        (np.log(pop) + mix.allin_vol_pow * lv, 1, 2),
        (mix.savvy_pow * lv, 1, 1),
        (0.5 * np.log(pop) + mix.momentum_beta * mom, 1, 5),
    ]


def _draw_field_rows(rng, inp, mix, types, extra_logits=None):
    """One portfolio per row for the given archetype codes (0/1/2)."""
    n = len(types)
    idx = np.zeros((n, 15), np.int32)
    eff = np.zeros((n, 15))
    for t, (logq, lo, hi) in enumerate(_type_specs(inp, mix)):
        rows = np.flatnonzero(types == t)
        if not len(rows):
            continue
        lq = logq if extra_logits is None else logq[None, :] + extra_logits[rows]
        if t == 2:  # all-in: 1 name with prob p_single, else 2
            k1 = rng.random(len(rows)) < mix.p_single
            for sub, (a, b) in ((rows[k1], (1, 1)), (rows[~k1], (2, 2))):
                if len(sub):
                    lqs = lq if lq.ndim == 1 else lq[np.searchsorted(rows, sub)]
                    i_, e_ = _draw_portfolios(rng, len(sub), lqs, a, b, mix.dirichlet_alpha / 2,
                                              inp.price_eur)
                    idx[sub], eff[sub] = i_, e_
        else:
            i_, e_ = _draw_portfolios(rng, len(rows), lq, lo, hi, mix.dirichlet_alpha, inp.price_eur)
            idx[rows], eff[rows] = i_, e_
    return idx, eff


@dataclass
class FieldResult:
    top1: np.ndarray        # (S, K) opponents' best period-1 scores, sorted desc
    top8: np.ndarray        # (S, K) opponents' best final (8-week) scores
    n_hold: np.ndarray      # (S, N) opponents holding stock i in period 1
    max_w: np.ndarray       # (S, N) largest opponent weight on stock i
    mix: config.FieldMix

    @property
    def field_max1(self):
        return self.top1[:, 0]

    @property
    def field_max8(self):
        return self.top8[:, 0]


class _Pool:
    """Pre-drawn portfolios per archetype. Portfolio choice does not depend
    on the return scenario, so opponents are sampled from a large pool
    instead of being drawn from scratch for every scenario (same
    distribution, ~10x faster). Within a scenario duplicates are as rare as
    1-in-pool-size, apart from the genuinely common all-in picks."""

    def __init__(self, inp, mix, rng, size=60_000):
        self.idx, self.eff = [], []
        probs = mix.type_probs()
        for t in range(N_TYPES):
            # every type a re-picker can switch into (all-in) gets a pool
            n_t = size if (probs[t] > 0 or t == 2) else 0
            if n_t and t >= 3:
                n_t = max(2_000, size // 4)
            i_, e_ = _draw_field_rows(rng, inp, mix, np.full(n_t, t)) if n_t else \
                (np.zeros((0, 15), np.int32), np.zeros((0, 15)))
            self.idx.append(i_)
            self.eff.append(e_)

    def draw(self, rng, types):
        idx = np.zeros((len(types), 15), np.int32)
        eff = np.zeros((len(types), 15))
        for t in range(N_TYPES):
            rows = np.flatnonzero(types == t)
            if not len(rows):
                continue
            pick = rng.integers(0, len(self.idx[t]), size=len(rows))
            idx[rows], eff[rows] = self.idx[t][pick], self.eff[t][pick]
        return idx, eff


def _popularity_worlds(n_scen: int, mix: config.FieldMix) -> int:
    """Number of popularity draws ("worlds") per field: one per ~1,000 scenarios."""
    noisy = mix.pop_noise > 0 or mix.group_noise > 0 or mix.fad_prob > 0
    return max(20, n_scen // 1000) if noisy else 1


def _world_multiplier(inp: SimInputs, mix: config.FieldMix, rng) -> np.ndarray:
    """Popularity multiplier for one world: deterministic group stress x
    shared group factor x per-name noise (lognormal factors have mean 1)."""
    mult = np.ones(inp.n)
    groups = inp.groups or {}
    for g, m in mix.group_mult:
        mult[groups[g]] *= m
    if mix.group_noise > 0:
        sig = mix.group_noise
        for idx in groups.values():
            mult[idx] *= math.exp(sig * rng.standard_normal() - 0.5 * sig ** 2)
    if mix.pop_noise > 0:
        sig = mix.pop_noise
        mult *= np.exp(sig * rng.standard_normal(inp.n) - 0.5 * sig ** 2)
    if mix.fad_prob > 0 and rng.random() < mix.fad_prob:
        # one high-vol name becomes "the" stock everyone talks about
        top = np.argsort(-inp.vol_ann)[:30]
        q = inp.vol_ann[top] / inp.vol_ann[top].sum()
        j = rng.choice(top, p=q)
        mult[j] *= mix.fad_mult * math.exp(0.5 * rng.standard_normal())
    return mult


def simulate_field(inp: SimInputs, G1: np.ndarray, G2: np.ndarray, mix: config.FieldMix,
                   rng: np.random.Generator, n_opp: int | None = None,
                   chunk: int = 500, pool_inp: SimInputs | None = None,
                   n_worlds: int | None = None, pool_size: int | None = None) -> FieldResult:
    """Fresh field of ``mix.n_opponents`` opponents for every scenario.

    Popularity is uncertain (the weights are judgement calls): scenarios are
    split into "worlds", each drawing one true popularity vector shared by
    every opponent in that world (per-name lognormal noise, optional shared
    factor per group, optional deterministic group stress). Noise is per
    contest, not per student, so it does not average away across opponents.
    A share ``mix.foreign_share`` of opponents uses the non-Spanish European
    popularity profile instead of the Spanish one.

    Period 2: a share ``p_rebalance`` of opponents re-pick (same archetype
    and origin, optionally tilted to period-1 winners via ``mix.chase``);
    the rest keep their shares, so their final score is buy-and-hold.
    ``pool_inp`` (prices for the re-pick) defaults to ``inp``.
    """
    S, N = G1.shape
    n_opp = n_opp or mix.n_opponents
    probs = mix.type_probs()
    top1 = np.empty((S, TOPK))
    top8 = np.empty((S, TOPK))
    n_hold = np.zeros((S, N), np.int16)
    max_w = np.zeros((S, N), np.float32)
    n_worlds = n_worlds or _popularity_worlds(S, mix)
    pool_size = pool_size or (60_000 if n_worlds == 1 else 12_000)
    bounds = np.linspace(0, S, n_worlds + 1).astype(int)
    eu = mix.foreign_share > 0 and inp.popularity_eu is not None
    for w in range(n_worlds):
        mult = _world_multiplier(inp, mix, rng)
        pinp = pool_inp or inp
        profiles = [("es", lambda x: x.popularity)] + ([("eu", lambda x: x.popularity_eu)] if eu else [])
        pools1, pools2 = [], []
        for _, getpop in profiles:
            inp_w = dataclasses.replace(inp, popularity=getpop(inp) * mult)
            pinp_w = dataclasses.replace(pinp, popularity=getpop(pinp) * mult)
            p1 = _Pool(inp_w, mix, rng, pool_size)
            pools1.append(p1)
            # re-picks come from the same pool unless period-2 prices differ
            pools2.append(None if mix.chase else (p1 if pool_inp is None else _Pool(pinp_w, mix, rng, pool_size)))
        chase_inp = dataclasses.replace(pinp, popularity=pinp.popularity * mult)
        for s0 in range(bounds[w], bounds[w + 1], chunk):
            s1 = min(bounds[w + 1], s0 + chunk)
            _field_chunk(s0, s1, G1, G2, mix, rng, n_opp, probs, pools1, pools2, chase_inp,
                         top1, top8, n_hold, max_w)
    return FieldResult(top1=top1, top8=top8, n_hold=n_hold, max_w=max_w, mix=mix)


def _draw_mixed(rng, pools, types, origin):
    """Draw from the Spanish pool, or the European one where ``origin`` is set."""
    idx, eff = pools[0].draw(rng, types)
    if len(pools) > 1 and origin.any():
        i2, e2 = pools[1].draw(rng, types[origin])
        idx[origin], eff[origin] = i2, e2
    return idx, eff


def _field_chunk(s0, s1, G1, G2, mix, rng, n_opp, probs, pools1, pools2, chase_inp,
                 top1, top8, n_hold, max_w):
    """Score opponents for scenarios s0:s1 and record leaderboard stats."""
    N = G1.shape[1]
    m = s1 - s0
    rows = m * n_opp
    scen = np.repeat(np.arange(s0, s1), n_opp)
    types = rng.choice(N_TYPES, size=rows, p=probs)
    origin = rng.random(rows) < mix.foreign_share
    idx, eff = _draw_mixed(rng, pools1, types, origin)
    g1 = G1[scen[:, None], idx]
    cash = 1.0 - eff.sum(axis=1)
    r1 = (eff * g1).sum(axis=1) + cash
    # period 2
    reb = rng.random(rows) < mix.p_rebalance
    r8 = (eff * g1 * G2[scen[:, None], idx]).sum(axis=1) + cash
    types2 = types
    if mix.p2_loser_allin > 0:
        med = np.median(r1.reshape(m, n_opp), axis=1)
        behind = r1 < np.repeat(med, n_opp)
        types2 = np.where(behind & (rng.random(rows) < mix.p2_loser_allin), 2, types)
    if reb.any():
        if mix.chase:
            lg = np.log(G1[s0:s1])
            z = (lg - lg.mean(1, keepdims=True)) / (lg.std(1, keepdims=True) + 1e-12)
            extra = np.repeat(mix.chase * z, n_opp, axis=0)
            idx2, eff2 = _draw_field_rows(rng, chase_inp, mix, types2, extra)
        else:
            idx2, eff2 = _draw_mixed(rng, pools2, types2, origin)
        r2 = (eff2 * G2[scen[:, None], idx2]).sum(axis=1) + 1.0 - eff2.sum(axis=1)
        r8 = np.where(reb, r1 * r2, r8)
    r1m = r1.reshape(m, n_opp)
    r8m = r8.reshape(m, n_opp)
    top1[s0:s1] = -np.sort(-r1m, axis=1)[:, :TOPK]
    top8[s0:s1] = -np.sort(-r8m, axis=1)[:, :TOPK]
    held = eff > 0
    flat = (scen[:, None] * N + idx)[held] - s0 * N
    n_hold[s0:s1] += np.bincount(flat, minlength=m * N).reshape(m, N).astype(np.int16)
    big = eff[held] >= 0.15   # only concentrated holdings matter for "shadowing"
    np.maximum.at(max_w[s0:s1].reshape(-1), flat[big], eff[held][big].astype(np.float32))


# ==========================================================================
# Candidates
# ==========================================================================
def whole_shares(target_w: np.ndarray, price: np.ndarray, capital: float = config.CAPITAL_EUR):
    """Floor each target allocation to whole shares, then spend leftover cash
    one share at a time on the name furthest below its target."""
    budget = target_w * capital
    shares = np.floor(budget / price)
    cash = capital - shares @ price
    names = np.flatnonzero(target_w > 0)
    while True:
        ok = names[price[names] <= cash + 1e-9]
        if not len(ok):
            break
        gap = budget[ok] - shares[ok] * price[ok]
        j = ok[np.argmax(gap)]
        shares[j] += 1
        cash -= price[j]
    return shares, cash


@dataclass
class CandidateSet:
    labels: list
    kinds: list
    W: np.ndarray           # (C, N) effective weights after whole shares
    cash: np.ndarray        # (C,) cash fraction
    shares: np.ndarray      # (C, N)

    @classmethod
    def build(cls, inp: SimInputs, targets: list[tuple[str, str, np.ndarray]]):
        labels, kinds, W, cash, sh = [], [], [], [], []
        for label, kind, tw in targets:
            s, c = whole_shares(tw, inp.price_eur)
            if s.sum() == 0:
                continue
            labels.append(label)
            kinds.append(kind)
            sh.append(s)
            W.append(s * inp.price_eur / config.CAPITAL_EUR)
            cash.append(c / config.CAPITAL_EUR)
        return cls(labels, kinds, np.array(W), np.array(cash), np.array(sh))

    def subset(self, rows):
        rows = list(rows)
        return CandidateSet([self.labels[r] for r in rows], [self.kinds[r] for r in rows],
                            self.W[rows], self.cash[rows], self.shares[rows])

    def __len__(self):
        return len(self.labels)


def _label(inp, w):
    nz = np.flatnonzero(w)
    if len(nz) == 1:
        return inp.tickers[nz[0]]
    return " + ".join(f"{inp.tickers[i]} {w[i]:.0%}" for i in nz)


def single_targets(inp: SimInputs):
    out = []
    for i in range(inp.n):
        w = np.zeros(inp.n)
        w[i] = 1.0
        out.append((inp.tickers[i], "single", w))
    return out


def pair_targets(inp: SimInputs, names: list[int]):
    out = []
    for a, b in itertools.combinations(names, 2):
        for wa, wb in config.PAIR_WEIGHTS:
            w = np.zeros(inp.n)
            w[a], w[b] = wa, wb
            out.append((_label(inp, w), "pair", w))
    return out


def triple_targets(inp: SimInputs, base_pairs: list[np.ndarray], thirds: list[int]):
    out, seen = [], set()
    for wp in base_pairs:
        held = set(np.flatnonzero(wp))
        for c in thirds:
            if c in held:
                continue
            for w3 in config.TRIPLE_THIRD_WEIGHTS:
                w = wp * (1 - w3)
                w[c] = w3
                key = tuple(np.round(w, 3))
                if key in seen:
                    continue
                seen.add(key)
                out.append((_label(inp, w), "triple", w))
    return out


def benchmark_targets(inp: SimInputs):
    def ew(names):
        w = np.zeros(inp.n)
        ix = [inp.tickers.index(t) for t in names if t in inp.tickers]
        w[ix] = 1.0 / len(ix)
        return w
    pop_top10 = [inp.tickers[i] for i in np.argsort(-inp.popularity)[:10]]
    return [
        ("Consensus basket", "benchmark", inp.cons_w.copy()),
        ("Top-10 popular (EW)", "benchmark", ew(pop_top10)),
        ("Magnificent 7 (EW)", "benchmark", ew(["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"])),
        ("IBEX blue chips (EW)", "benchmark", ew(["ITX.MC", "SAN.MC", "IBE.MC", "BBVA.MC", "TEF.MC"])),
    ]


# ==========================================================================
# Metrics
# ==========================================================================
def _win_top5(R: np.ndarray, top: np.ndarray, exact_ties: bool):
    """P(rank 1) and P(rank <= 5) with ties split uniformly.

    R: (c, S) my scores; top: (S, K) opponents' best scores, sorted desc.
    Exact ties only arise when an opponent holds the identical whole-share
    portfolio (single-name all-in), so they are only counted when asked.
    """
    above = (top[None, :, :5] > R[:, :, None] + TIE_TOL).sum(axis=2)
    tie = np.zeros_like(above)
    if exact_ties:
        for a in range(0, len(R), 8):   # (8, S, K) at a time keeps memory small
            tie[a:a + 8] = (np.abs(top[None, :, :] - R[a:a + 8, :, None]) <= TIE_TOL).sum(axis=2)
    win = np.where(above == 0, 1.0 / (1 + tie), 0.0)
    top5 = np.clip((5 - above) / (1 + tie), 0.0, 1.0)
    return win.mean(axis=1), top5.mean(axis=1)


# Period-2 policies without a leaderboard: on Nov 22 I only know my own
# score and the realised stock returns. If my score is at least TAU, move to
# a defensive basket; otherwise keep the portfolio.
POLICY_TAUS = (1.25, 1.35, 1.50)


def chaser_returns(inp: SimInputs, G1: np.ndarray, G2: np.ndarray, k: int = 3, pool: int = 40) -> np.ndarray:
    """"Cover the chasers": the opponents who can still catch a leader are the
    all-in holders of period 1's best performers. Among the ``pool`` names
    most likely to be held all-in (popularity x vol), take the ``k`` best
    period-1 performers, equal weight, and return their period-2 gross."""
    likely = np.argsort(-(inp.popularity * inp.vol_ann))[:pool]
    sub = G1[:, likely]
    top = np.argpartition(-sub, k - 1, axis=1)[:, :k]
    names = likely[top]
    return np.take_along_axis(G2, names, axis=1).mean(axis=1)


def policy_names() -> list[str]:
    return [f"{a}@{t:g}" for t in POLICY_TAUS for a in ("cons", "chase")]


def evaluate(cs: CandidateSet, G1: np.ndarray, G2: np.ndarray, field: FieldResult,
             cons_w: np.ndarray, horizon1: int = config.P1_DAYS, chunk: int = 128,
             chase2: np.ndarray | None = None, extra_stats: bool = True) -> pd.DataFrame:
    """Score every candidate on the same scenarios (common random numbers).

    8-week metrics: ``8w_hold`` (no rebalance), ``8w_switch`` (oracle: switch
    to the consensus only when actually leading; kept for comparison) and,
    per realistic policy, ``8w_<basket>@<tau>``; ``p_win_8w_policy`` is the
    best realistic policy and ``policy_8w`` names it (hold if none helps)."""
    G12 = G1 * G2
    cons1 = G1 @ cons_w
    cons2 = G2 @ cons_w
    lead_bar = field.field_max1
    pols = policy_names()
    out = []
    n_names = (cs.W > 0).sum(axis=1)
    for c0 in range(0, len(cs), chunk):
        c1 = min(len(cs), c0 + chunk)
        W, cash = cs.W[c0:c1], cs.cash[c0:c1, None]
        R1 = W @ G1.T + cash
        R8 = W @ G12.T + cash
        # Two-stage policy: if leading after period 1, switch to the consensus.
        R8s = np.where(R1 > lead_bar[None, :] + TIE_TOL, R1 * cons2[None, :], R8)
        single = n_names[c0:c1] == 1
        res = {}
        runs = [("4w", R1, field.top1), ("8w_hold", R8, field.top8), ("8w_switch", R8s, field.top8)]
        for t in POLICY_TAUS:
            hit = R1 >= t
            runs.append((f"8w_cons@{t:g}", np.where(hit, R1 * cons2[None, :], R8), field.top8))
            if chase2 is not None:
                runs.append((f"8w_chase@{t:g}", np.where(hit, R1 * chase2[None, :], R8), field.top8))
        for name, R, top in runs:
            win = np.zeros(c1 - c0)
            t5 = np.zeros(c1 - c0)
            for flag in (True, False):
                sel = single == flag
                if sel.any():
                    win[sel], t5[sel] = _win_top5(R[sel], top, exact_ties=flag)
            res[f"p_win_{name}"], res[f"p_top5_{name}"] = win, t5
        avail = ["8w_hold"] + [f"8w_{p}" for p in pols if f"p_win_8w_{p}" in res]
        stack = np.vstack([res[f"p_win_{a}"] for a in avail])
        best = stack.argmax(axis=0)
        res["p_win_8w_policy"] = stack.max(axis=0)
        pol_names = np.array(["hold"] + [a[3:] for a in avail[1:]])
        if not extra_stats:
            for j in range(c1 - c0):
                row = {"candidate": cs.labels[c0 + j], "kind": cs.kinds[c0 + j],
                       "n_names": int(n_names[c0 + j]), "policy_8w": pol_names[best[j]]}
                row.update({k: float(v[j]) for k, v in res.items()})
                out.append(row)
            continue
        q1 = np.percentile(R1, [10, 50, 90], axis=1)
        q8 = np.percentile(R8, [10, 50, 90], axis=1)
        lr = np.log(R1)
        vol = lr.std(axis=1) * math.sqrt(252 / horizon1)
        cc = np.array([np.corrcoef(R1[j], cons1)[0, 1] if R1[j].std() > 0 else np.nan
                       for j in range(c1 - c0)])
        for j in range(c1 - c0):
            row = {"candidate": cs.labels[c0 + j], "kind": cs.kinds[c0 + j],
                   "n_names": int(n_names[c0 + j]), "cash_pct": float(cs.cash[c0 + j]),
                   "vol_ann": float(vol[j]), "corr_consensus": float(cc[j]),
                   "ret_p10_4w": q1[0, j] - 1, "ret_median_4w": q1[1, j] - 1,
                   "ret_p90_4w": q1[2, j] - 1,
                   "ret_p10_8w": q8[0, j] - 1, "ret_median_8w": q8[1, j] - 1,
                   "ret_p90_8w": q8[2, j] - 1}
            row.update({k: float(v[j]) for k, v in res.items()})
            row["policy_8w"] = pol_names[best[j]]
            out.append(row)
    return pd.DataFrame(out)


def overlap_metrics(cs: CandidateSet, G1: np.ndarray, field: FieldResult) -> pd.DataFrame:
    """How crowded is my winning idea?

    For each scenario take my best-contributing stock b. Report the average
    number of opponents holding b (overall and when I win), and the share of
    scenarios where b is a top-3 performer but some opponent holds it at least
    as heavily as I do ("shadowed": my idea worked but cannot win on its own).
    """
    S, N = G1.shape
    rank = np.argsort(np.argsort(-G1, axis=1), axis=1)
    rows = []
    for j in range(len(cs)):
        w = cs.W[j]
        held = np.flatnonzero(w)
        contrib = w[held][None, :] * (G1[:, held] - 1.0)
        b = held[np.argmax(contrib, axis=1)]
        sidx = np.arange(S)
        holders = field.n_hold[sidx, b].astype(float)
        R1 = G1 @ w + cs.cash[j]
        win = R1 > field.field_max1 + TIE_TOL
        hit = rank[sidx, b] < 3
        shadow = (field.max_w[sidx, b] >= w[b] - 1e-6) & hit
        rows.append({"candidate": cs.labels[j],
                     "avg_coholders": holders.mean(),
                     "avg_coholders_when_win": holders[win].mean() if win.any() else np.nan,
                     "p_idea_hits_top3": hit.mean(),
                     "shadowed_when_hits": shadow.sum() / max(hit.sum(), 1)})
    return pd.DataFrame(rows)


def stock_period_vol(G: np.ndarray, horizon: int) -> np.ndarray:
    return np.log(G).std(axis=0) * math.sqrt(252 / horizon)
