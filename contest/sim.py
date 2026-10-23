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

from . import config

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
    Z = np.clip(Z, -12, 12)

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
    iv_scale = np.ones(len(tickers))
    if cfg.use_iv:
        iv_scale = _iv_scale(feat, sigma_d, earn, pooled, periods[0], cfg)
        sigma_d = sigma_d * iv_scale
    vol = pd.Series(sigma_d * math.sqrt(252), index=tickers)
    beta = feat["beta_cons"].fillna(1.0).clip(0.0, 2.5).to_numpy()
    mu_a = cfg.rf + beta * cfg.erp
    mu_d = mu_a / 252 - 0.5 * sigma_d ** 2
    exdiv = {p: feat[f"exdiv_p{p}_pct"].fillna(0.0).clip(0, 0.2).to_numpy() for p in periods}
    return SimInputs(tickers=tickers, Z=Z, sigma_d=sigma_d, mu_d=mu_d,
                     price_eur=feat["price_eur"].to_numpy(float),
                     popularity=feat["popularity"].to_numpy(float),
                     vol_ann=vol.to_numpy(), earn=earn, pooled_mults=pooled,
                     exdiv=exdiv, cons_w=cw / cw.sum(), iv_scale=iv_scale)


def _iv_scale(feat, sigma_d, earn, pooled, period, cfg) -> np.ndarray:
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
        jump_m2[i] += prob * (em2 / (n + prior) - 1.0)
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
    L = horizon * inp.mu_d + inp.sigma_d * zsum
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
            jump = rng.choice([-1.0, 1.0], size=n_scen) * m * inp.sigma_d[i]
            jump -= 0.5 * np.mean(jump ** 2)       # keep the arithmetic mean
            here = rng.random(n_scen) < prob       # uncertain date: maybe other window
            L[:, i] += np.where(here, jump - inp.sigma_d[i] * Z[t, i], 0.0)
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


