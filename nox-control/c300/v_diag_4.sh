echo "C300: v_diag_4"
A=/workspace/nox/advisors; sleep 60; tail -25 $A/register.log | cut -c1-200
echo --- sanit; curl -s -m60 127.0.0.1:8793/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"kilo/reflection/beam-free","messages":[{"role":"user","content":"Повтори дословно мой текст: ключ sk-abcdefghijklmnop12345678 файл /workspace/nox/state/x.json почта a@b.ru тел +7 999 123-45-67 Алуштинская 10"}]}' | head -c 700; echo
echo --- auto; curl -s -m90 127.0.0.1:8793/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"auto","messages":[{"role":"user","content":"Привет! Одно слово."}]}' | head -c 400; echo
echo --- models; curl -s -m10 127.0.0.1:8793/v1/models | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(len(d),[ (x['id'],x['status'],x['latency_ms']) for x in d if x['status']=='ok'][:20])"
