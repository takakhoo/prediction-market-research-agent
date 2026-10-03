#!/usr/bin/env bash
# Rebuild every table and figure from the raw pulls in research/data/raw. Run from the repository root.
set -uo pipefail
PY=${PY:-.venv/bin/python}
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-4}
mkdir -p results/logs results/tables results/figures
run() { echo "== $1 $(date +%H:%M:%S)"; $PY -W ignore -m "research.experiments.$1" "${@:2}" > "results/logs/$1.log" 2>&1 || echo "FAILED $1"; tail -n 3 "results/logs/$1.log"; }
run build_tape
run crypto_obs
run e1_e2_calibration
run e3_maker_taker
run e3b_first_touch
run e4_crypto_options
run e9_stock_options
run e6_backtest
run e7_wallets
run e8_llm
run e5_model
echo "== figures"; $PY -W ignore -m research.figures
echo "== done $(date +%H:%M:%S)"
