"""First look at WR route drills (Combine) and WR routes (regular season)."""
import os
import sys

import numpy as np
import polars as pl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "dl_first_step"))
from common import KEY, REP, parse_time, read

DATA = sys.argv[1]
pl.Config.set_tbl_rows(60)
pl.Config.set_tbl_cols(20)
pl.Config.set_tbl_width_chars(230)

cmb = read(DATA, "combine_results.csv")
ct = read(DATA, "combine_tracking.csv", schema_overrides={"time": pl.Utf8})
ct = (parse_time(ct).join(cmb.select("nfl_id", "combine_position"), on="nfl_id")
      .filter((pl.col("combine_position") == "WR") & (pl.col("entity_type") == "PLAYER"))
      .sort(REP + ["time"]))
ct = ct.with_columns(((pl.col("time") - pl.col("time").first().over(REP)).dt.total_milliseconds() / 1000).alias("t"))


def turns(df, keys, lag=3):
    """Heading change (deg) between the 0.3 s before and the 0.3 s after each frame."""
    d = df.with_columns(
        (pl.col("x") - pl.col("x").shift(lag).over(keys)).alias("ax"), (pl.col("y") - pl.col("y").shift(lag).over(keys)).alias("ay"),
        (pl.col("x").shift(-lag).over(keys) - pl.col("x")).alias("bx"), (pl.col("y").shift(-lag).over(keys) - pl.col("y")).alias("by"))
    na = (pl.col("ax") ** 2 + pl.col("ay") ** 2).sqrt()
    nb = (pl.col("bx") ** 2 + pl.col("by") ** 2).sqrt()
    cosv = ((pl.col("ax") * pl.col("bx") + pl.col("ay") * pl.col("by")) / (na * nb)).clip(-1, 1)
    return d.with_columns(pl.when((na > 0.3) & (nb > 0.3)).then(cosv.arccos().degrees()).otherwise(None).alias("turn"),
                          (pl.col("x").diff().over(keys) ** 2 + pl.col("y").diff().over(keys) ** 2).sqrt().fill_null(0).cum_sum().over(keys).alias("path"))


ct = turns(ct, REP)
reps = ct.group_by(REP + ["drill_name", "draft_year"]).agg(
    pl.len().alias("frames"), pl.col("s").sort_by("t").first().alias("s_first"), pl.col("s").max().alias("s_max"),
    pl.col("path").max().alias("path_total"),
    pl.col("turn").max().alias("turn_max"),
    pl.col("t").sort_by("turn", descending=True, nulls_last=True).first().alias("t_turn_max"),
    pl.col("path").sort_by("turn", descending=True, nulls_last=True).first().alias("path_at_turn_max"),
    pl.col("t").filter((pl.col("turn") >= 35) & (pl.col("path") >= 3)).min().alias("t_first_turn35"),
    pl.col("path").filter((pl.col("turn") >= 35) & (pl.col("path") >= 3)).min().alias("path_first_turn35"))
print("=== WR Combine drills (players = WR at the Combine)")
print(reps.group_by("drill_name").agg(
    pl.col("nfl_id").n_unique().alias("players"), pl.len().alias("reps"), (pl.col("s_first") < 1).mean().round(2).alias("clean"),
    pl.col("frames").median().alias("frames"), pl.col("path_total").median().round(1).alias("path"),
    pl.col("s_max").median().round(2).alias("s_max"), pl.col("turn_max").median().round(0).alias("turn_max"),
    pl.col("path_at_turn_max").median().round(1).alias("path_at_max"), pl.col("t_first_turn35").is_not_null().mean().round(2).alias("has_turn35"),
    pl.col("path_first_turn35").median().round(1).alias("path_first35")).sort("players", descending=True))

# one example per drill: speed and turn profile around the first big turn
for drill in ("SLANT_ROUTE_LEFT", "CURL_ROUTE_RIGHT", "COMEBACK_ROUTE_RIGHT", "SPEED_OUT_ROUTE_LEFT", "DAGGER_ROUTE_LEFT"):
    r = reps.filter((pl.col("drill_name") == drill) & pl.col("t_first_turn35").is_not_null()).head(1)
    if r.height == 0:
        continue
    e = ct.join(r.select(REP + ["t_first_turn35"]), on=REP).filter((pl.col("t") >= pl.col("t_first_turn35") - 1.2) & (pl.col("t") <= pl.col("t_first_turn35") + 1.2))
    print(f"--- {drill}: t, s, turn, path around the first turn >= 35 deg")
    print(e.select(pl.col("t").round(1), pl.col("s").round(2), pl.col("turn").round(0), pl.col("path").round(1)).gather_every(2).transpose(include_header=True))

# ---------- in-game WR routes, regular season
games = read(DATA, "games.csv")
pp = read(DATA, "player_play.csv", schema_overrides={"game_clock": pl.Utf8})
wr = (pp.join(games.filter(pl.col("season_type") == "REG").select("game_id"), on="game_id")
      .join(cmb.filter(pl.col("combine_position") == "WR").select("nfl_id"), on="nfl_id")
      .filter(pl.col("route_ran").is_not_null()))
print(f"\n=== WR regular-season routes: {wr.height:,}, players {wr['nfl_id'].n_unique()}")
print(wr.group_by("route_ran").agg(pl.len().alias("routes"), pl.col("separation_at_pass_forward").is_not_null().mean().round(3).alias("sep_filled"),
      pl.col("separation_at_pass_forward").median().round(2).alias("sep_median"), pl.col("target").mean().round(3).alias("target_rate"))
      .sort("routes", descending=True))
print("alignment:", wr.group_by("lined_up_position").len().sort("len", descending=True).rows())
print("coverage:", wr.group_by("team_coverage_man_zone").len().sort("len", descending=True).rows())
parts = []
for year in (2023, 2024, 2025):
    t = read(DATA, f"game_tracking_{year}.csv", schema_overrides={"time": pl.Utf8, "event": pl.Utf8})
    parts.append(t.join(wr.select(KEY), on=KEY, how="semi").filter(pl.col("event").is_in(["ball_snap", "pass_forward", "qb_sack", "run"])))
ev = parse_time(pl.concat(parts))
snap = ev.filter(pl.col("event") == "ball_snap").group_by(KEY).agg(pl.col("time").min().alias("snap"))
pf = ev.filter(pl.col("event") == "pass_forward").group_by(KEY).agg(pl.col("time").min().alias("pf"))
j = snap.join(pf, on=KEY, how="left").with_columns(((pl.col("pf") - pl.col("snap")).dt.total_milliseconds() / 1000).alias("t_pf"))
print(f"routes with snap: {snap.height:,}; with pass_forward: {j['pf'].is_not_null().sum():,}")
print("time from snap to pass forward (s), quantiles:", [round(j["t_pf"].quantile(q), 2) for q in (0.05, 0.25, 0.5, 0.75, 0.95)])
k = wr.join(j, on=KEY, how="left")
print("separation filled when pass_forward exists:", round(k.filter(pl.col("pf").is_not_null())["separation_at_pass_forward"].is_not_null().mean(), 3),
      " when it does not:", round(k.filter(pl.col("pf").is_null())["separation_at_pass_forward"].is_not_null().mean(), 3))
