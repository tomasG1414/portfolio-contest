"""Markdown report and plots."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from . import config, universe

# Reference palette (light mode): surface, inks, categorical slots 1-3.
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = {"single": "#2a78d6", "pair": "#eb6834", "triple": "#1baf7a"}


def _pct(x, d=1):
    return "" if pd.isna(x) else f"{100 * x:.{d}f}%"


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |")
    return "\n".join(lines)


def holdings_str(cs, j, inp) -> str:
    return ", ".join(f"{int(cs.shares[j, i])}x {inp.tickers[i]}" for i in np.flatnonzero(cs.shares[j]))


def flags_str(cs, j, inp, feat: pd.DataFrame) -> str:
    """Earnings (E1/E2 = reaction day in period 1/2) and ex-div (D1/D2) flags."""
    out = []
    for i in np.flatnonzero(cs.shares[j]):
        t = inp.tickers[i]
        f = feat.loc[t]
        tags = []
        if f["earn_period"] in (1, 2):
            unc = "?" if not str(f["earn_status"]).startswith(("confirmed", "verified")) else ""
            alt = ""
            if f.get("earn_p_primary", 1.0) < 1.0:
                where = f"P{int(f['earn_alt_period'])}" if f["earn_alt_period"] in (1, 2) else "outside"
                alt = f" ({f['earn_p_primary']:.0%}; else {where} {f['earn_alt_reaction']})"
            tags.append(f"E{int(f['earn_period'])} {f['earn_reaction']}{unc}{alt}")
        for p in (1, 2):
            if f.get(f"exdiv_p{p}_pct", 0) and f[f"exdiv_p{p}_pct"] > 0:
                est = "~" if "est" in str(f[f"exdiv_p{p}_source"]) else ""
                tags.append(f"D{p} {est}-{f[f'exdiv_p{p}_pct']:.1%}")
        if f.get("short_history"):
            tags.append("short history")
        if tags:
            out.append(f"{t}: " + "; ".join(tags))
    return " | ".join(out)


# --------------------------------------------------------------------------
# Plots
# --------------------------------------------------------------------------
def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def plot_pwin_vs_vol(res: pd.DataFrame, path, metric: str, highlight=(), n_entrants=config.N_OPPONENTS + 1):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 5.6), dpi=160, facecolor=SURFACE)
    _style(ax)
    for kind, color in SERIES.items():
        d = res[res["kind"] == kind]
        ax.scatter(100 * d["vol_ann"], 100 * d[metric], s=14, color=color, alpha=0.65,
                   edgecolors=SURFACE, linewidths=0.4, label=f"{kind}s ({len(d)})")
    b = res[res["kind"] == "benchmark"]
    ax.scatter(100 * b["vol_ann"], 100 * b[metric], s=40, marker="D", color=INK,
               label="benchmarks: " + ", ".join(b["candidate"].str.replace(" (EW)", "", regex=False)),
               edgecolors=SURFACE, linewidths=1.0, zorder=3)
    for n, lab in enumerate(list(highlight)[:3]):
        r = res[res["candidate"] == lab]
        if len(r):
            r = r.iloc[0]
            ax.scatter([100 * r["vol_ann"]], [100 * r[metric]], s=60, facecolors="none",
                       edgecolors=INK, linewidths=1.2, zorder=4)
            ax.annotate(lab, (100 * r["vol_ann"], 100 * r[metric]), xytext=(-10, 8 - 14 * n),
                        textcoords="offset points", fontsize=8, color=INK, ha="right")
    ax.axhline(100 / n_entrants, color=INK2, linewidth=1, linestyle=(0, (4, 3)))
    ax.annotate(f"1/{n_entrants} (random entrant)", (ax.get_xlim()[1], 100 / n_entrants),
                xytext=(-4, 4), textcoords="offset points", fontsize=8, color=INK2, ha="right")
    ax.set_xlabel("Simulated portfolio volatility, period 1 (annualised, %)", color=INK, fontsize=10)
    nice = {"p_win_8w_switch": "P(win at Dec 18), switch-if-leading policy",
            "p_win_4w": "P(lead at Nov 20)", "p_win_8w_hold": "P(win at Dec 18), buy and hold"}
    ax.set_ylabel(f"{nice.get(metric, metric)} (%)", color=INK, fontsize=10)
    ax.set_title("Win probability vs volatility, all candidates", color=INK, fontsize=12, loc="left")
    leg = ax.legend(frameon=False, fontsize=9, loc="upper left")
    for t in leg.get_texts():
        t.set_color(INK)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def plot_winning_score(fmax1, fmax8, path, mine=None, my_now=None):
    """Two panels (period-1 leader score, final winning score)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), dpi=160, facecolor=SURFACE, sharey=False)
    panels = (("Best opponent score at Nov 20 (4 weeks)", fmax1, None if mine is None else mine[1]),
              ("Winning opponent score at Dec 18 (8 weeks)", fmax8, None if mine is None else mine[2]))
    for ax, (title, x, my) in zip(axes, panels):
        _style(ax)
        lo, hi = np.quantile(x, [0.001, 0.995])
        ax.hist(x, bins=np.linspace(lo, hi, 70), color=SERIES["single"], edgecolor=SURFACE,
                linewidth=0.6)
        med = np.median(x)
        ax.axvline(med, color=INK2, linewidth=1, linestyle=(0, (4, 3)))
        ax.annotate(f"median {med:.3f}", (med, ax.get_ylim()[1] * 0.92), xytext=(4, 0),
                    textcoords="offset points", fontsize=8, color=INK2)
        if my is not None:
            p90 = np.quantile(my, 0.9)
            ax.axvline(p90, color=INK, linewidth=1.2)
            ax.annotate(f"my pick, 90th pct {p90:.3f}", (p90, ax.get_ylim()[1] * 0.80),
                        xytext=(4, 0), textcoords="offset points", fontsize=8, color=INK)
        if my_now is not None and ax is axes[0]:
            ax.axvline(my_now, color=INK, linewidth=1.2)
            ax.annotate(f"my score {my_now:.3f}", (my_now, ax.get_ylim()[1] * 0.80),
                        xytext=(4, 0), textcoords="offset points", fontsize=8, color=INK)
        ax.set_title(title, color=INK, fontsize=10.5, loc="left")
        ax.set_xlabel("score = final / starting net worth", color=INK, fontsize=9)
    axes[0].set_ylabel("scenarios", color=INK, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------
def _data_section(md, prices) -> list[str]:
    rep = md.fetch_report or {}
    lines = ["## Data", "",
             f"- Prices through **{prices.asof.date()}** (fetched {rep.get('fetched_at_utc', '?')}); "
             f"{len(md.universe)} names after de-duplication."]
    for idx, r in (rep.get("universe") or {}).items():
        lines.append(f"- {idx}: {r['source']}, {r['count']} names"
                     + (f"; vs snapshot +{r['added_vs_snapshot']} -{r['removed_vs_snapshot']}"
                        if r['added_vs_snapshot'] or r['removed_vs_snapshot'] else ""))
    failed = sorted(set(rep.get("failed_downloads") or []) | set(md.failed))
    lines.append(f"- Failed downloads: {', '.join(failed) if failed else 'none'}")
    stale = rep.get("stale_tickers") or []
    if stale:
        lines.append(f"- Stale price series (last close >4 days old): {', '.join(stale)}")
    lines.append("- Cross-listings folded into the EUR line: ASML (Nasdaq) -> ASML.AS, "
                 "FER (Nasdaq) -> FER.MC; IBEX/Euro Stoxx overlaps (SAN, BBVA, IBE, ITX) counted once.")
    return lines + [""]


def _flags_table(feat: pd.DataFrame, tickers) -> str:
    rows = []
    for t in tickers:
        f = feat.loc[t]
        rows.append({"ticker": t, "name": f["name"],
                     "last reported": f.get("earn_last") or "",
                     "next earnings": f["earn_date"] or "", "timing": f["earn_timing"] or "",
                     "reaction day": f["earn_reaction"] or "",
                     "period": {1: "P1", 2: "P2"}.get(f["earn_period"], "-"),
                     "status": f["earn_status"],
                     "hist. |move|": _pct(f["earn_move_mean_abs"]),
                     "ex-div P1": (f"{f['exdiv_p1_date']} (-{f['exdiv_p1_pct']:.2%}, {f['exdiv_p1_source']})"
                                   if f["exdiv_p1_pct"] > 0 else ""),
                     "ex-div P2": (f"{f['exdiv_p2_date']} (-{f['exdiv_p2_pct']:.2%}, {f['exdiv_p2_source']})"
                                   if f["exdiv_p2_pct"] > 0 else "")})
    return _md_table(pd.DataFrame(rows))


def period1_markdown(c: dict) -> str:
    feat, val, res, pick, hold = c["feat"], c["val"], c["res"], c["pick"], c["hold"]
    mixes, base_key, rank_by, cfg, mix = c["mixes"], c["base_key"], c["rank_by"], c["cfg"], c["mix"]
    f = c["field"]
    L = [f"# Stock contest - period 1 submission (Oct 25, prices {c['prices'].asof.date()})", ""]
    n_ent = mix.n_opponents + 1
    L += [f"Objective: maximise the probability of finishing **first** of {n_ent} "
          "(not expected return). Ranking metric: `" + rank_by + "` = P(win at Dec 18) if I hold "
          "this portfolio through period 1 and, on Nov 22, switch to the consensus basket only "
          "when I am leading, otherwise keep it.", ""]
    # ---- submission
    invested = hold["value_eur"].sum()
    L += ["## Submission (do not trade - enter these in the contest platform)", "",
          f"**{pick['candidate']}** - P(win Dec 18) {_pct(pick[rank_by], 2)}, "
          f"P(lead Nov 20) {_pct(pick['p_win_4w'], 2)}, P(top 5 Nov 20) {_pct(pick['p_top5_4w'], 1)} "
          f"(validated on {cfg.n_validate:,} fresh scenarios).", ""]
    h = hold.assign(price_local=hold["price_local"].map("{:,.2f}".format),
                    price_eur=hold["price_eur"].map("{:,.2f}".format),
                    value_eur=hold["value_eur"].map("{:,.2f}".format),
                    weight=hold["weight"].map(lambda x: f"{x:.1%}"))
    L += [_md_table(h[["ticker", "name", "shares", "price_local", "currency", "price_eur",
                       "value_eur", "weight", "last_close"]]), "",
          f"Invested {invested:,.2f} EUR, cash left {config.CAPITAL_EUR - invested:,.2f} EUR "
          f"(earns nothing). EUR/USD used: {c['prices'].fx.iloc[-1]:.4f}.", ""]
    if c["prices"].asof.date() < config.P1_PRICE_DATE:
        L += [f"> Prices are the {c['prices'].asof.date()} close. The contest uses the Fri "
              f"{config.P1_PRICE_DATE} close: re-run `python -m contest --mode fetch` and "
              "`--mode period1` after the close (or recompute shares = floor(10,000 / EUR price)) "
              "before submitting.", ""]
    rb = c["robust"]
    if rb["candidate"] != pick["candidate"]:
        L += [f"Most mixture-robust alternative: **{rb['candidate']}** "
              f"(worst rank {int(rb['worst_rank'])} across field mixtures, "
              f"P(win) {_pct(rb[rank_by], 2)}): " + ", ".join(
                  f"{int(r.shares)}x {r.ticker}" for r in c["hold_r"].itertuples()), ""]
    # ---- top 10
    top = val[val["kind"] != "benchmark"].head(10)
    t = pd.DataFrame({
        "#": range(1, len(top) + 1), "portfolio": top["candidate"],
        "P(win) Dec18": top[rank_by].map(lambda x: _pct(x, 2)),
        "P(win) hold 8w": top["p_win_8w_hold"].map(lambda x: _pct(x, 2)),
        "P(lead) Nov20": top["p_win_4w"].map(lambda x: _pct(x, 2)),
        "P(top5) Nov20": top["p_top5_4w"].map(_pct),
        "median 4w": top["ret_median_4w"].map(_pct),
        "p10 / p90 4w": [f"{_pct(a)} / {_pct(b)}" for a, b in zip(top["ret_p10_4w"], top["ret_p90_4w"])],
        "vol": top["vol_ann"].map(lambda x: f"{x:.0%}"),
        "corr cons.": top["corr_consensus"].map(lambda x: f"{x:.2f}"),
        "co-holders": top["avg_coholders"].map(lambda x: f"{x:.1f}"),
        "shadowed": top["shadowed_when_hits"].map(lambda x: f"{x:.0%}"),
        "flags": top["flags"]})
    L += ["## Top 10 (re-scored on fresh scenarios)", "", _md_table(t), "",
          "P(win) Dec18 = switch-if-leading policy; hold 8w = no rebalance; P(lead) Nov20 = rank 1 "
          "after period 1. co-holders = avg. number of opponents holding my best-performing name; "
          "shadowed = when that name is a top-3 performer, share of scenarios where an opponent "
          "holds it at least as heavily as I do. Flags: E1/E2 earnings reaction day in period 1/2 "
          "(`?` = date not confirmed by a second source), D1/D2 ex-dividend drop (`~` = estimated).",
          "", "Benchmarks for scale: " + "; ".join(
              f"{r.candidate} {_pct(getattr(r, rank_by), 2)}" for r in val[val['kind'] == 'benchmark'].itertuples())
          + f". A random entrant has {_pct(1 / n_ent, 2)}.", ""]
    # ---- sensitivity
    keys = list(mixes)
    sens = val[val["kind"] != "benchmark"].sort_values("worst_rank").head(15)
    srows = []
    for _, r in sens.iterrows():
        row = {"portfolio": r["candidate"]}
        for k in keys:
            row[f"all-in {k:.0%}"] = f"{_pct(r[f'{rank_by}@allin{k:.0%}'], 2)} (#{int(r[f'rank@allin{k:.0%}'])})"
        if c.get("alt_label"):
            row[f"vol model: {c['alt_label']}"] = (f"{_pct(r[f'{rank_by}@volmodel'], 2)} "
                                                   f"(#{int(r['rank@volmodel'])})")
        row["worst rank"] = int(r["worst_rank"])
        row["robust"] = "**yes**" if r["worst_rank"] <= 10 else ""
        srows.append(row)
    L += ["## Sensitivity to the field mixture", "",
          "P(win Dec 18) and rank within the shortlist when the share of all-in opponents changes "
          "(diversified : moderate kept at 60 : 25). Sorted by worst rank; **robust** = top 10 under "
          "every mixture. The vol-model column re-scores the same portfolios with the other US-vol "
          "choice (base mixture) as a model-risk check; it does not enter the worst rank.", "",
          _md_table(pd.DataFrame(srows)), ""]
    cr = c.get("crowd")
    if cr is not None and len(cr):
        ct = cr.map(lambda x: _pct(x, 2)).reset_index().rename(columns={"index": "portfolio"})
        ct.columns = ["portfolio", "base"] + [f"{t} popularity x3" for t in cr.columns[1:]]
        L += ["Crowding check (popularity is the softest assumption): P(win Dec 18) when one lead "
              "name is three times as popular with the field as assumed.", "", _md_table(ct), ""]
    # ---- field
    q1 = np.quantile(f.field_max1, [0.1, 0.5, 0.9])
    q8 = np.quantile(f.field_max8, [0.1, 0.5, 0.9])
    L += ["## What it takes to win", "",
          f"Best opponent after 4 weeks: median score {q1[1]:.3f} (10-90%: {q1[0]:.3f}-{q1[2]:.3f}). "
          f"Winning score at Dec 18: median {q8[1]:.3f} (10-90%: {q8[0]:.3f}-{q8[2]:.3f}).", "",
          "![P(win) vs vol](pwin_vs_vol.png)", "", "![winning score](winning_score_hist.png)", ""]
    # ---- earnings / ex-div flags
    names = []
    for lab in top["candidate"]:
        names += [p.rsplit(" ", 1)[0] if "%" in p else p for p in lab.split(" + ")]
    names = list(dict.fromkeys(names))
    cons = universe.consensus_weights(list(feat.index))
    L += ["## Earnings and ex-dividend flags", "", "Names in the top 10:", "",
          _flags_table(feat, names), "", "Consensus names:", "",
          _flags_table(feat, [t for t in cons.index if t in feat.index]), ""]
    unc = feat[feat["earn_period"].isin([1, 2]) &
               ~feat["earn_status"].astype(str).str.startswith(("confirmed", "verified"))]
    rel = unc[unc.index.isin(names) | unc.index.isin(cons.index)]
    if len(unc):
        L += [f"{len(unc)} names have an earnings date inside a period that is **not** confirmed by "
              "two independent sources (most European names: Yahoo is the only automated source; "
              "see `stock_features.csv`). Relevant ones: " + ", ".join(
                  f"{t} {r['earn_reaction']} [{r['earn_status']}]" for t, r in rel.iterrows()) + ".",
              "Checked by hand (see `data/earnings_overrides.csv`): MRNA Nov 6 8:00 ET confirmed on "
              "the company IR site; NVDA and MU not yet announced by the companies (modelled as "
              "85% / 50% inside the window); CRWV not yet announced, both candidate dates (Nov 9 / "
              "Nov 11) fall in period 1; GRF.MC Nov 10 from Investing.com.", ""]
    # ---- consensus + method
    L += ["## Consensus basket and field model", "",
          "Popularity weights (students' likely holdings; base weight "
          f"{universe.BASE_POPULARITY} for everything else). Consensus basket = names with "
          f"popularity >= {universe.CONSENSUS_MIN}, weighted by popularity:", "",
          ", ".join(f"{t} {w:.1%}" for t, w in cons.sort_values(ascending=False).items()), "",
          f"Field: {mix.n_opponents} opponents per scenario, {mix.label()}; diversified = "
          f"{mix.div_k[0]}-{mix.div_k[1]} names ~ popularity, moderate = {mix.mod_k[0]}-{mix.mod_k[1]} "
          f"names ~ popularity^{mix.mod_pop_power}, all-in = 1-2 names ~ popularity x vol; Dirichlet "
          f"weights, whole shares. On Nov 22 {mix.p_rebalance:.0%} of opponents re-pick, the rest hold."
          + (f" Popularity is uncertain: every ~1,000 scenarios draw one true popularity vector = weights "
             f"x lognormal(sigma {mix.pop_noise:.0%}), shared by the whole field." if mix.pop_noise > 0 else ""),
          "",
          "## Method", "",
          f"- {cfg.n_scenarios:,} search scenarios + {cfg.n_validate:,} validation scenarios, seed "
          f"{cfg.seed}. Joint daily EUR total-return block bootstrap ({cfg.block}-day blocks) over the "
          f"last {config.HISTORY_YEARS} years, filtered-historical-simulation residuals rescaled to the "
          f"current vol (`{cfg.vol_target}` = avg of EWMA({cfg.ewma_lambda}) and 60d, ex-earnings, "
          "jumps winsorised at 4 sigma)."
          + (f" US names: period variance moved {cfg.iv_weight:.0%} toward ATM option-implied variance "
             "for the Nov 20 expiry (= end of period 1), level-neutral (IV rescaled by the median "
             "model/IV ratio, so only the US cross-section changes)." if cfg.use_iv else ""),
          f"- Drift: CAPM, rf {cfg.rf:.0%} + beta to consensus x {cfg.erp:.0%} ERP. Horizon "
          f"{config.P1_DAYS} + {config.P2_DAYS} trading days.",
          "- Earnings: historical reaction days are replaced by their market component; inside a "
          "window the reaction day gets a jump = (own earnings move multiple, shrunk to the pooled "
          "one) x current daily vol, random sign.",
          "- Price-only scoring: known/estimated ex-dividend drops are subtracted in the window.",
          f"- Candidates: {c['n_cands']:,} (all singles, pairs of the {config.TOP_VOL_FOR_PAIRS} "
          f"highest-vol names in 5 weightings, greedy triples, benchmarks), whole shares at the "
          "latest close. Ties split.",
          "- The switch policy uses the realised field leader (an oracle: on Nov 22 you only have "
          "an estimate), so P(win Dec18) is slightly optimistic for every candidate alike.", ""]
    return "\n".join(L)


def period2_markdown(c: dict) -> str:
    res, rule, pick, hold, f = c["res"], c["rule"], c["pick"], c["hold"], c["field"]
    g = c["my_gross"]
    q = np.quantile(f.field_max1, [0.1, 0.5, 0.9])
    L = [f"# Stock contest - period 2 rebalance (Nov 22)", "",
         f"Period-1 returns: {c['source']}. My score after period 1: **{g:.4f}**.", "",
         f"Estimated best opponent score now (random portfolios, known returns): median {q[1]:.3f} "
         f"(10-90%: {q[0]:.3f}-{q[2]:.3f}). P(I am leading now) = {_pct((g > f.field_max1).mean())}.", ""]
    invested = hold["value_eur"].sum() if len(hold) else 0.0
    L += ["## Rebalance (do not trade - enter in the contest platform)", "",
          f"**{pick['candidate']}** - P(win Dec 18) {_pct(pick['p_win'], 2)}, P(top 5) {_pct(pick['p_top5'])}.",
          "", "Shares below are sized on 10,000 EUR; scale by your actual net worth "
          f"({10_000 * g:,.0f} EUR): shares = floor(net worth x weight / EUR price).", ""]
    if len(hold):
        L += [_md_table(hold.assign(weight=hold["weight"].map(lambda x: f"{x:.1%}"))
                        [["ticker", "name", "shares", "price_local", "currency", "price_eur", "weight"]]), ""]
    top = res.head(10)
    L += ["## Top 10", "", _md_table(pd.DataFrame({
        "#": top["rank"], "portfolio": top["candidate"], "P(win)": top["p_win"].map(lambda x: _pct(x, 2)),
        "P(top5)": top["p_top5"].map(_pct), "vol": top["vol_ann"].map(lambda x: f"{x:.0%}"),
        "corr cons.": top["corr_consensus"].map(lambda x: f"{x:.2f}"),
        "median": top["ret_median_p2"].map(_pct), "p90": top["ret_p90_p2"].map(_pct)})), ""]
    rt = rule.assign(**{k: rule[k].map(lambda x: _pct(x, 2)) for k in
                        ("p_leading_now", "p_win_best", "p_win_concentrated", "p_win_consensus_like",
                         "p_win_low_vol", "p_win_consensus_basket")})
    L += ["## Rule of thumb test: de-risk when ahead, concentrate when behind", "",
          _md_table(rt), "",
          "Concentrated = 1-2 names with vol >= 60%; consensus-like = correlation to the consensus "
          ">= 0.8; low vol = portfolio vol <= 25%. `rule_says` applies the rule (de-risk if my score "
          "is above the median estimated field max); `model_says` is what the simulation prefers. "
          "Where they disagree, follow the simulation.", "",
          "![winning score](winning_score_hist.png)", ""]
    return "\n".join(L)


def stress_markdown(tab: pd.DataFrame) -> str:
    t = tab.copy()
    for col in t.columns:
        if "P(win)" in col or col == "random entrant":
            t[col] = t[col].map(lambda x: _pct(x, 2))
    t["winning score median"] = t["winning score median"].map(lambda x: f"{x:.3f}")
    for col in [c for c in t.columns if c.endswith(" rank")]:
        t[col] = t[col].map(lambda x: "" if pd.isna(x) else f"#{int(x)}")
    return "\n".join([
        "# Stress tests - period 1 (full search per variant)", "",
        "Each row re-runs the candidate search and validation with a different field. "
        "P(win) = P(win at Dec 18) with the switch-if-leading policy; tracked portfolios use the "
        "search-set scenarios (same returns in every row, common random numbers).", "",
        _md_table(t), ""])
