# Stock contest - period 1 submission (Oct 25, prices 2026-10-22)

Objective: maximise the probability of finishing **first** of 120 (not expected return). Ranking metric: `p_win_8w_switch` = P(win at Dec 18) if I hold this portfolio through period 1 and, on Nov 22, switch to the consensus basket only when I am leading, otherwise keep it.

## Submission (do not trade - enter these in the contest platform)

**CRWV** - P(win Dec 18) 17.46%, P(lead Nov 20) 17.02%, P(top 5 Nov 20) 33.2% (validated on 40,000 fresh scenarios).

| ticker | name | shares | price_local | currency | price_eur | value_eur | weight | last_close |
|---|---|---|---|---|---|---|---|---|
| CRWV | CoreWeave, Inc. Class A Common Stock | 202 | 55.60 | USD | 49.49 | 9,996.89 | 100.0% | 2026-10-22 |

Invested 9,996.89 EUR, cash left 3.11 EUR (earns nothing). EUR/USD used: 1.1235.

> Prices are the 2026-10-22 close. The contest uses the Fri 2026-10-23 close: re-run `python -m contest --mode fetch` and `--mode period1` after the close (or recompute shares = floor(10,000 / EUR price)) before submitting.

## Top 10 (re-scored on fresh scenarios)

| # | portfolio | P(win) Dec18 | P(win) hold 8w | P(lead) Nov20 | P(top5) Nov20 | median 4w | p10 / p90 4w | vol | corr cons. | co-holders | shadowed | flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | CRWV | 17.46% | 16.87% | 17.02% | 33.2% | -0.7% | -33.9% / 48.2% | 113% | 0.31 | 13.1 | 26% | CRWV: E1 2026-11-12? |
| 2 | MRNA | 14.51% | 13.80% | 14.17% | 28.8% | -3.9% | -34.7% / 42.5% | 112% | 0.14 | 16.0 | 34% | MRNA: E1 2026-11-06 |
| 3 | SNDK 20% + CRWV 80% | 14.26% | 14.13% | 13.29% | 31.9% | -0.2% | -30.6% / 44.1% | 102% | 0.33 | 8.8 | 38% | SNDK: E1 2026-10-30 | CRWV: E1 2026-11-12? |
| 4 | MPWR 20% + CRWV 80% | 14.04% | 13.79% | 13.15% | 31.5% | -0.5% | -30.7% / 43.8% | 102% | 0.33 | 6.6 | 24% | MPWR: E1 2026-10-30 | CRWV: E1 2026-11-12? |
| 5 | NBIS 20% + CRWV 80% | 13.41% | 13.23% | 12.44% | 31.0% | -0.3% | -30.1% / 42.0% | 99% | 0.36 | 11.2 | 39% | NBIS: E1 2026-11-10 | CRWV: E1 2026-11-12? |
| 6 | MU 20% + CRWV 80% | 13.24% | 13.13% | 12.35% | 31.1% | -0.3% | -29.7% / 42.3% | 99% | 0.35 | 12.4 | 30% | MU: E2 2026-12-17? (50%; else outside 2026-12-24) | CRWV: E1 2026-11-12? |
| 7 | ALAB 20% + CRWV 80% | 13.00% | 12.82% | 12.20% | 30.8% | -0.3% | -29.3% / 41.5% | 97% | 0.36 | 9.0 | 34% | ALAB: E1 2026-11-04 | CRWV: E1 2026-11-12? |
| 8 | STX 20% + CRWV 80% | 12.85% | 12.81% | 12.22% | 30.7% | -0.3% | -29.2% / 41.5% | 97% | 0.35 | 7.1 | 26% | STX: E1 2026-10-28 | CRWV: E1 2026-11-12? |
| 9 | CRWV 80% + HONA 20% | 12.84% | 12.87% | 12.07% | 30.9% | 0.3% | -26.9% / 40.3% | 91% | 0.34 | 7.1 | 26% | CRWV: E1 2026-11-12? | HONA: E1 2026-10-29; short history |
| 10 | ARM 20% + CRWV 80% | 12.82% | 12.80% | 12.07% | 30.9% | -0.2% | -29.6% / 41.5% | 98% | 0.35 | 12.9 | 44% | ARM: E1 2026-11-05 | CRWV: E1 2026-11-12? |

