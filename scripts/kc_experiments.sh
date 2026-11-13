#!/usr/bin/env bash
# Run Knowledge Commons experiments for one model, in two stages.
#
#   Stage 1, the alpha sweep (run this first, for every model):
#     scripts/kc_experiments.sh haiku  sweep 10
#     scripts/kc_experiments.sh sonnet sweep 10
#     scripts/kc_experiments.sh opus   sweep 8
#
#   Stage 2, info conditions + bot probes, at the alpha picked from stage 1
#   (pick one where cooperation is partial, not 100% or 0%):
#     scripts/kc_experiments.sh haiku followup 10 1.5
#
# Every command has a --max-calls cap (2x expected calls) so nothing runs away.
# All runs start at seed 0, so every model and condition sees the same codes.
set -euo pipefail

case "${1:-}" in
  haiku)  MODEL=claude-haiku-5-5 ;;
  sonnet) MODEL=claude-sonnet-5-5 ;;
  opus)   MODEL=claude-opus-5-5 ;;
  *) echo "usage: $0 haiku|sonnet|opus sweep|followup SEEDS [ALPHA]"; exit 1 ;;
esac
STAGE=${2:?usage: $0 MODEL sweep|followup SEEDS [ALPHA]}
SEEDS=${3:?usage: $0 MODEL sweep|followup SEEDS [ALPHA]}

BIN=.venv/bin/infocoop
OUT=results/kc/$1
FULL_CAP=$((SEEDS * 64 * 2))    # 4 LLM agents x 2 calls x 8 rounds, doubled
PROBE_CAP=$((SEEDS * 16 * 2))   # 1 LLM agent

case "$STAGE" in
  sweep)
    # E2: where does sharing break? Theory says the incentive to share
    # flips at alpha = 1, so the grid brackets it.
    for a in 0 1 1.5 2 3; do
      echo "-- E2 $MODEL alpha=$a"
      $BIN kc run kc_llm --model "$MODEL" --alpha "$a" --info private_memory \
        --seeds "$SEEDS" --max-calls "$FULL_CAP" --out "$OUT/e2_alpha" --no-metrics
    done
    $BIN kc metrics "$OUT/e2_alpha" > "$OUT/e2_metrics.json"
    echo "== sweep done: $MODEL -> $OUT/e2_metrics.json"
    ;;
  followup)
    ALPHA=${4:?followup needs ALPHA, e.g. 1.5}
    # E3: does information about past behavior matter?
    # (private_memory at this alpha is already in the sweep)
    for info in no_memory public_reputation; do
      echo "-- E3 $MODEL info=$info alpha=$ALPHA"
      $BIN kc run kc_llm --model "$MODEL" --alpha "$ALPHA" --info "$info" \
        --seeds "$SEEDS" --max-calls "$FULL_CAP" --out "$OUT/e3_info" --no-metrics
    done
    # E4: one LLM vs scripted bots
    for c in kc_probe_honest kc_probe_recip_liar kc_probe_grudgers; do
      echo "-- E4 $MODEL $c alpha=$ALPHA"
      $BIN kc run "$c" --model "$MODEL" --alpha "$ALPHA" --info private_memory \
        --seeds "$SEEDS" --max-calls "$PROBE_CAP" --out "$OUT/e4_probes" --no-metrics
    done
    echo "== followup done: $MODEL"
    ;;
  *) echo "stage must be sweep or followup"; exit 1 ;;
esac
