"""Checks requested in the fourth review round. All post-hoc (after the planned tests).

1. Why the penalty filter removes no plays.
2. H3 in football units: the SD in seconds, effects in percentage points, pseudo R2.
3. H3 without quick passes (released under 2.5 s), a rough proxy for plays where the rush had no time.
4. Hierarchical models as a sensitivity check: linear mixed model for H1, Bayesian mixed logistic for H4.
5. Exploratory, interior only: momentum at the Combine (weight x mean speed over the first yards).

Usage: python review_round4.py DATA_DIR OUT_DIR
Writes OUT_DIR/review_round4.json and prints a log.
"""
import json
import os
import sys

import numpy as np
import polars as pl
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import special, stats
from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import KEY, boot_ci, eligible_plays, fit_beta_binomial, parse_time, partial_r, read

DATA, OUT = sys.argv[1], sys.argv[2]
RNG = np.random.default_rng(2027)
B = 5000
R = {}
QUICK = 2.5  # seconds from snap to release; below this the rush had little time

plays = pl.read_parquet(os.path.join(OUT, "game_rush_plays.parquet"))
games = read(DATA, "games.csv")
players = read(DATA, "players.csv")
cmb = read(DATA, "combine_results.csv")
comb = pl.read_parquet(os.path.join(OUT, "combine_dl_players.parquet"))

# ------------------------------------------------------------------ 1. the penalty filter
pp = read(DATA, "player_play.csv", schema_overrides={"game_clock": pl.Utf8})
dl_rows = pp.join(cmb.filter(pl.col("combine_position") == "DL").select("nfl_id"), on="nfl_id")
nullified = dl_rows.filter(pl.col("play_nullified_by_penalty") == "Y")
R["penalty"] = {"dl_rows_nullified": nullified.height, "dl_rows_total": dl_rows.height,
                "nullified_with_sack_field": int(nullified["sack"].is_not_null().sum()),
                "rush_rows_in_sample_nullified": int((plays["play_nullified_by_penalty"] == "Y").sum())}
print("== penalty filter:", R["penalty"])
print("   plays nullified by a penalty carry no pass-rush fields in player_play, so the pass-rush definition already drops them")

# ------------------------------------------------------------------ main sample (same rules as tests.py)
elig = eligible_plays(plays, games)
gp = elig.group_by("nfl_id").agg(pl.len().alias("rushes"), pl.col("edge").mean().alias("edge_share"),
                                 pl.col("pressure_f").sum().alias("pressures"), pl.col("burst_15").mean().alias("g_burst15"))
gp = gp.with_columns(pl.when(pl.col("edge_share") >= 0.5).then(pl.lit("EDGE")).otherwise(pl.lit("INTERIOR_LINE")).alias("role"))
pri = {r: fit_beta_binomial(gp.filter(pl.col("role") == r)["pressures"], gp.filter(pl.col("role") == r)["rushes"]) for r in ("EDGE", "INTERIOR_LINE")}
gp = gp.with_columns(pl.when(pl.col("role") == "EDGE").then((pl.col("pressures") + pri["EDGE"][0]) / (pl.col("rushes") + pri["EDGE"].sum()))
                     .otherwise((pl.col("pressures") + pri["INTERIOR_LINE"][0]) / (pl.col("rushes") + pri["INTERIOR_LINE"].sum())).alias("eb_group"))
main = (gp.filter(pl.col("rushes") >= 50).join(comb, on="nfl_id").filter(pl.col("forty_burst15_mean").is_not_null())
        .join(players.select("nfl_id", "draft_overall_pick"), on="nfl_id")
        .with_columns(pl.col("draft_overall_pick").fill_null(260).cast(pl.Float64).log().alias("log_pick")))
z = lambda c: (pl.col(c) - pl.col(c).mean()) / pl.col(c).std()
main = main.with_columns(z("forty_burst15_mean").alias("c_z"), z("combine_weight").alias("w_z"), z("log_pick").alias("pick_z"),
                         z("ten_yd_split").alias("ten_z"))
mp = elig.join(main.select("nfl_id", "c_z", "w_z", "pick_z", "ten_z"), on="nfl_id")
print(f"main sample: {main.height} players, {mp.height:,} rushes")

