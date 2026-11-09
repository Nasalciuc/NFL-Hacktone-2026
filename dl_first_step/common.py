"""Shared helpers for the DL first-step project."""
import os
import warnings

import numpy as np
import polars as pl
from scipy import optimize, special

KEY = ["game_id", "play_id", "nfl_id"]
REP = ["event_id", "nfl_id", "attempt"]


def _print_warning(message, category, filename, lineno, file=None, line=None):
    """Show warnings in the logs (stdout), without local file paths."""
    print(f"WARNING {category.__name__}: {str(message).splitlines()[0][:200]}", flush=True)


warnings.showwarning = _print_warning


def eligible_plays(plays, games=None, rushers_only=True):
    """Regular-season DL pass rushes used by every analysis.

    Stance start, lined up on the edge or the interior, not nullified by a penalty and, by default,
    the player actually rushed (`blitzing` true; see "Abateri" in ANALYSIS_PLAN.md). With `games`,
    also adds the score difference from the defense's side and groups formations with fewer than
    100 plays as OTHER, which the play-level models need.
    """
    e = plays.filter(pl.col("stance_start") & pl.col("lined_up_position").is_in(["EDGE", "INTERIOR_LINE"])
                     & (pl.col("play_nullified_by_penalty") == "N"))
    if games is not None:
        e = (e.join(games.select("game_id", "home_team_abbr"), on="game_id")
             .with_columns(pl.when(pl.col("team_abbr") == pl.col("home_team_abbr"))
                           .then(pl.col("pre_snap_home_score") - pl.col("pre_snap_visitor_score"))
                           .otherwise(pl.col("pre_snap_visitor_score") - pl.col("pre_snap_home_score")).alias("score_diff_def")))
    e = e.with_columns((pl.col("lined_up_position") == "EDGE").cast(pl.Float64).alias("edge"),
                       pl.col("pressure").cast(pl.Float64).alias("pressure_f"))
    if rushers_only:
        e = e.filter(pl.col("blitzing") == True)
    if games is not None:
        rare = e.group_by("offense_formation").len().filter(pl.col("len") < 100)["offense_formation"]
        e = e.with_columns(pl.when(pl.col("offense_formation").is_null() | pl.col("offense_formation").is_in(rare.drop_nulls().implode()))
                           .then(pl.lit("OTHER")).otherwise(pl.col("offense_formation")).alias("offense_formation"))
    return e


def fit_beta_binomial(k, n):
    """Beta prior (a, b) for pressure rates, by maximum likelihood; stops if the fit does not converge."""
    k, n = np.asarray(k, float), np.asarray(n, float)

    def nll(p):
        a, b = np.exp(p)
        return -np.sum(special.betaln(k + a, n - k + b) - special.betaln(a, b))

    res = optimize.minimize(nll, x0=np.log([2.0, 20.0]), method="Nelder-Mead",
                            options={"xatol": 1e-8, "fatol": 1e-10, "maxiter": 5000})
    if not res.success:
        raise RuntimeError(f"beta-binomial fit did not converge: {res.message}")
    return np.exp(res.x)


def loo_errors(y, X):
    """Leave-one-out residuals of a linear regression with intercept (closed form)."""
    X1 = np.column_stack([np.ones(len(y)), X])
    H = X1 @ np.linalg.pinv(X1.T @ X1) @ X1.T
    return (y - H @ y) / (1 - np.diag(H))


def loo_r2(y, X):
    e = loo_errors(y, X)
    return 1 - (e ** 2).sum() / ((y - y.mean()) ** 2).sum()


def boot_ci(fn, n, rng, b):
    """Percentile 95% interval of fn(resampled indices); failed or undefined replicates are counted and reported."""
    vals, failed = [], 0
    for _ in range(b):
        k = rng.integers(0, n, n)
        try:
            v = fn(k)
        except Exception:
            failed += 1
            continue
        if np.isnan(v):
            failed += 1
        else:
            vals.append(v)
    if failed:
        print(f"   note: {failed} of {b} bootstrap replicates failed or were undefined and were dropped", flush=True)
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def residualize(v, Z):
    Z1 = np.column_stack([np.ones(len(v)), Z])
    return v - Z1 @ np.linalg.lstsq(Z1, v, rcond=None)[0]


def partial_r(x, y, Z, rng, b, rank=False):
    """Correlation of x and y after removing the linear effect of Z (ranks first if rank=True), with bootstrap CI."""
    from scipy.stats import rankdata
    x, y, Z = np.asarray(x, float), np.asarray(y, float), np.asarray(Z, float).reshape(len(x), -1)

    def r_of(k):
        xx, yy, ZZ = x[k], y[k], Z[k]
        if rank:
            xx, yy, ZZ = rankdata(xx), rankdata(yy), np.column_stack([rankdata(c) for c in ZZ.T])
        return np.corrcoef(residualize(xx, ZZ), residualize(yy, ZZ))[0, 1]

    return {"n": int(len(x)), "r": float(r_of(np.arange(len(x)))), "ci": boot_ci(r_of, len(x), rng, b)}


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
