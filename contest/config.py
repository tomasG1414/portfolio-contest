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

    def with_allin(self, allin: float) -> "FieldMix":
        """Same mixture with a different all-in share; others keep their ratio."""
        rest = self.diversified + self.moderate
        scale = (1.0 - allin) / rest
        return replace(self, diversified=self.diversified * scale,
                       moderate=self.moderate * scale, allin=allin)

    def label(self) -> str:
        return (f"div {self.diversified:.0%} / mod {self.moderate:.0%} / "
                f"all-in {self.allin:.0%}")


SENSITIVITY_ALLIN = (0.05, 0.15, 0.30)

# Candidate search
TOP_VOL_FOR_PAIRS = 40
PAIR_WEIGHTS = ((0.5, 0.5), (0.65, 0.35), (0.35, 0.65), (0.8, 0.2), (0.2, 0.8))
N_PAIRS_FOR_TRIPLES = 25
TRIPLE_THIRD_WEIGHTS = (1 / 3, 0.2)
SHORTLIST_SIZE = 40
