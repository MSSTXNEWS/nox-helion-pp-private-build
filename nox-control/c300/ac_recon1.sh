echo "C300: ac_recon1"
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu,clocks.sm,clocks.max.sm,power.draw,power.limit --format=csv
nvidia-smi --query-compute-apps=pid,used_memory,name --format=csv
uptime; nproc; free -g | head -2; df -h /workspace | tail -1
ps -eo pid,ni,pcpu,pmem,etimes,args --sort=-pcpu | head -15 | cut -c1-200
cat /workspace/nox/state/speed.json 2>/dev/null | head -c 1500; echo
ls /workspace/nox/distill_v2/ /workspace/nox/ops | head -80
python3 -c "import torch,sys;print(torch.__version__,torch.version.cuda)" 2>&1
for p in unsloth unsloth_zoo liger_kernel peft transformers trl bitsandbytes triton xformers; do python3 -m pip show $p 2>/dev/null | grep -E "^(Name|Version)" | tr '\n' ' '; echo; done
