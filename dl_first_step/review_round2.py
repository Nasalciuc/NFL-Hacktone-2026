"""Checks requested in the second review round. All of them are post-hoc (after the pre-registered tests).

Usage: python review_round2.py DATA_DIR OUT_DIR
Writes OUT_DIR/review_round2.json and prints a log.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import patsy
import polars as pl
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import optimize, special, stats
from statsmodels.discrete.conditional_models import ConditionalLogit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import KEY, REP, anchored_measures, parse_time, read, split_half

DATA, OUT = sys.argv[1], sys.argv[2]
RNG = np.random.default_rng(2027)
B = 5000
R = {}


def log(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------ data (same rules as tests.py, rushers only)
plays = pl.read_parquet(os.path.join(OUT, "game_rush_plays.parquet"))
games = read(DATA, "games.csv")
players = read(DATA, "players.csv")
comb = pl.read_parquet(os.path.join(OUT, "combine_dl_players.parquet"))
elig = (plays.filter(pl.col("stance_start") & pl.col("lined_up_position").is_in(["EDGE", "INTERIOR_LINE"])
                     & (pl.col("play_nullified_by_penalty") == "N") & (pl.col("blitzing") == True))
        .join(games.select("game_id", "home_team_abbr"), on="game_id")
        .with_columns(pl.when(pl.col("team_abbr") == pl.col("home_team_abbr"))
                      .then(pl.col("pre_snap_home_score") - pl.col("pre_snap_visitor_score"))
                      .otherwise(pl.col("pre_snap_visitor_score") - pl.col("pre_snap_home_score")).alias("score_diff_def"),
                      (pl.col("lined_up_position") == "EDGE").cast(pl.Float64).alias("edge"),
                      pl.col("pressure").cast(pl.Float64).alias("pressure_f")))
rare = elig.group_by("offense_formation").len().filter(pl.col("len") < 100)["offense_formation"]
elig = elig.with_columns(pl.when(pl.col("offense_formation").is_null() | pl.col("offense_formation").is_in(rare.drop_nulls().implode()))
                         .then(pl.lit("OTHER")).otherwise(pl.col("offense_formation")).alias("offense_formation"))


# ------------------------------------------------------------------ helpers
def value_at(df, keys, anchor, dt, col="s"):
    """Value of `col` at t_on + dt, interpolated between the two frames around it."""
    d = (df.select(keys + ["t", col]).join(anchor.select(keys + ["t_on"]), on=keys)
         .with_columns((pl.col("t") - pl.col("t_on") - dt).alias("u")))
    after = d.filter(pl.col("u") >= 0).group_by(keys).agg(pl.col("u").min().alias("ua"), pl.col(col).sort_by("u").first().alias("va"))
    before = d.filter(pl.col("u") < 0).group_by(keys).agg(pl.col("u").max().alias("ub"),
                                                          pl.col(col).sort_by("u", descending=True).first().alias("vb"))
    j = after.join(before, on=keys)
    return j.select(keys + [(pl.col("vb") - pl.col("ub") / (pl.col("ua") - pl.col("ub")) * (pl.col("va") - pl.col("vb"))).alias("v_at")])


def boot_ci(fn, n, b=B):
    vals = []
    for _ in range(b):
        k = RNG.integers(0, n, n)
        try:
            vals.append(fn(k))
        except Exception:
            pass
    return [float(np.nanpercentile(vals, 2.5)), float(np.nanpercentile(vals, 97.5))]


def pearson_ci(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    r, p = stats.pearsonr(x, y)
    ci = boot_ci(lambda k: np.corrcoef(x[k], y[k])[0, 1], len(x))
    return {"n": int(len(x)), "r": float(r), "ci": ci, "p": float(p)}


def partial_r(x, y, Z):
    def resid(v, Zm):
        Z1 = np.column_stack([np.ones(len(v)), Zm])
        return v - Z1 @ np.linalg.lstsq(Z1, v, rcond=None)[0]
    x, y, Z = np.asarray(x, float), np.asarray(y, float), np.asarray(Z, float)
    r = np.corrcoef(resid(x, Z), resid(y, Z))[0, 1]
    ci = boot_ci(lambda k: np.corrcoef(resid(x[k], Z[k]), resid(y[k], Z[k]))[0, 1], len(x))
    return {"n": int(len(x)), "r": float(r), "ci": ci}


def fmt(c):
    return f"r {c['r']:+.3f} [{c['ci'][0]:+.3f}, {c['ci'][1]:+.3f}] n {c['n']}" + (f" p {c['p']:.4f}" if "p" in c else "")


def fit_prior(k, n):
    nll = lambda p: -np.sum(special.betaln(k + np.exp(p[0]), n - k + np.exp(p[1])) - special.betaln(np.exp(p[0]), np.exp(p[1])))
    return np.exp(optimize.minimize(nll, np.log([2.0, 20.0]), method="Nelder-Mead").x)


def icc1(df, group, value):
    """One-way random-effects ICC for a single trial, unequal group sizes."""
    d = df.select(group, value).drop_nulls()
    g = d.group_by(group).agg(pl.col(value).mean().alias("m"), pl.len().alias("n"), pl.col(value).var(ddof=1).fill_null(0).alias("v"))
    N, k, grand = d.height, g.height, d[value].mean()
    n, m, v = g["n"].to_numpy(), g["m"].to_numpy(), g["v"].to_numpy()
    msb = (n * (m - grand) ** 2).sum() / (k - 1)
    msw = ((n - 1) * v).sum() / (N - k)
    n0 = (N - (n ** 2).sum() / N) / (k - 1)
    return float((msb - msw) / (msb + (n0 - 1) * msw))


def sb(r):
    return 2 * r / (1 + r)


# ------------------------------------------------------------------ 1. short windows, snap speed (needs tracking again)
log("== reading tracking for eligible rushes")
parts = []
for year in (2023, 2024, 2025):
    t = read(DATA, f"game_tracking_{year}.csv", schema_overrides={"time": pl.Utf8, "event": pl.Utf8})
    parts.append(t.join(elig.select(KEY), on=KEY, how="semi"))
tr = parse_time(pl.concat(parts)).sort(KEY + ["time"])
snap = tr.filter(pl.col("event") == "ball_snap").group_by(KEY).agg(pl.col("time").min().alias("snap"))
tr = tr.join(snap, on=KEY).with_columns(((pl.col("time") - pl.col("snap")).dt.total_milliseconds() / 1000).alias("t"))

# speed around the snap: real movement or smoothing?
tr = tr.with_columns(((pl.col("x") - pl.col("x").shift(1).over(KEY)) ** 2 + (pl.col("y") - pl.col("y").shift(1).over(KEY)) ** 2).sqrt().alias("step"))
around = (tr.filter(pl.col("t").is_between(-0.5, 0.3)).group_by(pl.col("t").round(1).alias("t"))
          .agg(pl.col("s").median().round(3).alias("s_median"), (pl.col("step") / 0.1).median().round(3).alias("step_speed_median"),
               (pl.col("s") > 1).mean().round(3).alias("share_s_over_1")).sort("t"))
log("== speed around the snap: reported speed vs speed from position change (median, yd/s)")
log(around)
R["snap_speed"] = around.to_dicts()

post = tr.filter(pl.col("t") >= 0)
g05 = anchored_measures(post, KEY, 0.5, suffix="_05")
g_acc = value_at(post, KEY, g05.rename({"t_on_05": "t_on"}), 0.2).rename({"v_at": "s_02"})
gshort = g05.join(g_acc, on=KEY, how="left").with_columns(((pl.col("s_02") - 1.0) / 0.2).alias("acc_02"))
elig = elig.join(gshort.select(KEY + ["burst_05", "acc_02"]), on=KEY, how="left")

cmb = read(DATA, "combine_results.csv")
ct = read(DATA, "combine_tracking.csv", schema_overrides={"time": pl.Utf8})
ct = (parse_time(ct).join(cmb.filter(pl.col("combine_position") == "DL").select("nfl_id"), on="nfl_id")
      .filter((pl.col("entity_type") == "PLAYER") & (pl.col("drill_name") == "FORTY_YARD_DASH")).sort(REP + ["time"])
      .with_columns(((pl.col("time") - pl.col("time").first().over(REP)).dt.total_milliseconds() / 1000).alias("t")))
c05 = anchored_measures(ct, REP, 0.5, suffix="_05")
c_acc = value_at(ct, REP, c05.rename({"t_on_05": "t_on"}), 0.2).rename({"v_at": "s_02"})
creps = (c05.join(c_acc, on=REP, how="left").with_columns(((pl.col("s_02") - 1.0) / 0.2).alias("acc_02"))
         .join(pl.read_parquet(os.path.join(OUT, "combine_reps.parquet")).filter(pl.col("drill_name") == "FORTY_YARD_DASH")
               .select(REP + ["burst_15", "burst_25"]), on=REP, how="left"))
cshort = creps.group_by("nfl_id").agg(pl.col("burst_05").mean().alias("c_burst05"), pl.col("acc_02").mean().alias("c_acc02"))

# ------------------------------------------------------------------ player table, main sample (62)
gp = elig.group_by("nfl_id").agg(
    pl.len().alias("rushes"), pl.col("burst_15").mean().alias("g_burst15"), pl.col("burst_05").mean().alias("g_burst05"),
    pl.col("acc_02").mean().alias("g_acc02"), pl.col("t_react").mean().alias("g_react"),
    pl.col("edge").mean().alias("edge_share"), pl.col("pressure_f").sum().alias("pressures"))
a_all, b_all = fit_prior(gp["pressures"].to_numpy(), gp["rushes"].to_numpy())
gp = gp.with_columns(pl.when(pl.col("edge_share") >= 0.5).then(pl.lit("EDGE")).otherwise(pl.lit("INTERIOR_LINE")).alias("role"))
priors = {}
for role in ("EDGE", "INTERIOR_LINE"):
    s = gp.filter(pl.col("role") == role)
    priors[role] = fit_prior(s["pressures"].to_numpy(), s["rushes"].to_numpy())
gp = gp.with_columns(
    ((pl.col("pressures") + a_all) / (pl.col("rushes") + a_all + b_all)).alias("eb_global"),
    pl.when(pl.col("role") == "EDGE")
    .then((pl.col("pressures") + priors["EDGE"][0]) / (pl.col("rushes") + priors["EDGE"].sum()))
    .otherwise((pl.col("pressures") + priors["INTERIOR_LINE"][0]) / (pl.col("rushes") + priors["INTERIOR_LINE"].sum())).alias("eb_group"))
R["priors"] = {"global_mean": float(a_all / (a_all + b_all)), **{k: float(v[0] / v.sum()) for k, v in priors.items()}}
log("\n== shrinkage targets (prior means of pressure rate):", {k: round(v, 4) for k, v in R["priors"].items()})

full = (gp.filter(pl.col("rushes") >= 50).join(comb, on="nfl_id")
        .join(cshort, on="nfl_id", how="left")
        .join(players.select("nfl_id", "draft_overall_pick", "nfl_position"), on="nfl_id")
        .with_columns(pl.col("draft_overall_pick").fill_null(260).cast(pl.Float64).alias("pick")))
main = full.filter(pl.col("forty_burst15_mean").is_not_null())
log(f"main sample players: {main.height}")

# ------------------------------------------------------------------ 2. who is missing from the 62
log("\n== sample: 98 DL with rushes -> 79 with >= 50 -> 62 with a clean Combine 40")
miss = full.filter(pl.col("forty_burst15_mean").is_null())
R["sample"] = {"dl_with_rushes": gp.height, "ge50": full.height, "main": main.height, "no_clean_forty": miss.height,
               "skipped_forty_officially": int(miss["forty"].is_null().sum())}
log(R["sample"])
comp = {}
for col in ("pick", "eb_global", "g_burst15", "combine_weight", "edge_share", "rushes"):
    a_, b_ = main[col].drop_nulls().to_numpy(), miss[col].drop_nulls().to_numpy()
    p = stats.mannwhitneyu(a_, b_).pvalue
    comp[col] = {"main_median": float(np.median(a_)), "missing_median": float(np.median(b_)), "p": float(p)}
    log(f"   {col:15s} main median {np.median(a_):8.3f}   missing median {np.median(b_):8.3f}   Mann-Whitney p {p:.3f}")
R["missing_vs_main"] = comp

# ------------------------------------------------------------------ 3. reliability: per trial and per player, overall and within role
log("\n== reliability")
elig = elig.with_columns(*[((pl.col(c) - pl.col(c).mean().over("lined_up_position")) / pl.col(c).std().over("lined_up_position")).alias(f"{c}_z")
                           for c in ("burst_15", "burst_05", "acc_02", "t_react")])
rel = {}
for c in ("burst_15", "burst_05", "acc_02", "t_react"):
    row = {}
    n_, r_, _ = split_half(elig, c, 25)
    row["nfl_season_mixed_roles"] = sb(r_)
    n_, r_, _ = split_half(elig, f"{c}_z", 25)
    row["nfl_season_role_adjusted"] = sb(r_)
    for align in ("EDGE", "INTERIOR_LINE"):
        n_, r_, _ = split_half(elig.filter(pl.col("lined_up_position") == align), c, 25)
        row[f"nfl_season_{align}"] = sb(r_)
        row[f"n_{align}"] = n_
    big = elig.filter(pl.col("nfl_id").is_in(gp.filter(pl.col("rushes") >= 50)["nfl_id"].implode()))
    row["nfl_single_play_role_adjusted"] = icc1(big, "nfl_id", f"{c}_z")
    if c != "t_react":
        ccol = {"burst_15": "burst_15", "burst_05": "burst_05", "acc_02": "acc_02"}[c]
        cr = creps.filter(pl.col(ccol).is_not_null())
        n2, r2, _ = split_half(cr, ccol, 1, order="attempt")
        row["combine_single_attempt"] = r2
        row["combine_single_attempt_icc"] = icc1(cr, "nfl_id", ccol)
        row["combine_players_two_attempts"] = n2
        row["combine_mean_of_attempts"] = sb(r2)
    rel[c] = row
    log(f"   {c:9s} " + "  ".join(f"{k} {v:.2f}" if isinstance(v, float) else f"{k} {v}" for k, v in row.items()))
R["reliability"] = rel

# ------------------------------------------------------------------ 4. transfer by window length (Combine vs NFL first step)
log("\n== transfer Combine -> NFL by window (main sample)")
tw = {}
for label, ccol, gcol in (("0.5 yd", "c_burst05", "g_burst05"), ("first 0.2 s (accel.)", "c_acc02", "g_acc02"),
                          ("1.5 yd", "forty_burst15_mean", "g_burst15"), ("2.5 yd", "forty_burst25_mean", None)):
    if gcol is None:
        continue
    d = main.drop_nulls([ccol, gcol])
    res = {"all": pearson_ci(d[ccol], d[gcol]),
           "partial_weight_role": partial_r(d[ccol], d[gcol], np.column_stack([d["combine_weight"], d["edge_share"]]))}
    for role in ("EDGE", "INTERIOR_LINE"):
        dd = d.filter(pl.col("role") == role)
        res[role] = pearson_ci(dd[ccol], dd[gcol])
    tw[label] = res
    log(f"   {label:22s} all {fmt(res['all'])} | after weight+role {fmt(res['partial_weight_role'])}")
    log(f"   {'':22s} edge {fmt(res['EDGE'])} | interior {fmt(res['INTERIOR_LINE'])}")
R["transfer_by_window"] = tw

# ------------------------------------------------------------------ 5. disattenuation of H1
rc = rel["burst_15"]["combine_mean_of_attempts"]
rg = rel["burst_15"]["nfl_season_mixed_roles"]
rg_adj = rel["burst_15"]["nfl_season_role_adjusted"]
h1 = tw["1.5 yd"]
R["disattenuation"] = {
    "ceiling_all": float(np.sqrt(rc * rg)), "r_all_corrected": h1["all"]["r"] / np.sqrt(rc * rg),
    "ci_all_corrected": [v / np.sqrt(rc * rg) for v in h1["all"]["ci"]],
    "ceiling_partial": float(np.sqrt(rc * rg_adj)), "r_partial_corrected": h1["partial_weight_role"]["r"] / np.sqrt(rc * rg_adj),
    "ci_partial_corrected": [v / np.sqrt(rc * rg_adj) for v in h1["partial_weight_role"]["ci"]]}
log("\n== disattenuation (H1):", {k: (round(v, 3) if isinstance(v, float) else [round(x, 3) for x in v]) for k, v in R["disattenuation"].items()})

# ------------------------------------------------------------------ 6. H3: between vs within player, and a pre-contact window
log("\n== H3 decomposed (play level, situation controls, SE clustered by player)")
CTRL = "edge + C(down) + yards_to_go + C(offense_formation) + score_diff_def"


def h3_parts(e, measure):
    d = (e.drop_nulls([measure, "t_react", "down", "yards_to_go", "score_diff_def"])
         .with_columns(((pl.col(measure) - pl.col(measure).mean().over("lined_up_position")) / pl.col(measure).std().over("lined_up_position")).alias("m_z"))
         .with_columns(pl.col("m_z").mean().over("nfl_id").alias("m_b"), (pl.col("m_z") - pl.col("m_z").mean().over("nfl_id")).alias("m_w")))
    pdf = d.select("nfl_id", "pressure_f", "m_z", "m_b", "m_w", "t_react", "edge", "down", "yards_to_go", "offense_formation", "score_diff_def").to_pandas()
    m = smf.logit(f"pressure_f ~ m_w + m_b + t_react + {CTRL}", data=pdf).fit(disp=False, maxiter=500, cov_type="cluster", cov_kwds={"groups": pdf["nfl_id"]})
    assert m.mle_retvals["converged"]
    sd_w = float(pdf["m_w"].std())
    # player fixed effects as dummies (hundreds of plays per player, so the incidental-parameter bias is negligible);
    # players who never created a pressure carry no within-player information and are dropped, as a conditional logit would
    has_var = pdf.groupby("nfl_id")["pressure_f"].transform("max") > 0
    fe = pdf[has_var]
    cl = smf.logit(f"pressure_f ~ m_z + t_react + {CTRL} + C(nfl_id)", data=fe).fit(
        disp=False, maxiter=500, cov_type="cluster", cov_kwds={"groups": fe["nfl_id"]})
    assert cl.mle_retvals["converged"]
    lo, hi = m.conf_int().loc["m_w"]
    out = {"plays": int(m.nobs), "players": int(pdf["nfl_id"].nunique()), "sd_within": sd_w,
           "or_within_per_overall_sd": float(np.exp(m.params["m_w"])), "or_within_ci": [float(np.exp(lo)), float(np.exp(hi))],
           "p_within": float(m.pvalues["m_w"]), "or_within_per_within_sd": float(np.exp(m.params["m_w"] * sd_w)),
           "or_between": float(np.exp(m.params["m_b"])), "p_between": float(m.pvalues["m_b"]),
           "or_between_ci": [float(np.exp(v)) for v in m.conf_int().loc["m_b"]],
           "fixed_effects_or": float(np.exp(cl.params["m_z"])), "fixed_effects_p": float(cl.pvalues["m_z"]),
           "fixed_effects_ci": [float(np.exp(v)) for v in cl.conf_int().loc["m_z"]]}
    log(f"   {measure:9s} within player: OR {out['or_within_per_overall_sd']:.3f} per SD [{out['or_within_ci'][0]:.3f}, {out['or_within_ci'][1]:.3f}] "
        f"p {out['p_within']:.2g} (within-player SD = {sd_w:.2f}) | between players: OR {out['or_between']:.3f} "
        f"[{out['or_between_ci'][0]:.3f}, {out['or_between_ci'][1]:.3f}] p {out['p_between']:.2g} | player fixed effects: OR {out['fixed_effects_or']:.3f} "
        f"[{out['fixed_effects_ci'][0]:.3f}, {out['fixed_effects_ci'][1]:.3f}] p {out['fixed_effects_p']:.2g}  ({out['plays']:,} plays, {out['players']} players)")
    return out


R["H3_decomposed"] = {}
main_ids = main.select("nfl_id")
for label, e in (("main_62", elig.join(main_ids, on="nfl_id", how="semi")), ("all_98", elig)):
    log(f"  sample {label}")
    R["H3_decomposed"][label] = {m_: h3_parts(e, m_) for m_ in ("burst_15", "burst_05", "acc_02")}

# ------------------------------------------------------------------ 7. pressure link by role, with controls and group shrinkage
log("\n== Combine first step vs pressure, by role (exploratory)")
byrole = {}
for role in ("INTERIOR_LINE", "EDGE"):
    d = main.filter(pl.col("role") == role)
    x = d["forty_burst15_mean"].to_numpy()
    out = {"positions": dict(d.group_by("nfl_position").len().rows()),
           "r_global_shrink": pearson_ci(x, d["eb_global"]), "r_group_shrink": pearson_ci(x, d["eb_group"]),
           "spearman_group": float(stats.spearmanr(x, d["eb_group"])[0]), "spearman_p": float(stats.spearmanr(x, d["eb_group"])[1])}
    jk = [np.corrcoef(np.delete(x, i), np.delete(d["eb_group"].to_numpy(), i))[0, 1] for i in range(len(x))]
    out["jackknife_min_max"] = [float(min(jk)), float(max(jk))]
    out["partial_weight"] = partial_r(x, d["eb_group"], d["combine_weight"].to_numpy()[:, None])
    Z = np.column_stack([d["combine_weight"].to_numpy(), (d["nfl_position"] == "NT").cast(pl.Float64).to_numpy()])
    if Z[:, 1].sum() > 0:
        out["partial_weight_nt"] = partial_r(x, d["eb_group"], Z)
    w = d.select(pl.col("eb_group"), pl.col("forty_burst15_mean"), pl.col("combine_weight"),
                 (pl.col("nfl_position") == "NT").cast(pl.Float64).alias("nt")).to_pandas()
    xs = ["forty_burst15_mean", "combine_weight"] + (["nt"] if w["nt"].sum() > 0 else [])
    z = (w - w.mean()) / w.std()
    ols = sm.OLS(z["eb_group"], sm.add_constant(z[xs])).fit(cov_type="HC3")
    out["ols_std_beta"] = float(ols.params["forty_burst15_mean"])
    out["ols_ci"] = [float(v) for v in ols.conf_int().loc["forty_burst15_mean"]]
    out["ols_p"] = float(ols.pvalues["forty_burst15_mean"])
    out["weight_vs_combine_burst_r"] = float(np.corrcoef(x, d["combine_weight"])[0, 1])
    byrole[role] = out
    log(f"   {role}: positions {out['positions']}")
    log(f"      shrunk to global mean {fmt(out['r_global_shrink'])} | to group mean {fmt(out['r_group_shrink'])}")
    log(f"      Spearman {out['spearman_group']:+.3f} (p {out['spearman_p']:.3f}); jackknife r range {out['jackknife_min_max'][0]:+.3f} to {out['jackknife_min_max'][1]:+.3f}")
    log(f"      Combine first step vs weight r {out['weight_vs_combine_burst_r']:+.3f}; partial r after weight {fmt(out['partial_weight'])}"
        + (f"; after weight + NT {fmt(out['partial_weight_nt'])}" if "partial_weight_nt" in out else ""))
    log(f"      OLS (standardized) beta {out['ols_std_beta']:+.3f} [{out['ols_ci'][0]:+.3f}, {out['ols_ci'][1]:+.3f}] p {out['ols_p']:.4f} with {xs[1:]}")
R["pressure_by_role"] = byrole
R["bonferroni_threshold_20_checks"] = 0.05 / 20

# ------------------------------------------------------------------ 8. leave-one-out R2 with bootstrap intervals (main sample)
log("\n== leave-one-out R2 for the NFL first step, with bootstrap 95% intervals over players")
y = main["g_burst15"].to_numpy()
cols = {"role": main["edge_share"].to_numpy(), "weight": main["combine_weight"].to_numpy(), "ten": main["ten_yd_split"].to_numpy(),
        "combine": main["forty_burst15_mean"].to_numpy()}
sets = {"Role (share of snaps on the edge)": ["role"], "Weight": ["weight"], "Official 10-yard split (stopwatch)": ["ten"],
        "Combine first step (tracking)": ["combine"], "Role + weight": ["role", "weight"],
        "Role + weight + 10-yard split": ["role", "weight", "ten"], "Role + weight + Combine first step": ["role", "weight", "combine"]}


def loo_err(yv, X):
    X1 = np.column_stack([np.ones(len(yv)), X])
    H = X1 @ np.linalg.pinv(X1.T @ X1) @ X1.T
    return (yv - H @ yv) / (1 - np.diag(H))


errs = {k: loo_err(y, np.column_stack([cols[c] for c in v])) for k, v in sets.items()}
loo = {}
n = len(y)
idx = RNG.integers(0, n, size=(B, n))
for k, e in errs.items():
    r2 = 1 - (e ** 2).mean() / y.var()
    boots = 1 - (e[idx] ** 2).mean(1) / y[idx].var(1)
    loo[k] = {"r2": float(r2), "ci": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]}
    log(f"   {k:40s} {r2:+.3f} [{loo[k]['ci'][0]:+.3f}, {loo[k]['ci'][1]:+.3f}]")
for a_, b_ in (("Role + weight + Combine first step", "Role + weight"), ("Role + weight + 10-yard split", "Role + weight")):
    diff = ((errs[b_] ** 2) - (errs[a_] ** 2))
    d0 = diff.mean() / y.var()
    bd = diff[idx].mean(1) / y[idx].var(1)
    loo[f"{a_} minus {b_}"] = {"r2": float(d0), "ci": [float(np.percentile(bd, 2.5)), float(np.percentile(bd, 97.5))]}
    log(f"   difference: {a_} vs {b_}: {d0:+.3f} [{np.percentile(bd, 2.5):+.3f}, {np.percentile(bd, 97.5):+.3f}]")
R["loo_r2"] = loo
log(f"   official 10-yd split vs weight, r = {np.corrcoef(cols['ten'], cols['weight'])[0, 1]:.3f}")

with open(os.path.join(OUT, "review_round2.json"), "w") as f:
    json.dump(R, f, indent=2, default=float)
log("\nsaved review_round2.json")
