# Stock-contest Monte Carlo: maximise P(rank 1)

Picks portfolios for a 180-entrant virtual stock contest (10,000 EUR, long only,
whole shares, price-only scoring, IBEX 35 + Euro Stoxx 50 + Nasdaq-100) by
simulating the market **and** the opponents, then ranking candidates by the
probability of finishing first rather than by expected return or Sharpe.

## Layout

| path | what |
|---|---|
| `contest/config.py` | contest dates/rules, simulation and field-mixture defaults |
| `contest/universe.py` | constituent scraping (with checked-in fallback), de-duplication, popularity / consensus basket |
| `contest/data.py` | **data module**: download (fetch mode only), cache loading, EUR returns, features (vols, IV, earnings, ex-dividends, beta/corr to consensus) |
| `contest/sim.py` | **sim module**: block bootstrap with vol rescaling and earnings jumps, opponent field, whole-share candidates, win/top-5 metrics |
| `contest/pipeline.py` | period-1 and period-2 runs (search, validation, sensitivity) |
| `contest/report.py` | markdown report and plots |
| `contest/cli.py` | **CLI** |
| `data/constituents_snapshot.csv` | index members as of Oct 22, 2026 (fallback if scraping fails) |
| `data/earnings_overrides.csv`, `data/exdiv_overrides.csv` | manually verified dates (take precedence) |
| `data/cache/` | downloaded data (written by `--mode fetch`) |
| `outputs/period1/`, `outputs/period2/` | results |

## Usage

```bash
pip install -r requirements.txt

# 1. refresh data (needs internet; ~10 min). In the cloud sandbox this runs in
#    GitHub Actions instead: Actions -> fetch-market-data -> Run workflow, or
#    edit data/REFRESH and push. The workflow commits data/cache back.
python -m contest --mode fetch

# 2. period 1 (submission Sun Oct 25, priced at the Fri Oct 23 close)
python -m contest --mode period1

# 3. period 2 (rebalance Sun Nov 22): fetch after the Fri Nov 20 close, then
python -m contest --mode period2 --my-return 0.083      # or 8.3%
```

Useful options: `--scenarios 50000`, `--seed`, `--mix 0.6,0.25,0.15`,
`--sensitivity 0.05,0.15,0.30`, `--vol-target ewma|60d|1y|blend`, `--no-iv`, `--iv-weight 0.5`,
`--p-rebalance 0.5`, `--chase 0.5` (opponents chase period-1 winners),
`--rank-by p_win_4w`, `--asof 2026-10-22`. `--mode period2 --dry-run` exercises the
period-2 code with a simulated period-1 outcome before real data exists.

Tests: `python -m pytest tests -q` (synthetic data, no network).

## Model in one paragraph

Daily EUR total-return log returns of all names (USD names converted with
EURUSD=X) are standardised by their own EWMA vol (filtered historical simulation),
with historical earnings-reaction days replaced by their market component. A
scenario draws 5-day blocks of whole cross-sectional rows from the last two years,
rescales each stock to its current ex-earnings vol (avg of EWMA and 60d, jumps
winsorised at 4 sigma; for US names the period variance is moved halfway toward
the ATM option-implied variance of the expiry that ends the period, level-neutral,
`--no-iv` to switch off), adds a CAPM drift, and on a
stock's earnings reaction day swaps the diffusive move for an earnings jump drawn
from that stock's history (shrunk toward the pooled distribution). Known or
estimated ex-dividend drops are subtracted because the contest scores price only.
Each scenario gets a fresh field of 179 opponents from a mixture of diversified,
moderately concentrated and all-in archetypes sampled by popularity (all-in by
popularity x vol), with whole shares. Candidates are scored on P(rank 1) and
P(top 5) with ties split, at 4 weeks and at 8 weeks (buy-and-hold, and a policy
that switches to the consensus basket on Nov 22 only when leading). The shortlist
is re-scored on fresh scenarios to remove selection bias, under 5/15/30%
all-in field mixtures, under the other vol model, and with each lead name 3x as
popular as assumed (crowding check).

Nothing here places trades.