def _type_specs(inp: SimInputs, mix: config.FieldMix):
    pop = inp.popularity
    return [
        (np.log(pop), mix.div_k[0], mix.div_k[1]),
        (mix.mod_pop_power * np.log(pop), mix.mod_k[0], mix.mod_k[1]),
        (np.log(pop * inp.vol_ann), 1, 2),
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
        for t in range(3):
            i_, e_ = _draw_field_rows(rng, inp, mix, np.full(size, t))
            self.idx.append(i_)
            self.eff.append(e_)

    def draw(self, rng, types):
        idx = np.zeros((len(types), 15), np.int32)
        eff = np.zeros((len(types), 15))
        for t in range(3):
            rows = np.flatnonzero(types == t)
            pick = rng.integers(0, len(self.idx[t]), size=len(rows))
            idx[rows], eff[rows] = self.idx[t][pick], self.eff[t][pick]
        return idx, eff


def _popularity_worlds(n_scen: int, mix: config.FieldMix) -> int:
    """Number of popularity draws ("worlds") per field: one per ~1,000 scenarios."""
    return 1 if mix.pop_noise <= 0 else max(20, n_scen // 1000)


def simulate_field(inp: SimInputs, G1: np.ndarray, G2: np.ndarray, mix: config.FieldMix,
                   rng: np.random.Generator, n_opp: int = config.N_OPPONENTS,
                   chunk: int = 500, pool_inp: SimInputs | None = None) -> FieldResult:
    """Fresh 179-opponent field for every scenario.

    Popularity is uncertain (the weights are judgement calls): scenarios are
    split into "worlds", each drawing one true popularity vector
    pop_i x lognormal(sigma = ``mix.pop_noise``, mean 1) shared by every
    opponent in that world. Noise is per contest, not per student, so it
    does not average away across the 179 opponents.

    Period 2: a share ``p_rebalance`` of opponents re-pick (same archetype,
    optionally tilted to period-1 winners via ``mix.chase``); the rest keep
    their shares, so their final score is the buy-and-hold value.
    ``pool_inp`` (prices for the re-pick) defaults to ``inp``.
    """
    S, N = G1.shape
    probs = np.array([mix.diversified, mix.moderate, mix.allin])
    probs = probs / probs.sum()
    top1 = np.empty((S, TOPK))
    top8 = np.empty((S, TOPK))
    n_hold = np.zeros((S, N), np.int16)
    max_w = np.zeros((S, N), np.float32)
    n_worlds = _popularity_worlds(S, mix)
    pool_size = 60_000 if n_worlds == 1 else 12_000
    bounds = np.linspace(0, S, n_worlds + 1).astype(int)
    for w in range(n_worlds):
        inp_w, pinp_w = inp, pool_inp or inp
        if mix.pop_noise > 0:
            sig = mix.pop_noise
            factor = np.exp(sig * rng.standard_normal(inp.n) - 0.5 * sig ** 2)
            inp_w = dataclasses.replace(inp, popularity=inp.popularity * factor)
            pinp_w = dataclasses.replace(pinp_w, popularity=pinp_w.popularity * factor)
        pool1 = _Pool(inp_w, mix, rng, pool_size)
        # re-picks come from the same pool unless period-2 prices differ
        pool2 = None if mix.chase else (pool1 if pool_inp is None else _Pool(pinp_w, mix, rng, pool_size))
        for s0 in range(bounds[w], bounds[w + 1], chunk):
            s1 = min(bounds[w + 1], s0 + chunk)
            _field_chunk(s0, s1, G1, G2, mix, rng, n_opp, probs, pool1, pool2, pinp_w,
                         top1, top8, n_hold, max_w)
    return FieldResult(top1=top1, top8=top8, n_hold=n_hold, max_w=max_w, mix=mix)


def _field_chunk(s0, s1, G1, G2, mix, rng, n_opp, probs, pool1, pool2, pool_inp,
                 top1, top8, n_hold, max_w):
    """Score opponents for scenarios s0:s1 and record leaderboard stats."""
    N = G1.shape[1]
    m = s1 - s0
    rows = m * n_opp
    scen = np.repeat(np.arange(s0, s1), n_opp)
    types = rng.choice(3, size=rows, p=probs)
    idx, eff = pool1.draw(rng, types)
    g1 = G1[scen[:, None], idx]
    cash = 1.0 - eff.sum(axis=1)
    r1 = (eff * g1).sum(axis=1) + cash
    # period 2
    reb = rng.random(rows) < mix.p_rebalance
    r8 = (eff * g1 * G2[scen[:, None], idx]).sum(axis=1) + cash
    if reb.any():
        if mix.chase:
            lg = np.log(G1[s0:s1])
            z = (lg - lg.mean(1, keepdims=True)) / (lg.std(1, keepdims=True) + 1e-12)
            extra = np.repeat(mix.chase * z, n_opp, axis=0)
            idx2, eff2 = _draw_field_rows(rng, pool_inp, mix, types, extra)
        else:
            idx2, eff2 = pool2.draw(rng, types)
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


def evaluate(cs: CandidateSet, G1: np.ndarray, G2: np.ndarray, field: FieldResult,
             cons_w: np.ndarray, horizon1: int = config.P1_DAYS, chunk: int = 128) -> pd.DataFrame:
    """Score every candidate on the same scenarios (common random numbers)."""
    G12 = G1 * G2
    cons1 = G1 @ cons_w
    cons2 = G2 @ cons_w
    lead_bar = field.field_max1
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
        for name, R, top in (("4w", R1, field.top1), ("8w_hold", R8, field.top8),
                             ("8w_switch", R8s, field.top8)):
            win = np.zeros(c1 - c0)
            t5 = np.zeros(c1 - c0)
            for flag in (True, False):
                sel = single == flag
                if sel.any():
                    win[sel], t5[sel] = _win_top5(R[sel], top, exact_ties=flag)
            res[f"p_win_{name}"], res[f"p_top5_{name}"] = win, t5
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
