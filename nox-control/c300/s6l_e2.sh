echo "K1: s6l_e2"
F=/workspace/nox/web/pkg/server/chat_core.py
sed -n '1674,1715p;1760,1800p' $F | cut -c1-260
echo END
