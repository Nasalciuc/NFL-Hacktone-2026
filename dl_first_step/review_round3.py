"""Checks requested in the third review round. All post-hoc (after the planned tests).

1. H1 with the alternative measures (2.5 yd, acceleration 1-3 yd/s) and Spearman, adjusted like the
   primary measure, plus a version adjusted for weight only (known before the draft).
2. Is role a mediator? Does the Combine first step predict how often a player lines up on the edge?
3. The interior pressure signal with the H4 specification (draft slot, 10-yard split, edge share).
4. The H3 between-player effect expressed per player-level SD, next to the play-level SD.

Usage: python review_round3.py DATA_DIR OUT_DIR
Writes OUT_DIR/review_round3.json and prints a log.
"""
import json
import os
import sys

import numpy as np
import polars as pl
import statsmodels.api as sm
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import boot_ci, eligible_plays, fit_beta_binomial, partial_r, read

DATA, OUT = sys.argv[1], sys.argv[2]
RNG = np.random.default_rng(2027)
B = 5000
R = {}

plays = pl.read_parquet(os.path.join(OUT, "game_rush_plays.parquet"))
games = read(DATA, "games.csv")
players = read(DATA, "players.csv")
comb = pl.read_parquet(os.path.join(OUT, "combine_dl_players.parquet"))
elig = eligible_plays(plays)

gp = (elig.group_by("nfl_id").agg(
    pl.len().alias("rushes"), pl.col("burst_15").mean().alias("g_burst15"), pl.col("burst_25").mean().alias("g_burst25"),
    pl.col("acc_1to3").mean().alias("g_acc"), pl.col("edge").mean().alias("edge_share"), pl.col("pressure_f").sum().alias("pressures"))
    .with_columns(pl.when(pl.col("edge_share") >= 0.5).then(pl.lit("EDGE")).otherwise(pl.lit("INTERIOR_LINE")).alias("role")))
a_all, b_all = fit_beta_binomial(gp["pressures"], gp["rushes"])
pri = {r: fit_beta_binomial(gp.filter(pl.col("role") == r)["pressures"], gp.filter(pl.col("role") == r)["rushes"]) for r in ("EDGE", "INTERIOR_LINE")}
gp = gp.with_columns(
    ((pl.col("pressures") + a_all) / (pl.col("rushes") + a_all + b_all)).alias("eb_global"),
    pl.when(pl.col("role") == "EDGE").then((pl.col("pressures") + pri["EDGE"][0]) / (pl.col("rushes") + pri["EDGE"].sum()))
    .otherwise((pl.col("pressures") + pri["INTERIOR_LINE"][0]) / (pl.col("rushes") + pri["INTERIOR_LINE"].sum())).alias("eb_group"))
main = (gp.filter(pl.col("rushes") >= 50).join(comb, on="nfl_id").filter(pl.col("forty_burst15_mean").is_not_null())
        .join(players.select("nfl_id", "draft_overall_pick", "nfl_position"), on="nfl_id")
        .with_columns(pl.col("draft_overall_pick").fill_null(260).cast(pl.Float64).log().alias("log_pick"),
                      (pl.col("nfl_position") == "NT").cast(pl.Float64).alias("nt")))
print(f"main sample: {main.height} players")


def arr(d, *cols):
    return [d[c].to_numpy().astype(float) for c in cols]


def corr_ci(x, y, rank=False):
    if rank:
        r, p = stats.spearmanr(x, y)
        f = lambda k: stats.spearmanr(x[k], y[k])[0]
    else:
        r, p = stats.pearsonr(x, y)
        f = lambda k: np.corrcoef(x[k], y[k])[0, 1]
    return {"n": int(len(x)), "r": float(r), "p": float(p), "ci": boot_ci(f, len(x), RNG, B)}


def fmt(c):
    return f"r {c['r']:+.3f} [{c['ci'][0]:+.3f}, {c['ci'][1]:+.3f}]" + (f" p {c['p']:.3f}" if "p" in c else "")


# ------------------------------------------------------------------ 1. H1 robustness, adjusted
print("\n== H1 by measure: Combine vs NFL, unadjusted and adjusted")
h1 = {}
for label, ccol, gcol in (("1.5 yd (primary)", "forty_burst15_mean", "g_burst15"), ("2.5 yd", "forty_burst25_mean", "g_burst25"),
                          ("acceleration 1-3 yd/s", "forty_acc_mean", "g_acc")):
    d = main.drop_nulls([ccol, gcol])
    x, y, w, e = arr(d, ccol, gcol, "combine_weight", "edge_share")
    res = {"pearson": corr_ci(x, y), "spearman": corr_ci(x, y, rank=True),
           "partial_weight_role": partial_r(x, y, np.column_stack([w, e]), RNG, B),
           "partial_spearman_weight_role": partial_r(x, y, np.column_stack([w, e]), RNG, B, rank=True),
           "partial_weight_only": partial_r(x, y, w, RNG, B)}
    h1[label] = res
    print(f"   {label:22s} Pearson {fmt(res['pearson'])} | Spearman {fmt(res['spearman'])}")
    print(f"   {'':22s} after weight + role: Pearson {fmt(res['partial_weight_role'])} | Spearman {fmt(res['partial_spearman_weight_role'])}")
    print(f"   {'':22s} after weight only (pre-draft): {fmt(res['partial_weight_only'])}")
