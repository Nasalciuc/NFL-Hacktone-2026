"""Break mechanics for WRs: Combine route drills and regular-season routes, measured the same way.

A break is found from speed alone, so field direction and turn angle do not matter:
after the receiver first reaches 4.5 yd/s, the break starts when speed falls below 70% of the
highest speed so far. Measures per break:
  decel    yd/s^2, (entry speed - lowest speed) / time between them
  drop     share of entry speed lost
  reaccel  yd/s^2, speed gained in the 0.5 s after the lowest speed, divided by 0.5
In games only the part of the route between the snap and the pass is used.

Usage: python wr_measures.py DATA_DIR OUT_DIR
"""
import os
import sys

import numpy as np
import polars as pl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "dl_first_step"))
from common import KEY, REP, parse_time, read, split_half

DATA, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
STEM = 4.5
DIP = float(sys.argv[3]) if len(sys.argv) > 3 else 0.7
print(f"break threshold: speed below {DIP:.0%} of the highest speed so far")


def breaks(df, keys):
    """df: keys, t (s), s; sorted by keys + t. Returns one row per group that has a break."""
    d = (df.select(keys + ["t", "s"])
         .with_columns((pl.col("s") >= STEM).cast(pl.Int8).cum_max().over(keys).alias("_go"))
         .filter(pl.col("_go") == 1)
         .with_columns(pl.col("s").cum_max().over(keys).alias("_m")))
    start = (d.filter(pl.col("s") < DIP * pl.col("_m")).group_by(keys)
             .agg(pl.col("t").min().alias("t_dip")))
    d = d.join(start, on=keys)
    entry = (d.filter(pl.col("t") <= pl.col("t_dip")).group_by(keys)
             .agg(pl.col("s").max().alias("s_entry"), pl.col("t").sort_by("s", descending=True).first().alias("t_entry")))
    low = (d.filter((pl.col("t") >= pl.col("t_dip")) & (pl.col("t") <= pl.col("t_dip") + 1.0)).group_by(keys)
           .agg(pl.col("s").min().alias("s_min"), pl.col("t").sort_by("s").first().alias("t_min")))
    b = entry.join(low, on=keys)
    after = (df.select(keys + ["t", "s"]).join(b.select(keys + ["t_min"]), on=keys)
             .filter(((pl.col("t") - pl.col("t_min") - 0.5).abs() < 0.051)).group_by(keys)
             .agg(pl.col("s").first().alias("s_after")))
    b = b.join(after, on=keys, how="left")
    return b.with_columns(
        ((pl.col("s_entry") - pl.col("s_min")) / (pl.col("t_min") - pl.col("t_entry"))).alias("decel"),
        ((pl.col("s_entry") - pl.col("s_min")) / pl.col("s_entry")).alias("drop"),
        ((pl.col("s_after") - pl.col("s_min")) / 0.5).alias("reaccel"))


def zscore(df, col, by):
    return ((pl.col(col) - pl.col(col).mean().over(by)) / pl.col(col).std().over(by)).alias(f"{col}_z")


cmb = read(DATA, "combine_results.csv")
wr_ids = cmb.filter(pl.col("combine_position") == "WR").select("nfl_id")

# ---------------- Combine route drills
ROUTE_DRILLS = ["SLANT_ROUTE_LEFT", "CURL_ROUTE_RIGHT", "COMEBACK_ROUTE_RIGHT", "DAGGER_ROUTE_LEFT", "SPEED_OUT_ROUTE_LEFT",
                "SPEED_OUT_LEFT", "SLOT_STRIKE_ROUTE_LEFT", "SLOT_SAIL_ROUTE_RIGHT", "POST_CORNER_ROUTE_RIGHT", "POST_CORNER_ROUTE_LEFT"]
ct = read(DATA, "combine_tracking.csv", schema_overrides={"time": pl.Utf8})
ct = (parse_time(ct).join(wr_ids, on="nfl_id")
      .filter((pl.col("entity_type") == "PLAYER") & pl.col("drill_name").is_in(ROUTE_DRILLS))
      .with_columns(pl.col("drill_name").replace({"SPEED_OUT_LEFT": "SPEED_OUT_ROUTE_LEFT"}))
      .sort(REP + ["time"]))
ct = ct.with_columns(((pl.col("time") - pl.col("time").first().over(REP)).dt.total_milliseconds() / 1000).alias("t"))
reps = ct.group_by(REP + ["drill_name", "draft_year"]).agg(pl.col("s").sort_by("t").first().alias("s_first"))
cb = breaks(ct, REP)
reps = reps.join(cb, on=REP, how="left")
print("=== Combine: share of reps with a break, and median measures, by drill")
print(reps.group_by("drill_name").agg(pl.len().alias("reps"), pl.col("nfl_id").n_unique().alias("players"),
      pl.col("decel").is_not_null().mean().round(2).alias("has_break"), pl.col("s_entry").median().round(2).alias("entry"),
      pl.col("s_min").median().round(2).alias("low"), pl.col("decel").median().round(2).alias("decel"),
      pl.col("drop").median().round(2).alias("drop"), pl.col("reaccel").median().round(2).alias("reaccel"))
      .sort("has_break", descending=True))
TAG = f"dip{int(DIP * 100)}"
reps.write_parquet(os.path.join(OUT, f"wr_combine_reps_{TAG}.parquet"))

