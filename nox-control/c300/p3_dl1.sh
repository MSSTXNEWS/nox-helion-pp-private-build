M=/workspace/nox/models/flux; date +%T
a=$(stat -c %s $M/flux1-schnell-q4_0.gguf.part 2>/dev/null); sleep 20; b=$(stat -c %s $M/flux1-schnell-q4_0.gguf.part 2>/dev/null); echo "bytes $a -> $b  ($(( (b-a)/20/1024 )) KB/s)"
ls -la $M | cut -c20-120; pgrep -fa "curl.*flux" | cut -c1-120 | head -3; cat $M/dl.log
