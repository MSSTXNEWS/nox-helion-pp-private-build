echo "K1: mu1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles
W=$(mktemp -d); curl -fsSL $R/enc_in/mu1.enc -o $W/e; curl -fsSL $R/enc_in/mu1.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W || { echo DECRYPT_FAIL; exit 0; }
cp -a $N/mods/inspector.py $N/mods/inspector.py.bak_mu1 2>/dev/null
cp $W/mods/* $N/mods/; mkdir -p $N/mods/sup_pending; cp $W/sup/* $N/mods/sup_pending/; rm -rf $W
supervisorctl restart nox_inspector >/dev/null 2>&1; sleep 3; echo "inspector $(supervisorctl status nox_inspector | awk '{print $2}')"
free_g=$(df -BG /workspace | awk 'NR==2{gsub("G","",$4);print $4}'); echo "disk_free_before=$free_g"
if [ "$free_g" -lt 25 ]; then echo "SKIP_MUSIC low disk"; echo END; exit 0; fi
cd $N/mods && (nice -n 19 timeout 1600 bash install_music.sh > $N/logs/install_music.log 2>&1; echo "rc=$?" >> $N/logs/install_music.log)
grep -iE '"ok"|rtf|vram|seconds|sec=|rc=|error|fail|sha' $N/logs/install_music.log | sed -E 's/[0-9a-f]{40,64}/<sha>/g' | cut -c1-200 | tail -12
echo "disk_free_after=$(df -BG /workspace | awk 'NR==2{print $4}')"
echo END
