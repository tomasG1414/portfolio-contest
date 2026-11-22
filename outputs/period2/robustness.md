# Period-2 robustness check (my return -25.37%, prices 2026-11-20)

Top pick and P(win) under each variant (`python -m contest --mode period2 --my-return -0.2537 ...`):

| variant | #1 | P(win) | #2 | P(win) |
|---|---|---|---|---|
| base (seed 20261025) | MRVL | 3.28% | ASML.AS 20% + MRVL 80% | 2.51% |
| `--seed 1 --scenarios 50000 --validate-scenarios 80000` | MRVL | 3.62% | ASML.AS 20% + MRVL 80% | 2.58% |
| `--seed 2` | MRVL | 3.48% | ASML.AS 20% + MRVL 80% | 2.51% |
| `--vol-target 60d` | MRVL | 2.62% | NBIS | 1.98% |
| `--no-iv` | MRVL | 4.71% | ASML.AS 20% + MRVL 80% | 3.72% |
| `--mix 0.5,0.25,0.25` (more all-in opponents) | MRVL | 2.44% | ASML.AS 20% + MRVL 80% | 1.81% |
| `--chase 0.5` (opponents chase P1 winners) | MRVL | 3.82% | NBIS | 3.32% |

MRVL all-in ranks first in every variant: ~118% simulated vol, confirmed earnings Dec 1 AMC
(reaction Dec 2, inside period 2, mean |move| 12%), and low popularity (few opponents share its upside).

Sizing on net worth 7,462.87 EUR: floor(7,462.87 / 111.4705) = **66 MRVL** (122.28 USD, EURUSD 1.0970),
7,357.05 EUR invested, ~105.82 EUR cash.
