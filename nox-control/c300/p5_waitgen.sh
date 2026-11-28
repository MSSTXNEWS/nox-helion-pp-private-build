echo "K1: p5_waitgen"; N=/workspace/nox
for i in $(seq 170); do
  ph=$(cut -c1-5 $N/state/gpu_phase 2>/dev/null); h=$(curl -s -m3 localhost:8104/health)
  P=$(ss -ltnp | grep ':8104 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
  oth=$(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits | grep -v "^$P," | awk -F, '{s+=$2} END{print s+0}')
  fr=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)
  if [ $((i%6)) = 1 ]; then echo "$(date -u +%T) phase=$ph health=$([ -n "$h" ] && echo ok || echo no) other_mib=$oth free_mib=$fr ncmoe=$(tr '\0' '\n' < /proc/${P:-1}/cmdline 2>/dev/null | grep -A1 -x -- '--n-cpu-moe' | tail -1)"; fi
  if [ "$ph" != train ] && [ -n "$h" ] && [ "$oth" -lt 12000 ]; then echo "READY phase=$ph"; echo END; exit 0; fi
  sleep 10
done; echo TIMEOUT; echo END
