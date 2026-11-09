"""First-step measures from Combine tracking: the 40-yard dash for every player and six drills for DL players.

Usage: python combine_starts.py DATA_DIR OUT_DIR
Writes combine_reps.parquet and combine_dl_players.parquet, and prints the checks.
"""
import os
import sys

import numpy as np
import polars as pl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REP, anchored_measures, corr, first_crossing, parse_time, read, split_half

DATA, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
FORTY = "FORTY_YARD_DASH"
DL_DRILLS = {"PASS_RUSH_DRILL": "pass_rush", "FRONT_START_WAVE_DRILL_AND_LATERAL_REACTION": "front_start",
             "FOUR_BAG_AGILITY_DRILL": "four_bag", "RUN_THE_HOOP_DRILL": "hoop", "BODY_CONTROL_DRILL": "body_control",
             "RUN_AND_CLUB_DRILL": "run_club"}

cmb = read(DATA, "combine_results.csv")
ct = read(DATA, "combine_tracking.csv", schema_overrides={"time": pl.Utf8}).filter(pl.col("entity_type") == "PLAYER")
ct = (parse_time(ct).join(cmb.select("nfl_id", "combine_position"), on="nfl_id")
      .filter((pl.col("drill_name") == FORTY) | ((pl.col("combine_position") == "DL") & pl.col("drill_name").is_in(list(DL_DRILLS))))
      .sort(REP + ["time"]))
ct = ct.with_columns(
    (pl.col("time") - pl.col("time").first().over(REP)).dt.total_milliseconds().alias("ms"),
    ((pl.col("x") - pl.col("x").first().over(REP)) ** 2 + (pl.col("y") - pl.col("y").first().over(REP)) ** 2).sqrt().alias("disp"),
).with_columns((pl.col("ms") / 1000).alias("t"))

reps = ct.group_by(REP + ["drill_name", "combine_position", "draft_year"]).agg(
    pl.col("s").sort_by("t").first().alias("s_first"), pl.len().alias("frames"), pl.col("disp").max().alias("disp_max"))
for thr, name in ((0.25, "t_move"), (0.5, "t_0p5"), (2.5, "t_2p5"), (5, "t_5"), (10, "t_10"), (40, "t_40")):
    reps = reps.join(first_crossing(ct, REP, "t", "disp", thr, name), on=REP, how="left")
one = ct.filter(pl.col("ms") == 1000).select(REP + [pl.col("disp").alias("disp_1s"), pl.col("s").alias("s_1s")])
for dist, sfx in ((1.5, "_15"), (2.5, "_25")):
    reps = reps.join(anchored_measures(ct, REP, dist, suffix=sfx), on=REP, how="left")
reps = reps.drop("t_on_15", "t_on_25", "acc_25").rename({"acc_15": "acc_1to3"})
reps = (reps.join(one, on=REP, how="left")
        .with_columns((pl.col("t_2p5") - pl.col("t_0p5")).alias("burst_0p5_2p5"),
                      (pl.col("s_first") < 1.0).alias("clean_start")))
reps.write_parquet(os.path.join(OUT, "combine_reps.parquet"))

first = ct.filter((pl.col("drill_name") == FORTY) & (pl.col("ms") == 0))
print("40-yard first frame, x and y quantiles by year (is the start line fixed?)")
print(first.group_by("draft_year").agg(*[pl.col(c).quantile(q).round(2).alias(f"{c}_{int(q * 100)}")
                                         for c in ("x", "y") for q in (0.05, 0.5, 0.95)]).sort("draft_year"))

# ---------------- checks on the 40-yard dash (all positions)
f = reps.filter(pl.col("drill_name") == FORTY)
best = (f.group_by("nfl_id", "combine_position").agg(pl.len().alias("attempts"), pl.col("t_10").min().alias("t10_best"),
        pl.col("t_40").min().alias("t40_best"), pl.col("burst_0p5_2p5").mean().alias("burst_mean"),
        pl.col("burst_0p5_2p5").min().alias("burst_best"), pl.col("disp_1s").max().alias("disp_1s_best"),
        pl.col("burst_15").mean().alias("burst15_mean"), pl.col("burst_25").mean().alias("burst25_mean"),
        pl.col("acc_1to3").mean().alias("acc_mean"))
        .join(cmb.select("nfl_id", "ten_yd_split", "forty", "combine_weight"), on="nfl_id"))
