#!/usr/bin/env bash
# One-time opt-in private receipt return channel. No training or STOP changes.
set -Eeuo pipefail
set +x
umask 077
NODE="$1"
case "$NODE" in vast-60254538|runpod-5f3j8hwyicc0bp) ;; *) echo "USAGE: bash installer.sh vast-60254538|runpod-5f3j8hwyicc0bp"; exit 2;; esac
SCRIPT=/root/.local/lib/nox-private-receipts/publish_receipts.py
CONF=/root/.config/nox-control/private-receipts.json
STATE=/root/.local/state/nox-private-receipts
mkdir -p /root/.local/lib/nox-private-receipts /root/.config/nox-control "$STATE"
chmod 700 /root/.config/nox-control /root/.local/lib/nox-private-receipts "$STATE"
TMP=$(mktemp /tmp/nox-private-XXXXXX)
trap 'rm -f "$TMP"' EXIT
curl --proto '=https' --tlsv1.2 -fsSL --retry 3 \
 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/19088f8d74aea6ba451741abe18db41d940c9bed/nox_remote_control/private_receipts/publish_receipts.py' -o "$TMP"
DIGEST=$(python3 - "$TMP" <<'PY'
import hashlib,sys
b=open(sys.argv[1],"rb").read()
print(hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest())
PY
)
if [ "$DIGEST" != 72e56b550945e88176634fa5dfe834fcf813afa9 ]; then echo HOLD_SOURCE_MISMATCH; exit 4; fi
python3 -m py_compile "$TMP"
if test -e "$SCRIPT" && ! cmp -s "$TMP" "$SCRIPT"; then echo HOLD_EXISTING_AGENT_DIFFERS; exit 5; fi
if ! test -e "$SCRIPT"; then cp "$TMP" "$SCRIPT"; chmod 600 "$SCRIPT"; fi
if ! test -e "$CONF"; then
  echo "Configure a fine-grained GitHub PAT: private MSSTXNEWS/runpod-control, Contents Read/Write only."
  printf "Paste token (hidden; never send via ChatGPT): "
  IFS= read -rs TOKEN
  echo
  if [[ "$TOKEN" != github_pat_* && "$TOKEN" != ghp_* ]]; then echo HOLD_TOKEN_FORMAT; exit 6; fi
  printf '%s' "$TOKEN" | python3 -c 'import sys,json,pathlib; p=pathlib.Path(sys.argv[1]); p.write_text(json.dumps({"private_repo":"MSSTXNEWS/runpod-control","token":sys.stdin.read()},indent=2)+"\n")' "$CONF"
  unset TOKEN
  chmod 600 "$CONF"
fi
PIDFILE="$STATE/$NODE.pid"
if test -e "$PIDFILE"; then
  PID=$(cat "$PIDFILE")
  if [[ "$PID" =~ ^[0-9]+$ ]] && test -e "/proc/$PID/cmdline" &&
     tr '\0' ' ' <"/proc/$PID/cmdline" | grep -Fq "publish_receipts.py --node $NODE"; then
    echo "PRIVATE_RECEIPTS_ALREADY_RUNNING PID=$PID"; exit 0
  fi
fi
nohup python3 -u "$SCRIPT" --node "$NODE" >> "$STATE/$NODE.log" 2>&1 </dev/null &
PID=$!
printf '%s\n' "$PID" > "$PIDFILE"
sleep 2
if kill -0 "$PID" 2>/dev/null; then
  echo "PRIVATE_RECEIPTS_STARTED NODE=$NODE PID=$PID"
  echo "Results destination: private GitHub MSSTXNEWS/runpod-control/receipts/$NODE"
else
  echo HOLD_RECEIPT_AGENT_FAILED
  tail -n 8 "$STATE/$NODE.log"
  exit 7
fi
