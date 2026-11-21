#!/bin/bash
# Установка NOX_V5_CANADA_EXECUTION на S1: распаковка, сверка SHA256, 122 теста, read-only проба сервера, интеграция (обёртки, таймер, реестр).
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/canada
D=/root/nox/canada; mkdir -p /root/nox/canada_dl /root/nox/run /root/nox/receipts /root/nox/bin /root/nox/state /root/nox/logs
curl -fsSL "$R/NOX_V5_CANADA_EXECUTION.tgz?t=$RANDOM" -o /root/nox/canada_dl/pack.tgz || { echo "download failed"; exit 1; }
rm -rf "$D.new"; mkdir -p "$D.new" && tar xzf /root/nox/canada_dl/pack.tgz -C "$D.new" || exit 1
P="$D.new/NOX_V5_CANADA_EXECUTION"
( cd "$P" && sha256sum -c SHA256SUMS 2>&1 | grep -vc ": OK" | sed 's/^/sha_bad_lines=/' )
( cd "$P" && python3 -B -m unittest discover -s . -p "test_*.py" 2>&1 | tail -3 )
rm -rf "$D.prev"; [ -d "$D" ] && mv "$D" "$D.prev"; mv "$D.new" "$D"; P="$D/NOX_V5_CANADA_EXECUTION"
ln -sfn "$P" /root/nox/canada_pack
# обёртки
cat > /root/nox/bin/nox_probe.sh <<'X'
#!/bin/bash
# read-only проба S1: RAM/cgroup/NUMA/GPU/диск/health -> /root/nox/run/server_probe.json
P=/root/nox/canada_pack
python3 -B "$P/server_probe.py" --expected-instance 61825960 --disk-path /root/nox --disk-path /dev/shm --health-port 8081 --health-port 8082 > /root/nox/run/server_probe.json.tmp 2>/root/nox/logs/server_probe.err && mv /root/nox/run/server_probe.json.tmp /root/nox/run/server_probe.json
X
chmod +x /root/nox/bin/nox_probe.sh; /root/nox/bin/nox_probe.sh; echo probe_rc=$?; head -c 700 /root/nox/run/server_probe.json; echo
[ -w /etc/cron.d ] && echo '*/15 * * * * root /root/nox/bin/nox_probe.sh' > /etc/cron.d/nox-probe && echo cron_ok
# реестр интеграции (чтобы NOX/диспетчер видели набор)
python3 -I - <<'Y'
import json,time,os
p='/root/nox/canada_pack'
reg={"installed":time.strftime("%FT%TZ",time.gmtime()),"path":os.path.realpath(p),"tools":{"probe":"/root/nox/bin/nox_probe.sh","model_plan":p+"/model_plan.py","fetch_model":p+"/fetch_model.py","shadow_glm":p+"/shadow_glm.py","s03_snapshot":p+"/s03_snapshot.py","chat_bench":p+"/chat_bench.py","acceptance":p+"/acceptance.py","glm_gate":p+"/glm20/gate.py","eval":p+"/evaluation/nox_eval.py"},"queues":{"pareto200":p+"/relay/pareto-200.json","pareto220_glm":p+"/relay/pareto-220-glm.json","pareto270_glm":p+"/relay/pareto-270-glm.json","wave50":p+"/wave-50-canada.json","canon_cards":p+"/canon-v5-cards.json"},"rules":"один главный модель; без --no-mmap/--mlock; KV f16; S2 не удалять; fetch/shadow только по явному запросу"}
json.dump(reg,open('/root/nox/state/canada_pack.json','w'),indent=1,ensure_ascii=False); print("registry ok")
Y
# согласованность с блоком 1: читаем план модели (read-only)
python3 -B "$P/model_plan.py" manifest 2>&1 | head -6 | cut -c1-160
ls /root/nox/state | head; ls /root/nox/canada_pack | wc -l
