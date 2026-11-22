"""Explicit RU/ES requests for read-only Brain800 operations.

For task diagrams, A -> B means A must be finished before B. A leading check
marks a completed task. Semicolons and line breaks separate chains. Previous
text is used only if explicitly requested and comes from a user message.
"""
import re


TEXT_ACTIONS = {
    "посчитай частоты слов": "frequency",
    "посчитай частоту слов": "frequency",
    "calcula la frecuencia de palabras": "frequency",
    "извлеки числа": "numbers",
    "extrae los números": "numbers",
    "разбей на предложения": "sentences",
    "divide en oraciones": "sentences",
    "оцени время чтения": "reading_time",
    "estima el tiempo de lectura": "reading_time",
    "выдели цитаты": "quote_pairs",
    "extrae las citas": "quote_pairs",
    "удали повторяющиеся строки": "dedupe_lines",
    "quita las líneas duplicadas": "dedupe_lines",
}
GRAPH_ACTIONS = {
    "упорядочи задачи": "dependency_order",
    "ordena las tareas": "dependency_order",
    "покажи доступные задачи": "ready_queue",
    "muestra las tareas disponibles": "ready_queue",
    "разбей работы на параллельные этапы": "parallel_waves",
    "agrupa las tareas por etapas paralelas": "parallel_waves",
    "найди блокирующие задачи": "blocker_map",
    "identifica las tareas bloqueantes": "blocker_map",
}
PREVIOUS_SUFFIXES = (" в моём предыдущем сообщении", " в моем предыдущем сообщении",
                     " en mi mensaje anterior")


def graph_data(fragment):
    tasks = {}
    chains = [s.strip() for s in re.split(r"[;\n]+",fragment) if s.strip()]
    if not chains or len(chains)>100:
        return None
    linked = False
    for chain in chains:
        names = re.split(r"\s*(?:->|→)\s*", chain)
        linked |= len(names)>1
        prev = None
        for name in names:
            raw = name.strip()
            done = raw.startswith("✓")
            task = raw.removeprefix("✓").strip()
            if not re.fullmatch(r"[\w][\w .()/–-]{0,79}",task) or len(tasks)>200:
                return None
            item = tasks.setdefault(task, {"id":task,"deps":[],"status":"todo"})
            if done:
                item["status"] = "done"
            if prev is not None and prev not in item["deps"]:
                item["deps"].append(prev)
            prev = task
    return {"tasks":list(tasks.values())} if linked else None


def score_data(fragment):
    rows=[s.strip() for s in fragment.split(";")]
    if not 3<=len(rows)<=30: return None
    variants={}
    weights={}
    for i,row in enumerate(rows):
        name,colon,ratings=row.partition(":")
        name=name.strip()
        if not name or not colon: return None
        if i==0 and name.casefold() not in {"веса","pesos"}: return None
        if name in variants: return None
        scores={}
        for field in ratings.split(","):
            m=re.fullmatch(r"\s*([\w -]{1,40}?)\s*=\s*(\d{1,5}(?:\.\d{1,3})?)\s*",field)
            if not m or m[1].strip() in scores: return None
            scores[m[1].strip()]=float(m[2])
        if i==0:
            if not any(scores.values()): return None
            weights=scores
        elif scores.keys()==weights.keys():
            variants[name]=scores
        else:
            return None
    return {"decision_id":"comparison","decisions":[{"id":"comparison","weights":weights,"options":variants}]}


def last_user(history, current):
    if not isinstance(history,(list,tuple)):
        return None
    for row in reversed(history):
        if not isinstance(row,dict) or row.get("role")!="user":
            continue
        body = row.get("content",row.get("text"))
        if isinstance(body,str) and body.strip() and body.strip()!=current and len(body)<=30000:
            return body
    return None


def route_phrase(text,history=None):
    if not isinstance(text,str) or len(text)>40000:
        return None
    command=text.strip()
    head,sep,fragment=command.partition(":")
    action=" ".join(head.casefold().split())
    if sep and fragment.strip():
        if action in TEXT_ACTIONS:
            return {"op":"perception.document."+TEXT_ACTIONS[action],"data":{"text":fragment.lstrip()}}
        if action in {"сравни варианты по баллам","compara las opciones por puntos"}:
            data=score_data(fragment)
            if data is not None: return {"op":"project.option_utilities","data":data}
        if action in GRAPH_ACTIONS:
            data=graph_data(fragment.strip())
            if data is not None: return {"op":"project."+GRAPH_ACTIONS[action],"data":data}
        if action in {"сравни формулировки","compara las versiones"}:
            pair=re.fullmatch(r'\s*«([^»]+)»\s*(?:и|y|→)\s*«([^»]+)»\s*[.!]?\s*',fragment,re.S|re.I)
            if pair: return {"op":"perception.document.word_diff","data":{"text":pair[1],"new_text":pair[2]}}
        find=re.fullmatch(r'(?:найди в тексте|busca en el texto)\s+«([^»]{1,256})»',head.strip(),re.I)
        if find:
            return {"op":"perception.document.find","data":{"query":find[1],"text":fragment.lstrip()}}
    elif not sep:
        bare=action.rstrip(".!?")
        for suffix in PREVIOUS_SUFFIXES:
            if bare.endswith(suffix) and bare[:-len(suffix)] in TEXT_ACTIONS:
                body=last_user(history,command)
                if body is not None:
                    return {"op":"perception.document."+TEXT_ACTIONS[bare[:-len(suffix)]],"data":{"text":body}}
    return None


EXAMPLES=[
    ("Сравни варианты по баллам: веса: качество=2, время=1; утро: качество=5, время=2; вечер: качество=3, время=4","project.option_utilities"),
    ("Упорядочи задачи: запись → монтаж → выпуск; титры → выпуск","project.dependency_order"),
    ("Muestra las tareas disponibles: ✓guion -> grabación -> mezcla","project.ready_queue"),
    ("Разбей работы на параллельные этапы: звук -> показ; цвет -> показ","project.parallel_waves"),
    ("Identifica las tareas bloqueantes: guion -> voz; voz -> mezcla","project.blocker_map"),
    ("Посчитай частоты слов: Свет, голос, свет.","perception.document.frequency"),
    ("Extrae los números: Duró 12 minutos y costó 9 €.","perception.document.numbers"),
    ("Разбей на предложения: Солнце взошло. Потом пошёл дождь.","perception.document.sentences"),
    ("Estima el tiempo de lectura: Vamos a leer este pequeño texto.","perception.document.reading_time"),
    ("Сравни формулировки: «Войти в чат» и «Открыть разговор»","perception.document.word_diff"),
    ("Busca en el texto «voz»: La voz del relato.","perception.document.find"),
    ("Выдели цитаты: Он добавил «ещё одну паузу».","perception.document.quote_pairs"),
    ("Quita las líneas duplicadas: cine\ncine\nvoz","perception.document.dedupe_lines"),
]
