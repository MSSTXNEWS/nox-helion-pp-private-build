"""Ten project-memory entities, with revisioned transitions in a conversation-scoped journal."""
KINDS = {"intent":"замысел","choice":"решение","question":"открытый вопрос","hypothesis":"гипотеза",
         "promise":"обещание","preference":"предпочтение","cue":"ориентир","objection":"возражение",
         "lesson":"урок","draft":"черновик"}
ACTIONS = {"open":"создать запись","revise":"исправить запись","close":"закрыть","reopen":"вернуть в работу",
           "read":"открыть текущее состояние","history":"показать все версии","active":"найти открытые записи",
           "search":"найти по фрагменту","compare":"сравнить две ревизии","source":"показать происхождение"}
WRITES = {"open","revise","close","reopen"}
META = {f"{k}.{a}":f"{v.capitalize()} • {label}" for k,v in KINDS.items() for a,label in ACTIONS.items()}

def execute(db, scope, kind, act, p):
    if act in ("active","search"):
        term = p.get("query","")
        if not isinstance(term,str) or (act=="search" and not term.strip()):
            raise ValueError("Для поиска нужен текст")
        rows = db.execute("""SELECT key,text,version,closed,source FROM latest
                             WHERE scope=? AND kind=? AND (?='search' OR closed=0)
                             AND instr(fold(text),fold(?))>0 ORDER BY seq DESC LIMIT 100""",
                          (scope,kind,act,term))
        return [dict(r) for r in rows]
    key = p.get("key")
    if not isinstance(key,str) or not 1<=len(key)<=150: raise ValueError("Нужен key длиной 1–150")
    args = (scope,kind,key)
    def versions():
        return [dict(r) for r in db.execute("""SELECT version,text,closed,source FROM entries
                       WHERE scope=? AND kind=? AND key=? ORDER BY version""",args)]
    if act == "open":
        cur = db.execute("SELECT 1 FROM entries WHERE scope=? AND kind=? AND key=? LIMIT 1",args).fetchone()
        if cur:raise ValueError("Запись с таким key уже существует")
        old = {"version":0,"text":"","source":"","closed":False}
    else:
        cur = db.execute("""SELECT version,text,source,closed FROM entries WHERE scope=? AND kind=? AND key=?
                          ORDER BY version DESC LIMIT 1""",args).fetchone()
        if not cur:raise ValueError("Запись не найдена")
        old = dict(cur)
    if act == "history":return versions()
    if act == "read":return {"key":key,**old}
    if act == "source":
        return [{"version":r["version"],"source":r["source"]} for r in versions()]
    if act == "compare":
        v = {r["version"]:r for r in versions()}
        a,b = v[p["before"]],v[p["after"]]
        return {k:{"before":a[k],"after":b[k]} for k in ("text","source","closed") if a[k]!=b[k]}
    if act != "open" and p.get("expected_version") != old["version"]:
        raise ValueError("Версия изменилась: откройте актуальную запись")
    if act == "close" and old["closed"] or act == "reopen" and not old["closed"]:
        raise ValueError("Переход из текущего состояния невозможен")
    text = p["text"] if act in ("open","revise") else old["text"]
    source = p.get("source",old["source"])
    if not isinstance(text,str) or not text.strip() or len(text)>4000 or not isinstance(source,str) or len(source)>500:
        raise ValueError("Требуется текст до 4000 символов, источник до 500")
    closed = act == "close" or bool(old["closed"] and act != "reopen")
    version = old["version"]+1
    db.execute("INSERT INTO entries(scope,kind,key,version,text,closed,source) VALUES(?,?,?,?,?,?,?)",
               (*args,version,text,int(closed),source))
    return {"key":key,"version":version,"text":text,"closed":closed,"source":source}
