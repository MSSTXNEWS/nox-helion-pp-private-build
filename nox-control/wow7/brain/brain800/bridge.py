"""Recognize explicit actions. Ordinary conversation stays on NOX's original route."""
import asyncio
import hashlib
import json
from pathlib import Path
from .phrases import route_phrase
import re
import sys

LABELS = {"замысел":"intent","решение":"choice","обещание":"promise","гипотезу":"hypothesis",
          "урок":"lesson","предпочтение":"preference","черновик":"draft","возражение":"objection",
          "ориентир":"cue","вопрос":"question"}
PLURAL = {"замыслы":"intent","решения":"choice","обещания":"promise","гипотезы":"hypothesis",
          "уроки":"lesson","предпочтения":"preference","черновики":"draft","возражения":"objection",
          "ориентиры":"cue","вопросы":"question"}
def route(text,turn):
    command = text.strip()
    aliases={"как ты изменился":"summary","чему ты научился":"skills","над чем ты работаешь":"agenda","это помогло":"positive","это не помогло":"negative",
             "открой мастерскую навыков":"on","закрой мастерскую навыков":"off"}
    life=aliases.get(command.casefold().rstrip(" .!?"))
    if life in ("positive","negative"):return {"life":"feedback","data":{"value":1 if life=="positive" else -1}}
    if life:return {"life":life,"data":{}}
    if command.startswith("/brain "):
        key,_,args=command[6:].strip().partition(" ")
        if key in ("self","agenda","skills","feedback","event","apply","revoke","teach","on","off"):
            return {"life":"state" if key=="self" else key,"data":json.loads(args or "{}")}
        if key in ("предложи","подбери","suggest"):return {"suggest":args.lstrip(": ")}
        if key=="find":return {"find":args}
        if key=="help":return {"help":True}
        return {"op":key,"data":json.loads(args or "{}")}
    match = re.fullmatch(r"(?:запомни|сохрани) (\w+)\s*:\s*(.+)",command,re.I|re.S)
    if match and match[1].casefold() in LABELS:
        key=hashlib.sha256(turn.encode()).hexdigest()[:20]
        return {"op":"intent."+LABELS[match[1].casefold()]+".open",
                "data":{"key":key,"text":match[2],"source":"turn:"+turn},"view":"new"}
    match = re.fullmatch(r"(?:покажи|вспомни) (?:наши |мои )?(\w+)(?:\s*:\s*(.+?))?[.!?]?",command,re.I|re.S)
    if match and match[1].casefold() in PLURAL:
        return {"op":"intent."+PLURAL[match[1].casefold()]+(".search" if match[2] else ".active"),
                "data":{"query":match[2] or ""},"view":"list"}
    match = re.fullmatch(r"(?:продолжи замысел|вернёмся к замыслу|retoma la idea)\s*:\s*(.+)",command,re.I|re.S)
    if match:
        return {"op":"intent.intent.search","data":{"query":match[1]},"view":"context"}
    return None

async def handle(text,scope,token,state,history=()):
    try:
        request=route(text,token) or route_phrase(text,history)
    except (TypeError,ValueError) as error:
        return {"ok":False,"text":"Не удалось разобрать запрос: "+str(error)}
    if request is None:return None
    if request.get("help"):return {"ok":True,"text":"Запомни замысел: … | Покажи замыслы | /brain find запрос | /brain идентификатор {JSON}"}
    if len(text.encode())>97000:return {"ok":False,"text":"Слишком большой запрос"}
    # A separate process can be cancelled without leaving CPU work on the model's event loop.
    proc=await asyncio.create_subprocess_exec(sys.executable,"-m","brain800",str(Path(state)/"brain800.sqlite3"),
        cwd=str(Path(__file__).resolve().parent.parent),
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
    try:
        raw=json.dumps({**request,"scope":scope,"token":token},ensure_ascii=False).encode()
        out,_=await asyncio.wait_for(proc.communicate(raw),12)
        if not out:return {"ok":False,"text":"Вычисление превысило доступный ресурс"}
        result=json.loads(out)
    except asyncio.TimeoutError:
        return {"ok":False,"text":"Превышено время операции"}
    finally:
        if proc.returncode is None:
            try:proc.kill()
            except ProcessLookupError:pass
            await proc.wait()
    if not result["ok"]:return {"ok":False,"text":result["error"]}
    v=result["result"]
    if request.get("view")=="context":
        if not v:return {"ok":True,"op":request["op"],"text":"По этому фрагменту замысел не найден."}
        if len(v)>1:return {"ok":True,"op":request["op"],"text":"Нашёл несколько замыслов. Уточните фрагмент:\n"+"\n".join("• "+r["text"][:180] for r in v[:5])}
        return {"ok":True,"op":request["op"],"context":{"text":v[0]["text"],"source":v[0]["source"],"version":v[0]["version"]}}
    if request.get("view")=="new":answer="Сохранил: "+v["text"]
    elif request.get("view")=="list":answer="\n".join("• "+r["text"] for r in v) or "В этой беседе таких записей пока нет."
    else:answer=json.dumps(v,ensure_ascii=False,indent=2)
    return {"ok":True,"op":request.get("op",request.get("life","suggest" if "suggest" in request else "find")),"text":answer}
