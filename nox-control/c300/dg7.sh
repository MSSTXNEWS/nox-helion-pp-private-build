echo "K1: dg7 (read-only)"; N=/workspace/nox; A=$N/agent/autotrain
for f in donor_hybrid.cmd.known_good donor_hybrid.cmd.gpu_ncmoe0 donor_hybrid.cmd.liska_ncmoe22 donor_hybrid.cmd.p5_best; do [ -f $A/$f ] || continue; echo "== $f"; tr ' ' '\n' < $A/$f | awk '/^-/{f=$0; getline v; if (v ~ /^-/) {print f; print v} else if (v ~ /^[0-9a-zA-Z.,=_\\*+-]{1,24}$/ && v !~ /\//) print f" "v; else print f" <val>"}' | tr '\n' ';' | cut -c1-700; echo; done
echo "== running 8104 flags"; P=$(pgrep -f 'llama-server.*8104' | head -1); tr '\0' '\n' </proc/$P/cmdline | awk '/^-/{f=$0; getline v; if (v ~ /^[0-9a-zA-Z.,=_\\*+-]{1,24}$/ && v !~ /\//) print f" "v; else print f" <val>"}' | tr '\n' ';' | cut -c1-700; echo
echo "== body_ttft_upgrade.sh ($(wc -l < $N/ops/body_ttft_upgrade.sh) lines)"; grep -nE "known_good|body_restart|flock|\.off|LOCK|train|cmd" $N/ops/body_ttft_upgrade.sh | cut -c1-170 | head -25
echo "== body_restart.sh guards"; grep -nE "known_good|fallback|BODY_LOCK|flock|VRAM|free|--cmd" $N/ops/body_restart.sh | cut -c1-170 | head -25
echo "== body watcher (who restarts body on failure)"; grep -lE "body_restart.sh" $N/ops/*.sh $N/ops/claude/*.sh $N/operators/*.sh $N/stewards/*.py 2>/dev/null | sed 's#/workspace/nox/##' | head -8
echo END
