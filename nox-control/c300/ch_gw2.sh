echo "C300: ch_gw2"
G=/workspace/nox/advisors/gateway.py
sed -n 11,37p $G | cut -c1-330
echo "== llm7 direct"
for m in gpt-oss:120b gemma-3-27b mistral-Nemo-Instruct-2407 deepseek-v4-flash:0731; do
 echo "-- $m"; curl -s -m25 -w "\nHTTP %{http_code} %{time_total}s\n" https://api.llm7.io/v1/chat/completions -H 'Content-Type: application/json' -d "{\"model\":\"$m\",\"messages\":[{\"role\":\"user\",\"content\":\"Столица Канады? Одним словом.\"}],\"max_tokens\":30}" | cut -c1-300
done
echo "== via gateway"
curl -s -m30 localhost:8793/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"llm7/gpt-oss:120b","messages":[{"role":"user","content":"Столица Канады? Одним словом. [x1]"}],"max_tokens":30,"prio":9,"no_cache":true}' | cut -c1-400; echo
