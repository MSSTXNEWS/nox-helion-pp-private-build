echo "C300: k2_r14"
N=/workspace/nox; ST=$N/state; F=$N/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf
pgrep -af "k2_dl.py" | cut -c1-120; ls -la $F* | cut -c20-120; tail -3 $ST/k2_dl.log $ST/k2_dl.err 2>&1 | cut -c1-200; tail -4 $ST/k2_restart.log
stat -c '%y' $ST/orch/OWNER_ACTIVE; date; df -BG /workspace | tail -1
