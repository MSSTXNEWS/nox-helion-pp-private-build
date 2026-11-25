echo "C300: v_diag_2"
D=/workspace/nox/router/advisors; ls -la $D | head -30
echo --- shim; head -c 2500 $D/keyless_shim.py
echo --- router; head -c 2500 $D/advisor_router.py
echo --- ports; ss -ltnp 2>/dev/null | grep -E "python|gateway" | awk '{print $4,$6}' | head -20
for f in $D/*.json; do echo "== $f"; head -c 1200 $f; echo; done 2>/dev/null | head -60
echo --- llm7
curl -s -m20 https://api.llm7.io/v1/models | python3 -c "import sys,json;d=json.load(sys.stdin);d=d if isinstance(d,list) else d['data'];print(len(d));print(' '.join(m['id'] for m in d))"
for m in gpt-oss-20b deepseek-v4-pro mistral-Nemo-Instruct-2407 gemma4:31b DeepSeek-V4-Flash-0731 glm-5.2 minimax-m3 nemotron-3-nano-30b codestral-latest; do
 echo "== $m"; curl -s -m50 -w " HTTP %{http_code} %{time_total}s\n" https://api.llm7.io/v1/chat/completions -H 'Content-Type: application/json' -H 'Authorization: Bearer unused' -d "{\"model\":\"$m\",\"max_tokens\":120,\"messages\":[{\"role\":\"user\",\"content\":\"Столица Франции? Ответь по-русски одним словом.\"}]}" | tail -c 300; sleep 3
done
