echo "C300: ac_mb1"
cat /workspace/nox/state/train_overrides.json | head -c 1500; echo; cat /workspace/nox/state/train_vram_cap_mib; echo
F=/workspace/nox/distill_v2/code/distill_v2.py; wc -l $F
grep -nE "accum|micro|bucket|max_seq|MAXLEN|max_len|per_device|ladder|лестниц|parts|VRAM_CAP|vram_cap" $F | head -60 | cut -c1-190
tail -3 /workspace/nox/agent/autotrain/rounds/r038/train.log | cut -c1-200
cat /workspace/nox/tmp/ab/res.txt | cut -c1-60
