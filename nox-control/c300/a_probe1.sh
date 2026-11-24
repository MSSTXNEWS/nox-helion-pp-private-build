# A: проба реальных данных для Организма/Ядра/Обучения (без изменения файлов)
echo "DISK $(df -BG /workspace/nox | tail -1)"
echo "VRAM $(nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null | head -2)"
echo "ORGANS_JSON $(head -c 600 /workspace/nox/state/organs.json 2>/dev/null)"
echo "FLAGS $(head -c 300 /workspace/nox/state/flags.json 2>/dev/null)"
for port in 8104 8105 8106 8141 8300 8400 8130 8120 8097; do echo "PORT $port $(curl -s -m 3 -o /dev/null -w '%{http_code}' 127.0.0.1:$port/health)"; done
echo "AUTOTRAIN_TAIL $(tail -n 3 /workspace/nox/agent/out/autotrain.log 2>/dev/null | cut -c1-200)"
echo "CKPT $(ls /workspace/nox/distill_v2/ckpt_keep/ 2>/dev/null | tail -n 3 | tr '\n' ' ')"
echo "OPS_TAIL $(tail -n 3 /workspace/nox/agent/out/ops_changes.log 2>/dev/null | cut -c1-200)"
echo "PROGRESS_EXISTS $(ls -la /workspace/nox/ops/controller/PROGRESS.md 2>/dev/null)"
