"""Shared helpers for the DL first-step project."""
import os

import numpy as np
import polars as pl

KEY = ["game_id", "play_id", "nfl_id"]
REP = ["event_id", "nfl_id", "attempt"]


def read(data, name, **kw):
    return pl.read_csv(os.path.join(data, name), null_values=["NA", ""], infer_schema_length=200000, **kw)


def parse_time(df):
    return df.with_columns(pl.col("time").str.to_datetime("%Y-%m-%dT%H:%M:%S%.f"))


def first_crossing(df, keys, tcol, vcol, thr, name):
    """Time at which `vcol` first reaches `thr` in each group, interpolated between frames.

    `df` must be sorted by keys + tcol. Groups whose first value is already at or above
    `thr` get null, because their start was not recorded.
    """
    d = df.select(keys + [tcol, vcol]).with_columns(
        pl.col(vcol).shift(1).over(keys).alias("_vp"),
        pl.col(tcol).shift(1).over(keys).alias("_tp"),
    )
    hit = (d.filter((pl.col(vcol) >= thr) & (pl.col("_vp") < thr))
           .group_by(keys).agg(pl.all().sort_by(tcol).first()))
    t = pl.col("_tp") + (thr - pl.col("_vp")) / (pl.col(vcol) - pl.col("_vp")) * (pl.col(tcol) - pl.col("_tp"))
    res = hit.select(keys + [t.alias(name)])
    v0 = d.group_by(keys).agg(pl.col(vcol).sort_by(tcol).first().alias("_v0"))
    return (res.join(v0, on=keys)
            .with_columns(pl.when(pl.col("_v0") >= thr).then(None).otherwise(pl.col(name)).alias(name))
            .drop("_v0"))


def anchored_measures(df, keys, dist, s_on=1.0, s_hi=3.0, suffix=""):
    """First-step timing that does not depend on where a recording starts.

    The anchor is the moment speed first reaches `s_on` (interpolated), together with the
    position at that moment. Returns per group:
      t_on      time of the anchor (in games: seconds after the snap)
      burst     seconds to cover `dist` yards in a straight line from the anchor
      acc       seconds from `s_on` to `s_hi` yd/s
    `df` needs keys, t, x, y, s and must be sorted by keys + t. Groups already at `s_on`
    in their first frame are dropped, because their start was not recorded.
    """
    d = df.select(keys + ["t", "x", "y", "s"]).with_columns(
        *[pl.col(c).shift(1).over(keys).alias(f"{c}_p") for c in ("t", "x", "y", "s")])
    hit = (d.filter((pl.col("s") >= s_on) & (pl.col("s_p") < s_on))
           .group_by(keys).agg(pl.all().sort_by("t").first()))
    f = (s_on - pl.col("s_p")) / (pl.col("s") - pl.col("s_p"))
    anchor = hit.select(keys + [(pl.col(f"{c}_p") + f * (pl.col(c) - pl.col(f"{c}_p"))).alias(n)
                                for c, n in (("t", "t_on"), ("x", "xa"), ("y", "ya"))])
    s0 = d.group_by(keys).agg(pl.col("s").sort_by("t").first().alias("s0"))
    anchor = anchor.join(s0, on=keys).filter(pl.col("s0") < s_on).drop("s0")

    after = (df.select(keys + ["t", "x", "y"]).join(anchor, on=keys).filter(pl.col("t") > pl.col("t_on"))
             .select(keys + ["t", ((pl.col("x") - pl.col("xa")) ** 2 + (pl.col("y") - pl.col("ya")) ** 2).sqrt().alias("da")]))
    start = anchor.select(keys + [pl.col("t_on").alias("t"), pl.lit(0.0).alias("da")])
    seq = pl.concat([start, after]).sort(keys + ["t"])
    res = (anchor.select(keys + ["t_on"])
           .join(first_crossing(seq, keys, "t", "da", dist, "_t_d"), on=keys, how="left")
           .join(first_crossing(df, keys, "t", "s", s_hi, "_t_hi"), on=keys, how="left"))
    return res.select(keys + [pl.col("t_on").alias(f"t_on{suffix}"),
                              (pl.col("_t_d") - pl.col("t_on")).alias(f"burst{suffix}"),
                              (pl.col("_t_hi") - pl.col("t_on")).alias(f"acc{suffix}")])


def split_half(df, value, min_n, group="nfl_id", order="game_id"):
    """Player averages over odd vs even games (or attempts); returns (players, r, Spearman-Brown reliability)."""
    d = df.select(group, order, value).drop_nulls(value)
    d = d.with_columns((pl.col(order).rank("dense").over(group) % 2).alias("_half"))
    agg = d.group_by(group, "_half").agg(pl.col(value).mean().alias("m"), pl.len().alias("n"))
    a = agg.filter(pl.col("_half") == 0).select(group, pl.col("m").alias("m0"), pl.col("n").alias("n0"))
    b = agg.filter(pl.col("_half") == 1).select(group, pl.col("m").alias("m1"), pl.col("n").alias("n1"))
    w = a.join(b, on=group).filter((pl.col("n0") >= min_n) & (pl.col("n1") >= min_n))
    if w.height < 10:
        return w.height, float("nan"), float("nan")
    r = float(np.corrcoef(w["m0"], w["m1"])[0, 1])
    return w.height, r, 2 * r / (1 + r)


def corr(df, a, b):
    d = df.select(a, b).drop_nulls()
    return d.height, float(np.corrcoef(d[a], d[b])[0, 1]) if d.height > 2 else float("nan")
