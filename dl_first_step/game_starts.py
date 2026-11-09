"""First-step measures for every regular-season DL pass rush, from game tracking.

Usage: python game_starts.py DATA_DIR OUT_DIR
Writes OUT_DIR/game_rush_plays.parquet and prints the checks.
"""
import os
import sys

import polars as pl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import KEY, anchored_measures, corr, first_crossing, parse_time, read, split_half

DATA, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)

games = read(DATA, "games.csv")
cmb = read(DATA, "combine_results.csv")
pp = read(DATA, "player_play.csv", schema_overrides={"game_clock": pl.Utf8})

# regular-season pass rushes by players who did the Combine as DL
plays = (pp.join(games.filter(pl.col("season_type") == "REG").select("game_id", "season", "week"), on="game_id")
         .join(cmb.filter(pl.col("combine_position") == "DL").select("nfl_id"), on="nfl_id")
         .filter(pl.col("sack").is_not_null()))
# line of scrimmage in field coordinates; 'right' means the offense moves toward larger x
dist_own = (pl.when(pl.col("yardline_side").is_null()).then(50)
            .when(pl.col("yardline_side") == pl.col("possession_team")).then(pl.col("yardline_number"))
            .otherwise(100 - pl.col("yardline_number")))
plays = plays.with_columns(
    pl.when(pl.col("play_direction") == "right").then(10 + dist_own).otherwise(110 - dist_own).cast(pl.Float64).alias("los_x"),
    pl.when(pl.col("play_direction") == "right").then(1.0).otherwise(-1.0).alias("sign"),
    pl.col("time_to_pressure").is_not_null().alias("pressure"),
)

parts = []
for year in (2023, 2024, 2025):
    t = read(DATA, f"game_tracking_{year}.csv", schema_overrides={"time": pl.Utf8, "event": pl.Utf8})
    parts.append(t.join(plays.select(KEY), on=KEY, how="semi"))
tr = parse_time(pl.concat(parts)).sort(KEY + ["time"])
snap = tr.filter(pl.col("event") == "ball_snap").group_by(KEY).agg(pl.col("time").min().alias("snap_time"))
tr = (tr.join(snap, on=KEY).join(plays.select(KEY + ["los_x", "sign"]), on=KEY)
      .with_columns((pl.col("time") - pl.col("snap_time")).dt.total_milliseconds().alias("ms")))
tr = tr.with_columns((pl.col("ms") / 1000).alias("t"), ((pl.col("x") - pl.col("los_x")) * pl.col("sign")).alias("depth"))

at_snap = tr.filter(pl.col("ms") == 0).select(KEY + [pl.col("x").alias("x0"), pl.col("y").alias("y0"),
                                                     pl.col("s").alias("s_snap"), pl.col("depth").alias("depth_snap")])
post = (tr.filter(pl.col("ms") >= 0).join(at_snap, on=KEY)
        .with_columns(((pl.col("x") - pl.col("x0")) ** 2 + (pl.col("y") - pl.col("y0")) ** 2).sqrt().alias("disp"),
                      (-pl.col("depth")).alias("past_los"))
        .sort(KEY + ["t"]))

feat = at_snap
for thr, name in ((0.25, "t_move"), (0.5, "t_0p5"), (2.5, "t_2p5")):
    feat = feat.join(first_crossing(post, KEY, "t", "disp", thr, name), on=KEY, how="left")
feat = feat.join(first_crossing(post, KEY, "t", "past_los", 0.0, "t_cross_los"), on=KEY, how="left")
one = post.filter(pl.col("ms") == 1000).select(KEY + [pl.col("disp").alias("disp_1s"), pl.col("s").alias("s_1s"),
                                                      (pl.col("depth_snap") - pl.col("depth")).alias("upfield_1s")])
