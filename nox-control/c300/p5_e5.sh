echo "K1: p5_e5"; mkdir -p /workspace/nox/state/p5/slots; NAME=e5_np10; export P5_BG9=1
MODS="[('set','--parallel',['10']),('set','-c',['49152'])]"
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
curl -fsSL $RAW/p5_lib.sh -o /tmp/p5_lib.sh; . /tmp/p5_lib.sh
