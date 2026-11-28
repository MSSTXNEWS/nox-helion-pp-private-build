echo "K1: p5_e2"; mkdir -p /workspace/nox/state/p5/slots; NAME=e2_cachereuse; MODS="[('set','--cache-reuse',['256']),('set','--slot-save-path',['/workspace/nox/state/p5/slots'])]"
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
curl -fsSL $RAW/p5_lib.sh -o /tmp/p5_lib.sh; . /tmp/p5_lib.sh
