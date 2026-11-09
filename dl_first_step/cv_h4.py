"""Leave-one-out check of the Combine -> pressure link (H4), with draft slot controlled.

Descriptive, added on 9 Nov 2026 to complete the week-4 item "test with cross-validation and
draft control". It is not a new pre-registered test; the H4 result stays the one in tests.py.

Usage: python cv_h4.py DATA_DIR OUT_DIR
"""
import os
import sys

import numpy as np
import polars as pl
from scipy import optimize, special

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import read

DATA, OUT = sys.argv[1], sys.argv[2]
plays = pl.read_parquet(os.path.join(OUT, "game_rush_plays.parquet"))
elig = plays.filter(pl.col("stance_start") & pl.col("lined_up_position").is_in(["EDGE", "INTERIOR_LINE"])
                    & (pl.col("play_nullified_by_penalty") == "N") & (pl.col("blitzing") == True))
gp = elig.group_by("nfl_id").agg(pl.len().alias("rushes"), (pl.col("lined_up_position") == "EDGE").mean().alias("edge_share"),
                                 pl.col("pressure").cast(pl.Float64).sum().alias("pressures"))
k, n = gp["pressures"].to_numpy(), gp["rushes"].to_numpy()
nll = lambda p: -np.sum(special.betaln(k + np.exp(p[0]), n - k + np.exp(p[1])) - special.betaln(np.exp(p[0]), np.exp(p[1])))
a, b = np.exp(optimize.minimize(nll, np.log([2.0, 20.0]), method="Nelder-Mead").x)
df = (gp.with_columns(((pl.col("pressures") + a) / (pl.col("rushes") + a + b)).alias("eb_rate"))
      .filter(pl.col("rushes") >= 50)
      .join(pl.read_parquet(os.path.join(OUT, "combine_dl_players.parquet")), on="nfl_id")
      .filter(pl.col("forty_burst15_mean").is_not_null())
      .join(read(DATA, "players.csv").select("nfl_id", "draft_overall_pick"), on="nfl_id")
      .with_columns(pl.col("draft_overall_pick").fill_null(260).cast(pl.Float64).log().alias("log_pick")))


def loo_r2(y, X):
    X1 = np.column_stack([np.ones(len(y)), X])
    H = X1 @ np.linalg.pinv(X1.T @ X1) @ X1.T
    loo = (y - H @ y) / (1 - np.diag(H))
    return 1 - (loo ** 2).sum() / ((y - y.mean()) ** 2).sum()


y = df["eb_rate"].to_numpy()
col = {c: df[c].to_numpy() for c in ("log_pick", "ten_yd_split", "edge_share", "forty_burst15_mean")}
sets = [("draft slot", ["log_pick"]),
        ("draft slot + 10-yd split + role", ["log_pick", "ten_yd_split", "edge_share"]),
        ("draft slot + 10-yd split + role + Combine first step", ["log_pick", "ten_yd_split", "edge_share", "forty_burst15_mean"]),
        ("Combine first step alone", ["forty_burst15_mean"])]
print(f"players {df.height}; outcome: pressure rate shrunk for sample size")
for label, cs in sets:
    print(f"  leave-one-out R2  {label:55s} {loo_r2(y, np.column_stack([col[c] for c in cs])):+.3f}")
