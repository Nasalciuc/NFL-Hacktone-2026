"""Figures for the DL first-step writeup (corrected definition: plays where the player rushed).

Usage: python figures.py DATA_DIR OUT_DIR [WR_OUT_DIR]
Writes PNGs to dl_first_step/figures/.
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
from common import KEY, REP, anchored_measures, parse_time, read, split_half

DATA, OUT = sys.argv[1], sys.argv[2]
WR_OUT = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "..", "wr_breaks", "outputs")
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)

# reference palette (validated: blue / orange / aqua, light surface)
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
    ax.set_title(title, loc="left", fontsize=12.5, fontweight="semibold", color=INK, pad=26)
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


def sb(r):
    return 2 * r / (1 + r)


def loo_r2(y, X):
    X1 = np.column_stack([np.ones(len(y)), X])
    H = X1 @ np.linalg.pinv(X1.T @ X1) @ X1.T
    loo = (y - H @ y) / (1 - np.diag(H))
    return 1 - (loo ** 2).sum() / ((y - y.mean()) ** 2).sum()


# ---------------------------------------------------------------- data
plays = pl.read_parquet(os.path.join(OUT, "game_rush_plays.parquet"))
elig = plays.filter(pl.col("stance_start") & pl.col("lined_up_position").is_in(list(ALIGN))
                    & (pl.col("play_nullified_by_penalty") == "N") & (pl.col("blitzing") == True))
comb = pl.read_parquet(os.path.join(OUT, "combine_dl_players.parquet"))
players = read(DATA, "players.csv")
res = json.load(open(os.path.join(OUT, "tests_results_rushers_only.json")))

gp = elig.group_by("nfl_id").agg(pl.len().alias("rushes"), pl.col("burst_15").mean().alias("g_burst15"),
                                 (pl.col("lined_up_position") == "EDGE").mean().alias("edge_share"),
                                 pl.col("pressure").cast(pl.Float64).sum().alias("pressures"))
k, n = gp["pressures"].to_numpy(), gp["rushes"].to_numpy()
nll = lambda p: -np.sum(special.betaln(k + np.exp(p[0]), n - k + np.exp(p[1])) - special.betaln(np.exp(p[0]), np.exp(p[1])))
a, b = np.exp(optimize.minimize(nll, np.log([2.0, 20.0]), method="Nelder-Mead").x)
df = (gp.with_columns(((pl.col("pressures") + a) / (pl.col("rushes") + a + b)).alias("eb_rate"))
      .filter(pl.col("rushes") >= 50).join(comb, on="nfl_id").filter(pl.col("forty_burst15_mean").is_not_null())
      .join(players.select("nfl_id", "draft_overall_pick"), on="nfl_id")
      .with_columns(pl.when(pl.col("edge_share") >= 0.5).then(pl.lit("EDGE")).otherwise(pl.lit("INTERIOR_LINE")).alias("role")))
print(f"players in main sample: {df.height}")

# ---------------------------------------------------------------- F1 speed curves
parts = []
for year in (2023, 2024, 2025):
    t = read(DATA, f"game_tracking_{year}.csv", schema_overrides={"time": pl.Utf8, "event": pl.Utf8})
    parts.append(t.join(elig.select(KEY), on=KEY, how="semi"))
tr = parse_time(pl.concat(parts)).sort(KEY + ["time"])
snap = tr.filter(pl.col("event") == "ball_snap").group_by(KEY).agg(pl.col("time").min().alias("snap"))
tr = (tr.join(snap, on=KEY).join(elig.select(KEY + ["lined_up_position", "t_react"]), on=KEY)
      .with_columns(((pl.col("time") - pl.col("snap")).dt.total_milliseconds() / 1000).alias("t")))
by_snap = (tr.filter((pl.col("t") >= 0) & (pl.col("t") <= 2.0)).group_by("lined_up_position", "t")
           .agg(pl.col("s").mean().alias("s")).sort("t"))
rel = (tr.with_columns(((pl.col("t") - pl.col("t_react")) * 10).floor().alias("b"))
       .filter((pl.col("b") >= 0) & (pl.col("b") <= 15)).group_by("lined_up_position", "b").agg(pl.col("s").mean().alias("s")).sort("b"))
cmb = read(DATA, "combine_results.csv")
ct = read(DATA, "combine_tracking.csv", schema_overrides={"time": pl.Utf8})
ct = (parse_time(ct).join(cmb.filter(pl.col("combine_position") == "DL").select("nfl_id"), on="nfl_id")
      .filter((pl.col("entity_type") == "PLAYER") & (pl.col("drill_name") == "FORTY_YARD_DASH")).sort(REP + ["time"])
      .with_columns(((pl.col("time") - pl.col("time").first().over(REP)).dt.total_milliseconds() / 1000).alias("t")))
anc = anchored_measures(ct, REP, 1.5)
crel = (ct.join(anc.select(REP + ["t_on"]), on=REP).with_columns(((pl.col("t") - pl.col("t_on")) * 10).floor().alias("b"))
        .filter((pl.col("b") >= 0) & (pl.col("b") <= 15)).group_by("b").agg(pl.col("s").mean().alias("s")).sort("b"))
react_med = elig.group_by("lined_up_position").agg(pl.col("t_react").median()).rows()

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.4), gridspec_kw={"wspace": 0.28})
for key, (label, color) in ALIGN.items():
    d = by_snap.filter(pl.col("lined_up_position") == key)
    ax1.plot(d["t"], d["s"], color=color, label=label)
    r = dict(react_med)[key]
    ax1.axvline(r, color=color, lw=1, alpha=0.6)
    d2 = rel.filter(pl.col("lined_up_position") == key)
    ax2.plot(d2["b"] / 10 + 0.05, d2["s"], color=color, label=f"NFL, {label.lower()}")
ax1.text(dict(react_med)["EDGE"] + 0.03, 0.3, f"median time to 1 yd/s:\n{dict(react_med)['EDGE']:.2f} s edge, "
         f"{dict(react_med)['INTERIOR_LINE']:.2f} s interior", fontsize=8.5, color=INK2)
ax2.plot(crel["b"] / 10 + 0.05, crel["s"], color=AQUA, label="Combine 40-yard dash")
ax2.text(1.57, crel["s"][-1], "Combine 40", color=INK2, fontsize=9, va="center")
for key, (label, color) in ALIGN.items():
    d2 = rel.filter(pl.col("lined_up_position") == key)
    ax2.text(1.57, d2["s"][-1], label, color=INK2, fontsize=9, va="center")
for ax in (ax1, ax2):
    style(ax)
    ax.set_ylabel("speed (yd/s)")
    ax.set_ylim(0, 7.5)
ax1.set_xlabel("seconds after the snap")
ax2.set_xlabel("seconds after first reaching 1 yd/s")
ax2.set_xlim(0, 1.85)
ax1.legend(loc="upper left")
heading(ax1, "Two pieces of an NFL get-off", "Average pass-rush speed after the snap, regular season 2023-25")
heading(ax2, "Only the second piece exists at the Combine", "Same clock for both: starts when the player reaches 1 yd/s")
save(fig, "f1_speed_curves.png")

# ---------------------------------------------------------------- F2 reliability
creps = pl.read_parquet(os.path.join(OUT, "combine_reps.parquet")).filter(
    (pl.col("drill_name") == "FORTY_YARD_DASH") & (pl.col("combine_position") == "DL"))
rows = []
for col, label in (("burst_15", "First step, 1.5 yd"), ("burst_25", "First step, 2.5 yd"), ("acc_1to3", "Acceleration 1 to 3 yd/s")):
    _, rc, _ = split_half(creps, col, 1, order="attempt")
    _, rg, _ = split_half(elig, col, 25)
    rows.append((label, sb(rc), sb(rg)))
_, rg, _ = split_half(elig, "t_react", 25)
rows.append(("Reaction: snap to 1 yd/s", None, sb(rg)))
_, rg, _ = split_half(elig, "player_get_off", 25)
rows.append(("Official NGS get-off", None, sb(rg)))
wr_reps = pl.read_parquet(os.path.join(WR_OUT, "wr_combine_reps_dip70.parquet"))
good = ["COMEBACK_ROUTE_RIGHT", "CURL_ROUTE_RIGHT", "SLOT_STRIKE_ROUTE_LEFT"]
wr_reps = (wr_reps.filter(pl.col("drill_name").is_in(good) & (pl.col("s_first") < 1.0))
           .with_columns(((pl.col("decel") - pl.col("decel").mean().over("drill_name")) / pl.col("decel").std().over("drill_name")).alias("dz"),
                         pl.col("drill_name").replace_strict({d: i for i, d in enumerate(good)}).alias("o")))
_, rc, _ = split_half(wr_reps, "dz", 1, order="o")
wr_routes = pl.read_parquet(os.path.join(WR_OUT, "wr_game_routes_dip70.parquet")).filter(pl.col("play_nullified_by_penalty") == "N")
_, rg, _ = split_half(wr_routes, "separation_at_pass_forward", 25)
rows.append(("WR: braking into the break", sb(rc), None))
rows.append(("WR: separation at the throw", None, sb(rg)))
print("reliability rows:", [(r[0], None if r[1] is None else round(r[1], 2), None if r[2] is None else round(r[2], 2)) for r in rows])

fig, ax = plt.subplots(figsize=(8.6, 4.4))
ys = np.arange(len(rows))[::-1]
for y, (label, rc, rg) in zip(ys, rows):
    if rc is not None and rg is not None:
        ax.plot([rc, rg], [y, y], color=GRID, lw=2, zorder=1)
    if rc is not None:
        ax.scatter(rc, y, s=70, color=AQUA, edgecolor=SURF, linewidth=2, zorder=3)
        ax.text(rc, y + 0.28, f"{rc:.2f}", ha="center", fontsize=8.5, color=INK2)
    if rg is not None:
        ax.scatter(rg, y, s=70, color=INK2, edgecolor=SURF, linewidth=2, zorder=3)
        ax.text(rg, y + 0.28, f"{rg:.2f}", ha="center", fontsize=8.5, color=INK2)
ax.set_yticks(ys, [r[0] for r in rows], color=INK)
ax.set_xlim(0, 1.02)
ax.set_xlabel("reliability (share of player-to-player differences that is real, not noise)")
ax.scatter([], [], s=70, color=AQUA, label="Combine (average of the player's attempts or drills)")
ax.scatter([], [], s=70, color=INK2, label="NFL regular season (all of the player's plays)")
ax.legend(loc="upper left", bbox_to_anchor=(-0.02, -0.16), ncol=2, fontsize=9)
style(ax, grid="x")
heading(ax, "Games measure a pass rusher's first step far better than the Combine does",
        "Reliability of each measure, from odd vs even games or attempts (Spearman-Brown)")
save(fig, "f2_reliability.png")

# ---------------------------------------------------------------- F3 pressure vs in-game first step
fig, ax = plt.subplots(figsize=(8.2, 4.6))
bins = (elig.drop_nulls("burst_15")
        .with_columns(((pl.col("burst_15").rank("ordinal").over("lined_up_position") - 1) * 10
                       // pl.len().over("lined_up_position")).alias("dec")))
for key, (label, color) in ALIGN.items():
    d = (bins.filter(pl.col("lined_up_position") == key).group_by("dec")
         .agg(pl.col("burst_15").median().alias("x"), pl.col("pressure").sum().alias("k"), pl.len().alias("n")).sort("dec"))
    p = (d["k"] / d["n"]).to_numpy()
    lo, hi = wilson(d["k"].to_numpy(), d["n"].to_numpy())
    ax.vlines(d["x"], lo * 100, hi * 100, color=color, lw=1.2, alpha=0.5)
    ax.plot(d["x"], p * 100, color=color, marker="o", ms=7, mec=SURF, mew=2, label=label)
h3 = res["robustness"]["H3_all_players"]
ax.text(0.98, 0.95, f"Logistic model, situation held equal ({h3['players']} DL):\n1 SD faster first step: {100 * h3['rate_fast_1sd']:.1f}% pressure\n"
        f"1 SD slower: {100 * h3['rate_slow_1sd']:.1f}% pressure", transform=ax.transAxes, ha="right", va="top", fontsize=9, color=INK2)
ax.set_xlabel("in-game first step: seconds to cover 1.5 yd after reaching 1 yd/s (deciles)")
ax.set_ylabel("plays with a pressure (%)")
handles = [matplotlib.lines.Line2D([0], [0], color=c, lw=2, marker="o", ms=6, mec=c) for _, c in ALIGN.values()]
ax.legend(handles, [lab for lab, _ in ALIGN.values()], loc="lower left")
style(ax)
heading(ax, "A faster first step in the game comes with more pressure",
        f"Regular-season pass rushes by {elig['nfl_id'].n_unique()} DL from the 2023-25 draft classes; bars are 95% CIs")
save(fig, "f3_pressure_vs_first_step.png")

# ---------------------------------------------------------------- F4 Combine vs NFL first step
fig, ax = plt.subplots(figsize=(7.6, 5.0))
for key, (label, color) in ALIGN.items():
    d = df.filter(pl.col("role") == key)
    x, y = d["forty_burst15_mean"].to_numpy(), d["g_burst15"].to_numpy()
    r = np.corrcoef(x, y)[0, 1]
    ax.scatter(x, y, s=48, color=color, edgecolor=SURF, linewidth=1.5, label=f"Mostly {label.lower()} (n = {len(x)}, r = {r:+.2f})", zorder=3)
    kf, c0 = np.polyfit(x, y, 1)
    xx = np.linspace(x.min(), x.max(), 20)
    ax.plot(xx, kf * xx + c0, color=color, lw=1.5)
h1 = res["H1"]
ax.text(0.98, 0.04, f"All 62 players: r = {h1['r']:+.2f} (95% CI {h1['ci'][0]:+.2f} to {h1['ci'][1]:+.2f})\n"
        f"after weight and role: {h1['adjusted_beta_std']:+.2f} SD", transform=ax.transAxes, ha="right", fontsize=9, color=INK2)
ax.set_xlabel("Combine first step: 40-yard dash, seconds for 1.5 yd")
ax.set_ylabel("NFL first step: same measure, average per player")
ax.legend(loc="upper left", bbox_to_anchor=(-0.02, -0.13), ncol=2, fontsize=9)
style(ax, grid="both")
heading(ax, "The Combine first step does not carry over", "Role, not the 40-yard start, separates the two groups")
save(fig, "f4_combine_vs_nfl.png")

# ---------------------------------------------------------------- F5 what explains the NFL first step
y = df["g_burst15"].to_numpy()
cols = {"edge": df["edge_share"].to_numpy(), "w": df["combine_weight"].to_numpy(),
        "ten": df["ten_yd_split"].to_numpy(), "cb": df["forty_burst15_mean"].to_numpy()}
sets = [("Role (share of snaps on the edge)", ["edge"]), ("Weight", ["w"]), ("Official 10-yard split (stopwatch)", ["ten"]),
        ("Combine first step (tracking)", ["cb"]), ("Role + weight", ["edge", "w"]), ("Role + weight + Combine first step", ["edge", "w", "cb"])]
vals = [(label, loo_r2(y, np.column_stack([cols[c] for c in cs]))) for label, cs in sets]
print("leave-one-out R2:", [(l, round(v, 3)) for l, v in vals])
fig, ax = plt.subplots(figsize=(8.2, 4.0))
ys = np.arange(len(vals))[::-1]
for yv, (label, v) in zip(ys, vals):
    color = AQUA if "tracking" in label else INK2
    ax.barh(yv, max(v, 0), height=0.5, color=color)
    ax.text(max(v, 0) + 0.01, yv, f"{v:+.2f}", va="center", fontsize=9, color=INK2)
ax.set_yticks(ys, [v[0] for v in vals], color=INK)
ax.set_xlim(0, 0.8)
ax.set_xlabel("share of the NFL first step explained in players left out of the fit (leave-one-out R²)")
style(ax, grid="x")
heading(ax, "Role and size explain the NFL first step; the Combine first step adds nothing",
        "62 DL; negative values mean worse than guessing the average")
save(fig, "f5_what_explains_nfl_first_step.png")

# ---------------------------------------------------------------- F6 Combine first step vs pressure, by role
fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.3), sharey=True, gridspec_kw={"wspace": 0.12})
for ax, (key, (label, color)) in zip(axes, ALIGN.items()):
    d = df.filter(pl.col("role") == key)
    x, yv = d["forty_burst15_mean"].to_numpy(), 100 * d["eb_rate"].to_numpy()
    r, p = stats.pearsonr(x, yv)
    ax.scatter(x, yv, s=48, color=color, edgecolor=SURF, linewidth=1.5, zorder=3)
    kf, c0 = np.polyfit(x, yv, 1)
    xx = np.linspace(x.min(), x.max(), 20)
    ax.plot(xx, kf * xx + c0, color=color, lw=1.5)
    note = f"n = {len(x)}, r = {r:+.2f}, p = {p:.3f}"
    if key == "INTERIOR_LINE":
        keep = x < x.max()
        r2, p2 = stats.pearsonr(x[keep], yv[keep])
        note += f"\nwithout the slowest Combine starter: r = {r2:+.2f}, p = {p2:.3f}"
    ax.text(0.98, 0.95, note, transform=ax.transAxes, ha="right", va="top", fontsize=9, color=INK2)
    ax.set_xlabel("Combine first step (s for 1.5 yd)")
    style(ax, grid="both")
    ax.set_title(f"Mostly {label.lower()}", loc="left", fontsize=10.5, color=INK)
axes[0].set_ylabel("pressure rate, shrunk for sample size (%)")
fig.suptitle("Only interior linemen show a link between Combine first step and NFL pressure", x=0.125, ha="left",
             fontsize=12.5, fontweight="semibold", y=1.06)
fig.text(0.125, 0.985, "Exploratory: one of about 20 robustness checks, not a pre-registered test", fontsize=9.5, color=INK2)
save(fig, "f6_pressure_by_role.png")
