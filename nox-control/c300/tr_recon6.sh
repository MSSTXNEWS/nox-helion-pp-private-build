echo "C300: tr_recon6"
cd /workspace/nox
red(){ sed -E 's/(sk-|ghp_|hf_|AIza|xox[a-z]-)[A-Za-z0-9_-]{8,}/\1REDACTED/g; s/((TOKEN|KEY|SECRET|PASS)[A-Z_]*=)[^ "]+/\1REDACTED/g'; }
for f in ops/dpo/build_dpo.py ops/dpo/build_dpo2.py ops/dpo/teacher_dump.py; do echo "######## $f"; cut -c1-250 $f | red; done
echo "== sample"; head -c 700 ops/dpo/dpo_train.jsonl; echo; cat ops/dpo/build_stats.json ops/dpo/build2_stats.json
echo "== judge_one reward"; awk '/^def _judge_one/,/^class JudgeIn/' judges/judge_service.py | cut -c1-220
echo "== JudgeIn"; sed -n 317,327p judges/judge_service.py
echo "== ckpt_best_global"; cat agent/out/ckpt_best_global.json | head -c 600; echo; ls state/p3 | head -30; ls state/p3/*.json | head
echo "== owner_active flags"; ls state | grep -i -E "owner|live_turn|pause" | head; ls /workspace/nox | grep -i -E "OWNER|LIVE|STOP"
echo "== hold_frozen"; wc -l distill_v2/hold_frozen_v1.jsonl
echo END
