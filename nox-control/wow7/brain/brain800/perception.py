"""NOX perception operations. All positions use Unicode code-point indices.
Times are integer milliseconds, and all ranges are half-open [start,end).
Input is JSON. Operations have no I/O and return independent JSON values.
"""
import bisect
import collections
import difflib
import hashlib
import html
import re
import textwrap
import unicodedata

OPS, META = {}, {}
WORDS = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
SENTENCES = re.compile(r"[^.!?…\n]+(?:[.!?…]+|(?=\n)|$)")
LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^()\s]+)\)")
HEADING = re.compile(r"(?m)^(#{1,6})[ \t]+(.+?)\s*?$")


def register(group, name, description, function):
    key = group + "." + name
    if key in OPS:
        raise RuntimeError(key)
    OPS[key], META[key] = function, description


def text(p, key="text"):
    value = p.get(key, "")
    if not isinstance(value, str):
        raise ValueError(key + " must be a string")
    return value


def num(p, key, default=0, minimum=0):
    v = p.get(key, default)
    if isinstance(v, bool) or not isinstance(v, int) or v < minimum:
        raise ValueError(key + " must be an integer >= " + str(minimum))
    return v


def spans(s, pattern):
    out = []
    for m in pattern.finditer(s):
        raw = m.group()
        left = m.start() + len(raw) - len(raw.lstrip())
        right = m.end() - len(raw) + len(raw.rstrip())
        if left < right:
            out.append({"start": left, "end": right, "text": s[left:right]})
    return out


def words(s):
    return [m.group() for m in WORDS.finditer(s)]


def paragraphs(s):
    return spans(s, re.compile(r"(?s).+?(?=\n[ \t]*\r?\n|\Z)"))


def lines(s):
    pos, rows = 0, []
    for raw in s.splitlines(keepends=True):
        content = raw.splitlines()[0] if raw.splitlines() else ""
        rows.append({"line": len(rows) + 1, "start": pos, "end": pos + len(content), "text": content})
        pos += len(raw)
    if not rows or s.endswith(("\r", "\n")):
        rows.append({"line": len(rows)+1, "start": pos, "end": pos, "text": ""})
    return rows


def hash_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def frequency(s):
    counts = collections.Counter(w.casefold() for w in words(s))
    return [{"word": w, "count": n} for w, n in sorted(counts.items(), key=lambda x:(-x[1],x[0]))]


def search(s, p):
    q = text(p,"query")
    if not q:
        raise ValueError("query must contain text")
    flags = re.IGNORECASE if p.get("ignore_case", False) else 0
    return [{"start":m.start(),"end":m.end(),"text":m.group()} for m in re.finditer(re.escape(q),s,flags)]


def window(s, k):
    chunks, start = [], 0
    while start < len(s):
        end = min(start + k, len(s))
        if end < len(s):
            cut = max(s.rfind(" ", start, end), s.rfind("\n", start, end))
            if cut > start:
                end = cut + 1
        chunks.append({"start":start,"end":end,"text":s[start:end]})
        start = end
    return chunks


def worddiff(old, new):
    a, b = words(old), words(new)
    return [{"operation":tag,"before":a[i:j],"after":b[k:l]}
            for tag,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=True).get_opcodes() if tag!="equal"]


def dedupe_lines(s):
    seen, out = set(), []
    for line in s.splitlines():
        key = line.strip().casefold()
        if key not in seen:
            out.append(line)
            seen.add(key)
    return "\n".join(out)


