#!/bin/bash
# t_train_audit.sh (исполнитель T): ТОЛЬКО ЧТЕНИЕ. Аудит обучения NOX HELION.
set -u
W=/workspace/nox
mask(){ sed -E 's/(token|key|secret|passw[a-z]*|auth)([=: "'"'"']+)[^ "'"'"',]{6,}/\1\2***/Ig'; }
echo "== host"; date -u; uptime; free -g | head -2; df -h /workspace / 2>&1 | head -5
echo "== gpu"; nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,clocks.sm,clocks.max.sm --format=csv
nvidia-smi --query-compute-apps=pid,used_memory,name --format=csv
echo "== train procs"
ps -eo pid,ppid,etime,pcpu,pmem,rss,args --sort=-pcpu | grep -i -E "train|lora|distill|peft|unsloth|deepspeed|accelerate|torchrun|llama|arbiter|v5_|python" | grep -v grep | cut -c1-400 | mask | head -40
echo "== services"; (systemctl list-units --type=service --no-pager 2>/dev/null | grep -i -E "nox|arbit|llama|train") ; (supervisorctl status 2>/dev/null | head -30)
echo "== files"
ls -la $W | head -80
find $W -maxdepth 3 \( -name "train*" -o -name "lora*" -o -name "distill*" -o -name "v5_*" -o -name "arbiter*" \) -not -path "*/node_modules/*" -not -path "*/.git/*" 2>/dev/null | head -80
echo "== ops/v5"; ls -la $W/ops 2>/dev/null | grep -i v5 | head -30
echo "== configs"
for f in $(find $W -maxdepth 4 \( -name "*.yaml" -o -name "*.yml" -o -name "*.json" \) -not -path "*/node_modules/*" -not -path "*/site/*" -not -path "*/.git/*" -size -40k 2>/dev/null | xargs grep -l -i -E "lora|learning_rate|per_device|batch_size|gradient_acc|max_seq|r_lora|lora_r" 2>/dev/null | head -12); do echo "--- $f"; head -c 3500 $f | mask; echo; done
echo "== train scripts head"
for f in $(find $W -maxdepth 3 \( -name "train*.py" -o -name "lora*.py" -o -name "distill*.py" -o -name "v5_*.py" -o -name "v5_*.sh" -o -name "train*.sh" \) -not -path "*/.git/*" 2>/dev/null | head -8); do echo "--- $f ($(wc -l <$f) lines)"; head -c 5000 $f | mask; echo; done
echo "== logs tail"
for f in $(find $W /var/log /workspace -maxdepth 3 \( -name "*train*.log" -o -name "*lora*.log" -o -name "*distill*.log" -o -name "*v5*.log" \) -mmin -2880 2>/dev/null | sort -u | head -6); do echo "--- $f ($(stat -c %s $f) B, mtime $(stat -c %y $f))"; tail -n 25 $f | cut -c1-300 | mask; done
echo "== checkpoints/datasets"
find / -xdev \( -name "checkpoint-*" -o -name "*.safetensors" -o -name "*.jsonl" -o -name "*.parquet" -o -name "*.arrow" \) -size +50M -not -path "/proc/*" 2>/dev/null | head -40 | xargs -r ls -laSh 2>/dev/null | head -40
du -sh $W/* 2>/dev/null | sort -rh | head -15
echo "== libs"
python3 - <<'PY' 2>&1
import importlib, importlib.metadata as m
for p in ["torch","transformers","peft","trl","unsloth","unsloth_zoo","deepspeed","flash_attn","xformers","bitsandbytes","liger_kernel","accelerate","datasets","triton","vllm","safetensors"]:
    try: print(p, m.version(p.replace("_","-")) )
    except Exception:
        try: print(p, m.version(p))
        except Exception: print(p, "-")
try:
    import torch; print("cuda", torch.version.cuda, "cap", torch.cuda.get_device_capability(0), "sdpa flash/mem/math", torch.backends.cuda.flash_sdp_enabled(), torch.backends.cuda.mem_efficient_sdp_enabled(), torch.backends.cuda.math_sdp_enabled(), "bf16", torch.cuda.is_bf16_supported())
except Exception as e: print("torch err", e)
PY
which -a python3 python 2>/dev/null; ls /opt /workspace/*/bin/python 2>/dev/null | head
echo "== cpu/io"; top -b -n1 | head -15; (iostat -x 1 2 2>/dev/null | tail -12); nproc
echo "== chat/arbiter"
ss -ltnp 2>/dev/null | grep -E ":8200|:82|:81" | head
curl -s -m 5 localhost:8200/running 2>&1 | head -c 800; echo
curl -s -m 5 localhost:8200/v1/models 2>&1 | head -c 600; echo
for f in $(find $W -maxdepth 3 -name "arbiter*.py" -o -maxdepth 3 -name "llama-swap*.y*ml" -o -maxdepth 3 -name "config.yaml" -path "*swap*" 2>/dev/null | head -4); do echo "--- $f ($(wc -l <$f) lines)"; head -c 7000 $f | mask; echo; done
echo "== dmon 30s"
timeout 40 nvidia-smi dmon -s pucm -c 30 2>&1 | tail -35
echo "== done"
