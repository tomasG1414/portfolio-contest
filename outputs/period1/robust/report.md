# Period 1 - model-uncertainty run (prices 2026-10-23)

P(win at Dec 18) averaged over parameter worlds: every world draws the return model and the opponent field from the priors below (no crowding data, no leaderboard). Each portfolio keeps one period-2 policy, picked on the search worlds: `hold`, or switch to the consensus (`cons`) or to the chaser basket (`chase`, the period-1 best performers among the names most likely held all-in) when my own score is at least the threshold.

Search: 48 worlds; validation: 160 fresh worlds; 500 scenarios per world.

**Pick: CRWV** - P(win) 8.28% (+/- 0.19% s.e.), period-2 policy `cons@1.5`.

## Shortlist (fresh worlds)

| # | portfolio | P(win) Dec18 | s.e. | worst 10% of worlds | best 10% | best in worlds | P(lead) Nov20 | oracle switch | policy | vol |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | CRWV | 8.28% | 0.19% | 5.49% | 11.35% | 36% | 8.52% | 8.14% | cons@1.5 | 111% |
| 2 | AXON | 7.69% | 0.15% | 5.40% | 9.81% | 19% | 10.05% | 7.56% | cons@1.5 | 87% |
| 3 | ALAB | 7.38% | 0.15% | 5.20% | 10.00% | 6% | 8.56% | 7.37% | cons@1.5 | 95% |
| 4 | DDOG | 7.32% | 0.12% | 5.49% | 9.49% | 10% | 9.92% | 7.45% | chase@1.5 | 88% |
| 5 | MRNA | 6.78% | 0.17% | 3.97% | 9.73% | 9% | 6.50% | 6.53% | cons@1.5 | 108% |
| 6 | RKLB | 6.75% | 0.13% | 4.50% | 8.82% | 4% | 8.04% | 6.76% | cons@1.5 | 86% |
| 7 | TER | 6.73% | 0.14% | 4.49% | 9.00% | 4% | 9.56% | 6.78% | cons@1.35 | 87% |
| 8 | NBIS | 6.43% | 0.17% | 3.76% | 9.51% | 2% | 6.96% | 6.32% | cons@1.5 | 95% |
| 9 | ARM | 6.30% | 0.15% | 4.10% | 8.70% | 3% | 7.21% | 6.25% | cons@1.5 | 91% |
| 10 | SLR.MC | 6.27% | 0.12% | 4.30% | 8.41% | 3% | 6.96% | 6.07% | cons@1.5 | 62% |
| 11 | SNDK 20% + CRWV 80% | 6.06% | 0.19% | 3.18% | 9.20% | 0% | 4.95% | 5.55% | cons@1.35 | 103% |
| 12 | MPWR 20% + CRWV 80% | 6.03% | 0.19% | 3.20% | 9.02% | 0% | 4.99% | 5.48% | cons@1.35 | 102% |
| 13 | LITE | 6.03% | 0.13% | 3.89% | 8.51% | 1% | 7.24% | 5.94% | cons@1.35 | 88% |
| 14 | APP | 5.87% | 0.12% | 3.89% | 7.82% | 2% | 8.20% | 5.82% | cons@1.35 | 88% |
| 15 | MRVL | 5.84% | 0.14% | 3.60% | 8.41% | 1% | 3.20% | 5.74% | cons@1.5 | 63% |
| 16 | AXON 80% + SNDK 20% | 5.77% | 0.13% | 3.98% | 7.60% | 0% | 8.03% | 5.69% | cons@1.5 | 78% |
| 17 | LITE 20% + CRWV 80% | 5.74% | 0.18% | 2.80% | 8.64% | 0% | 4.99% | 5.36% | cons@1.35 | 101% |
| 18 | ALAB 80% + SNDK 20% | 5.71% | 0.15% | 3.38% | 8.02% | 0% | 6.19% | 5.64% | cons@1.35 | 88% |
| 19 | AXON 80% + DDOG 20% | 5.59% | 0.13% | 3.80% | 7.40% | 0% | 7.65% | 5.47% | cons@1.5 | 75% |
| 20 | NBIS 20% + CRWV 80% | 5.57% | 0.18% | 2.80% | 8.42% | 0% | 4.84% | 5.29% | cons@1.5 | 99% |

Benchmarks: IBEX blue chips (EW) 0.05%; Top-10 popular (EW) 0.00%; Magnificent 7 (EW) 0.00%; Consensus basket 0.00%

`worst/best 10% of worlds` = P(win) in the 10th / 90th percentile world (includes ~1.6% per-world Monte Carlo noise). `best in worlds` = share of worlds where it has the highest P(win) in the shortlist (noisy per world, read as relative). `oracle switch` = the v1 metric (switch only when actually leading).

## What drives the uncertainty

First-order decomposition of per-world P(win): share of the explained variance and the effect of a one-s.d. move in the parameter (percentage points).

**ALAB** (R^2 0.63): allin 39% (-1.0pp); allin_vol_pow 29% (-0.9pp); n_savvy 12% (-0.5pp); vol_target 10% (-0.8pp); n_entrants 2% (-0.2pp); momentum_share 2% (-0.2pp)

**AXON** (R^2 0.62): allin 60% (-1.2pp); allin_vol_pow 15% (-0.6pp); vol_target 8% (-0.2pp); block 4% (+0.3pp); n_savvy 3% (-0.3pp); p2_loser_allin 2% (-0.2pp)

**CRWV** (R^2 0.65): allin_vol_pow 38% (-1.2pp); allin 35% (-1.2pp); n_savvy 15% (-0.8pp); iv_weight 4% (+0.4pp); volvol_idio 2% (-0.3pp); z_clip 2% (+0.3pp)

**CRWV - AXON** (R^2 0.29): allin_vol_pow 29% (-0.6pp); n_savvy 17% (-0.5pp); iv_weight 16% (+0.5pp); vol_target 10% (+0.4pp); n_entrants 9% (+0.4pp); block 8% (-0.3pp)

## Priors

| parameter | meaning | range in validation worlds |
|---|---|---|
| iv_weight | weight on option-implied variance (US) | 0.01 - 1.00 |
| vol_target | vol forecaster | blend 44%, 60d 28%, ewma 19%, 1y 9% |
| z_clip | clip on bootstrap residuals (sigmas) | 6.02 - 11.99 |
| volvol_mkt | vol-of-vol, market-wide (lognormal sd) | 0.05 - 0.25 |
| volvol_idio | vol-of-vol, per stock | 0.05 - 0.20 |
| cluster_corr | extra AI-infra cluster correlation | 0.01 - 0.50 |
| earn_implied_weight | weight on option-implied earnings moves | 0.00 - 1.00 |
| tail_skew_weight | call-skew tilt of US vols | 0.01 - 0.99 |
| block | bootstrap block length (days) | 3.00 - 10.00 |
| allin | share of all-in opponents | 0.05 - 0.25 |
| allin_vol_pow | all-in sampling ~ pop x vol^k | 1.01 - 2.99 |
| n_savvy | expected savvy max-vol opponents | 0.14 - 3.98 |
| momentum_share | share of momentum buyers | 0.00 - 0.15 |
| fad_prob | chance a high-vol name becomes a fad (x3) | 0.01 - 0.59 |
| pop_noise | per-name popularity noise (lognormal sd) | 0.20 - 0.60 |
| p2_loser_allin | trailing re-pickers who go all-in | 0.00 - 0.99 |
| p_rebalance | opponents who re-pick on Nov 22 | 0.30 - 0.79 |
| n_entrants | entrants incl. me | 160.00 - 200.00 |
