echo "K1: p5_e1"; NAME=e1_ub2048; MODS="[('set','-ub',['2048']),('set','-b',['4096'])]"
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
curl -fsSL $RAW/p5_lib.sh -o /tmp/p5_lib.sh; . /tmp/p5_lib.sh
