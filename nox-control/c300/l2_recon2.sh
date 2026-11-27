echo "K1: l2_recon2"
N=/workspace/nox; F=$N/web/pkg/server/chat_core.py
echo "--- embed_server"; wc -l $N/canon_night/embed_server.py; sed -n 1,80p $N/canon_night/embed_server.py
echo "--- chat_core 266-335"; sed -n 266,335p $F
echo "--- 431-470"; sed -n 431,470p $F
echo "--- run_turn 469-640"; sed -n 469,640p $F
