echo "K1: s6l_t2"
N=/workspace/nox
sed -n '1,7p;168,209p;274,292p' $N/canon/canon.py | cut -c1-330
echo "## mind dir"; ls -la $N/state/mind | awk '{print $5,$9}' | head -40
echo "## find initiative/promises"; find $N/state -maxdepth 3 \( -iname "initiative*" -o -iname "promises*" -o -iname "threads*" -o -iname "outbox*" \) 2>/dev/null | head
echo END
