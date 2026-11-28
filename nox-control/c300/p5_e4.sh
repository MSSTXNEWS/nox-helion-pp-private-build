echo "K1: p5_e4"; mkdir -p /workspace/nox/state/p5/slots; NAME=e4_t8; MODS="[('set','-t',['8']),('set','-tb',['8'])]"
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
curl -fsSL $RAW/p5_lib.sh -o /tmp/p5_lib.sh; . /tmp/p5_lib.sh