ctx = ["season", "week", "team_abbr", "lined_up_position", "down", "yards_to_go", "quarter", "pre_snap_home_score",
       "pre_snap_visitor_score", "offense_formation", "pass_result", "dropback_duration", "blitzing", "unblocked_pressure",
       "sack", "pressure", "time_to_pressure", "player_get_off", "play_nullified_by_penalty"]
for dist, sfx in ((1.5, "_15"), (2.5, "_25")):
    feat = feat.join(anchored_measures(post, KEY, dist, suffix=sfx), on=KEY, how="left")
feat = feat.drop("t_on_25", "acc_25").rename({"t_on_15": "t_react", "acc_15": "acc_1to3"})
feat = (feat.join(one, on=KEY, how="left")
        .with_columns((pl.col("t_2p5") - pl.col("t_0p5")).alias("burst_0p5_2p5"),
                      (pl.col("s_snap") < 1.0).alias("stance_start"))
        .join(plays.select(KEY + ctx), on=KEY))
feat.write_parquet(os.path.join(OUT, "game_rush_plays.parquet"))

# ---------------- checks
print(f"pass rushes {plays.height:,}; with tracking and snap {feat.height:,}; stance starts {feat['stance_start'].sum():,}")
q = [round(feat["depth_snap"].quantile(p), 2) for p in (0.01, 0.1, 0.5, 0.9, 0.99)]
print(f"depth from line of scrimmage at snap (yd), 1/10/50/90/99%: {q}; behind the line at snap: {(feat['depth_snap'] <= 0).mean():.4f}")
print(f"crossed the line within the track: {feat['t_cross_los'].is_not_null().mean():.3f}")

st = feat.filter(pl.col("stance_start"))
print("\nwhich tracking measure matches the official get-off column (stance starts)?")
for c in ("t_cross_los", "t_2p5", "t_move", "burst_0p5_2p5"):
    n, r = corr(st, c, "player_get_off")
    diff = st.select((pl.col(c) - pl.col("player_get_off")).alias("d")).drop_nulls()["d"]
    print(f"  {c:15s} plays {n:6,}  r {r:5.3f}  mean diff {diff.mean():+.3f}s  median abs diff {diff.abs().median():.3f}s")
pm = st.group_by("nfl_id").agg(pl.len().alias("n"), pl.col("t_cross_los").mean(), pl.col("player_get_off").mean()).filter(pl.col("n") >= 30)
n, r = corr(pm, "t_cross_los", "player_get_off")
print(f"  player averages (>=30 rushes): players {n}, r {r:.3f}")

print("\nstability across odd vs even games (stance starts, >=25 rushes per half)")
for c in ("t_move", "burst_0p5_2p5", "t_2p5", "t_cross_los", "player_get_off", "disp_1s", "upfield_1s", "s_1s",
          "t_react", "burst_15", "burst_25", "acc_1to3"):
    n, r, rel = split_half(st, c, 25)
    print(f"  {c:15s} players {n:3d}  split-half r {r:5.2f}  reliability {rel:5.2f}  filled {st[c].is_not_null().mean():.3f}")
print("\nhow the anchored pieces relate to the official get-off (play level, stance starts)")
for c in ("t_react", "burst_15", "burst_25", "acc_1to3"):
    n, r = corr(st, c, "player_get_off")
    print(f"  {c:10s} plays {n:6,}  r {r:5.3f}  median {st[c].median():.3f}s")
n, r = corr(st.with_columns((pl.col("t_react") + pl.col("burst_25")).alias("react_plus_burst")), "react_plus_burst", "player_get_off")
print(f"  t_react + burst_25 vs official get-off: plays {n:,}, r {r:.3f}")

print("\nmedians by alignment (stance starts)")
print(st.group_by("lined_up_position").agg(pl.len().alias("rushes"), pl.col("nfl_id").n_unique().alias("players"),
      *[pl.col(c).median().round(3) for c in ("t_move", "burst_0p5_2p5", "t_cross_los", "player_get_off", "disp_1s")],
      pl.col("pressure").mean().round(3).alias("pressure_rate")).sort("rushes", descending=True))
