echo "K1: s6l_pc$CH"
S=/workspace/nox/state/s6; F=${F:-corpus}
echo "CHUNK $CH"; echo "ED_BEGIN"; tail -c +$(( CH*300000+1 )) $S/$F.b64 | head -c 300000; echo; echo "ED_END"; echo END