FORMULA = "pressure_f ~ m_z + t_react + edge + C(down) + yards_to_go + C(offense_formation) + score_diff_def"


def h3_frame(e):
    return (e.drop_nulls(["burst_15", "t_react", "down", "yards_to_go", "score_diff_def"])
            .with_columns(pl.col("burst_15").mean().over("lined_up_position").alias("mu"),
                          pl.col("burst_15").std().over("lined_up_position").alias("sd"))
            .with_columns(((pl.col("burst_15") - pl.col("mu")) / pl.col("sd")).alias("m_z")))


def fit_h3(d):
    pdf = d.select("nfl_id", "pressure_f", "m_z", "t_react", "edge", "down", "yards_to_go", "offense_formation",
                   "score_diff_def", "sd", "lined_up_position").to_pandas()
    m = smf.logit(FORMULA, data=pdf).fit(disp=False, maxiter=500, cov_type="cluster", cov_kwds={"groups": pdf["nfl_id"]})
    if not m.mle_retvals.get("converged", False):
        raise RuntimeError("H3 logit did not converge")
    return m, pdf


def predicted(m, pdf, **shift):
    q = pdf.copy()
    for col, val in shift.items():
        q[col] = val(q) if callable(val) else val
    return float(m.predict(q).mean())


# ------------------------------------------------------------------ 2. H3 in football units
d3 = h3_frame(mp)
m3, pdf3 = fit_h3(d3)
sd_by_role = dict(d3.group_by("lined_up_position").agg(pl.col("sd").first()).rows())
base = predicted(m3, pdf3)
units = {
    "plays": int(m3.nobs), "pseudo_r2_mcfadden": float(m3.prsquared), "observed_rate": float(pdf3["pressure_f"].mean()),
    "sd_seconds": {k: float(v) for k, v in sd_by_role.items()},
    "rate_play_1sd_faster": predicted(m3, pdf3, m_z=-1.0), "rate_play_1sd_slower": predicted(m3, pdf3, m_z=1.0),
    "pp_if_every_play_0p1s_faster": 100 * (predicted(m3, pdf3, m_z=lambda q: q["m_z"] - 0.1 / q["sd"]) - base),
    "pp_if_reaction_0p1s_faster": 100 * (predicted(m3, pdf3, t_react=lambda q: q["t_react"] - 0.1) - base),
    "baseline_predicted_rate": base,
}
rev2 = json.load(open(os.path.join(OUT, "review_round2.json")))
fe = rev2["H3_decomposed"]["main_62"]["burst_15"]
logit_base = special.logit(units["observed_rate"])
per_01 = {}
for k, sdv in sd_by_role.items():
    step = np.log(fe["fixed_effects_or"]) * (0.1 / sdv)
    per_01[k] = 100 * (units["observed_rate"] - special.expit(logit_base + step))
units["within_player_pp_per_0p1s_faster_at_mean_rate"] = per_01
R["h3_units"] = units
print(f"\n== H3 in football units ({units['plays']:,} rushes, 62 players)")
print(f"   one play-level SD = {units['sd_seconds']['EDGE']:.3f} s on the edge, {units['sd_seconds']['INTERIOR_LINE']:.3f} s on the interior")
print(f"   a play 1 SD faster: {100 * units['rate_play_1sd_faster']:.1f}% pressure; 1 SD slower: {100 * units['rate_play_1sd_slower']:.1f}%")
print(f"   every play 0.1 s faster in the first step: {units['pp_if_every_play_0p1s_faster']:+.2f} points of pressure")
print(f"   reaction 0.1 s faster on every play: {units['pp_if_reaction_0p1s_faster']:+.2f} points")
print(f"   within the same player, 0.1 s faster than his own average (at the mean rate): "
      + ", ".join(f"{k} {v:+.2f} points" for k, v in per_01.items()))
print(f"   McFadden pseudo R2 = {units['pseudo_r2_mcfadden']:.3f} (a single play is mostly unexplained)")

# ------------------------------------------------------------------ 3. without quick passes
parts = []
for year in (2023, 2024, 2025):
    t = read(DATA, f"game_tracking_{year}.csv", schema_overrides={"time": pl.Utf8, "event": pl.Utf8})
    parts.append(t.join(mp.select(KEY), on=KEY, how="semi").filter(pl.col("event").is_in(["ball_snap", "pass_forward"])))