P(win) Dec18 = switch-if-leading policy; hold 8w = no rebalance; P(lead) Nov20 = rank 1 after period 1. co-holders = avg. number of opponents holding my best-performing name; shadowed = when that name is a top-3 performer, share of scenarios where an opponent holds it at least as heavily as I do. Flags: E1/E2 earnings reaction day in period 1/2 (`?` = date not confirmed by a second source), D1/D2 ex-dividend drop (`~` = estimated).

Benchmarks for scale: IBEX blue chips (EW) 0.21%; Magnificent 7 (EW) 0.02%; Top-10 popular (EW) 0.00%; Consensus basket 0.00%. A random entrant has 0.83%.

## Sensitivity to the field mixture

P(win Dec 18) and rank within the shortlist when the share of all-in opponents changes (diversified : moderate kept at 60 : 25). Sorted by worst rank; **robust** = top 10 under every mixture. The vol-model column re-scores the same portfolios with the other US-vol choice (base mixture) as a model-risk check; it does not enter the worst rank.

| portfolio | all-in 15% | worst rank | robust |
|---|---|---|---|
| CRWV | 17.46% (#1) | 1 | **yes** |
| MRNA | 14.51% (#2) | 2 | **yes** |
| SNDK 20% + CRWV 80% | 14.26% (#3) | 3 | **yes** |
| MPWR 20% + CRWV 80% | 14.04% (#4) | 4 | **yes** |
| NBIS 20% + CRWV 80% | 13.41% (#5) | 5 | **yes** |
| MU 20% + CRWV 80% | 13.24% (#6) | 6 | **yes** |
| ALAB 20% + CRWV 80% | 13.00% (#7) | 7 | **yes** |
| STX 20% + CRWV 80% | 12.85% (#8) | 8 | **yes** |
| CRWV 80% + HONA 20% | 12.84% (#9) | 9 | **yes** |
| ARM 20% + CRWV 80% | 12.82% (#10) | 10 | **yes** |
| TER 20% + CRWV 80% | 12.72% (#11) | 11 |  |
| LRCX 20% + CRWV 80% | 12.60% (#12) | 12 |  |
| LITE 20% + CRWV 80% | 12.40% (#13) | 13 |  |
| RKLB 20% + CRWV 80% | 12.35% (#14) | 14 |  |
| WDC 20% + CRWV 80% | 12.34% (#15) | 15 |  |

## What it takes to win

Best opponent after 4 weeks: median score 1.278 (10-90%: 1.113-1.600). Winning score at Dec 18: median 1.390 (10-90%: 1.156-1.822).

![P(win) vs vol](pwin_vs_vol.png)

![winning score](winning_score_hist.png)

## Earnings and ex-dividend flags

Names in the top 10:

| ticker | name | last reported | next earnings | timing | reaction day | period | status | hist. |move| | ex-div P1 | ex-div P2 |
|---|---|---|---|---|---|---|---|---|---|---|
| CRWV | CoreWeave, Inc. Class A Common Stock | 2026-08-11 | 2026-11-11 | AMC | 2026-11-12 | P1 | sources differ, same window | 15.7% |  |  |
| MRNA | Moderna, Inc. Common Stock | 2026-07-31 | 2026-11-06 | BMO | 2026-11-06 | P1 | confirmed (2 sources) | 7.2% |  |  |
| SNDK | Sandisk Corporation Common Stock | 2026-08-05 | 2026-10-29 | AMC | 2026-10-30 | P1 | confirmed (2 sources) | 7.4% |  |  |
| MPWR | Monolithic Power Systems, Inc. Common Stock | 2026-07-30 | 2026-10-29 | AMC | 2026-10-30 | P1 | confirmed (2 sources) | 8.3% |  |  |
| NBIS | Nebius Group N.V. Class A Ordinary Shares | 2026-08-12 | 2026-11-10 | BMO | 2026-11-10 | P1 | confirmed (2 sources) | 10.9% |  |  |
| MU | Micron Technology, Inc. Common Stock | 2026-09-30 | 2026-12-16 | AMC | 2026-12-17 | P2 | unconfirmed (manual check) | 8.2% |  |  |
| ALAB | Astera Labs, Inc. Common Stock | 2026-08-04 | 2026-11-03 | AMC | 2026-11-04 | P1 | confirmed (2 sources) | 13.4% |  |  |
| STX | Seagate Technology Holdings PLC Ordinary Shares (Ireland) | 2026-07-28 | 2026-10-27 | AMC | 2026-10-28 | P1 | confirmed (2 sources) | 7.0% |  |  |
| HONA | Honeywell Aerospace Inc. Common Stock  | 2026-08-05 | 2026-10-28 | AMC | 2026-10-29 | P1 | confirmed (2 sources) | 26.6% |  |  |
| ARM | Arm Holdings plc American Depositary Shares | 2026-07-29 | 2026-11-04 | AMC | 2026-11-05 | P1 | confirmed (2 sources) | 9.3% |  |  |

Consensus names:

| ticker | name | last reported | next earnings | timing | reaction day | period | status | hist. |move| | ex-div P1 | ex-div P2 |
|---|---|---|---|---|---|---|---|---|---|---|
| BBVA.MC | BBVA | 2026-07-30 | 2026-10-29 | DMH | 2026-10-29 | P1 | yahoo-confirmed | 3.5% | 2026-11-04 (-1.44%, est: same window last year) |  |
| CABK.MC | CaixaBank | 2026-07-29 | 2026-10-30 | DMH | 2026-10-30 | P1 | yahoo-confirmed | 2.7% | 2026-11-04 (-1.51%, est: same window last year) |  |
| IAG.MC | International Airlines Group | 2026-07-31 | 2026-11-06 | DMH | 2026-11-06 | P1 | yahoo-confirmed | 4.1% |  | 2026-11-26 (-0.99%, est: same window last year) |
| IBE.MC | Iberdrola | 2026-10-21 |  |  |  | - | none | 1.5% |  |  |
| IDR.MC | Indra | 2026-07-23 | 2026-10-29 | DMH | 2026-10-29 | P1 | yahoo-confirmed | 3.1% |  |  |
| ITX.MC | Inditex | 2026-09-09 | 2026-12-02 | DMH | 2026-12-02 | P2 | yahoo-confirmed | 3.5% | 2026-10-29 (-1.56%, yahoo) |  |
| REP.MC | Repsol | 2026-07-23 | 2026-10-29 | DMH | 2026-10-29 | P1 | yahoo-confirmed | 2.5% |  |  |
| SAN.MC | Santander | 2026-07-22 | 2026-10-28 | DMH | 2026-10-28 | P1 | yahoo-confirmed | 3.2% | 2026-10-29 (-1.09%, yahoo) |  |
| TEF.MC | Telefónica | 2026-07-29 | 2026-11-12 | DMH | 2026-11-12 | P1 | yahoo-confirmed | 2.5% |  | 2026-12-15 (-4.31%, est: same window last year) |
| ASML.AS | ASML Holding | 2026-10-14 |  |  |  | - | none | 6.4% | 2026-10-26 (-0.13%, yahoo) |  |
| RACE.MI | Ferrari | 2026-07-30 | 2026-11-03 | BMO | 2026-11-03 | P1 | yahoo-confirmed | 5.7% |  |  |
| MC.PA | LVMH Moët Hennessy Louis Vuitton |  |  |  |  | - | none |  |  | 2026-12-01 (-1.93%, yahoo) |
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

64 names have an earnings date inside a period that is **not** confirmed by two independent sources (most European names: Yahoo is the only automated source; see `stock_features.csv`). Relevant ones: BBVA.MC 2026-10-29 [yahoo-confirmed], CABK.MC 2026-10-30 [yahoo-confirmed], IAG.MC 2026-11-06 [yahoo-confirmed], IDR.MC 2026-10-29 [yahoo-confirmed], ITX.MC 2026-12-02 [yahoo-confirmed], REP.MC 2026-10-29 [yahoo-confirmed], SAN.MC 2026-10-28 [yahoo-confirmed], TEF.MC 2026-11-12 [yahoo-confirmed], RACE.MI 2026-11-03 [yahoo-confirmed], RHM.DE 2026-11-05 [yahoo-confirmed], NVDA 2026-11-19 [unconfirmed (manual check)], MU 2026-12-17 [unconfirmed (manual check)], CRWV 2026-11-12 [sources differ, same window].
Checked by hand (see `data/earnings_overrides.csv`): MRNA Nov 6 8:00 ET confirmed on the company IR site; NVDA and MU not yet announced by the companies (modelled as 85% / 50% inside the window); CRWV not yet announced, both candidate dates (Nov 9 / Nov 11) fall in period 1; GRF.MC Nov 10 from Investing.com.

## Consensus basket and field model

Popularity weights (students' likely holdings; base weight 0.3 for everything else). Consensus basket = names with popularity >= 3.0, weighted by popularity:

NVDA 7.1%, AAPL 5.7%, TSLA 5.7%, AMZN 5.0%, ITX.MC 5.0%, MSFT 5.0%, SPCX 5.0%, SAN.MC 5.0%, META 4.3%, GOOGL 4.3%, PLTR 4.3%, BBVA.MC 3.6%, AMD 3.6%, IBE.MC 3.6%, ASML.AS 3.6%, IDR.MC 2.8%, REP.MC 2.8%, MC.PA 2.8%, TEF.MC 2.8%, NFLX 2.8%, RHM.DE 2.5%, CABK.MC 2.1%, IAG.MC 2.1%, RACE.MI 2.1%, MSTR 2.1%, AVGO 2.1%, MU 2.1%

Field: 119 opponents per scenario, div 60% / mod 25% / all-in 15%, 30% non-Spanish European students, hype popularity x2; diversified = 8-15 names ~ popularity, moderate = 3-5 names ~ popularity^1.5, all-in = 1-2 names ~ popularity x vol; Dirichlet weights, whole shares. On Nov 22 50% of opponents re-pick, the rest hold. Popularity is uncertain: every ~1,000 scenarios draw one true popularity vector = weights x lognormal(sigma 20%), shared by the whole field.

## Method

- 20,000 search scenarios + 40,000 validation scenarios, seed 20261025. Joint daily EUR total-return block bootstrap (5-day blocks) over the last 2 years, filtered-historical-simulation residuals rescaled to the current vol (`blend` = avg of EWMA(0.94) and 60d, ex-earnings, jumps winsorised at 4 sigma). US names: period variance moved 50% toward ATM option-implied variance for the Nov 20 expiry (= end of period 1), level-neutral (IV rescaled by the median model/IV ratio, so only the US cross-section changes).
- Drift: CAPM, rf 2% + beta to consensus x 5% ERP. Horizon 20 + 20 trading days.
- Earnings: historical reaction days are replaced by their market component; inside a window the reaction day gets a jump = (own earnings move multiple, shrunk to the pooled one) x current daily vol, random sign.
- Price-only scoring: known/estimated ex-dividend drops are subtracted in the window.
- Candidates: 6,084 (all singles, pairs of the 40 highest-vol names in 5 weightings, greedy triples, benchmarks), whole shares at the latest close. Ties split.
- The switch policy uses the realised field leader (an oracle: on Nov 22 you only have an estimate), so P(win Dec18) is slightly optimistic for every candidate alike.
