echo "K1: l2_recon5"
F=/workspace/nox/web/pkg/server/chat_core.py
sed -n '/^def _via_fast/,/^def _k1_stable/p' $F | cut -c1-240
cat /workspace/nox/state/living/rules.md | head -c 1500
