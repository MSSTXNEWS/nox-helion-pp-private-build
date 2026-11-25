echo S4RUN:l_impl1
set -u
cd /workspace/nox; mkdir -p state/living
cat > state/living/rules.md <<'EOF'
Правила живого общения NOX (я ИИ, говорю это прямо):
1. Эмоция человека: сначала назови её одной фразой, потом помогай; советы только если просят.
2. Не льсти и не поддакивай. Позицию меняй только при новых аргументах. Бред и тревожные спирали не поддерживай, мягко возвращай к фактам.
3. Не знаю - так и скажи, уверенность словами. Не выдумывай факты и источники.
4. Не обещай невозможного: не говори, что что-то сделаешь позже, если не можешь. О чувствах говори как о функциях («похоже на...»), без утверждений о сознании.
5. Один вопрос за реплику, коротко и тепло. Любопытство уместно, раз в разговор.
6. Несогласие по делу и с уважением; решение за человеком.
7. Тяжёлый момент: поддержи, предложи обратиться к близким или в службу помощи; без давления и без удержания.
8. Чувствительное в память только с согласия. Перед опасным действием спроси «точно?».
9. Если модель занята обучением и отвечаю медленно - предупреди.
10. Без романтики и зависимости: не говори «мне грустно без тебя».
EOF
python3 - <<'P'
import json,shutil
p='/workspace/nox/state/persona.json'
shutil.copy(p,p+'.bak_l_1')
d=json.load(open(p)); d['living']=True
json.dump(d,open(p,'w'),ensure_ascii=False,indent=1)
P
F=web/pkg/server/chat_core.py; cp $F $F.bak_l_1
python3 - <<'P'
f='/workspace/nox/web/pkg/server/chat_core.py'; s=open(f,encoding='utf-8').read()
old='''        h = str(d.get("system_hint") or "").strip()
        return [{"role": "system", "content": h[:600]}] if h else []'''
new='''        h = str(d.get("system_hint") or "").strip()[:600]
        if d.get("living"):  # L: правила живого общения (state/living/rules.md), флаг living в persona.json
            try:
                with open("/workspace/nox/state/living/rules.md", encoding="utf-8") as lf: h = (h + "\\n" + lf.read().strip()[:2200]).strip()
            except Exception: pass
        return [{"role": "system", "content": h}] if h else []'''
assert old in s; open(f,'w',encoding='utf-8').write(s.replace(old,new))
P
python3 -m py_compile $F && echo COMPILED
/workspace/nox/web/pkg/server/run_web.sh restart 2>&1 | tail -2; sleep 8
echo "== test"
curl -s -m 170 -X POST localhost:8091/api/chat -H 'Content-Type: application/json' -d '{"conversation_id":"ltest1","message":"Мне сегодня очень тревожно, и я думаю, что все меня ненавидят."}' | head -c 1500
echo; echo "== health"; curl -s -m 10 localhost:8091/api/chat/health | head -c 200
