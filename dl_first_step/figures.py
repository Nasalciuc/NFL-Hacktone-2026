"""Figures for the DL first-step writeup, in hypothesis order (corrected definition: plays where the player rushed).

F1 speed curves, F2 reliability, F3 = H1, F4 = H2, F5 = H3, F6 = H4.
Usage: python figures.py DATA_DIR OUT_DIR [WR_OUT_DIR]
Needs tests_results_rushers_only.json (tests.py) and review_round2.json (review_round2.py) in OUT_DIR.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from scipy import optimize, special, stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import KEY, REP, anchored_measures, parse_time, read

DATA, OUT = sys.argv[1], sys.argv[2]
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)

# reference palette (validated: blue / orange / aqua on the light surface)
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
ALIGN = {"EDGE": ("Edge", BLUE), "INTERIOR_LINE": ("Interior", ORANGE)}
plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10, "axes.facecolor": SURF, "figure.facecolor": SURF,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
    "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.8, "lines.linewidth": 2,
    "lines.solid_capstyle": "round", "legend.frameon": False, "savefig.dpi": 150, "savefig.bbox": "tight"})


def style(ax, grid="y"):
    ax.grid(axis=grid, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def heading(ax, title, sub):
    ax.set_title(title, loc="left", fontsize=12.5, fontweight="bold", color=INK, pad=26)
    ax.text(0, 1.035, sub, transform=ax.transAxes, fontsize=9.5, color=INK2, va="bottom")


def save(fig, name):
    fig.savefig(os.path.join(FIG, name))
    plt.close(fig)
    print("saved", name)


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def fit_prior(k, n):
    nll = lambda p: -np.sum(special.betaln(k + np.exp(p[0]), n - k + np.exp(p[1])) - special.betaln(np.exp(p[0]), np.exp(p[1])))
    return np.exp(optimize.minimize(nll, np.log([2.0, 20.0]), method="Nelder-Mead").x)


# ---------------------------------------------------------------- data
plays = pl.read_parquet(os.path.join(OUT, "game_rush_plays.parquet"))
elig = plays.filter(pl.col("stance_start") & pl.col("lined_up_position").is_in(list(ALIGN))
                    & (pl.col("play_nullified_by_penalty") == "N") & (pl.col("blitzing") == True))
comb = pl.read_parquet(os.path.join(OUT, "combine_dl_players.parquet"))
players = read(DATA, "players.csv")
res = json.load(open(os.path.join(OUT, "tests_results_rushers_only.json")))
rev = json.load(open(os.path.join(OUT, "review_round2.json")))

gp = (elig.group_by("nfl_id").agg(pl.len().alias("rushes"), pl.col("burst_15").mean().alias("g_burst15"),
                                  (pl.col("lined_up_position") == "EDGE").mean().alias("edge_share"),
                                  pl.col("pressure").cast(pl.Float64).sum().alias("pressures"))
      .with_columns(pl.when(pl.col("edge_share") >= 0.5).then(pl.lit("EDGE")).otherwise(pl.lit("INTERIOR_LINE")).alias("role")))
prior = {r: fit_prior(gp.filter(pl.col("role") == r)["pressures"].to_numpy(), gp.filter(pl.col("role") == r)["rushes"].to_numpy())
         for r in ALIGN}
gp = gp.with_columns(pl.when(pl.col("role") == "EDGE")
                     .then((pl.col("pressures") + prior["EDGE"][0]) / (pl.col("rushes") + prior["EDGE"].sum()))
                     .otherwise((pl.col("pressures") + prior["INTERIOR_LINE"][0]) / (pl.col("rushes") + prior["INTERIOR_LINE"].sum()))
                     .alias("eb_group"))
df = (gp.filter(pl.col("rushes") >= 50).join(comb, on="nfl_id").filter(pl.col("forty_burst15_mean").is_not_null())
      .join(players.select("nfl_id", "draft_overall_pick"), on="nfl_id"))
print(f"players in main sample: {df.height}")

# ---------------------------------------------------------------- F1 speed curves (median and interquartile band)
parts = []
for year in (2023, 2024, 2025):
    t = read(DATA, f"game_tracking_{year}.csv", schema_overrides={"time": pl.Utf8, "event": pl.Utf8})
    parts.append(t.join(elig.select(KEY), on=KEY, how="semi"))
tr = parse_time(pl.concat(parts)).sort(KEY + ["time"])
snap = tr.filter(pl.col("event") == "ball_snap").group_by(KEY).agg(pl.col("time").min().alias("snap"))
tr = (tr.join(snap, on=KEY).join(elig.select(KEY + ["lined_up_position", "t_react"]), on=KEY)
      .with_columns(((pl.col("time") - pl.col("snap")).dt.total_milliseconds() / 1000).alias("t")))
q = [pl.col("s").median().alias("med"), pl.col("s").quantile(0.25).alias("q25"), pl.col("s").quantile(0.75).alias("q75")]
by_snap = tr.filter((pl.col("t") >= 0) & (pl.col("t") <= 2.0)).group_by("lined_up_position", "t").agg(q).sort("t")
rel = (tr.with_columns(((pl.col("t") - pl.col("t_react")) * 10).floor().alias("b"))
       .filter((pl.col("b") >= 0) & (pl.col("b") <= 15)).group_by("lined_up_position", "b").agg(q).sort("b"))
cmb = read(DATA, "combine_results.csv")
ct = read(DATA, "combine_tracking.csv", schema_overrides={"time": pl.Utf8})
ct = (parse_time(ct).join(cmb.filter(pl.col("combine_position") == "DL").select("nfl_id"), on="nfl_id")
      .filter((pl.col("entity_type") == "PLAYER") & (pl.col("drill_name") == "FORTY_YARD_DASH")).sort(REP + ["time"])
      .with_columns(((pl.col("time") - pl.col("time").first().over(REP)).dt.total_milliseconds() / 1000).alias("t")))
anc = anchored_measures(ct, REP, 1.5)
crel = (ct.join(anc.select(REP + ["t_on"]), on=REP).with_columns(((pl.col("t") - pl.col("t_on")) * 10).floor().alias("b"))
        .filter((pl.col("b") >= 0) & (pl.col("b") <= 15)).group_by("b").agg(q).sort("b"))
react_med = dict(elig.group_by("lined_up_position").agg(pl.col("t_react").median()).rows())
burst_end = dict(elig.group_by("lined_up_position").agg(pl.col("burst_15").median()).rows())

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"wspace": 0.28})
for key, (label, color) in ALIGN.items():
    d = by_snap.filter(pl.col("lined_up_position") == key)
    ax1.fill_between(d["t"], d["q25"], d["q75"], color=color, alpha=0.12, lw=0)
    ax1.plot(d["t"], d["med"], color=color, label=label)
    ax1.axvline(react_med[key], color=color, lw=1, alpha=0.6)
    d2 = rel.filter(pl.col("lined_up_position") == key)
    ax2.fill_between(d2["b"] / 10 + 0.05, d2["q25"], d2["q75"], color=color, alpha=0.12, lw=0)
    ax2.plot(d2["b"] / 10 + 0.05, d2["med"], color=color)
    ax2.text(1.57, d2["med"][-1], label, color=INK2, fontsize=9, va="center")
    ax2.plot([burst_end[key]] * 2, [0, 0.35], color=color, lw=2)
ax1.text(react_med["INTERIOR_LINE"] + 0.04, 0.25, f"median time to 1 yd/s:\n{react_med['EDGE']:.2f} s edge, "
         f"{react_med['INTERIOR_LINE']:.2f} s interior", fontsize=8.5, color=INK2)
ax2.fill_between(crel["b"] / 10 + 0.05, crel["q25"], crel["q75"], color=AQUA, alpha=0.12, lw=0)
ax2.plot(crel["b"] / 10 + 0.05, crel["med"], color=AQUA)
ax2.text(1.57, crel["med"][-1], "Combine 40", color=INK2, fontsize=9, va="center")
ax2.text(0.03, 0.45, "ticks on the x-axis: where the 1.5-yd first step\nends in games (median, edge and interior)", fontsize=8, color=INK2)
for ax in (ax1, ax2):
    style(ax)
    ax.set_ylabel("speed (yd/s)")
    ax.set_ylim(0, 8.5)
ax1.set_xlabel("seconds after the snap")
ax2.set_xlabel("seconds after first reaching 1 yd/s")
ax2.set_xlim(0, 1.85)
ax1.legend(loc="upper left")
heading(ax1, "Two pieces of an NFL get-off", "Pass-rush speed after the snap, regular season 2023-25: median and middle 50%")
heading(ax2, "Interior speed flattens almost at once", "Same clock for both: starts when the player reaches 1 yd/s")
save(fig, "f1_speed_curves.png")

# ---------------------------------------------------------------- F2 reliability: per trial and per player
rl = rev["reliability"]
rows = [("First step, 1.5 yd", "burst_15"), ("First step, 0.5 yd", "burst_05"), ("Acceleration, first 0.2 s", "acc_02"),
        ("Reaction: snap to 1 yd/s", "t_react")]
fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.9), sharey=True, gridspec_kw={"wspace": 0.08})
for ax, (title, ckey, gkey) in zip(axes, (("One trial", "combine_single_attempt", "nfl_single_play_role_adjusted"),
                                          ("One player", "combine_mean_of_attempts", "nfl_season_role_adjusted"))):
    ys = np.arange(len(rows))[::-1]
    for y, (label, key) in zip(ys, rows):
        cv, gv = rl[key].get(ckey), rl[key][gkey]
        close = cv is not None and abs(cv - gv) < 0.1
        if cv is not None:
            ax.plot([cv, gv], [y, y], color=GRID, lw=2, zorder=1)
            ax.scatter(cv, y, s=70, color=AQUA, edgecolor=SURF, linewidth=2, zorder=3)
            ax.text(cv - (0.02 if close else 0), y + 0.27, f"{cv:.2f}", ha="right" if close else "center", fontsize=8.5, color=INK2)
        ax.scatter(gv, y, s=70, color=INK2, edgecolor=SURF, linewidth=2, zorder=3)
        ax.text(gv + (0.02 if close else 0), y + 0.27, f"{gv:.2f}", ha="left" if close else "center", fontsize=8.5, color=INK2)
    ax.set_yticks(ys, [r[0] for r in rows], color=INK)
    ax.set_xlim(-0.03, 1.03)
    ax.set_ylim(-0.6, len(rows) - 0.3)
    style(ax, grid="x")
    ax.set_title(title, loc="left", fontsize=10.5, color=INK)
axes[0].set_xlabel("one 40 attempt vs one NFL snap")
axes[1].set_xlabel("mean of ~2 attempts vs a season of snaps")
axes[0].scatter([], [], s=70, color=AQUA, label="Combine 40-yard dash")
axes[0].scatter([], [], s=70, color=INK2, label="NFL regular season, edge and interior each centred on their own mean")
axes[0].legend(loc="upper left", bbox_to_anchor=(-0.02, -0.2), ncol=2, fontsize=9)
fig.suptitle("Per trial the Combine is the cleaner measurement; games win by volume", x=0.125, ha="left",
             fontsize=12.5, fontweight="bold", y=1.07)
fig.text(0.125, 0.99, "Reliability = share of player-to-player differences that is real, not noise (odd vs even games or attempts)",
         fontsize=9.5, color=INK2)
save(fig, "f2_reliability.png")

# ---------------------------------------------------------------- F3 (H1) Combine vs NFL first step, and transfer by window
tw = rev["transfer_by_window"]
fig, (ax, axr) = plt.subplots(1, 2, figsize=(12, 5.0), gridspec_kw={"width_ratios": [1.15, 1], "wspace": 0.42})
for key, (label, color) in ALIGN.items():
    d = df.filter(pl.col("role") == key)
    x, y = d["forty_burst15_mean"].to_numpy(), d["g_burst15"].to_numpy()
    c = tw["1.5 yd"][key]
    ax.scatter(x, y, s=48, color=color, edgecolor=SURF, linewidth=1.5, zorder=3,
               label=f"Mostly {label.lower()}: n = {len(x)}, r = {c['r']:+.2f} [{c['ci'][0]:+.2f}, {c['ci'][1]:+.2f}]")
    kf, c0 = np.polyfit(x, y, 1)
    xx = np.linspace(x.min(), x.max(), 20)
    ax.plot(xx, kf * xx + c0, color=color, lw=1.5)
h1, dis = res["H1"], rev["disattenuation"]
ax.text(0.0, -0.30, f"All 62: r = {h1['r']:+.2f} [{h1['ci'][0]:+.2f}, {h1['ci'][1]:+.2f}]\n"
        f"after weight and role: {h1['adjusted_beta_std']:+.2f} SD [{h1['adjusted_ci_std'][0]:+.2f}, {h1['adjusted_ci_std'][1]:+.2f}]\n"
        f"corrected for measurement noise: {dis['r_partial_corrected']:+.2f} [{dis['ci_partial_corrected'][0]:+.2f}, {dis['ci_partial_corrected'][1]:+.2f}]",
        transform=ax.transAxes, ha="left", va="top", fontsize=8.5, color=INK2)
ax.set_xlabel("Combine first step: 40-yard dash, seconds for 1.5 yd")
ax.set_ylabel("NFL first step: same measure, average per player")
ax.legend(loc="upper left", bbox_to_anchor=(-0.02, -0.12), ncol=1, fontsize=9)
style(ax, grid="both")
heading(ax, "No detectable carry-over of the Combine first step", "H1: role, not the 40-yard start, separates the groups")

labels, ys = [], []
y = 0
for win in ("0.5 yd", "first 0.2 s (accel.)", "1.5 yd"):
    for gkey, glabel, color in (("partial_weight_role", "all, after weight and role", INK2), ("EDGE", "edge", BLUE),
                                ("INTERIOR_LINE", "interior", ORANGE)):
        c = tw[win][gkey]
        axr.plot(c["ci"], [y, y], color=color, lw=2, alpha=0.55)
        axr.scatter(c["r"], y, s=55, color=color, edgecolor=SURF, linewidth=1.5, zorder=3)
        labels.append(f"{win}: {glabel}")
        ys.append(y)
        y -= 1
    y -= 0.6
axr.axvline(0, color=AXIS, lw=1)
axr.set_yticks(ys, labels, fontsize=8.5, color=INK)
axr.set_xlim(-0.65, 0.75)
axr.set_xlabel("correlation, Combine vs NFL (95% CI); positive = transfer")
style(axr, grid="x")
heading(axr, "Shorter windows do not rescue it", "Post-hoc: windows that end before most blocker contact")
save(fig, "f3_combine_vs_nfl.png")

# ---------------------------------------------------------------- F4 (H2) what explains the NFL first step
loo = rev["loo_r2"]
order = ["Role (share of snaps on the edge)", "Weight", "Official 10-yard split (stopwatch)", "Combine first step (tracking)",
         "Role + weight", "Role + weight + 10-yard split", "Role + weight + Combine first step"]
fig, ax = plt.subplots(figsize=(8.6, 4.4))
ys = np.arange(len(order))[::-1]
for yv, k in zip(ys, order):
    v, (lo, hi) = loo[k]["r2"], loo[k]["ci"]
    color = AQUA if "tracking" in k else INK2
    ax.barh(yv, max(v, 0), height=0.5, color=color)
    ax.plot([max(lo, 0), hi], [yv, yv], color=INK, lw=1)
    ax.text(hi + 0.012, yv, f"{v:+.2f}", va="center", fontsize=9, color=INK2)
ax.set_yticks(ys, order, color=INK)
ax.set_xlim(0, 0.9)
ax.set_xlabel("share of the NFL first step explained in players left out of the fit (leave-one-out R², 95% bootstrap CI)")
d1, d2 = loo["Role + weight + Combine first step minus Role + weight"], loo["Role + weight + 10-yard split minus Role + weight"]
ax.text(0, -0.2, f"Added to role + weight: Combine first step {d1['r2']:+.3f} [{d1['ci'][0]:+.3f}, {d1['ci'][1]:+.3f}], "
        f"10-yard split {d2['r2']:+.3f} [{d2['ci'][0]:+.3f}, {d2['ci'][1]:+.3f}].\nThe 10-yard split tracks weight (r = 0.84).",
        transform=ax.transAxes, ha="left", va="top", fontsize=8.5, color=INK2)
style(ax, grid="x")
heading(ax, "Role and size explain the NFL first step; neither Combine time adds to them",
        "H2, 62 DL. Role is observed in the NFL, so a scout would not know it before the draft")
save(fig, "f4_what_explains_nfl_first_step.png")

# ---------------------------------------------------------------- F5 (H3) pressure vs in-game first step
XMAX = 0.95
fig, ax = plt.subplots(figsize=(8.4, 4.7))
bins = (elig.drop_nulls("burst_15")
        .with_columns(((pl.col("burst_15").rank("ordinal").over("lined_up_position") - 1) * 10
                       // pl.len().over("lined_up_position")).alias("dec")))
for key, (label, color) in ALIGN.items():
    d = (bins.filter(pl.col("lined_up_position") == key).group_by("dec")
         .agg(pl.col("burst_15").median().alias("x"), pl.col("pressure").sum().alias("k"), pl.len().alias("n")).sort("dec"))
    x, p = d["x"].to_numpy(), (d["k"] / d["n"]).to_numpy() * 100
    lo, hi = wilson(d["k"].to_numpy(), d["n"].to_numpy())
    inside = x <= XMAX
    ax.vlines(x[inside], lo[inside] * 100, hi[inside] * 100, color=color, lw=1.2, alpha=0.5)
    ax.plot(x[inside], p[inside], color=color, marker="o", ms=7, mec=SURF, mew=2)
    for xo, po in zip(x[~inside], p[~inside]):
        ax.scatter(XMAX + 0.004, po, s=50, facecolor=SURF, edgecolor=color, linewidth=2, zorder=3)
        ax.annotate(f"slowest {label.lower()} decile, off the axis at {xo:.2f} s", (XMAX + 0.004, po), xytext=(-2, -16),
                    textcoords="offset points", ha="right", fontsize=8.5, color=INK2)
ax.set_xlim(0.53, XMAX + 0.015)
handles = [matplotlib.lines.Line2D([0], [0], color=c, lw=2, marker="o", ms=6, mec=c) for _, c in ALIGN.values()]
ax.legend(handles, [lab for lab, _ in ALIGN.values()], loc="lower left")
h3, fe = res["robustness"]["H3_all_players"], rev["H3_decomposed"]["all_98"]["burst_15"]
ax.text(0.98, 0.96, f"Situation held equal ({h3['players']} DL): 1 SD faster first step {100 * h3['rate_fast_1sd']:.1f}% pressure, "
        f"1 SD slower {100 * h3['rate_slow_1sd']:.1f}%\nSame player, faster than his own average (fixed effects): "
        f"OR {fe['fixed_effects_or']:.2f} per SD slower [{fe['fixed_effects_ci'][0]:.2f}, {fe['fixed_effects_ci'][1]:.2f}]",
        transform=ax.transAxes, ha="right", va="top", fontsize=8.5, color=INK2)
ax.set_xlabel("in-game first step: seconds to cover 1.5 yd after reaching 1 yd/s (deciles)")
ax.set_ylabel("plays with a pressure (%)")
style(ax)
heading(ax, "Plays with a faster first step are plays with more pressure",
        f"H3, regular-season pass rushes by {elig['nfl_id'].n_unique()} DL; bars are 95% CIs. An association: blocking also sets the first step")
save(fig, "f5_pressure_vs_first_step.png")

# ---------------------------------------------------------------- F6 (H4) Combine first step vs pressure, by role
pr = rev["pressure_by_role"]
fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.5), sharey=True, gridspec_kw={"wspace": 0.12})
for ax, (key, (label, color)) in zip(axes, ALIGN.items()):
    d = df.filter(pl.col("role") == key)
    x, yv = d["forty_burst15_mean"].to_numpy(), 100 * d["eb_group"].to_numpy()
    ax.scatter(x, yv, s=48, color=color, edgecolor=SURF, linewidth=1.5, zorder=3)
    kf, c0 = np.polyfit(x, yv, 1)
    xx = np.linspace(x.min(), x.max(), 20)
    ax.plot(xx, kf * xx + c0, color=color, lw=1.5)
    s = pr[key]
    c = s["r_group_shrink"]
    note = f"n = {c['n']}, r = {c['r']:+.2f} [{c['ci'][0]:+.2f}, {c['ci'][1]:+.2f}], p = {c['p']:.3f}"
    if key == "INTERIOR_LINE":
        pw = s["partial_weight_nt"]
        note += (f"\nafter weight and NT: r = {pw['r']:+.2f} [{pw['ci'][0]:+.2f}, {pw['ci'][1]:+.2f}]"
                 f"\ndropping any one player: r from {s['jackknife_min_max'][0]:+.2f} to {s['jackknife_min_max'][1]:+.2f}")
    else:
        pw = s["partial_weight"]
        note += f"\nafter weight: r = {pw['r']:+.2f} [{pw['ci'][0]:+.2f}, {pw['ci'][1]:+.2f}]"
    ax.text(0.98, 0.97, note, transform=ax.transAxes, ha="right", va="top", fontsize=8.5, color=INK2)
    ax.set_xlabel("Combine first step (s for 1.5 yd)")
    style(ax, grid="both")
    ax.set_title(f"Mostly {label.lower()}", loc="left", fontsize=10.5, color=INK)
axes[0].set_ylabel("pressure rate, shrunk toward the role's mean (%)")
fig.suptitle("Only interior linemen show a link between Combine first step and NFL pressure", x=0.125, ha="left",
             fontsize=12.5, fontweight="bold", y=1.07)
fig.text(0.125, 0.99, "H4, exploratory: one of about 20 checks (Bonferroni threshold p < 0.0025); "
         "it survives weight and nose-tackle controls", fontsize=9.5, color=INK2)
save(fig, "f6_pressure_by_role.png")
