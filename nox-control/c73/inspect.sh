#!/bin/bash
# c73 инспектор: один запуск — снимок + безопасная самопочинка + DIGEST. Не трогает STOP, volta pin, защиту качества, данные.
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-210; }
STOP=""; for s in /root/nox/STOP /root/nox/STOP.flag /root/nox/state/STOP /root/nox/state/STOP.flag /root/nox/program/STOP /workspace/NOX_STOP; do [ -e $s ] && STOP=$s; done
echo "== train"; supervisorctl status nox-train-qwen9b-t131u nox-train-keeper 2>&1 | awk '{print $1,$2,$3,$4}'
tail -n 4 /root/nox/logs/train_qwen9b_t131u.log | a; grep -E '"event": "(holdout|early_stop_quality_guard|checkpoint)"' /root/nox/logs/train_qwen9b_t131u.log 2>/dev/null | tail -n 2 | a
nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
echo "== heal (allowlist only)"
if [ -n "$STOP" ]; then echo "STOP flag $STOP -> no restarts"; else
 for svc in nox-train-keeper nox-agent-architect-t859u nox-agent-integrator-t859u nox-agent-tuner-t858u nox-dispatcher-t855u nox-priority-scheduler nox-self-learning-loop nox-dialog-miner nox-knowledge-index-t168u; do
  st=$(supervisorctl status $svc 2>/dev/null | awk '{print $2}'); case "$st" in STOPPED|EXITED) supervisorctl start $svc 2>&1 | a;; esac; done; fi
echo "== disk"; df -h / | tail -1 | awk '{print $4,$5}'
echo "== dispatcher/agents"; head -c 500 /root/nox/status/agents_t856u.json 2>/dev/null | a; echo
python3 - <<'PY'
import json,collections,hashlib,os
s=json.load(open('/root/nox/state/dispatcher/state.json'))['tasks']
c=collections.Counter(t.get('status') for t in s.values()); print(dict(c))
bl=[(k,t) for k,t in s.items() if t.get('status') in('blocked','failed')]
print('blocked/failed sample keys:',sorted({x for _,t in bl[:20] for x in t})[:25])
for k,t in bl[:4]: print(' ',k,{x:str(t.get(x))[:70] for x in ('reason','blocked_by','error','note','last_error','deps','handler','status')})
pend=[(k,t) for k,t in s.items() if t.get('status')=='pending']
print('pending sample:',[(k,str(t.get('deps'))[:40],t.get('assigned_to'),t.get('next_try')) for k,t in pend[:3]])
d={'done':c.get('done',0),'pending':c.get('pending',0),'blocked':c.get('blocked',0),'failed':c.get('failed',0),'running':c.get('running',0)}
log=open('/root/nox/logs/train_qwen9b_t131u.log',errors='replace').read()[-1500:]
d['train_state']=os.popen("supervisorctl status nox-train-qwen9b-t131u | awk '{print $2}'").read().strip()
d['train_last']=hashlib.sha1(log.encode()).hexdigest()[:8]
print('DIGEST',json.dumps(d,sort_keys=True))
PY
echo "== services not running"; supervisorctl status | awk '$2!="RUNNING"{print $1,$2}' | head -12
