echo "K1: p5_e3"; mkdir -p /workspace/nox/state/p5/slots; NAME=e3_kvf16; MODS="[('set','-ctk',['f16']),('set','-ctv',['f16'])]"
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
curl -fsSL $RAW/p5_lib.sh -o /tmp/p5_lib.sh; . /tmp/p5_lib.sh