R["h1_by_measure"] = h1

# ------------------------------------------------------------------ 2. role as a mediator?
print("\n== Does the Combine first step predict how often a player lines up on the edge?")
x, e, w = arr(main, "forty_burst15_mean", "edge_share", "combine_weight")
z = lambda v: (v - v.mean()) / v.std()
ols = sm.OLS(z(e), sm.add_constant(np.column_stack([z(x), z(w)]))).fit(cov_type="HC3")
med = {"r_unadjusted": corr_ci(x, e), "partial_given_weight": partial_r(x, e, w, RNG, B),
       "ols_std_beta_combine": float(ols.params[1]), "ols_ci": [float(v) for v in ols.conf_int()[1]], "ols_p": float(ols.pvalues[1]),
       "ols_std_beta_weight": float(ols.params[2]), "ols_p_weight": float(ols.pvalues[2]), "r2": float(ols.rsquared)}
R["role_mediator"] = med
print(f"   edge share vs Combine first step: {fmt(med['r_unadjusted'])}; given weight {fmt(med['partial_given_weight'])}")
print(f"   OLS (standardized): Combine first step {med['ols_std_beta_combine']:+.3f} {[round(v, 3) for v in med['ols_ci']]} p {med['ols_p']:.3f}; "
      f"weight {med['ols_std_beta_weight']:+.3f} p {med['ols_p_weight']:.2g}; R2 {med['r2']:.3f}")

# ------------------------------------------------------------------ 3. interior signal with the H4 specification
print("\n== Combine first step vs pressure by role, with the H4 controls (draft slot, 10-yd split, edge share)")
h4spec = {}
for role in ("INTERIOR_LINE", "EDGE"):
    d = main.filter(pl.col("role") == role)
    out = {"n": d.height}
    for shrink in ("eb_group", "eb_global"):
        x, y, lp, ten, es, w, nt = arr(d, "forty_burst15_mean", shrink, "log_pick", "ten_yd_split", "edge_share", "combine_weight", "nt")
        Z = np.column_stack([lp, ten, es])
        X = sm.add_constant(np.column_stack([z(x), z(lp), z(ten), z(es)]))
        m = sm.OLS(z(y), X).fit(cov_type="HC3")
        boot = boot_ci(lambda k: np.linalg.lstsq(X[k], z(y)[k], rcond=None)[0][1], len(y), RNG, B)
        out[shrink] = {"std_beta": float(m.params[1]), "ci_hc3": [float(v) for v in m.conf_int()[1]], "ci_boot": boot,
                       "p": float(m.pvalues[1]), "partial_h4_controls": partial_r(x, y, Z, RNG, B),
                       "partial_h4_controls_weight_nt": partial_r(x, y, np.column_stack([Z, w, nt]), RNG, B)}
        o = out[shrink]
        print(f"   {role:13s} {shrink:9s} n {d.height}: beta {o['std_beta']:+.3f} HC3 {[round(v, 3) for v in o['ci_hc3']]} "
              f"boot {[round(v, 3) for v in o['ci_boot']]} p {o['p']:.4f} | partial r {fmt(o['partial_h4_controls'])} | "
              f"+ weight + NT {fmt(o['partial_h4_controls_weight_nt'])}")
    h4spec[role] = out
R["pressure_by_role_h4_spec"] = h4spec

# ------------------------------------------------------------------ 4. H3 between players, per player-level SD
rev = json.load(open(os.path.join(OUT, "review_round2.json")))
e3 = (eligible_plays(plays, games).join(main.select("nfl_id"), on="nfl_id", how="semi")
      .drop_nulls(["burst_15", "t_react", "down", "yards_to_go", "score_diff_def"])
      .with_columns(((pl.col("burst_15") - pl.col("burst_15").mean().over("lined_up_position"))
                     / pl.col("burst_15").std().over("lined_up_position")).alias("m_z")))
sd_between = float(e3.group_by("nfl_id").agg(pl.col("m_z").mean())["m_z"].std())
b = rev["H3_decomposed"]["main_62"]["burst_15"]
R["h3_scales"] = {"play_level_sd": 1.0, "sd_of_player_averages_in_play_sd_units": sd_between,
                  "or_within_per_play_sd": b["fixed_effects_or"], "or_between_per_player_sd": float(b["or_between"] ** sd_between),
                  "or_between_per_player_sd_ci": [float(v ** sd_between) for v in b["or_between_ci"]]}
print(f"\n== H3 scales: player averages vary by {sd_between:.2f} play-level SDs; "
      f"between players, OR per player-level SD slower = {R['h3_scales']['or_between_per_player_sd']:.3f} "
      f"{[round(v, 3) for v in R['h3_scales']['or_between_per_player_sd_ci']]}")

with open(os.path.join(OUT, "review_round3.json"), "w") as f:
    json.dump(R, f, indent=2)
print("\nsaved review_round3.json")
