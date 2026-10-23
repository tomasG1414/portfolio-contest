"""Contest constants and model defaults.

Everything that encodes a *rule of the contest* or a *modelling assumption*
lives here so the data/sim modules stay generic and the assumptions are easy
to audit and change.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = ROOT / "outputs"
SNAPSHOT_CSV = DATA_DIR / "constituents_snapshot.csv"
EARNINGS_OVERRIDES_CSV = DATA_DIR / "earnings_overrides.csv"
EXDIV_OVERRIDES_CSV = DATA_DIR / "exdiv_overrides.csv"

# --------------------------------------------------------------------------
# Contest rules
# --------------------------------------------------------------------------
CAPITAL_EUR = 10_000.0
N_OPPONENTS = 179          # ~180 entrants including me

# Submission prices are the Friday close before each Sunday submission.
P1_PRICE_DATE = dt.date(2026, 10, 23)   # Fri close -> Sun Oct 25 submission
P1_START = dt.date(2026, 10, 26)        # first trading day held in period 1
P1_END = dt.date(2026, 11, 20)          # Fri close -> Sun Nov 22 rebalance
P2_START = dt.date(2026, 11, 23)
P2_END = dt.date(2026, 12, 18)          # valuation date

# Trading days in each holding window (Mon-Fri; Euronext/BME/Xetra have no
# holidays in either window, the US misses Thanksgiving Nov 26 in period 2,
# which we ignore: one fewer US day changes the vol by ~2.5%).
P1_DAYS = 20
P2_DAYS = 20
US_P2_DAYS = 19             # US is closed on Thanksgiving (Nov 26)

HISTORY_YEARS = 2           # bootstrap sample length
HISTORY_BUFFER_DAYS = 45    # extra history so the 1y vol / EWMA have warm-up

# Cross-listed names: drop the USD line, keep the EUR primary listing.
CROSS_LISTINGS = {"ASML": "ASML.AS", "FER": "FER.MC"}

# Wikipedia ticker quirks -> Yahoo tickers.
TICKER_FIXES = {"VOW.DE": "VOW3.DE", "DPW.DE": "DHL.DE", "NDA FI.HE": "NDA-FI.HE"}

FX_TICKER = "EURUSD=X"      # USD per EUR


# --------------------------------------------------------------------------
# Simulation defaults
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class SimConfig:
    n_scenarios: int = 20_000
    n_validate: int = 40_000      # fresh scenarios used to re-score the shortlist
    seed: int = 20261025
    block: int = 5                # block-bootstrap block length (days)
    ewma_lambda: float = 0.94
    vol_target: str = "blend"     # 'ewma' | '60d' | '1y' | 'blend' (= avg of ewma & 60d)
    vol_floor: float = 0.12       # annualised floor / cap on the target vol
    vol_cap: float = 2.50
    rf: float = 0.02              # EUR risk-free (annual) for the CAPM drift
    erp: float = 0.05             # equity risk premium (annual) x beta to consensus
    earnings_prior_n: int = 4     # shrink own earnings moves toward the pooled multiple
    use_iv: bool = True           # move US period variance toward option-implied (level-neutral)
    iv_weight: float = 0.5        # weight on the options market in that blend
    # --- v2 return-model knobs --------------------------------------------
    z_clip: float = 12.0          # clip on standardised bootstrap residuals (sigmas)
    volvol_mkt: float = 0.12      # lognormal sd of a per-scenario market-wide vol multiplier
    volvol_idio: float = 0.12     # ... and of a per-scenario, per-stock one (both variance-neutral)
    cluster_corr: float = 0.0     # extra common-factor share of variance for the AI-infra cluster
    earn_implied_weight: float = 0.5  # weight on option-implied earnings moves (term structure)
    earn_sign_prior: int = 8      # shrink the historical up/down frequency of earnings moves to 50/50
    tail_skew_weight: float = 0.0 # >0: tilt US vols by the Dec-18 call skew (IV at 1.3x / ATM), level-neutral
    thanksgiving: bool = True     # US names get 19 trading days in period 2


@dataclass(frozen=True)
class FieldMix:
    """Mixture of opponent archetypes (shares must sum to 1)."""
    diversified: float = 0.60     # 8-15 names, popularity-weighted
    moderate: float = 0.25        # 3-5 popular names
    allin: float = 0.15           # 1-2 names, sampled ~ popularity x vol
    div_k: tuple = (8, 15)
    mod_k: tuple = (3, 5)
    p_single: float = 0.6         # share of all-in players with exactly 1 name
    mod_pop_power: float = 1.5    # moderate players concentrate on the most popular names
    dirichlet_alpha: float = 4.0  # weight dispersion within a portfolio (high = near equal)
    p_rebalance: float = 0.5      # opponents who re-pick at the Nov 22 rebalance
    chase: float = 0.0            # >0: re-pickers tilt toward period-1 winners
    pop_noise: float = 0.20       # lognormal sigma on the popularity weights (they are judgement calls)
    group_noise: float = 0.0      # lognormal sigma of a shared factor per popularity group
    group_mult: tuple = ()        # deterministic stress, e.g. (("hype", 2.0),)
    foreign_share: float = 0.0    # opponents with the non-Spanish European profile
    n_opponents: int = N_OPPONENTS
    # --- v2 field knobs ----------------------------------------------------
    allin_vol_pow: float = 1.0    # all-in players sample ~ popularity x vol^pow
    n_savvy: float = 0.0          # expected opponents who go all-in on max-vol names (ignore popularity)
    savvy_pow: float = 6.0        # their sampling ~ vol^savvy_pow
    momentum_share: float = 0.0   # opponents who buy recent winners (3-month return)
    momentum_beta: float = 1.5    # their tilt per s.d. of trailing return
    fad_prob: float = 0.0         # per popularity world: chance one high-vol name becomes a fad
    fad_mult: float = 3.0         # median popularity multiplier of a fad (lognormal, sd 0.5)
    p2_loser_allin: float = 0.0   # re-pickers in the bottom half switch to all-in with this prob.

    def type_probs(self) -> "np.ndarray":
        """Shares of the five archetypes: diversified, moderate, all-in, savvy, momentum."""
        import numpy as np
        sav = min(self.n_savvy / max(self.n_opponents, 1), 0.5)
        mom = self.momentum_share
        base = np.array([self.diversified, self.moderate, self.allin], float)
        base = base / base.sum() * max(1.0 - sav - mom, 0.0)
        return np.concatenate([base, [sav, mom]])

    def with_allin(self, allin: float) -> "FieldMix":
        """Same mixture with a different all-in share; others keep their ratio."""
        rest = self.diversified + self.moderate
        scale = (1.0 - allin) / rest
        return replace(self, diversified=self.diversified * scale,
                       moderate=self.moderate * scale, allin=allin)

    def label(self) -> str:
        out = (f"div {self.diversified:.0%} / mod {self.moderate:.0%} / "
               f"all-in {self.allin:.0%}")
        if self.foreign_share:
            out += f", {self.foreign_share:.0%} non-Spanish European students"
        if self.group_mult:
            out += ", " + ", ".join(f"{g} popularity x{m:g}" for g, m in self.group_mult)
        if self.group_noise:
            out += f", group popularity noise {self.group_noise:.0%}"
        if self.allin_vol_pow != 1.0:
            out += f", all-in ~ pop x vol^{self.allin_vol_pow:g}"
        if self.n_savvy:
            out += f", {self.n_savvy:g} savvy max-vol opponents"
        if self.momentum_share:
            out += f", {self.momentum_share:.0%} momentum buyers"
        if self.fad_prob:
            out += f", fad prob {self.fad_prob:.0%} (x{self.fad_mult:g})"
        if self.p2_loser_allin:
            out += f", {self.p2_loser_allin:.0%} of trailing re-pickers go all-in"
        return out


SENSITIVITY_ALLIN = (0.05, 0.15, 0.30)

# AI-infrastructure / semis cluster (correlation stress)
AI_CLUSTER = ("CRWV", "NBIS", "ALAB", "SNDK", "MU", "LITE", "ARM", "NVDA", "AMD", "AVGO",
              "MRVL", "STX", "WDC", "TER", "LRCX", "AMAT", "KLAC", "MPWR", "INTC", "ASML.AS",
              "QCOM", "ASM.AS", "IFX.DE", "PLTR", "APP", "CEG")

# Candidate search
TOP_VOL_FOR_PAIRS = 40
PAIR_WEIGHTS = ((0.5, 0.5), (0.65, 0.35), (0.35, 0.65), (0.8, 0.2), (0.2, 0.8))
N_PAIRS_FOR_TRIPLES = 25
TRIPLE_THIRD_WEIGHTS = (1 / 3, 0.2)
SHORTLIST_SIZE = 40
