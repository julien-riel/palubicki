#!/usr/bin/env bash
# Re-run the emergent-species digests and diff against the captured baseline.
# Exits 0 only if every (species, seed) digest is BIT-IDENTICAL to baseline.
set -u
cd /Users/julienriel/src/palubicki
BASE=/tmp/digests_baseline.txt
CUR=/tmp/digests_current.txt
: > "$CUR"
for spec_years in "oak_emergent 11" "maple_emergent 9" "pine_emergent 11" "fir_emergent 11" "ash_emergent 11" "birch_emergent 11"; do
  set -- $spec_years
  for seed in 0 1; do
    .venv/bin/python scripts/sim_digest.py "$1" "$2" "$seed" >> "$CUR"
  done
done
echo "=== DIGEST COMPARISON (baseline vs current) ==="
# Compare only the DIGEST hex + the identity columns; ignore nothing.
if diff <(cut -d' ' -f2,4,5 "$BASE") <(cut -d' ' -f2,4,5 "$CUR") >/dev/null; then
  echo "RESULT: BIT-IDENTICAL ✓  (all $(wc -l < "$CUR" | tr -d ' ') digests match baseline)"
  exit 0
else
  echo "RESULT: MISMATCH ✗  — diff (baseline < / current >):"
  diff <(cat "$BASE") <(cat "$CUR")
  exit 1
fi
