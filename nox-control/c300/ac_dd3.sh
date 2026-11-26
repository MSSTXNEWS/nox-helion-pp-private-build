echo "C300: ac_dd3"
rm -rf /workspace/nox/tmp/ml
grep -nE "knowledge" /workspace/nox/distill_v2/code/distill_v2.py | grep -E "json|path|PATH|open" | head -12 | cut -c1-220
ls -la --time-style=+%F /workspace/nox/ops/v5_knowledge_gpu_20261125/*.json* 2>/dev/null | sort -k5 -rn | head -8 | cut -c1-160