def document(p, op):
    s = text(p)
    if op=="lines": return lines(s)
    if op=="paragraphs": return paragraphs(s)
    if op=="sentences": return spans(s, SENTENCES)
    if op=="tokens": return spans(s, WORDS)
    if op=="outline": return [{"depth":len(m[1]),"title":m[2],"start":m.start()} for m in HEADING.finditer(s)]
    if op=="links": return [{"label":m[1],"url":m[2],"start":m.start()} for m in LINK.finditer(s)]
    if op=="tasks":
        return [{"done":m[1].lower()=="x","text":m[2],"start":m.start()} for m in
                re.finditer(r"(?im)^[ \t]*[-*]\s+\[([ x])\][ \t]+([^\n]+)",s)]
    if op=="frequency": return frequency(s)
    if op=="reading_time":
        wpm=num(p,"words_per_minute",160,1)
        return {"words":len(words(s)),"seconds":(60*len(words(s))+wpm-1)//wpm}
    if op=="indent":
        return [{"line":r["line"],"columns":len(r["text"][:len(r["text"])-len(r["text"].lstrip(" \t"))].expandtabs(num(p,"tab_size",4,1)))} for r in lines(s)]
    if op=="find": return search(s,p)
    if op=="chunks": return window(s,num(p,"chunk_size",160,1))
    if op=="normalize": return unicodedata.normalize("NFC",s.replace("\r\n","\n").replace("\r","\n"))
    if op=="compact_spaces": return "\n".join(re.sub(r"[ \t]+"," ",v).strip() for v in s.split("\n"))
    if op=="dedupe_lines": return dedupe_lines(s)
    if op=="wrap": return "\n".join(textwrap.fill(line, width=num(p,"width",72,1)) for line in s.split("\n"))
    if op=="checksum": return hash_text(s)
    if op=="word_diff": return worddiff(s,text(p,"new_text"))
    if op=="numbers": return [{"value":m.group(),"start":m.start(),"end":m.end()} for m in re.finditer(r"(?<!\w)[−+-]?\d+(?:[,.]\d+)?(?:[ \u00a0]?(?:%|€|₽|\$))?",s)]
    if op=="quote_pairs": return [{"quote":m[1] or m[2],"start":m.start(),"end":m.end()} for m in re.finditer(r'«([^»]+)»|“([^”]+)”',s)]
    raise KeyError(op)


def selection(p):
    s = text(p)
    a, b = num(p,"start"), num(p,"end",len(s))
    if not a <= b <= len(s):
        raise ValueError("selection outside document")
    return s,a,b


def enclosing(rows, a, b):
    return [r for r in rows if (r["start"] < b and r["end"] > a) or (a==b and r["start"]<=a<r["end"])]


def anchor(s,a,b,radius):
    return {"quote":s[a:b],"prefix":s[max(0,a-radius):a],"suffix":s[b:b+radius],"start":a,"end":b,"document_sha256":hash_text(s)}


def relocate(old,a,b,new,radius):
    record = anchor(old,a,b,radius)
    q = record["quote"]
    if not q: raise ValueError("empty anchor")
    result = []
    pos = new.find(q)
    while pos >= 0:
        prefix=record["prefix"]
        suffix=record["suffix"]
        left=0
        while left < min(len(prefix),pos) and prefix[-1-left]==new[pos-1-left]: left+=1
        right=0
        while right < min(len(suffix),len(new)-pos-len(q)) and suffix[right]==new[pos+len(q)+right]: right+=1
        result.append({"start":pos,"end":pos+len(q),"context_match":left+right})
        pos=new.find(q,pos+1)
    result.sort(key=lambda r:(-r["context_match"],r["start"]))
    status="missing" if not result else "unique" if len(result)==1 or result[0]["context_match"]>result[1]["context_match"] else "ambiguous"
    return {"status":status,"candidates":result}


def selected(p, op):
    s,a,b=selection(p)
    q=s[a:b]
    if op=="extract": return q
    if op=="anchor": return anchor(s,a,b,num(p,"radius",32))
    if op=="relocate": return relocate(s,a,b,text(p,"new_text"),num(p,"radius",32))
    if op=="replace": return s[:a]+text(p,"replacement")+s[b:]
    if op=="redact": return s[:a]+"".join("█" if not c.isspace() else c for c in q)+s[b:]
    if op=="surround": return s[:a]+text(p,"left")+q+text(p,"right")+s[b:]
    if op=="before": return s[max(0,a-num(p,"radius",32)):a]
    if op=="after": return s[b:b+num(p,"radius",32)]
    if op=="coordinates":
        rows=lines(s)
        offsets=[r["start"] for r in rows]
        def xy(pos):
            i=bisect.bisect_right(offsets,pos)-1
            return {"line":i+1,"column":pos-offsets[i]+1}
        return {"start":xy(a),"end":xy(b)}
    if op=="utf8_offsets": return {"start":len(s[:a].encode()),"end":len(s[:b].encode())}
    if op=="utf16_offsets": return {"start":len(s[:a].encode("utf-16-le"))//2,"end":len(s[:b].encode("utf-16-le"))//2}
    if op=="sentences": return enclosing(spans(s,SENTENCES),a,b)
    if op=="paragraphs": return enclosing(paragraphs(s),a,b)
    if op=="words": return enclosing(spans(s,WORDS),a,b)
    if op=="heading_path":
        path=[]
        for m in HEADING.finditer(s):
            if m.start()>a: break
            depth=len(m[1])
            path=[r for r in path if r["depth"]<depth]+[{"depth":depth,"title":m[2]}]
        return path
    if op=="trim":
        start=a+len(q)-len(q.lstrip()); end=max(start,b-len(q)+len(q.rstrip()))
        return {"start":start,"end":end,"text":s[start:end]}
    if op=="intersection":
        c,d=num(p,"other_start"),num(p,"other_end",len(s))
        if not c<=d<=len(s):raise ValueError("invalid other selection")
        lo,hi=max(a,c),min(b,d)
        return {"start":lo,"end":hi,"text":s[lo:hi]} if lo<hi else None
    if op=="context_diff": return worddiff(q,text(p,"replacement"))
    if op=="positions":
        if not q: return []
        return [m.start() for m in re.finditer(re.escape(q),s)]
    if op=="selected_uri": return {"document":text(p,"document_id"),"revision":hash_text(s),"start":a,"end":b,"quote":q}
    raise KeyError(op)

def records(p, key):
    rows = p.get(key, [])
    if not isinstance(rows, list) or any(not isinstance(r,dict) for r in rows):
        raise ValueError(key+" must be an array of objects")
    return rows


def cues(p):
    result=[]
    for row in records(p,"cues"):
        start,end=num(row,"start_ms"),num(row,"end_ms")
        if end<=start:raise ValueError("cue duration must be positive")
        result.append({"start_ms":start,"end_ms":end,"text":text(row),"speaker":text(row,"speaker")})
    return sorted(result,key=lambda r:r["start_ms"])


def tc(ms,separator="."):
    h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); sec,ms=divmod(ms,1000)
    return f"{h:02}:{m:02}:{sec:02}{separator}{ms:03}"


def shifted(rows,offset):
    return [dict(r,start_ms=max(0,r["start_ms"]+offset),end_ms=r["end_ms"]+offset)
            for r in rows if r["end_ms"]+offset>0]


def coverage(rows):
    blocks=[]
    for r in rows:
        a,b=r["start_ms"],r["end_ms"]
        if blocks and blocks[-1][1]>=a: blocks[-1][1]=max(blocks[-1][1],b)
        else: blocks.append([a,b])
    return blocks


def gaps(rows):
    blocks=coverage(rows)
    return [{"start_ms":a[1],"end_ms":b[0],"duration_ms":b[0]-a[1]} for a,b in zip(blocks,blocks[1:])]


def clipping(rows,lo,hi):
    if hi<lo:raise ValueError("end_ms before start_ms")
    return [dict(r,start_ms=max(lo,r["start_ms"]),end_ms=min(hi,r["end_ms"])) for r in rows
            if max(lo,r["start_ms"])<min(hi,r["end_ms"])]


def parse_srt(s):
    result=[]
    regex=r"(\d+):(\d{2}):(\d{2})[,.](\d{3})"
    def ms(parts):
        h,m,sec,frac=map(int,parts)
        if max(m,sec)>59:raise ValueError("invalid SRT timestamp")
        return ((h*60+m)*60+sec)*1000+frac
    for block in re.split(r"\n[ \t]*\n",s.strip().replace("\r\n","\n")):
        if not block:continue
        items=block.splitlines()
        if items[0].strip().isdigit():items=items[1:]
        match=re.fullmatch(regex+r"\s*-->\s*"+regex,items[0].strip()) if items else None
        if not match:raise ValueError("invalid SRT time range")
        result.append({"start_ms":ms(match.groups()[:4]),"end_ms":ms(match.groups()[4:]),"text":"\n".join(items[1:])})
    return cues({"cues":result})


def caption(p,op):
    if op=="parse_srt":return parse_srt(text(p,"srt"))
    rows=cues(p)
    if op=="srt":return "\n\n".join(f"{i}\n{tc(r['start_ms'],',')} --> {tc(r['end_ms'],',')}\n{r['text']}" for i,r in enumerate(rows,1))
    if op=="vtt":return "WEBVTT\n\n"+"\n\n".join(f"{tc(r['start_ms'])} --> {tc(r['end_ms'])}\n{html.escape(r['text'])}" for r in rows)
    if op=="transcript":return "\n".join(r["text"] for r in rows)
    if op=="speech_turns":
        out=[]
        for r in rows:
            if out and r["speaker"]==out[-1]["speaker"]:
                x=out[-1];x["end_ms"]=max(x["end_ms"],r["end_ms"]);x["text"]+=" "+r["text"]
            else:out.append(r.copy())
        return out
    if op=="shift":return shifted(rows,num(p,"offset_ms",0,-10**15))
    if op=="clip":return clipping(rows,num(p,"start_ms"),num(p,"end_ms"))
    if op=="rebase":return shifted(rows,-rows[0]["start_ms"]) if rows else []
    if op=="remove_tags":return [dict(r,text=html.unescape(re.sub(r"</?[^<>\n]{1,128}>","",r["text"]))) for r in rows]
    if op=="wrap":return [dict(r,text=textwrap.fill(r["text"],width=num(p,"width",42,1))) for r in rows]
    if op=="reading_load":return [dict(r,characters_per_second=round(1000*len(r["text"])/(r["end_ms"]-r["start_ms"]),2)) for r in rows]
    if op=="overlaps":
        out=[];last_end=0
        for r in rows:
            if r["start_ms"]<last_end:out.append({"start_ms":r["start_ms"],"end_ms":min(last_end,r["end_ms"]),"text":r["text"]})
            last_end=max(last_end,r["end_ms"])
        return out
    if op=="gaps":return gaps(rows)
    if op=="collapse_spaces":return [dict(r,text=" ".join(r["text"].split())) for r in rows]
    if op=="speaker":return [r for r in rows if r["speaker"]==text(p,"speaker")]
    if op=="search":
        q=text(p,"query").casefold()
        if not q:raise ValueError("query must contain text")
        return [r for r in rows if q in r["text"].casefold()]
    if op=="split_lines":
        out=[]
        for r in rows:
            parts=[s for s in r["text"].splitlines() if s.strip()]
            width=r["end_ms"]-r["start_ms"]
            if len(parts)<2 or len(parts)>width:out.append(r);continue
            for i,s in enumerate(parts):
                out.append(dict(r,text=s,start_ms=r["start_ms"]+i*width//len(parts),end_ms=r["start_ms"]+(i+1)*width//len(parts)))
        return out
    if op=="dedupe":
        seen=set();out=[]
        for r in rows:
            k=tuple(r.values())
            if k not in seen:out.append(r);seen.add(k)
        return out
    if op=="coverage":return coverage(rows)
    if op=="word_alignment":
        out=[]
        for r in rows:
            tokens=words(r["text"]); duration=r["end_ms"]-r["start_ms"]
            for i,w in enumerate(tokens):
                out.append({"word":w,"estimated_start_ms":r["start_ms"]+duration*i//len(tokens),"estimated_end_ms":r["start_ms"]+duration*(i+1)//len(tokens)})
        return out
    raise KeyError(op)


def playback(p,op):
    rows=cues(p)
    pos=num(p,"position_ms")
    finish=max((r["end_ms"] for r in rows),default=0)
    completed=[r for r in rows if r["end_ms"]<=pos]
    active=[r for r in rows if r["start_ms"]<=pos<r["end_ms"]]
    ahead=[r for r in rows if r["start_ms"]>pos]
    if op=="active":return active
    if op=="last_completed":return max(completed,key=lambda r:r["end_ms"],default=None)
    if op=="completed_text":return " ".join(r["text"] for r in completed)
    if op=="future_text":return " ".join(r["text"] for r in ahead)
    if op=="next":return ahead[0] if ahead else None
    if op=="remaining":return max(0,finish-pos)
    if op=="resume":
        start=min((r["start_ms"] for r in active), default=ahead[0]["start_ms"] if ahead else finish)
        return {"resume_ms":start,"repeats_partial_cue":bool(active)}
    if op=="rewind":return max(0,min(finish,pos)-num(p,"step_ms",5000))
    if op=="forward":return min(finish,pos+num(p,"step_ms",5000))
    if op=="speaker":return sorted({r["speaker"] for r in active if r["speaker"]})
    if op=="nearest_boundary":
        bounds={n for r in rows for n in (r["start_ms"],r["end_ms"])}
        return min(bounds,key=lambda n:(abs(n-pos),n)) if bounds else None
    if op=="progress":return {"position_ms":pos,"timeline_end_ms":finish,"fraction":min(1,round(pos/finish,5)) if finish else None}
    if op=="upcoming":return clipping(rows,pos,pos+num(p,"window_ms",10000))
    if op=="recent":return clipping(rows,max(0,pos-num(p,"window_ms",10000)),pos)
    if op=="next_silence":return next((dict(g,start_ms=max(g["start_ms"],pos),duration_ms=g["end_ms"]-max(g["start_ms"],pos)) for g in gaps(rows) if g["end_ms"]>pos),None)
    if op=="covered_ms":return sum(b-a for a,b in coverage(clipping(rows,0,pos)))
    if op=="boundary_log":return sorted([{"at_ms":r[key],"event":event,"cue":i} for i,r in enumerate(rows) for key,event in (("start_ms","begin"),("end_ms","end"))],key=lambda t:(t["at_ms"],t["event"]=="begin",t["cue"]))
    if op=="bookmark":return {"media_id":text(p,"media_id"),"position_ms":pos,"active_text":[r["text"] for r in active]}
    if op=="range_loop":return {"loop_start_ms":min(r["start_ms"] for r in active),"loop_end_ms":max(r["end_ms"] for r in active)} if active else None
    if op=="interrupt":
        return {"completed_cues":len(completed),"played_to_ms":pos,"partial_cues":[dict(r,played_ms=pos-r["start_ms"]) for r in active],"next_full_cue":ahead[0] if ahead else None}
    raise KeyError(op)

def dialogue(p,op):
    turns=[{"role":text(t,"role"),"text":text(t),"id":text(t,"id"),"reply_to":text(t,"reply_to")} for t in records(p,"turns")]
    if op=="by_role": return [t for t in turns if t["role"]==text(p,"role")]
    if op=="last_user":return next((t for t in reversed(turns) if t["role"]=="user"),None)
    if op=="last_assistant":return next((t for t in reversed(turns) if t["role"]=="assistant"),None)
    if op=="transcript":return "\n".join(f"{t['role']}: {t['text']}" for t in turns)
    if op=="tail":return turns[max(0,len(turns)-num(p,"limit",4)):]
    if op=="unanswered":
        out=[]
        for t in turns:
            if t["role"]=="user":out.append(t)
            elif t["role"]=="assistant":out=[]
        return out
    if op=="pairs":
        pending=[];out=[]
        for t in turns:
            if t["role"]=="user":pending.append(t)
            if t["role"]=="assistant" and pending:
                out.append({"user":pending,"assistant":t});pending=[]
        return out
    if op=="quotes":return [{"turn_id":t["id"],**q} for t in turns for q in document({"text":t["text"]},"quote_pairs")]
    if op=="questions":return [{"turn_id":t["id"],"question":s["text"]} for t in turns for s in spans(t["text"],SENTENCES) if "?" in s["text"]]
    if op=="speaker_counts":return dict(collections.Counter(t["role"] for t in turns))
    if op=="word_counts":
        result=collections.Counter()
        for t in turns:result[t["role"]]+=len(words(t["text"]))
        return dict(result)
    if op=="duplicates":
        seen={};out=[]
        for i,t in enumerate(turns):
            k=(t["role"]," ".join(t["text"].casefold().split()))
            if k in seen:out.append({"index":i,"original_index":seen[k]})
            else:seen[k]=i
        return out
    if op=="floor_changes":return [{"index":i,"from":turns[i-1]["role"],"to":t["role"]} for i,t in enumerate(turns) if i and t["role"]!=turns[i-1]["role"]]
    if op=="search":return [{"turn_id":t["id"],"matches":found} for t in turns if (found:=search(t["text"],p))]
    if op=="citations":return [{"turn_id":t["id"],**link} for t in turns for link in document({"text":t["text"]},"links")]
    if op=="focus":
        ids=[i for i,t in enumerate(turns) if t["id"]==text(p,"turn_id")]
        if len(ids)!=1:return {"match_count":len(ids),"context":[]}
        i=ids[0];n=num(p,"neighbor_turns",1)
        return {"match_count":1,"context":turns[max(0,i-n):i+n+1]}
    if op=="reply_chain":
        index={}
        for t in turns:
            if t["id"] in index:raise ValueError("reply_chain requires unique turn ids")
            index[t["id"]]=t
        key=text(p,"turn_id"); seen=set();out=[]
        while key and key in index:
            if key in seen:raise ValueError("reply chain contains a cycle")
            seen.add(key);t=index[key];out.append(t);key=t["reply_to"]
        return list(reversed(out))
    if op=="turn_delta":
        a=[t for t in turns if t["id"]==text(p,"turn_id")]
        b=[t for t in turns if t["id"]==text(p,"other_turn_id")]
        if len(a)!=1 or len(b)!=1:raise ValueError("turn_delta needs two unique matching ids")
        return worddiff(a[0]["text"],b[0]["text"])
    if op=="budget_tail":
        budget=num(p,"char_budget",3000);out=[]
        for t in reversed(turns):
            if len(t["text"])>budget:break
            budget-=len(t["text"]);out.append(t)
        return list(reversed(out))
    if op=="role_vocabulary":
        return frequency(" ".join(t["text"] for t in turns if t["role"]==text(p,"role")))
    raise KeyError(op)


def family(group,fn,entries):
    for line in entries.strip().splitlines():
        op,desc=line.split("|",1)
        register(group,op,desc,lambda payload, name=op:fn(payload,name))


family("document",document,"""
lines|Разметить строки документа с номерами и исходными смещениями
paragraphs|Найти границы непустых абзацев
sentences|Выделить предложения по конечной пунктуации
tokens|Выделить словесные токены с исходными координатами
outline|Построить оглавление Markdown по уровням заголовков
links|Извлечь подписанные HTTP-ссылки Markdown
tasks|Извлечь открытые и завершённые пункты Markdown
frequency|Подсчитать частоты слов без учёта регистра
reading_time|Оценить длительность чтения по заданному темпу
indent|Измерить видимые отступы строк с учётом ширины табуляции
find|Найти вхождения буквального запроса
chunks|Разбить текст на фрагменты с ограничением длины и исходными границами
normalize|Привести переводы строк к LF и символы к Unicode NFC
compact_spaces|Нормализовать горизонтальные пробелы по строкам
dedupe_lines|Выбрать первое вхождение каждой строки без учёта регистра и краевых пробелов
wrap|Перенести строки под заданную ширину колонки
checksum|Вычислить SHA-256 текста для проверки версии
word_diff|Сравнить две редакции документа на уровне слов
numbers|Найти числа с десятичными дробями и символами валют или процентов
quote_pairs|Извлечь цитаты в угловых или типографских кавычках
""")
family("selection",selected,"""
extract|Прочитать точный фрагмент документа по границам
anchor|Закрепить цитату с соседним контекстом и версией текста
relocate|Перенести цитату в новую редакцию с оценкой неоднозначности
replace|Создать редакцию с заменённым выделением
redact|Закрыть выбранные символы с сохранением пробелов и координат
surround|Вставить обрамляющие символы вокруг выделения
before|Вернуть ограниченный контекст перед началом выделения
after|Вернуть ограниченный контекст после выделения
coordinates|Перевести позиции выделения в строки и столбцы
utf8_offsets|Вычислить байтовые координаты фрагмента в UTF-8
utf16_offsets|Перевести границы выделения в координаты браузера UTF-16
sentences|Найти предложения, пересекающие выделение
paragraphs|Найти абзацы, пересекающие выделение
words|Найти слова, которых касается выделение
heading_path|Восстановить цепочку разделов Markdown в точке выделения
trim|Уточнить границы выделения без краевых пробелов
intersection|Вычислить общую часть двух выделений
context_diff|Сопоставить слова исходной цитаты и предложенной замены
positions|Найти повторения выбранной цитаты в исходном документе
selected_uri|Собрать ссылочную запись фрагмента с документом и ревизией
""")
family("caption",caption,"""
parse_srt|Прочитать таймкоды и реплики из строки SRT
srt|Записать упорядоченные субтитры в SRT
vtt|Записать экранированные субтитры в WebVTT
transcript|Собрать чистую текстовую расшифровку субтитров
speech_turns|Собрать последовательные субтитры одного говорящего в реплику
shift|Сдвинуть дорожку на заданное число миллисекунд
clip|Обрезать субтитры по интервалу
rebase|Привязать начало первой реплики к нулю
remove_tags|Удалить оформительские теги из текста субтитров
wrap|Перенести субтитры под ширину экрана
reading_load|Оценить плотность субтитров в символах в секунду
overlaps|Найти участки наложения дорожек
gaps|Найти промежутки между покрытыми субтитрами интервалами
collapse_spaces|Свести многострочные субтитры в нормализованные фразы
speaker|Отфильтровать субтитры одного говорящего
search|Найти время упоминания фразы по тексту субтитров
split_lines|Разделить многострочную реплику на равные временные отрезки
dedupe|Убрать точные дубликаты субтитров
coverage|Объединить покрытые субтитрами интервалы
word_alignment|Приблизить временные границы слов равномерным разбиением
""")
family("playback",playback,"""
active|Показать субтитры в текущей точке воспроизведения
last_completed|Найти последнюю полностью воспроизведённую реплику по позиции плеера
completed_text|Собрать текст полностью прошедших к позиции плеера реплик
future_text|Собрать текст реплик, которые начнутся после позиции плеера
next|Найти следующую ещё не начатую реплику
remaining|Вычислить остаток времени до конца дорожки субтитров
resume|Подобрать точку возобновления с начала прерванной реплики
rewind|Рассчитать перемотку назад с ограничением начала дорожки
forward|Рассчитать перемотку вперёд с ограничением конца субтитров
speaker|Определить всех говорящих в текущей точке
nearest_boundary|Найти ближайшую границу любой реплики
progress|Вычислить прогресс по последней метке субтитров
upcoming|Извлечь содержимое ближайшего временного окна
recent|Извлечь недавний контекст в окне перед позицией
next_silence|Найти ближайшее незаполненное субтитрами окно
covered_ms|Подсчитать покрытые субтитрами миллисекунды до позиции
boundary_log|Построить последовательность событий входа и выхода реплик
bookmark|Создать закладку медиа с текущей позицией и видимой репликой
range_loop|Определить петлю для повтора активной группы реплик
interrupt|Сохранить состояние в точке перебивания с частичными репликами
""")
family("dialogue",dialogue,"""
by_role|Отобрать реплики участника по роли
last_user|Извлечь последнюю пользовательскую реплику
last_assistant|Извлечь последнюю реплику NOX
transcript|Собрать читаемую текстовую стенограмму с ролями
tail|Вернуть последние N реплик без изменения порядка
unanswered|Выделить пользовательские реплики после последнего ответа ассистента
pairs|Соотнести последовательные обращения пользователя с очередным ответом
quotes|Привязать каждую прямую цитату к реплике
questions|Извлечь вопросительные предложения с указанием реплики
speaker_counts|Подсчитать число реплик по ролям
word_counts|Подсчитать объём речи каждого участника в словах
duplicates|Найти повторные реплики и индексы оригиналов
floor_changes|Отметить моменты смены участника разговора
search|Найти буквальную фразу в истории с локальными координатами
citations|Привязать ссылки по ходу диалога к авторским репликам
focus|Раскрыть соседние реплики вокруг выбранного идентификатора
reply_chain|Пройти цепочку ответов к исходному сообщению
turn_delta|Показать изменения слов между двумя выбранными репликами
budget_tail|Выбрать непрерывный хвост целых реплик в символьном бюджете
role_vocabulary|Построить частотный словарь участника
""")

SAMPLE = {"text":"# Сцена\n\nГолос сказал «Hola».\n- [x] Прочесть [письмо](https://example.org).\nЦена 12 €.\n",
          "new_text":"Вступление\n# Сцена\n\nГолос сказал «Hola».","query":"Голос",
          "start":9,"end":14,"replacement":"NOX","left":"[","right":"]",
          "other_start":10,"other_end":16,"document_id":"script-1",
          "cues":[{"start_ms":250,"end_ms":1000,"speaker":"NOX","text":"Голос.\nHola."},
                  {"start_ms":900,"end_ms":1600,"speaker":"Иван","text":"Продолжай."},
                  {"start_ms":1800,"end_ms":2400,"speaker":"NOX","text":"Теперь финал."}],
          "position_ms":950,"start_ms":300,"end_ms":1500,"speaker":"NOX","media_id":"scene1",
          "srt":"1\n00:00:00,250 --> 00:00:01,000\nГолос.",
          "turns":[{"id":"1","role":"user","text":"Как звучит «Голос»?"},
                   {"id":"2","role":"assistant","text":"Голос говорит.","reply_to":"1"},
                   {"id":"3","role":"user","text":"Продолжай.","reply_to":"2"}],
          "role":"user","turn_id":"3","other_turn_id":"1"}
