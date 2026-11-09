#!/usr/bin/env bash
# Rebuilds every result, log and figure from the Kaggle data.
# Usage: bash run_all.sh [DATA_DIR]   (default: ./nfl-big-data-bowl-2027, the folder with the CSVs)
# Warnings are not silenced: common.py prints them into the logs (category and message, no local paths).
set -euo pipefail
cd "$(dirname "$0")"
DATA="${1:-nfl-big-data-bowl-2027}"
PY="${PYTHON:-python}"
export PYTHONUTF8=1   # tables printed by polars need UTF-8 on Windows consoles
DL=dl_first_step/outputs
WR=wr_breaks/outputs
mkdir -p "$DL" "$WR"

echo "== DL: first-step measures in games and at the Combine"
"$PY" dl_first_step/game_starts.py "$DATA" "$DL" | tee "$DL/game_starts_log.txt"
"$PY" dl_first_step/combine_starts.py "$DATA" "$DL" | tee "$DL/combine_starts_log.txt"

echo "== DL: planned tests H1-H4 (as first written, then corrected definition)"
"$PY" dl_first_step/tests.py "$DATA" "$DL" --as-written | tee "$DL/tests_log_as_written.txt"
"$PY" dl_first_step/tests.py "$DATA" "$DL" | tee "$DL/tests_log.txt"
"$PY" dl_first_step/cv_h4.py "$DATA" "$DL" | tee "$DL/cv_h4_log.txt"

echo "== DL: post-hoc checks from the review rounds"
"$PY" dl_first_step/review_round2.py "$DATA" "$DL" | tee "$DL/review_round2_log.txt"
"$PY" dl_first_step/review_round3.py "$DATA" "$DL" | tee "$DL/review_round3_log.txt"
"$PY" dl_first_step/review_round4.py "$DATA" "$DL" | tee "$DL/review_round4_log.txt"

echo "== WR: break measures and their stability (no outcome tests)"
"$PY" wr_breaks/wr_measures.py "$DATA" "$WR" 0.7 | tee "$WR/wr_measures_log_dip70.txt"
"$PY" wr_breaks/wr_measures.py "$DATA" "$WR" 0.8 | tee "$WR/wr_measures_log_dip80.txt"

echo "== figures for the writeup"
"$PY" dl_first_step/figures.py "$DATA" "$DL"

echo "== copy every chart into grafice/"
mkdir -p grafice
cp dl_first_step/figures/*.png "$DL"/check_h1_h4_*.png grafice/

echo "== review notebook (executed, readable without the data)"
"$PY" dl_first_step/make_review_notebook.py "$DATA"
echo "done"
