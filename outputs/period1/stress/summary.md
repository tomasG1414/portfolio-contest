# Stress tests - period 1 (full search per variant)

Each row re-runs the candidate search and validation with a different field. P(win) = P(win at Dec 18) with the switch-if-leading policy; tracked portfolios use the search-set scenarios (same returns in every row, common random numbers).

| variant | entrants | pick | P(win) pick | random entrant | winning score median | CRWV P(win) | CRWV rank | MRNA P(win) | MRNA rank | SNDK 20% + CRWV 80% P(win) | SNDK 20% + CRWV 80% rank |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 180 | CRWV | 17.16% | 0.56% | 1.397 | 17.30% | #1 | 13.94% | #4 | 14.39% | #2 |
| participants 60 | 60 | CRWV | 27.12% | 1.67% | 1.263 | 27.15% | #1 | 22.73% | #13 | 24.73% | #2 |
| participants 120 | 120 | CRWV | 20.66% | 0.83% | 1.344 | 20.54% | #1 | 17.07% | #4 | 17.66% | #2 |
| participants 200 | 200 | CRWV | 16.20% | 0.50% | 1.412 | 16.05% | #1 | 13.29% | #2 | 13.18% | #3 |
| 30% non-Spanish EU | 180 | CRWV | 17.14% | 0.56% | 1.397 | 17.07% | #1 | 13.72% | #4 | 14.21% | #2 |
| 50% non-Spanish EU | 180 | CRWV | 17.30% | 0.56% | 1.396 | 17.02% | #1 | 13.39% | #4 | 14.11% | #2 |
| hype names x2 | 180 | CRWV | 14.01% | 0.56% | 1.445 | 14.20% | #1 | 11.49% | #2 | 10.98% | #4 |
| Spanish bias x2 | 180 | CRWV | 18.38% | 0.56% | 1.377 | 18.45% | #1 | 15.04% | #4 | 15.65% | #2 |
| US mega-caps x2 | 180 | CRWV | 18.77% | 0.56% | 1.372 | 18.84% | #1 | 15.47% | #4 | 16.10% | #2 |
| group noise 50% | 180 | CRWV | 17.69% | 0.56% | 1.390 | 18.97% | #1 | 14.91% | #6 | 16.03% | #2 |
| combo: 120, 30% EU, hype x2 | 120 | CRWV | 17.46% | 0.83% | 1.390 | 16.96% | #1 | 13.94% | #3 | 14.02% | #2 |