print(f"40-yard reps {f.height}, players {best.height}, start speed median {f['s_first'].median():.2f} yd/s")
for a, b in (("t10_best", "ten_yd_split"), ("t40_best", "forty")):
    n, r = corr(best, a, b)
    d = best.select((pl.col(a) - pl.col(b)).alias("d")).drop_nulls()["d"]
    print(f"  tracked {a} vs official {b}: players {n}, r {r:.3f}, tracked minus official {d.mean():+.3f}s (sd {d.std():.3f})")
print("attempt-to-attempt stability, 40-yard dash (players with 2+ attempts)")
for c in ("burst_0p5_2p5", "t_10", "disp_1s", "t_40", "burst_15", "burst_25", "acc_1to3"):
    for label, sub in (("all", f), ("DL", f.filter(pl.col("combine_position") == "DL"))):
        n, r, _ = split_half(sub, c, 1, order="attempt")
        print(f"  {c:14s} {label:3s} players {n:3d}  r {r:5.2f}")

# ---------------- DL drills
dl = reps.filter(pl.col("combine_position") == "DL")
print("\nDL drills: reps with a clean start (speed under 1 yd/s at the first frame)")
print(dl.group_by("drill_name").agg(pl.len().alias("reps"), pl.col("clean_start").mean().round(2).alias("clean_share"),
      pl.col("burst_0p5_2p5").filter(pl.col("clean_start")).median().round(3).alias("burst_median"),
      pl.col("nfl_id").filter(pl.col("clean_start")).n_unique().alias("players_clean"))
      .sort(["players_clean", "drill_name"], descending=[True, False]))
prd = dl.filter((pl.col("drill_name") == "PASS_RUSH_DRILL") & pl.col("clean_start"))
for c in ("burst_0p5_2p5", "burst_15", "burst_25", "acc_1to3"):
    n, r, _ = split_half(prd, c, 1, order="attempt")
    print(f"pass-rush drill {c:14s} rep-to-rep stability: players {n}, r {r:.2f}")

# ---------------- one row per DL player
dlp = cmb.filter(pl.col("combine_position") == "DL").select("nfl_id", "draft_year", "combine_weight", "combine_height", "arm_length",
                                                           "ten_yd_split", "forty", "ngs_athleticism_score")
dlp = dlp.join(best.select("nfl_id", "attempts", "t10_best", "t40_best", "burst_mean", "burst_best", "disp_1s_best",
                           "burst15_mean", "burst25_mean", "acc_mean")
               .rename(lambda c: c if c == "nfl_id" else f"forty_{c}"), on="nfl_id", how="left")
for drill, short in DL_DRILLS.items():
    g = (dl.filter((pl.col("drill_name") == drill) & pl.col("clean_start")).group_by("nfl_id")
         .agg(pl.col("burst_0p5_2p5").mean().alias(f"{short}_burst"), pl.col("burst_25").mean().alias(f"{short}_burst25"),
              pl.col("acc_1to3").mean().alias(f"{short}_acc")))
    dlp = dlp.join(g, on="nfl_id", how="left")
dlp.write_parquet(os.path.join(OUT, "combine_dl_players.parquet"))

cols = ["forty_burst25_mean", "forty_acc_mean", "forty_t40_best", "ten_yd_split", "forty", "pass_rush_burst25", "front_start_burst25",
        "run_club_burst25", "hoop_burst25", "combine_weight"]
print(f"\nDL players {dlp.height}; available per measure:", {c: dlp[c].is_not_null().sum() for c in cols})
m = np.full((len(cols), len(cols)), np.nan)
for i, a in enumerate(cols):
    for j, b in enumerate(cols):
        m[i, j] = 1.0 if i == j else corr(dlp, a, b)[1]
print("correlations between DL Combine measures (pairwise complete)")
print(pl.DataFrame({"measure": cols, **{c[:12]: np.round(m[:, j], 2) for j, c in enumerate(cols)}}))
