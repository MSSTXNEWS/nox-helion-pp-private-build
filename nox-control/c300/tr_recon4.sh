echo "C300: tr_recon4"
cd /workspace/nox
red(){ sed -E 's/(sk-|ghp_|hf_|AIza|xox[a-z]-)[A-Za-z0-9_-]{8,}/\1REDACTED/g; s/((TOKEN|KEY|SECRET|PASS)[A-Z_]*=)[^ "]+/\1REDACTED/g'; }
sed -n 20,38p ops/liska_gates.py | cut -c1-400 | red
echo "== council_ab+round_gates"; sed -n 458,472p ops/liska_gates.py | cut -c1-300; sed -n 573,629p ops/liska_gates.py | cut -c1-260 | red
echo "== lora_ab"; wc -l ops/liska_lora_ab.py; sed -n 1,60p ops/liska_lora_ab.py | cut -c1-260 | red
echo "== judge /judge"; curl -s -m5 localhost:8300/judges | head -c 1500; echo
grep -n "def \|@app" agent/judge_service.py 2>/dev/null | head -5; find . -maxdepth 3 -name judge_service.py | head -2
echo "== guard_svc"; find . -maxdepth 3 -name guard_svc.py | head -2
echo END
