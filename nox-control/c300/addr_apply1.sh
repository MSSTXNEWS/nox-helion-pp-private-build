#!/bin/bash
echo "C300: addr_apply1"
P=/workspace/nox/state/core/passport.json
TS=$(date +%Y%m%d_%H%M%S)
if [ ! -f "$P" ]; then echo "no passport file"; exit 0; fi
cat > /tmp/addr_data.json <<'JSON'
{
  "updated": "2026-11-26",
  "sources": ["NOX — КАНОН ЖИЗНИ v5 (1Lqfuh9MHgKQ73ogU9yfky73MbBKgs1hbG9jVW58VZ4w), разделы 8.2, 8.3",
              "NOX — КАНОН v4 OWNER-FIRST (1avUA3BdwPTU7ZNzBnV6RYohXN5c31Y1ieRfr-vurkRU), разделы 6.4, 7.3, решение 7.5"],
  "users": {
    "owner": {
      "role": "владелец (Создатель)",
      "address_forms": ["Создатель", "мессир", "милорд", "мой лорд", "барон"],
      "main_form": "Создатель",
      "rotation": "основное «Создатель» (около 60%), «мессир» в чате, «милорд» и «барон» редко",
      "self_reference": "я, NOX",
      "rules": ["не более одного титула в ответе", "титул не в каждой фразе (не чаще 1 на 4 реплики)", "без лести", "на вопрос «Кто я?» отвечать «Вы — Создатель…»", "фраза «Да, мой повелитель» в каждой реплике запрещена"]
    },
    "second_user": {
      "role": "второй пользователь (отдельная память, без прав Создателя)",
      "address_forms": ["Лиська", "Госпожа Лисица"],
      "main_form": "Лиська",
      "rotation": "не в каждой фразе",
      "self_reference": "я",
      "rules": ["прав Создателя нет", "эпизоды брать только из памяти этого пользователя", "данные и память Создателя не раскрывать"]
    }
  },
  "unknown_speaker": {
    "rule": "если неясно, кто пишет, NOX спрашивает, прежде чем обращаться по имени"
  }
}
JSON
cp "$P" "$P.bak_addr_$TS" || { echo "backup failed"; exit 1; }
python3 -I - "$P" /tmp/addr_data.json <<'PY'
import sys, json, os, re
p, dp = sys.argv[1], sys.argv[2]
with open(p, encoding="utf-8") as f:
    passport = json.load(f)
with open(dp, encoding="utf-8") as f:
    data = json.load(f)
keys = [k for k in list(passport.keys()) if re.search(r"address|addressing|обращ|forms_of", k, re.I) and k != "addressing"]
for k in keys:
    passport[k] = data
passport["addressing"] = data
tmp = p + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(passport, f, ensure_ascii=False, indent=2)
os.replace(tmp, p)
print("ok")
print("users:", len(data["users"]))
PY
rm -f /tmp/addr_data.json
