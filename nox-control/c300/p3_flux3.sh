M=/workspace/nox/models/flux
cat $M/dl.log | tail -8; ls -la $M | cut -c1-120
/workspace/nox/bin/sd --help 2>&1 | grep -n -E -- "--backend|-t, --threads|--seed|-o, --output|--sampling-method" | cut -c1-170
df -h /workspace | tail -1
