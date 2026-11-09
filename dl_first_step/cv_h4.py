"""Leave-one-out check of the Combine -> pressure link (H4), with draft slot controlled.

Descriptive, added on 9 Nov 2026 to complete the week-4 item "test with cross-validation and
draft control". It is not a new planned test; the H4 result stays the one in tests.py.

Usage: python cv_h4.py DATA_DIR OUT_DIR
"""
import os
import sys

import numpy as np
import polars as pl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import eligible_plays, fit_beta_binomial, loo_r2, read

DATA, OUT = sys.argv[1], sys.argv[2]
elig = eligible_plays(pl.read_parquet(os.path.join(OUT, "game_rush_plays.parquet")))
gp = elig.group_by("nfl_id").agg(pl.len().alias("rushes"), pl.col("edge").mean().alias("edge_share"),
                                 pl.col("pressure_f").sum().alias("pressures"))
a, b = fit_beta_binomial(gp["pressures"].to_numpy(), gp["rushes"].to_numpy())
df = (gp.with_columns(((pl.col("pressures") + a) / (pl.col("rushes") + a + b)).alias("eb_rate"))
      .filter(pl.col("rushes") >= 50)
      .join(pl.read_parquet(os.path.join(OUT, "combine_dl_players.parquet")), on="nfl_id")
      .filter(pl.col("forty_burst15_mean").is_not_null())
      .join(read(DATA, "players.csv").select("nfl_id", "draft_overall_pick"), on="nfl_id")
      .with_columns(pl.col("draft_overall_pick").fill_null(260).cast(pl.Float64).log().alias("log_pick")))

y = df["eb_rate"].to_numpy()
col = {c: df[c].to_numpy() for c in ("log_pick", "ten_yd_split", "edge_share", "forty_burst15_mean")}
sets = [("draft slot", ["log_pick"]),
        ("draft slot + 10-yd split + role", ["log_pick", "ten_yd_split", "edge_share"]),
        ("draft slot + 10-yd split + role + Combine first step", ["log_pick", "ten_yd_split", "edge_share", "forty_burst15_mean"]),
        ("Combine first step alone", ["forty_burst15_mean"])]
print(f"players {df.height}; outcome: pressure rate shrunk for sample size")
for label, cs in sets:
    print(f"  leave-one-out R2  {label:55s} {loo_r2(y, np.column_stack([col[c] for c in cs])):+.3f}")
