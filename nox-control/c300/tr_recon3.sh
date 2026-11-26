echo "C300: tr_recon3"
cd /workspace/nox
red(){ sed -E 's/(sk-|ghp_|hf_|AIza|xox[a-z]-)[A-Za-z0-9_-]{8,}/\1REDACTED/g; s/((TOKEN|KEY|SECRET|PASS)[A-Z_]*=)[^ "]+/\1REDACTED/g'; }
echo "== who starts autotrain"; ps -o pid,ppid,etimes,args -p 186699,532189 | cut -c1-160; grep -l "autotrain.sh" /etc/supervisor/conf.d/* stewards/* ops/*.sh 2>/dev/null | head; 
echo "== liska_gates"; wc -l ops/liska_gates.py; grep -n "^def \|^class \|THRESH\|0\.85\|0\.60\|0\.9\b" ops/liska_gates.py | cut -c1-200 | head -80
echo "== decide"; awk '/^def decide/,/^def alive_gate/' ops/liska_gates.py | head -90 | red
echo "== policy"; awk '/^def policy/,/^def [a-z_]+\(/' ops/liska_gates.py | head -40
echo "== train_dpo"; red < ops/dpo/train_dpo.py
echo "== judges 8300"; curl -s -m5 localhost:8300/health | head -c 300; echo; curl -s -m5 localhost:8300/openapi.json | python3 -c "import json,sys;d=json.load(sys.stdin);print(list(d.get('paths',{}).keys()))" 2>&1 | head -3
ps aux | grep -E ":8300|judge_service" | grep -v grep | awk '{print $2,$11,$12,$13,$14,$15}' | head -3
echo "== gpu"; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader; df -h /workspace | tail -1
echo "== guard"; ps aux | grep -E "18218|guard_svc" | grep -v grep | awk '{print $2,$11,$12,$13,$14}' | head; ls ops | grep -i -E "guard|inject" | head; ls models | head -30
echo "== net"; for u in https://huggingface.co https://hf-mirror.com; do curl -s -m6 -o /dev/null -w "$u %{http_code}\n" $u; done
echo END
