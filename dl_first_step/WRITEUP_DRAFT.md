# Get-Off Is Two Skills. The Combine Clocks Only One.

*Linking 10 Hz Combine sensor data to regular-season pass rush for the 2023–25 draft classes*

## Why the first step

A pass rush is often won before the first block lands. Teams watch a rusher's *get-off* every week and pay for it in the draft. Combine sensors now record every prospect's 40-yard start at 10 Hz. So we ask: **does the first step a defensive lineman shows at the Combine become the first step he shows on Sundays, and does it turn into pressure?**

Before looking at any Combine-to-NFL relationship, we wrote down four hypotheses, the measures and the tests in a plan kept with the code. It is a written plan, not an external registration. Our answer is mostly *no*, and the reason is useful. An NFL get-off has two parts: reacting to the snap, and accelerating once moving. The Combine has no snap, so it can only time the second part. Even that part shows no detectable carry-over once body weight is known. In games, by contrast, plays with a faster first step are clearly plays with more pressure.

## Measuring a first step the same way twice

**The start problem.** Combine recordings begin with the player already moving, and the cut point varies from rep to rep. A 10-yard split timed from the first recorded frame agrees poorly with the official split (r = 0.47), while the tracked 40 matches the official 40 (r = 0.91).

**The fix: an anchored clock.** We start the clock when the player first reaches **1 yd/s**, at his position at that moment, both at the Combine and after the snap in games.

- **First step (`burst_15`)**: seconds to cover 1.5 yards in a straight line.
- **Reaction (`t_react`)**: in games only, seconds from the snap to 1 yd/s.

Figure 1 shows median speed with the middle 50% of plays. Interior rushers' speed splits from the Combine curve about 0.15–0.2 s after 1 yd/s. The 1.5-yard window ends near 0.6 s for edge rushers and 0.7 s for interior rushers. For interior players, the in-game "first step" therefore partly measures the block, not only acceleration.

Rushers also start moving about 0.2 s before the recorded snap frame. Position-derived speed shows the same rise, so this is not smoothing. If the snap frame is late by a constant amount, every reaction time shifts equally. If some rushers anticipate more, that difference is part of what reaction measures.

![Figure 1](figures/f1_speed_curves.png)

**Data.** We use regular-season pass rushes from 2023–25 by players who tested as DL at the Combine. Each play is from a stance start, lined up on the edge or the interior, not nullified by penalty, and the player rushed. That gives 26,133 rushes by 98 players. 79 of them have at least 50 such rushes, and **62** of those also have a clean Combine 40. These 62 are the main sample for every test.

Sixteen of the other 17 skipped the 40. They were picked earlier (median pick 66 vs 124) and played more on the edge, although neither difference is statistically clear. Their pressure rates match the 62.

**Reliability first** (Figure 2). Per trial, the Combine is the cleaner measurement. One 40 attempt has reliability 0.60, while one NFL snap has 0.01 once edge and interior are each compared with their own average. Games win only through volume: a season of snaps reaches 0.80, the mean of about two Combine attempts 0.75.

![Figure 2](figures/f2_reliability.png)

## Planned tests

The plan fixed the measures, thresholds, covariates and a Holm correction across the three primary tests before any test was run. Everything marked *post-hoc* below was added during two review rounds.

| | Question | Result (62 players) | Verdict |
|---|---|---|---|
| H1 | Does the Combine first step carry into the NFL first step? | r = +0.20 (95% CI −0.02 to +0.45); +0.02 SD after weight and role | Not supported (Holm p = 0.23) |
| H2 | Is it tied to reaction, and does it beat the stopwatch? | Reaction r = +0.13; 10-yard split explains 42% of the NFL first step, tracking 0% | Descriptive |
| H3 | Do plays with a faster first step have more pressure? | Odds ratio 0.74 per play-level SD slower (CI 0.65 to 0.84) | **Supported** (Holm p < 0.001) |
| H4 | Does the Combine first step predict pressure beyond draft slot and the 10-yard split? | −0.27 points per SD (CI includes 0) | Not supported (Holm p = 0.47) |

