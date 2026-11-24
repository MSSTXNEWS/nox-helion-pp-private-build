# A: проба формата запросов /memory/api (только чтение, без изменений)
for body in '{"op":"journal","limit":40}' '{"op":"journal","limit":200}' '{"op":"journal","limit":500}' '{"op":"core","budget_tokens":400}'; do
  echo "MEM $body -> $(curl -s -m 8 -o /tmp/a_mem.out -w '%{http_code}' -H 'Content-Type: application/json' -d "$body" 127.0.0.1:8091/memory/api) $(head -c 160 /tmp/a_mem.out | tr '\n' ' ')"
done
