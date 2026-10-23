# Stock contest - period 1 submission (Oct 25, prices 2026-10-23)

Objective: maximise the probability of finishing **first** of 180 (not expected return). Ranking metric: `p_win_8w_policy` = P(win at Dec 18) with the best realistic Nov 22 policy for that portfolio: there is no leaderboard, so on Nov 22 I only know my own score; if it is at least a threshold (1.25, 1.35, 1.5) I switch to the consensus basket (`cons`) or to the chaser basket (`chase`: period 1's best performers among the names most likely held all-in), else I hold. The policy is picked on the search scenarios and re-scored on fresh ones.

## Submission (do not trade - enter these in the contest platform)

**CRWV** - P(win Dec 18) 8.02%, P(lead Nov 20) 8.64%, P(top 5 Nov 20) 24.6% (validated on 40,000 fresh scenarios).

| ticker | name | shares | price_local | currency | price_eur | value_eur | weight | last_close |
|---|---|---|---|---|---|---|---|---|
| CRWV | CoreWeave, Inc. Class A Common Stock | 206 | 54.24 | USD | 48.44 | 9,978.08 | 99.8% | 2026-10-23 |

Invested 9,978.08 EUR, cash left 21.92 EUR (earns nothing). EUR/USD used: 1.1197.

## Top 10 (re-scored on fresh scenarios)

| # | portfolio | P(win) Dec18 | P(win) hold 8w | P(lead) Nov20 | P(top5) Nov20 | median 4w | p10 / p90 4w | vol | corr cons. | co-holders | shadowed | flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | CRWV | 8.02% | 7.66% | 8.64% | 24.6% | -3.2% | -32.5% / 38.7% | 113% | 0.35 | 12.5 | 56% | CRWV: E1 2026-11-12? |
| 2 | MRNA | 7.77% | 7.42% | 8.08% | 23.3% | -3.7% | -31.8% / 35.2% | 109% | 0.10 | 14.6 | 65% | MRNA: E1 2026-11-06 |
| 3 | ALAB | 7.27% | 7.19% | 8.36% | 22.2% | -1.7% | -27.5% / 32.0% | 93% | 0.35 | 5.2 | 25% | ALAB: E1 2026-11-04 |
| 4 | DDOG | 6.90% | 6.91% | 9.50% | 22.6% | -2.2% | -27.4% / 29.9% | 89% | 0.23 | 4.4 | 12% | DDOG: E1 2026-11-04 |
| 5 | AXON | 6.88% | 6.80% | 9.29% | 22.9% | -1.0% | -27.0% / 28.0% | 87% | 0.19 | 1.5 | 4% | AXON: E1 2026-11-06? |
| 6 | TER | 6.86% | 6.80% | 9.63% | 23.0% | -1.9% | -26.0% / 30.2% | 87% | 0.26 | 1.6 | 7% | TER: E1 2026-10-28; D2 ~-0.0% |
| 7 | ARM | 6.64% | 6.53% | 7.64% | 21.0% | -1.7% | -26.1% / 30.9% | 91% | 0.32 | 11.1 | 35% | ARM: E1 2026-11-05 |
| 8 | NBIS | 6.62% | 6.44% | 7.47% | 21.2% | -2.8% | -27.7% / 32.6% | 95% | 0.37 | 8.8 | 40% | NBIS: E1 2026-11-10 |
| 9 | LITE | 6.19% | 6.11% | 7.54% | 19.8% | -2.2% | -26.4% / 27.4% | 88% | 0.31 | 3.2 | 22% | LITE: E1 2026-11-06 |
| 10 | MRVL | 5.80% | 5.75% | 3.86% | 13.8% | -0.5% | -18.5% / 21.0% | 63% | 0.43 | 4.6 | 14% | MRVL: E2 2026-12-02 |

P(win) Dec18 = switch-if-leading policy; hold 8w = no rebalance; P(lead) Nov20 = rank 1 after period 1. co-holders = avg. number of opponents holding my best-performing name; shadowed = when that name is a top-3 performer, share of scenarios where an opponent holds it at least as heavily as I do. Flags: E1/E2 earnings reaction day in period 1/2 (`?` = date not confirmed by a second source), D1/D2 ex-dividend drop (`~` = estimated).

Benchmarks for scale: IBEX blue chips (EW) 0.04%; Magnificent 7 (EW) 0.00%; Top-10 popular (EW) 0.00%; Consensus basket 0.00%. A random entrant has 0.56%.

## Sensitivity to the field mixture

P(win Dec 18) and rank within the shortlist when the share of all-in opponents changes (diversified : moderate kept at 60 : 25). Sorted by worst rank; **robust** = top 10 under every mixture. The vol-model column re-scores the same portfolios with the other US-vol choice (base mixture) as a model-risk check; it does not enter the worst rank.

| portfolio | all-in 15% | worst rank | robust |
|---|---|---|---|
| CRWV | 8.02% (#1) | 1 | **yes** |
| MRNA | 7.77% (#2) | 2 | **yes** |
| ALAB | 7.27% (#3) | 3 | **yes** |
| DDOG | 6.90% (#4) | 4 | **yes** |
| AXON | 6.88% (#5) | 5 | **yes** |
| TER | 6.86% (#6) | 6 | **yes** |
| ARM | 6.64% (#7) | 7 | **yes** |
| NBIS | 6.62% (#8) | 8 | **yes** |
| LITE | 6.19% (#9) | 9 | **yes** |
| MRVL | 5.80% (#10) | 10 | **yes** |
| SNDK | 5.75% (#11) | 11 |  |
| RKLB | 5.68% (#12) | 12 |  |
| APP | 5.63% (#13) | 13 |  |
| SLR.MC | 5.61% (#14) | 14 |  |
| ALAB 80% + SNDK 20% | 5.60% (#15) | 15 |  |

## What it takes to win

Best opponent after 4 weeks: median score 1.287 (10-90%: 1.108-1.766). Winning score at Dec 18: median 1.437 (10-90%: 1.177-2.069).

![P(win) vs vol](pwin_vs_vol.png)

![winning score](winning_score_hist.png)

## Earnings and ex-dividend flags

Names in the top 10:

| ticker | name | last reported | next earnings | timing | reaction day | period | status | hist. |move| | ex-div P1 | ex-div P2 |
|---|---|---|---|---|---|---|---|---|---|---|
| CRWV | CoreWeave, Inc. Class A Common Stock | 2026-08-11 | 2026-11-11 | AMC | 2026-11-12 | P1 | sources differ, same window | 15.7% |  |  |
| MRNA | Moderna, Inc. Common Stock | 2026-07-31 | 2026-11-06 | BMO | 2026-11-06 | P1 | confirmed (2 sources) | 7.2% |  |  |
| ALAB | Astera Labs, Inc. Common Stock | 2026-08-04 | 2026-11-03 | AMC | 2026-11-04 | P1 | confirmed (2 sources) | 13.4% |  |  |
| DDOG | Datadog, Inc. Class A Common Stock | 2026-08-06 | 2026-11-04 | BMO | 2026-11-04 | P1 | confirmed (2 sources) | 11.6% |  |  |
| AXON | Axon Enterprise, Inc. Common Stock | 2026-08-05 | 2026-11-05 | AMC | 2026-11-06 | P1 | sources differ, same window | 13.3% |  |  |
| TER | Teradyne, Inc. Common Stock | 2026-07-28 | 2026-10-27 | AMC | 2026-10-28 | P1 | confirmed (2 sources) | 10.4% |  | 2026-12-02 (-0.04%, est: quarterly cadence) |
| ARM | Arm Holdings plc American Depositary Shares | 2026-07-29 | 2026-11-04 | AMC | 2026-11-05 | P1 | confirmed (2 sources) | 9.3% |  |  |
| NBIS | Nebius Group N.V. Class A Ordinary Shares | 2026-08-12 | 2026-11-10 | BMO | 2026-11-10 | P1 | confirmed (2 sources) | 10.9% |  |  |
| LITE | Lumentum Holdings Inc. Common Stock | 2026-08-11 | 2026-11-05 | AMC | 2026-11-06 | P1 | confirmed (2 sources) | 9.7% |  |  |
| MRVL | Marvell Technology, Inc. Common Stock | 2026-08-27 | 2026-12-01 | AMC | 2026-12-02 | P2 | confirmed (2 sources) | 12.4% |  |  |

Consensus names:

| ticker | name | last reported | next earnings | timing | reaction day | period | status | hist. |move| | ex-div P1 | ex-div P2 |
|---|---|---|---|---|---|---|---|---|---|---|
| BBVA.MC | BBVA | 2026-07-30 | 2026-10-29 | DMH | 2026-10-29 | P1 | yahoo-confirmed | 3.5% | 2026-11-04 (-1.44%, est: same window last year) |  |
| CABK.MC | CaixaBank | 2026-07-29 | 2026-10-30 | DMH | 2026-10-30 | P1 | yahoo-confirmed | 2.7% | 2026-11-04 (-1.50%, est: same window last year) |  |
| IAG.MC | International Airlines Group | 2026-07-31 | 2026-11-06 | DMH | 2026-11-06 | P1 | yahoo-confirmed | 4.1% |  | 2026-11-26 (-1.02%, est: same window last year) |
| IBE.MC | Iberdrola | 2026-10-21 |  |  |  | - | none | 1.5% |  |  |
| IDR.MC | Indra | 2026-07-23 | 2026-10-29 | DMH | 2026-10-29 | P1 | yahoo-confirmed | 3.1% |  |  |
| ITX.MC | Inditex | 2026-09-09 | 2026-12-02 | DMH | 2026-12-02 | P2 | yahoo-confirmed | 3.5% | 2026-10-29 (-1.54%, yahoo) |  |
| REP.MC | Repsol | 2026-07-23 | 2026-10-29 | DMH | 2026-10-29 | P1 | yahoo-confirmed | 2.5% |  |  |
| SAN.MC | Santander | 2026-07-22 | 2026-10-28 | DMH | 2026-10-28 | P1 | yahoo-confirmed | 3.2% | 2026-10-29 (-1.09%, yahoo) |  |
| TEF.MC | Telefónica | 2026-07-29 | 2026-11-12 | DMH | 2026-11-12 | P1 | yahoo-confirmed | 2.5% |  | 2026-12-15 (-4.39%, est: same window last year) |
| ASML.AS | ASML Holding | 2026-10-14 |  |  |  | - | none | 6.4% | 2026-10-26 (-0.13%, yahoo) |  |
| RACE.MI | Ferrari | 2026-07-30 | 2026-11-03 | BMO | 2026-11-03 | P1 | yahoo-confirmed | 5.7% |  |  |
| MC.PA | LVMH Moët Hennessy Louis Vuitton |  |  |  |  | - | none |  |  | 2026-12-01 (-1.96%, yahoo) |
| RHM.DE | Rheinmetall | 2026-08-06 | 2026-11-05 | DMH | 2026-11-05 | P1 | yahoo-confirmed | 4.9% |  |  |
| AAPL | Apple Inc. Common Stock | 2026-07-30 | 2026-11-02 | AMC | 2026-11-03 | P1 | confirmed (2 sources) | 2.4% | 2026-11-09 (-0.08%, est: quarterly cadence) |  |
| MSFT | Microsoft Corporation Common Stock | 2026-07-29 | 2026-10-28 | AMC | 2026-10-29 | P1 | confirmed (2 sources) | 5.4% | 2026-11-19 (-0.19%, nasdaq) |  |
| AMZN | Amazon.com, Inc. Common Stock | 2026-07-30 | 2026-10-29 | AMC | 2026-10-30 | P1 | confirmed (2 sources) | 5.5% |  |  |
| MSTR | Strategy Inc Common Stock Class A | 2026-07-30 | 2026-10-29 | AMC | 2026-10-30 | P1 | confirmed (2 sources) | 7.0% |  |  |
| NVDA | NVIDIA Corporation Common Stock | 2026-08-26 | 2026-11-18 | AMC | 2026-11-19 | P1 | unconfirmed (manual check) | 5.5% |  | 2026-12-10 (-0.12%, est: quarterly cadence) |
| AMD | Advanced Micro Devices, Inc. Common Stock | 2026-08-04 | 2026-11-03 | AMC | 2026-11-04 | P1 | confirmed (2 sources) | 8.2% |  |  |
| MU | Micron Technology, Inc. Common Stock | 2026-09-30 | 2026-12-16 | AMC | 2026-12-17 | P2 | unconfirmed (manual check) | 8.2% |  |  |
| NFLX | Netflix, Inc. Common Stock | 2026-10-20 | 2027-01-19 | unknown |  | - | estimate/single source | 7.6% |  |  |
| GOOGL | Alphabet Inc. Class A Common Stock | 2026-07-22 | 2026-10-28 | AMC | 2026-10-29 | P1 | confirmed (2 sources) | 5.4% |  | 2026-12-04 (-0.07%, est: quarterly cadence) |
| AVGO | Broadcom Inc. Common Stock | 2026-09-02 | 2026-12-09 | AMC | 2026-12-10 | P2 | confirmed (2 sources) | 9.2% |  |  |
| TSLA | Tesla, Inc. Common Stock | 2026-10-21 |  |  |  | - | none | 8.6% |  |  |
| META | Meta Platforms, Inc. Class A Common Stock | 2026-10-21 |  |  |  | - | none | 8.2% |  |  |
| PLTR | Palantir Technologies Inc. Class A Common Stock | 2026-08-03 | 2026-11-02 | AMC | 2026-11-03 | P1 | confirmed (2 sources) | 15.2% |  |  |
| SPCX | Space Exploration Technologies Corp. Class A Common Stock | 2026-10-20 |  |  |  | - | none | 11.1% |  |  |

64 names have an earnings date inside a period that is **not** confirmed by two independent sources (most European names: Yahoo is the only automated source; see `stock_features.csv`). Relevant ones: BBVA.MC 2026-10-29 [yahoo-confirmed], CABK.MC 2026-10-30 [yahoo-confirmed], IAG.MC 2026-11-06 [yahoo-confirmed], IDR.MC 2026-10-29 [yahoo-confirmed], ITX.MC 2026-12-02 [yahoo-confirmed], REP.MC 2026-10-29 [yahoo-confirmed], SAN.MC 2026-10-28 [yahoo-confirmed], TEF.MC 2026-11-12 [yahoo-confirmed], RACE.MI 2026-11-03 [yahoo-confirmed], RHM.DE 2026-11-05 [yahoo-confirmed], NVDA 2026-11-19 [unconfirmed (manual check)], MU 2026-12-17 [unconfirmed (manual check)], AXON 2026-11-06 [sources differ, same window], CRWV 2026-11-12 [sources differ, same window].
Checked by hand (see `data/earnings_overrides.csv`): MRNA Nov 6 8:00 ET confirmed on the company IR site; NVDA and MU not yet announced by the companies (modelled as 85% / 50% inside the window); CRWV not yet announced, both candidate dates (Nov 9 / Nov 11) fall in period 1; GRF.MC Nov 10 from Investing.com.

## Consensus basket and field model

Popularity weights (students' likely holdings; base weight 0.3 for everything else). Consensus basket = names with popularity >= 3.0, weighted by popularity:

NVDA 7.1%, AAPL 5.7%, TSLA 5.7%, AMZN 5.0%, ITX.MC 5.0%, MSFT 5.0%, SPCX 5.0%, SAN.MC 5.0%, META 4.3%, GOOGL 4.3%, PLTR 4.3%, BBVA.MC 3.6%, AMD 3.6%, IBE.MC 3.6%, ASML.AS 3.6%, IDR.MC 2.8%, REP.MC 2.8%, MC.PA 2.8%, TEF.MC 2.8%, NFLX 2.8%, RHM.DE 2.5%, CABK.MC 2.1%, IAG.MC 2.1%, RACE.MI 2.1%, MSTR 2.1%, AVGO 2.1%, MU 2.1%

Field: 179 opponents per scenario, div 60% / mod 25% / all-in 15%, all-in ~ pop x vol^2, 1 savvy max-vol opponents, fad prob 50% (x3), 100% of trailing re-pickers go all-in; diversified = 8-15 names ~ popularity, moderate = 3-5 names ~ popularity^1.5, all-in = 1-2 names ~ popularity x vol; Dirichlet weights, whole shares. On Nov 22 50% of opponents re-pick, the rest hold. Popularity is uncertain: every ~1,000 scenarios draw one true popularity vector = weights x lognormal(sigma 20%), shared by the whole field.

## Method

- 20,000 search scenarios + 40,000 validation scenarios, seed 20261025. Joint daily EUR total-return block bootstrap (5-day blocks) over the last 2 years, filtered-historical-simulation residuals rescaled to the current vol (`blend` = avg of EWMA(0.94) and 60d, ex-earnings, jumps winsorised at 4 sigma). US names: period variance moved 50% toward ATM option-implied variance for the Nov 20 expiry (= end of period 1), level-neutral (IV rescaled by the median model/IV ratio, so only the US cross-section changes).
- Drift: CAPM, rf 2% + beta to consensus x 5% ERP. Horizon 20 + 20 trading days (19 for US names in period 2: Thanksgiving).
- Vol-of-vol: each scenario scales the shocks by variance-neutral lognormal multipliers (market-wide sd 0.30, per stock 0.30; calibrated in `--mode validate`). Residuals clipped at 12 sigma.
- Earnings: historical reaction days are replaced by their market component; inside a window the reaction day gets a jump = (own earnings move multiple, shrunk to the pooled one) x current daily vol; size blended 50% toward the option-implied event move (term structure, level-neutral) where available; sign drawn with the stock's historical up-frequency shrunk to 50/50 (prior 8), mean kept.
- Price-only scoring: known/estimated ex-dividend drops are subtracted in the window.
- Candidates: 6,034 (all singles, pairs of the 40 highest-vol names in 5 weightings, greedy triples, benchmarks), whole shares at the latest close. Ties split.
- Period 2: no leaderboard, so the ranking uses realistic threshold policies on my own score; `P(win) oracle` in the CSV (`p_win_8w_switch`) is the v1 metric that switches only when actually leading.