# ---------------- regular-season routes
games = read(DATA, "games.csv")
pp = read(DATA, "player_play.csv", schema_overrides={"game_clock": pl.Utf8})
routes = (pp.join(games.filter(pl.col("season_type") == "REG").select("game_id", "season", "home_team_abbr"), on="game_id")
          .join(wr_ids, on="nfl_id").filter(pl.col("route_ran").is_not_null()))
parts = []
for year in (2023, 2024, 2025):
    t = read(DATA, f"game_tracking_{year}.csv", schema_overrides={"time": pl.Utf8, "event": pl.Utf8})
    parts.append(t.join(routes.select(KEY), on=KEY, how="semi"))
tr = parse_time(pl.concat(parts)).sort(KEY + ["time"])
ev = tr.filter(pl.col("event").is_in(["ball_snap", "pass_forward"]))
snap = ev.filter(pl.col("event") == "ball_snap").group_by(KEY).agg(pl.col("time").min().alias("snap"))
pf = ev.filter(pl.col("event") == "pass_forward").group_by(KEY).agg(pl.col("time").min().alias("pf"))
tr = (tr.join(snap, on=KEY).join(pf, on=KEY)
      .with_columns(((pl.col("time") - pl.col("snap")).dt.total_milliseconds() / 1000).alias("t"),
                    ((pl.col("pf") - pl.col("snap")).dt.total_milliseconds() / 1000).alias("t_pf"))
      .filter((pl.col("t") >= 0) & (pl.col("t") <= pl.col("t_pf"))))
gb = breaks(tr, KEY)
tpf = tr.group_by(KEY).agg(pl.col("t_pf").first(), pl.col("s").max().alias("s_max_route"))
g = (routes.select(KEY + ["season", "route_ran", "lined_up_position", "team_coverage_man_zone", "team_coverage_type", "cushion",
                          "separation_at_pass_forward", "target", "down", "yards_to_go", "play_nullified_by_penalty", "team_abbr"])
     .join(tpf, on=KEY).join(gb, on=KEY, how="left"))
print(f"\n=== games: routes with snap and pass {g.height:,}")
print(g.group_by("route_ran").agg(pl.len().alias("routes"), pl.col("decel").is_not_null().mean().round(2).alias("has_break"),
      pl.col("t_entry").median().round(2).alias("t_entry"), pl.col("s_entry").median().round(2).alias("entry"),
      pl.col("s_min").median().round(2).alias("low"), pl.col("decel").median().round(2).alias("decel"),
      pl.col("drop").median().round(2).alias("drop"), pl.col("reaccel").median().round(2).alias("reaccel"),
      pl.col("separation_at_pass_forward").median().round(2).alias("sep")).sort("routes", descending=True))
g.write_parquet(os.path.join(OUT, f"wr_game_routes_{TAG}.parquet"))

# ---------------- stability, measured on drills / route types where most reps have a break
good_drills = (reps.group_by("drill_name").agg(pl.col("decel").is_not_null().mean().alias("hb"))
               .filter(pl.col("hb") >= 0.8)["drill_name"].sort().to_list())
good_routes = (g.group_by("route_ran").agg(pl.col("decel").is_not_null().mean().alias("hb"), pl.len().alias("n"))
               .filter((pl.col("hb") >= 0.5) & (pl.col("n") >= 500))["route_ran"].sort().to_list())
print("\ndrills with a break in >= 80% of reps:", good_drills)
print("route types with a break in >= 50% of routes:", good_routes)
cr = (reps.filter(pl.col("drill_name").is_in(good_drills) & (pl.col("s_first") < 1.0))
      .with_columns(*[zscore(reps, c, "drill_name") for c in ("decel", "drop", "reaccel")]))
order = {d: i for i, d in enumerate(good_drills)}
cr = cr.with_columns(pl.col("drill_name").replace_strict(order).alias("drill_order"))
print("Combine stability across drills (odd vs even drills, z within drill):")
for c in ("decel_z", "drop_z", "reaccel_z"):
    n, r, rel = split_half(cr, c, 1, order="drill_order")
    print(f"  {c:10s} players {n:3d}  r {r:5.2f}  reliability {rel:5.2f}")
gr = (g.filter(pl.col("route_ran").is_in(good_routes) & (pl.col("play_nullified_by_penalty") == "N"))
      .with_columns(*[zscore(g, c, "route_ran") for c in ("decel", "drop", "reaccel")]))
print("Game stability across odd vs even games (z within route type, >= 25 breaks per half):")
for c in ("decel_z", "drop_z", "reaccel_z"):
    n, r, rel = split_half(gr, c, 25)
    print(f"  {c:10s} players {n:3d}  r {r:5.2f}  reliability {rel:5.2f}")
n, r, rel = split_half(g.filter(pl.col("play_nullified_by_penalty") == "N"), "separation_at_pass_forward", 25)
print(f"  separation (all routes)  players {n:3d}  r {r:5.2f}  reliability {rel:5.2f}")

pc = cr.group_by("nfl_id").agg(pl.len().alias("combine_breaks"), *[pl.col(f"{c}_z").mean().alias(f"c_{c}") for c in ("decel", "drop", "reaccel")])
pc.write_parquet(os.path.join(OUT, f"wr_combine_players_{TAG}.parquet"))
print(f"\nWR with Combine break measures: {pc.height}; breaks per player median {pc['combine_breaks'].median()}")
