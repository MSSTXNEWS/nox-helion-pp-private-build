echo "C300: ch_r2"
cd /workspace/nox/web/site && find . -maxdepth 1 -type f ! -name '*.bak*' -exec md5sum {} + | sed 's#\./##' | sort -k2
