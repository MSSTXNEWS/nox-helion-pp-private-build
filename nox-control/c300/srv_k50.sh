echo "C300: srv_k50"
cd /workspace/nox/ops/draw
/workspace/nox/venv/bin/python -I - <<'PY'
import sys; sys.path.insert(0,'.')
import invoke_draw as D
print(D.SD_BIN, D.FLUX_DIR, D.T5)
PY
SD=$(/workspace/nox/venv/bin/python -I -c "import sys;sys.path.insert(0,'.');import invoke_draw as D;print(D.SD_BIN)" 2>/dev/null | tail -1)
$SD --help 2>&1 | grep -i -E "diffusion-fa|flash|taesd|tae|vae-tiling|offload|preview|cache|circular|clip-on-cpu|vae-on-cpu|--version" | cut -c1-150 | head -20
$SD --version 2>&1 | head -2