Two deviations are reported openly. The plan's pass-rush definition also included 4.6% of snaps where the lineman dropped into coverage, and we removed them. We also dropped `blitzing` as a covariate, because for linemen it means "this player rushed". Both versions reach the same conclusions.

## H1: No detectable carry-over

Across 62 players the Combine and NFL first steps are weakly related (r = +0.20). Body weight alone, which is known before the draft, explains that link: after weight, r = −0.00 (CI −0.24 to +0.25), and adding role changes little (+0.04). Within each role the link is near zero (Figure 3).

Role is not a hidden route for the Combine start either. Once weight is known, the Combine first step does not predict how often a player lines up on the edge (standardized β = +0.04, p = 0.67).

Measurement noise does not explain the null. Reliability caps the observable correlation at 0.77, and the noise-corrected estimate is +0.05 (CI −0.24 to +0.38). A linear mixed model on every rush agrees: −0.000 s per SD of the Combine first step (CI −0.010 to +0.009). The data rule out a strong link, not a small one.

Table 2 shows the alternative measures. Their unadjusted links, including three with p < 0.05, also shrink once weight is known. Acceleration keeps the largest residual (+0.23 after weight and role, CI −0.01 to +0.47).

| Measure, Combine vs NFL (post-hoc) | Unadjusted r | Spearman | After weight | After weight and role |
|---|---|---|---|---|
| First step, 1.5 yd (primary) | +0.20 [−0.02, +0.45] | +0.26 [+0.02, +0.47] | −0.00 [−0.24, +0.25] | +0.04 [−0.18, +0.29] |
| First step, 2.5 yd | +0.25 [+0.02, +0.48] | +0.31 [+0.08, +0.52] | −0.04 [−0.28, +0.22] | +0.01 [−0.22, +0.27] |
| Acceleration, 1 to 3 yd/s | +0.27 [+0.00, +0.52] | +0.25 [−0.02, +0.49] | +0.10 [−0.21, +0.38] | +0.23 [−0.01, +0.47] |

*Table 2. Brackets are 95% bootstrap intervals; n = 62.*

*Post-hoc*, we also shortened the window to end before most contact: the first 0.5 yards, or acceleration over the first 0.2 s. No window shows transfer. The closest is interior early acceleration (r = +0.28, CI −0.03 to +0.55).

![Figure 3](figures/f3_combine_vs_nfl.png)

## H2: Role and size explain the NFL first step

Out of sample, edge share explains 68% of the NFL first step and weight 59% (Figure 4). The official 10-yard split explains 42%, because it tracks weight (r = 0.84). Added to role and weight, it lowers out-of-sample accuracy (−0.017, CI −0.034 to −0.005), as does the tracked Combine first step (−0.010). Role is observed in the NFL, so a scout cannot know it at the Combine; weight is enough to see the result. The Combine first step is also unrelated to snap reaction (r = +0.13).

![Figure 4](figures/f4_what_explains_nfl_first_step.png)

## H3: Plays with a faster get-off are plays with more pressure

Holding the situation equal (down, distance, formation, score, alignment and reaction time), **a play** whose first step is one SD faster comes with **12.4% pressure instead of 7.2%** (Figure 5). That SD is play-to-play variation: 0.17 s on the edge and 0.28 s on the interior.

In tenths of a second, a first step 0.1 s quicker on every rush would add about 1.4 points of pressure. A reaction 0.1 s quicker adds about 1.1 points.

