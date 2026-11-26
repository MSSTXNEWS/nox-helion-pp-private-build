echo "C300: srv_k88"
df -h /workspace | tail -1
K=/workspace/nox/distill_v2/ckpt_keep
du -sh $K/cand_dpo_* 2>/dev/null | sort -k2
du -sh /workspace/nox/models/gpu/* 2>/dev/null | sort -h | tail -8
ls -d /workspace/nox/models/gpu/*istral* /workspace/nox/models/gpu/*gpt-oss* 2>/dev/null
echo == bak by base name (>50MB)
find /workspace/nox -xdev -type f -size +50M \( -name "*.bak*" -o -name "*.before*" -o -name "*.backup*" \) -not -path "*/venv/*" -not -path "*nox-backup*" -not -path "*nox_mem*" -not -path "*restic*" -printf "%s %TY-%Tm-%Td %p\n" 2>/dev/null | sort -k3 | cut -c1-220 | head -40
echo == cache evidence
timeout 100 grep -rl "Mistral-Small\|gpt-oss" /workspace/nox/state /workspace/nox/ops/*/*.json /workspace/nox/distill_v2/*.json 2>/dev/null | head -8
ls /workspace/nox/ops | grep -i -E "ready_bulk|logit|teacher" | head
