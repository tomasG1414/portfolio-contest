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
| `contest/robust.py` | **v2** `--mode robust`: ranking averaged over model uncertainty (priors on return model and field), variance decomposition |
| `contest/validate.py` | **v2** `--mode validate`: vol-forecaster backtest (QLIKE), vol-of-vol calibration, tail reliability, options right tail and implied earnings moves |
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
`--pop-noise 0.2` (uncertainty on the popularity weights, 0 = exact),
`--rank-by p_win_4w`, `--asof 2026-10-22`. `--mode period2 --dry-run` exercises the
period-2 code with a simulated period-1 outcome before real data exists.

Stress tests: `python -m contest --mode stress` re-runs the full period-1 search
under alternative fields (60/120/200 entrants, 30%/50% non-Spanish European
students, hype names / Spanish bias / US mega-caps twice as popular, group-level
popularity noise, a combination), 4 processes at a time; summary in
`outputs/period1/stress/summary.md`. The same field options work on their own:
`--participants`, `--foreign-share`, `--group-mult hype=2`, `--group-noise 0.5`.

Tests: `python -m pytest tests -q` (synthetic data, no network).

## v2

```bash
python -m contest --mode validate          # outputs/validation/report.md
python -m contest --mode robust            # outputs/period1/robust/report.md
python -m contest --mode stress --workers 2
```

- **Period 2 without a leaderboard.** Default ranking metric is now `p_win_8w_policy`: on Nov 22
  you only know your own score, so the policy is "if my score >= tau (1.25 / 1.35 / 1.50), switch to
  the consensus (`cons`) or to the chaser basket (`chase`), else hold", picked per portfolio on the
  search scenarios and re-scored on fresh ones. The chaser basket = period 1's best performers among
  the names most likely held all-in (who can still catch a leader). `p_win_8w_switch` (oracle) is
  kept for comparison. Period 2 mode adds the chaser basket as a candidate.
- **Return model:** variance-neutral vol-of-vol multipliers (`--volvol 0.12,0.12`, calibrated by
  `--mode validate`), residual clip (`--z-clip`), extra AI-infra cluster correlation
  (`--cluster-corr`), earnings moves blended toward the option-implied event move from the ATM term
  structure (`--earn-implied-weight`), earnings sign from the stock's history shrunk to 50/50
  (`--earn-sign-prior`, mean kept), call-skew tilt of US vols (`--tail-skew-weight`), US period 2
  = 19 days (Thanksgiving; `--no-thanksgiving`).
- **Field:** all-in sampling ~ popularity x vol^k (`--allin-vol-pow`), savvy opponents all-in on
  max-vol names (`--savvy`), momentum buyers of recent winners (`--momentum-share`), fads that make
  one high-vol name x3 popular in a share of worlds (`--fad-prob`, `--fad-mult`), trailing
  re-pickers going all-in on Nov 22 (`--p2-loser-allin`).
- **Fetcher:** full option chains for the Nov 20 / Dec 18 expiries (`data/cache/option_chains.csv.gz`)
  and the ATM term structure up to Jan 1 for the 40 highest-vol US names (in `meta.json`).
- **Robust mode:** each world draws all of the above (plus IV weight, vol forecaster, block length,
  all-in share, popularity noise, re-pick share, 160-200 entrants) from the priors in
  `contest/robust.py`; candidates are ranked on the world-averaged P(win).

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
popularity x vol), with whole shares; the popularity weights themselves are
uncertain (one lognormal draw, sigma 20%, per ~1,000 scenarios, shared by the field). Candidates are scored on P(rank 1) and
P(top 5) with ties split, at 4 weeks and at 8 weeks (buy-and-hold, and a policy
that switches to the consensus basket on Nov 22 only when leading). The shortlist
is re-scored on fresh scenarios to remove selection bias, under 5/15/30%
all-in field mixtures, under the other vol model, and with each lead name 3x as
popular as assumed (crowding check).

Nothing here places trades.