*Post-hoc* checks:
- **Within the same player** (fixed effects): a rush 0.1 s quicker than his own average adds about 1.4 points on the edge and 0.9 on the interior (OR 0.74 per play-level SD, CI 0.66 to 0.84). It is not just faster edge rushers pressuring more.
- **In the pre-contact 0.5-yard window:** OR 0.86 (CI 0.79 to 0.93).
- **Without quick passes** (thrown within 2.5 s, 36% of rushes, pressured only 2.4% of the time): OR 0.77 (CI 0.68 to 0.87).
- **Between players:** averages differ by only 0.15 play-level SD, so per player-level SD the effect is modest (OR 0.87, CI 0.78 to 0.98).

With all 98 linemen the results are the same (12.5% vs 6.8%).

The model explains little of any single snap (pseudo-R² 0.03). One rush is mostly noise, and the advantage builds up over hundreds of rushes.

It is also an association, not a pure trait effect. A rusher who is unblocked or wins early accelerates freely, and one who meets a double team slows at once. We cannot observe blocking schemes, because blockers are not tracked.

![Figure 5](figures/f5_pressure_vs_first_step.png)

## H4: Pressure follows the game; the interior pattern stays a hypothesis

Beyond draft slot and the 10-yard split, the Combine first step does not predict pressure rate. Rates are shrunk toward each role's own mean (10.5% edge, 6.5% interior). Out of sample, it lowers accuracy from 44% to 42%.

*Post-hoc*, a mixed logistic model on every rush points the same way and stays small: OR 0.93 per SD slower Combine first step. Its variational interval excludes 1 (0.89 to 0.98), but variational Bayes understates uncertainty. Cluster-robust and GEE versions give the same size with intervals including 1 (p ≈ 0.2). Any effect is small, and we cannot confirm it.

One exploratory pattern deserves follow-up (Figure 6). Among mostly-interior linemen, a slower Combine start goes with less pressure (r = −0.49, n = 34):

- **Weight and nose tackles do not explain it:** after both, r = −0.48 (CI −0.70 to −0.10).
- **Not driven by one player:** dropping any single player leaves r between −0.53 and −0.40.
- ***Post-hoc*, with the full H4 controls** (draft slot, 10-yard split, edge share): the size holds (r = −0.46), but the interval now reaches zero (−0.71 to +0.04; p = 0.17).

It is also one of about 20 checks. The same Combine measure does not predict these players' NFL first step either. Explosiveness into contact would point to momentum (weight × early speed), but momentum does not track interior pressure (r = +0.14). The pattern may be chance; the 2026 draft class can test it.

![Figure 6](figures/f6_pressure_by_role.png)

## What teams can do with this

**Draft evaluation**
- Do not pay for Combine first-step burst on its own. Once weight is known, it does not forecast the NFL first step.
- Read the 10-yard split as mostly a size measure.

**Week to week**
- Track reaction (snap to 1 yd/s) and the first step separately from game tracking.
- Single snaps are noise, so use about 50+ rushes per player.

**Development**
- Reaction is the part a workout never sees and the game rewards. Snap-count drills target it.

**Measurement**
- Anchor first-step timing on movement, not on a recording's first frame.

## Limitations

- **Sample size.** With 62 players, only correlations above about 0.35 can be shown reliably.
- **Selection.** Players without regular-season snaps are not in H1, H3 or H4, and the players who skipped the 40 lean toward early picks.
- **Censoring.** The 2025 class has played one season.
- **Line of scrimmage.** It is known only to ±0.5 yd, and the snap frame timing is approximate.
- **Plan and code timing.** They were committed together, so version history alone cannot prove the order.
- **Causality.** None is claimed.

## Appendix

- Plan and deviations: `ANALYSIS_PLAN.md`
- Code:
  - measurement: `common.py`, `game_starts.py`, `combine_starts.py`
  - planned tests: `tests.py`
  - post-hoc review checks: `review_round2.py`, `review_round3.py`, `review_round4.py`, `cv_h4.py`
  - figures: `figures.py`
- Executed review notebook: `review_notebook.ipynb`
- Receiver comparison: `../wr_breaks/`
- Public Kaggle notebook: to be added
