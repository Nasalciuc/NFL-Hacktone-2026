"""Planned tests H1-H4 from ANALYSIS_PLAN.md (specified before testing), run once.

Usage: python tests.py DATA_DIR OUT_DIR
Reads the parquet files written by game_starts.py and combine_starts.py.
Writes OUT_DIR/tests_results.json and OUT_DIR/check_h1_h4.png.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warnings
from common import eligible_plays, fit_beta_binomial, loo_r2, read

DATA, OUT = sys.argv[1], sys.argv[2]
# --as-written keeps every row with `sack` filled, as the plan first said; the default keeps
# only plays where the player actually rushed (`blitzing` true), see "Abateri" in ANALYSIS_PLAN.md
AS_WRITTEN = "--as-written" in sys.argv
TAG = "as_written" if AS_WRITTEN else "rushers_only"
RNG = np.random.default_rng(2027)
B = 10000
MIN_RUSHES = 50
UNDRAFTED_PICK = 260
results = {}

plays = pl.read_parquet(os.path.join(OUT, "game_rush_plays.parquet"))
comb = pl.read_parquet(os.path.join(OUT, "combine_dl_players.parquet"))
players = read(DATA, "players.csv")
games = read(DATA, "games.csv")

elig = eligible_plays(plays, games, rushers_only=not AS_WRITTEN)
print(f"definition: {TAG}; eligible plays {elig.height:,}, players {elig['nfl_id'].n_unique()}")


# ---------------------------------------------------------------- helpers
def player_table(e):
    return e.group_by("nfl_id").agg(
        pl.len().alias("rushes"),
        pl.col("burst_15").mean().alias("g_burst15"), pl.col("burst_25").mean().alias("g_burst25"),
        pl.col("acc_1to3").mean().alias("g_acc"), pl.col("t_react").mean().alias("g_react"),
        pl.col("edge").mean().alias("edge_share"), pl.col("pressure_f").sum().alias("pressures"))


def build(e, min_rushes):
    gp = player_table(e)
    a, b = fit_beta_binomial(gp["pressures"].to_numpy(), gp["rushes"].to_numpy())
    gp = gp.with_columns(((pl.col("pressures") + a) / (pl.col("rushes") + a + b)).alias("eb_rate"),
                         (pl.col("pressures") / pl.col("rushes")).alias("raw_rate"))
    df = (gp.filter(pl.col("rushes") >= min_rushes)
          .join(comb, on="nfl_id").filter(pl.col("forty_burst15_mean").is_not_null())
          .join(players.select("nfl_id", "draft_overall_pick", "nfl_position", "display_name"), on="nfl_id")
          .with_columns(pl.col("draft_overall_pick").fill_null(UNDRAFTED_PICK).cast(pl.Float64).log().alias("log_pick")))
    return df, (a, b)


def boot_r(x, y, rank=False):
    n = len(x)
    idx = RNG.integers(0, n, size=(B, n))
    xs, ys = x[idx], y[idx]
    if rank:
        xs, ys = stats.rankdata(xs, axis=1), stats.rankdata(ys, axis=1)
    xm, ym = xs - xs.mean(1, keepdims=True), ys - ys.mean(1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (xm * ym).sum(1) / np.sqrt((xm ** 2).sum(1) * (ym ** 2).sum(1))
    undefined = int(np.isnan(r).sum())
    if undefined:
        print(f"   note: {undefined} of {B} bootstrap replicates were undefined (no variation) and were dropped")
    return np.nanpercentile(r, [2.5, 97.5])


def corr_block(df, a, b, rank=False):
    d = df.select(a, b).drop_nulls()
    x, y = d[a].to_numpy(), d[b].to_numpy()
    if rank:
        r, p = stats.spearmanr(x, y)
    else:
        r, p = stats.pearsonr(x, y)
    lo, hi = boot_r(x, y, rank)
    return {"n": len(x), "r": float(r), "ci": [float(lo), float(hi)], "p": float(p)}


def ols(df, y, xs, robust="HC3"):
    d = df.select([y] + xs).drop_nulls().to_pandas()
    z = (d - d.mean()) / d.std()
    m = sm.OLS(d[y], sm.add_constant(d[xs])).fit(cov_type=robust)
    mz = sm.OLS(z[y], sm.add_constant(z[xs])).fit(cov_type=robust)
    return m, mz, d


def boot_coef(d, y, xs, name):
    Y, X = d[y].to_numpy(), np.column_stack([np.ones(len(d))] + [d[c].to_numpy() for c in xs])
    j = 1 + xs.index(name)
    n = len(Y)
    out = np.empty(B // 2)
    for i in range(B // 2):
        k = RNG.integers(0, n, n)
        out[i] = np.linalg.lstsq(X[k], Y[k], rcond=None)[0][j]
    return np.percentile(out, [2.5, 97.5])


def fmt(c):
    return f"r {c['r']:+.3f}  95% CI [{c['ci'][0]:+.3f}, {c['ci'][1]:+.3f}]  p {c['p']:.4f}  n {c['n']}"


def logit_h3(e, measure="burst_15", extra=""):
    # `blitzing` is not a covariate: for DL rows it says whether this player rushed, not whether the defense blitzed
    d = (e.drop_nulls([measure, "t_react", "down", "yards_to_go", "score_diff_def"])
         .with_columns(((pl.col(measure) - pl.col(measure).mean().over("lined_up_position"))
                        / pl.col(measure).std().over("lined_up_position")).alias("m_z")))
    pdf = d.select("nfl_id", "pressure_f", "m_z", "t_react", "edge", "down", "yards_to_go",
                   "offense_formation", "score_diff_def").to_pandas()
    edge_term = " + edge" if pdf["edge"].nunique() > 1 else ""
    f = f"pressure_f ~ m_z + t_react{edge_term} + C(down) + yards_to_go + C(offense_formation) + score_diff_def{extra}"
    m = smf.logit(f, data=pdf).fit(disp=False, maxiter=500, cov_type="cluster", cov_kwds={"groups": pdf["nfl_id"]})
    if not m.mle_retvals.get("converged", False):
        raise RuntimeError(f"logit did not converge: {f}")
    lo_hi = m.conf_int().loc["m_z"].to_numpy()
    fast, slow = pdf.copy(), pdf.copy()
    fast["m_z"], slow["m_z"] = -1.0, 1.0
    return {"plays": int(m.nobs), "players": int(pdf["nfl_id"].nunique()), "coef": float(m.params["m_z"]),
            "or": float(np.exp(m.params["m_z"])), "or_ci": [float(np.exp(lo_hi[0])), float(np.exp(lo_hi[1]))],
            "p": float(m.pvalues["m_z"]), "t_react_coef": float(m.params["t_react"]), "t_react_p": float(m.pvalues["t_react"]),
            "rate_fast_1sd": float(m.predict(fast).mean()), "rate_slow_1sd": float(m.predict(slow).mean()),
            "rate_observed": float(pdf["pressure_f"].mean())}


def fmt_h3(h):
    return (f"OR per +1 SD slower {h['or']:.3f} [{h['or_ci'][0]:.3f}, {h['or_ci'][1]:.3f}]  p {h['p']:.4g}  "
            f"pressure at 1 SD faster {h['rate_fast_1sd']:.3f} vs 1 SD slower {h['rate_slow_1sd']:.3f}  "
            f"t_react coef {h['t_react_coef']:+.2f} (p {h['t_react_p']:.3g})  plays {h['plays']:,} players {h['players']}")


# ---------------------------------------------------------------- main sample
df, prior = build(elig, MIN_RUSHES)
print(f"main sample: {df.height} players; beta-binomial prior a={prior[0]:.2f} b={prior[1]:.2f} "
      f"(prior mean {prior[0] / sum(prior):.3f}); by class {df.group_by('draft_year').len().sort('draft_year').rows()}")
results["sample"] = {"definition": TAG, "players": df.height, "eligible_plays": elig.height}

# H1
h1 = corr_block(df, "forty_burst15_mean", "g_burst15")
m, mz, _ = ols(df, "g_burst15", ["forty_burst15_mean", "combine_weight", "edge_share"])
h1["adjusted_beta_std"] = float(mz.params["forty_burst15_mean"])
h1["adjusted_ci_std"] = [float(v) for v in mz.conf_int().loc["forty_burst15_mean"]]
h1["adjusted_p"] = float(mz.pvalues["forty_burst15_mean"])
results["H1"] = h1
print("\n=== H1 transfer: Combine burst_15 vs in-game burst_15")
print("  ", fmt(h1))
print(f"   controlled for weight and EDGE share: standardized beta {h1['adjusted_beta_std']:+.3f} "
      f"[{h1['adjusted_ci_std'][0]:+.3f}, {h1['adjusted_ci_std'][1]:+.3f}] p {h1['adjusted_p']:.4f}")
print("   full model (standardized):", {k: round(v, 3) for k, v in mz.params.items()})

# H2
h2r = corr_block(df, "forty_burst15_mean", "g_react")
y = df["g_burst15"].to_numpy()
r2_burst = loo_r2(y, df["forty_burst15_mean"].to_numpy())
r2_ten = loo_r2(y, df["ten_yd_split"].to_numpy())
r2_both = loo_r2(y, np.column_stack([df["forty_burst15_mean"].to_numpy(), df["ten_yd_split"].to_numpy()]))
ten_vs_game = corr_block(df, "ten_yd_split", "g_burst15")
results["H2"] = {"combine_burst_vs_reaction": h2r, "loo_r2_combine_burst": float(r2_burst), "loo_r2_ten_yd": float(r2_ten),
                 "loo_r2_both": float(r2_both), "ten_yd_vs_game_burst": ten_vs_game}
print("\n=== H2 specificity (descriptive)")
print("   Combine burst_15 vs in-game reaction to snap:", fmt(h2r))
print("   official 10-yd split vs in-game burst_15:     ", fmt(ten_vs_game))
print(f"   leave-one-out R2 for in-game burst_15: tracked burst {r2_burst:+.3f}, 10-yd split {r2_ten:+.3f}, both {r2_both:+.3f}")

# H3
main_ids = df.select("nfl_id")
h3 = logit_h3(elig.join(main_ids, on="nfl_id", how="semi"))
results["H3"] = h3
print("\n=== H3 in-game first step vs pressure (play level, main-sample players)")
print("  ", fmt_h3(h3))

# H4
xs = ["forty_burst15_mean", "log_pick", "ten_yd_split", "edge_share"]
m4, m4z, d4 = ols(df, "eb_rate", xs)
ci4 = boot_coef(d4, "eb_rate", xs, "forty_burst15_mean")
h4 = {"n": int(m4.nobs), "coef": float(m4.params["forty_burst15_mean"]), "coef_ci_boot": [float(v) for v in ci4],
      "p": float(m4.pvalues["forty_burst15_mean"]), "beta_std": float(m4z.params["forty_burst15_mean"]),
      "sd_combine_burst": float(d4["forty_burst15_mean"].std()), "params": {k: float(v) for k, v in m4.params.items()},
      "pvalues": {k: float(v) for k, v in m4.pvalues.items()}, "r2": float(m4.rsquared),
      "unadjusted": corr_block(df, "forty_burst15_mean", "eb_rate")}
h4["pp_per_sd"] = 100 * h4["coef"] * h4["sd_combine_burst"]
results["H4"] = h4
print("\n=== H4 Combine burst_15 -> pressure rate, beyond draft slot and 10-yd split (player level)")
print(f"   coef {h4['coef']:+.4f} per second; bootstrap 95% CI [{ci4[0]:+.4f}, {ci4[1]:+.4f}]; p (HC3) {h4['p']:.4f}; "
      f"standardized beta {h4['beta_std']:+.3f}; n {h4['n']}; model R2 {h4['r2']:.3f}")
print(f"   = {h4['pp_per_sd']:+.2f} percentage points of pressure rate per +1 SD slower Combine burst")
print("   other terms:", {k: (round(v, 4), round(h4['pvalues'][k], 4)) for k, v in h4["params"].items()})
print("   unadjusted:", fmt(h4["unadjusted"]))

# Holm
p = {"H1": h1["p"], "H3": h3["p"], "H4": h4["p"]}
order = sorted(p, key=p.get)
holm, running = {}, 0.0
for i, k in enumerate(order):
    running = max(running, min(1.0, (len(order) - i) * p[k]))
    holm[k] = running
results["holm"] = holm
print("\n=== Holm-adjusted p-values (primary tests):", {k: round(v, 4) for k, v in holm.items()})

# ---------------------------------------------------------------- robustness (pre-registered list)
rob = {}
print("\n=== robustness")
for k in (30, 100):
    dk, _ = build(elig, k)
    rob[f"H1_min{k}"] = corr_block(dk, "forty_burst15_mean", "g_burst15")
    mk, _, dd = ols(dk, "eb_rate", xs)
    rob[f"H4_min{k}"] = {"n": int(mk.nobs), "coef": float(mk.params["forty_burst15_mean"]), "p": float(mk.pvalues["forty_burst15_mean"])}
    print(f"   min {k} rushes  H1 {fmt(rob[f'H1_min{k}'])}")
    print(f"   min {k} rushes  H4 coef {rob[f'H4_min{k}']['coef']:+.4f} p {rob[f'H4_min{k}']['p']:.4f} n {rob[f'H4_min{k}']['n']}")
for comb_col, game_col, label in (("forty_burst25_mean", "g_burst25", "burst_25"), ("forty_acc_mean", "g_acc", "acc_1to3")):
    rob[f"H1_{label}"] = corr_block(df, comb_col, game_col)
    xs_alt = [comb_col, "log_pick", "ten_yd_split", "edge_share"]
    ma, _, _ = ols(df, "eb_rate", xs_alt)
    rob[f"H4_{label}"] = {"coef": float(ma.params[comb_col]), "p": float(ma.pvalues[comb_col])}
    rob[f"H3_{label}"] = logit_h3(elig.join(main_ids, on="nfl_id", how="semi"), measure=game_col.replace("g_", "").replace("burst25", "burst_25").replace("acc", "acc_1to3"))
    print(f"   {label}: H1 {fmt(rob[f'H1_{label}'])}")
    print(f"   {label}: H3 {fmt_h3(rob[f'H3_{label}'])}")
    print(f"   {label}: H4 coef {rob[f'H4_{label}']['coef']:+.4f} p {rob[f'H4_{label}']['p']:.4f}")
rob["H1_spearman"] = corr_block(df, "forty_burst15_mean", "g_burst15", rank=True)
rob["H4_spearman_unadjusted"] = corr_block(df, "forty_burst15_mean", "eb_rate", rank=True)
print(f"   Spearman H1 {fmt(rob['H1_spearman'])}")
print(f"   Spearman H4 (unadjusted) {fmt(rob['H4_spearman_unadjusted'])}")
for yr in (2023, 2024, 2025):
    dy = df.filter(pl.col("draft_year") == yr)
    rob[f"H1_class{yr}"] = corr_block(dy, "forty_burst15_mean", "g_burst15")
    rob[f"H4_class{yr}_unadjusted"] = corr_block(dy, "forty_burst15_mean", "eb_rate")
    print(f"   class {yr}: H1 {fmt(rob[f'H1_class{yr}'])} | H4 unadjusted {fmt(rob[f'H4_class{yr}_unadjusted'])}")
for label, cond in (("mostly_EDGE", pl.col("edge_share") >= 0.5), ("mostly_INTERIOR", pl.col("edge_share") < 0.5)):
    ds = df.filter(cond)
    rob[f"H1_{label}"] = corr_block(ds, "forty_burst15_mean", "g_burst15")
    rob[f"H4_{label}_unadjusted"] = corr_block(ds, "forty_burst15_mean", "eb_rate")
    print(f"   {label}: H1 {fmt(rob[f'H1_{label}'])} | H4 unadjusted {fmt(rob[f'H4_{label}_unadjusted'])}")
for align in ("EDGE", "INTERIOR_LINE"):
    rob[f"H3_{align}"] = logit_h3(elig.join(main_ids, on="nfl_id", how="semi").filter(pl.col("lined_up_position") == align))
    print(f"   H3 only {align}: {fmt_h3(rob[f'H3_{align}'])}")
no_unblocked = elig.filter(pl.col("unblocked_pressure") != True)
rob["H3_no_unblocked"] = logit_h3(no_unblocked.join(main_ids, on="nfl_id", how="semi"))
print(f"   H3 without unblocked: {fmt_h3(rob['H3_no_unblocked'])}")
dnu, _ = build(no_unblocked, MIN_RUSHES)
mnu, _, _ = ols(dnu, "eb_rate", xs)
rob["H4_no_unblocked"] = {"n": int(mnu.nobs), "coef": float(mnu.params["forty_burst15_mean"]), "p": float(mnu.pvalues["forty_burst15_mean"])}
print(f"   H4 without unblocked: coef {rob['H4_no_unblocked']['coef']:+.4f} p {rob['H4_no_unblocked']['p']:.4f} n {rob['H4_no_unblocked']['n']}")
print("   H3 + dropback_duration: not possible, the column is empty for every DL row")
rob["H3_all_players"] = logit_h3(elig)
print(f"   H3 all DL players: {fmt_h3(rob['H3_all_players'])}")
results["robustness"] = rob

# ---------------------------------------------------------------- descriptive: quartiles of Combine burst
with warnings.catch_warnings():
    # qcut is deprecated in polars 2.x; kept so the quartile split stays identical to the first run
    warnings.simplefilter("ignore", DeprecationWarning)
    qs = df.with_columns(pl.col("forty_burst15_mean").qcut(4, labels=["Q1 fastest", "Q2", "Q3", "Q4 slowest"]).alias("q"))
desc = qs.group_by("q").agg(pl.len().alias("players"), pl.col("forty_burst15_mean").mean().round(3).alias("combine_burst15"),
                            pl.col("g_burst15").mean().round(3).alias("game_burst15"), pl.col("eb_rate").mean().round(4).alias("eb_pressure_rate"),
                            pl.col("draft_overall_pick").mean().round(1).alias("mean_pick_drafted"),
                            pl.col("combine_weight").mean().round(1).alias("weight")).sort("q")
print("\n=== descriptive: quartiles of Combine burst_15 (main sample)")
print(desc)
results["quartiles"] = desc.to_dicts()

with open(os.path.join(OUT, f"tests_results_{TAG}.json"), "w") as f:
    json.dump(results, f, indent=2, default=str)

# ---------------------------------------------------------------- check figure
fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))
for a, (yc, title) in zip(ax, (("g_burst15", "H1: in-game burst_15 (s)"), ("eb_rate", "H4: pressure rate (shrunk)"))):
    x, yv = df["forty_burst15_mean"].to_numpy(), df[yc].to_numpy()
    colors = np.where(df["edge_share"].to_numpy() >= 0.5, "#2a78d6", "#eb6834")  # same palette as the writeup figures
    a.scatter(x, yv, c=colors, s=26, alpha=0.8)
    k, c0 = np.polyfit(x, yv, 1)
    xx = np.linspace(x.min(), x.max(), 50)
    a.plot(xx, k * xx + c0, color="black", lw=1)
    a.set_xlabel("Combine 40-yard burst_15 (s, lower = faster)")
    a.set_title(f"{title}   r = {np.corrcoef(x, yv)[0, 1]:+.2f}")
ax[0].text(0.02, 0.97, "blue = mostly edge, orange = mostly interior", transform=ax[0].transAxes, va="top", fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(OUT, f"check_h1_h4_{TAG}.png"), dpi=110)
print(f"\nsaved tests_results_{TAG}.json and check_h1_h4_{TAG}.png")