ev = parse_time(pl.concat(parts))
snap = ev.filter(pl.col("event") == "ball_snap").group_by(KEY).agg(pl.col("time").min().alias("snap"))
pf = ev.filter(pl.col("event") == "pass_forward").group_by(KEY).agg(pl.col("time").min().alias("pf"))
rel = snap.join(pf, on=KEY, how="left").select(KEY + [((pl.col("pf") - pl.col("snap")).dt.total_milliseconds() / 1000).alias("t_throw")])
dq = d3.join(rel, on=KEY, how="left")
quick = dq.filter(pl.col("t_throw").is_not_null() & (pl.col("t_throw") < QUICK))
kept = dq.filter(pl.col("t_throw").is_null() | (pl.col("t_throw") >= QUICK))
mq, pq = fit_h3(kept)
R["h3_without_quick_passes"] = {
    "threshold_s": QUICK, "quick_share": quick.height / dq.height, "pressure_rate_quick": float(quick["pressure_f"].mean()),
    "pressure_rate_kept": float(kept["pressure_f"].mean()), "plays": int(mq.nobs),
    "or_per_sd_slower": float(np.exp(mq.params["m_z"])), "or_ci": [float(np.exp(v)) for v in mq.conf_int().loc["m_z"]],
    "p": float(mq.pvalues["m_z"]), "rate_1sd_faster": predicted(mq, pq, m_z=-1.0), "rate_1sd_slower": predicted(mq, pq, m_z=1.0)}
q = R["h3_without_quick_passes"]
print(f"\n== H3 without passes released under {QUICK} s: {100 * q['quick_share']:.1f}% of rushes dropped "
      f"(pressure on them {100 * q['pressure_rate_quick']:.1f}%, on the rest {100 * q['pressure_rate_kept']:.1f}%)")
print(f"   OR {q['or_per_sd_slower']:.3f} {[round(v, 3) for v in q['or_ci']]} p {q['p']:.2g}; "
      f"1 SD faster {100 * q['rate_1sd_faster']:.1f}% vs slower {100 * q['rate_1sd_slower']:.1f}%")

# ------------------------------------------------------------------ 4. hierarchical models (sensitivity)
pdf1 = mp.drop_nulls("burst_15").sort("nfl_id", "game_id", "play_id").select("nfl_id", "burst_15", "c_z", "w_z", "edge").to_pandas()
mixed = {}
# the player variance is small next to play-to-play noise (about 0.03 s vs 0.23 s), so statsmodels flags it as near the
# boundary; L-BFGS can collapse it to zero, Powell and Nelder-Mead agree on the interior solution used here
for label, f in (("weight and play alignment", "burst_15 ~ c_z + w_z + edge"), ("weight only", "burst_15 ~ c_z + w_z")):
    mm = smf.mixedlm(f, pdf1, groups=pdf1["nfl_id"]).fit(reml=True, method="powell")
    mixed[label] = {"coef_s_per_sd": float(mm.params["c_z"]), "ci": [float(v) for v in mm.conf_int().loc["c_z"]], "p": float(mm.pvalues["c_z"]),
                    "player_sd_s": float(np.sqrt(mm.cov_re.iloc[0, 0])), "residual_sd_s": float(np.sqrt(mm.scale))}
pl_ = main.select("g_burst15", "c_z", "w_z", "edge_share").to_pandas()
two = smf.ols("g_burst15 ~ c_z + w_z + edge_share", pl_).fit(cov_type="HC3")
mixed["two-step, for comparison"] = {"coef_s_per_sd": float(two.params["c_z"]), "ci": [float(v) for v in two.conf_int().loc["c_z"]],
                                     "p": float(two.pvalues["c_z"])}
pdf4 = mp.sort("nfl_id", "game_id", "play_id").select("nfl_id", "pressure_f", "c_z", "pick_z", "ten_z", "edge").to_pandas()
F4 = "pressure_f ~ c_z + pick_z + ten_z + edge"
# random intercept per player. With the default settings the optimizer's convergence flag depended on row order;
# sorted rows, scaled fixed effects and L-BFGS-B converge, and BFGS / trust-constr give the same estimate to 4 decimals
glmm = BinomialBayesMixedGLM.from_formula(F4, {"player": "0 + C(nfl_id)"}, pdf4).fit_vb(
    scale_fe=True, fit_method="L-BFGS-B", minim_opts={"maxiter": 50000})
