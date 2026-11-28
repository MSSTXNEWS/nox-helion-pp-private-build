echo "K1: q29_sc_md5"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
echo "sidecar_md5 $(md5sum < $N/mods/nox_sidecar.py | cut -c1-32) lines=$(wc -l < $N/mods/nox_sidecar.py) helpers_md5 $(md5sum < $N/mods/chat_helpers.py | cut -c1-32)"
echo "sv: $(supervisorctl status nox_sidecar 2>&1 | awk '{print $1,$2}')"
echo "gate pid: $(pgrep -f 'owner_gate/Caddyfile' | head -2 | tr '\n' ' ') main caddy: $(pgrep -f 'web_chat_auth/Caddyfile' | head -2 | tr '\n' ' ')"
echo "token file: $(ls $N/state/owner_gate/ | tr '\n' ' ')"
echo END
