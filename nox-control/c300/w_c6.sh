echo "C300: w_c6"
cd /workspace/nox/web/site
grep -o ".\{0,400\}ollamaStatus.\{0,400\}" *.js 2>/dev/null | grep -i 'hold' | head -3 | cut -c1-900