i = list(glmm.model.exog_names).index("c_z")
mean, sd = float(glmm.fe_mean[i]), float(glmm.fe_sd[i])
mixed["H4 mixed logistic, random intercept (variational Bayes)"] = {
    "or_per_sd": float(np.exp(mean)), "or_ci": [float(np.exp(mean - 1.96 * sd)), float(np.exp(mean + 1.96 * sd))],
    "player_sd_logit": float(np.exp(glmm.vcp_mean[0])), "note": "variational Bayes tends to understate uncertainty"}
pooled = smf.logit(F4, pdf4).fit(disp=False, cov_type="cluster", cov_kwds={"groups": pdf4["nfl_id"]})
mixed["H4 pooled logistic, SE clustered by player"] = {"or_per_sd": float(np.exp(pooled.params["c_z"])),
                                                       "or_ci": [float(v) for v in np.exp(pooled.conf_int().loc["c_z"])], "p": float(pooled.pvalues["c_z"])}
gee = smf.gee(F4, "nfl_id", pdf4, family=sm.families.Binomial(), cov_struct=sm.cov_struct.Exchangeable()).fit()
mixed["H4 GEE, exchangeable, robust SE"] = {"or_per_sd": float(np.exp(gee.params["c_z"])),
                                            "or_ci": [float(v) for v in np.exp(gee.conf_int().loc["c_z"])], "p": float(gee.pvalues["c_z"])}
R["mixed_models"] = mixed
print("\n== hierarchical models")
for k, v in mixed.items():
    if "coef_s_per_sd" in v:
        extra = f" | player sd {v['player_sd_s']:.4f} s, residual sd {v['residual_sd_s']:.3f} s" if "player_sd_s" in v else ""
        print(f"   H1 {k:28s}: NFL first step changes {v['coef_s_per_sd']:+.4f} s per SD of Combine first step "
              f"{[round(x, 4) for x in v['ci']]} p {v['p']:.3f}{extra}")
    else:
        print(f"   {k}: OR per SD slower Combine first step {v['or_per_sd']:.3f} {[round(x, 3) for x in v['or_ci']]}"
              + (f" p {v['p']:.3f}" if "p" in v else ""))

# ------------------------------------------------------------------ 5. exploratory: momentum at the Combine
main = main.with_columns((pl.col("combine_weight") * 1.5 / pl.col("forty_burst15_mean")).alias("momentum_15"),
                         (pl.col("combine_weight") * 2.5 / pl.col("forty_burst25_mean")).alias("momentum_25"))
mom = {}
print("\n== exploratory: momentum (weight x mean speed over the first 1.5 or 2.5 yd) vs pressure, by role")
for role in ("INTERIOR_LINE", "EDGE"):
    d = main.filter(pl.col("role") == role).drop_nulls(["momentum_15", "momentum_25"])
    out = {"n": d.height}
    for mcol in ("momentum_15", "momentum_25"):
        x, y = d[mcol].to_numpy(), d["eb_group"].to_numpy()
        r, p = stats.pearsonr(x, y)
        out[mcol] = {"r": float(r), "p": float(p), "ci": boot_ci(lambda k: np.corrcoef(x[k], y[k])[0, 1], len(x), RNG, B),
                     "r_with_weight": float(np.corrcoef(x, d["combine_weight"].to_numpy())[0, 1]),
                     "partial_h4_controls": partial_r(x, y, d.select("log_pick", "ten_yd_split", "edge_share").to_numpy(), RNG, B)}
        o = out[mcol]
        print(f"   {role:13s} {mcol}: r {o['r']:+.3f} {[round(v, 3) for v in o['ci']]} p {o['p']:.3f} | corr with weight {o['r_with_weight']:+.2f} | "
              f"after H4 controls r {o['partial_h4_controls']['r']:+.3f} {[round(v, 3) for v in o['partial_h4_controls']['ci']]}")
    mom[role] = out
R["momentum_exploratory"] = mom

with open(os.path.join(OUT, "review_round4.json"), "w") as f:
    json.dump(R, f, indent=2)
print("\nsaved review_round4.json")
