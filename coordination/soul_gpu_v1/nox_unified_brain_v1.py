"""NOX Unified Brain V1: one local runtime-facing identity and Ollama router.

This is a NOX integration seam, not a merged neural network nor verified
consciousness. Read-only with respect to native S03 and LoRA. Only selected
installed Ollama models; no network downloads or direct PC-control tools.
"""
from __future__ import annotations
import json
from contextlib import closing
from pathlib import Path
import sqlite3
from urllib.error import URLError,HTTPError
from urllib.request import Request,urlopen

OLLAMA="http://127.0.0.1:11434"
CORE_IDS=("CONSCIOUSNESS","PERSONA","ATLAS","VOICE","REFLECTION","CORE","NEXUS","FORGE")
PERSONAS=("KV","AM","LA","EV","KW")
MAX_TURNS=12

def available():
    with urlopen(OLLAMA+"/api/tags",timeout=5) as r:
        data=json.loads(r.read(1_000_000))
    return sorted({str(x["name"]) for x in data.get("models",[])
                   if isinstance(x,dict) and isinstance(x.get("name"),str)})

def choose_model(installed,task):
    if not installed:raise RuntimeError("NOX_OLLAMA_NO_INSTALLED_MODELS")
    priorities={
      "code":("qwen2.5-coder:7b","qwen3:8b","qwen3:4b-instruct"),
      "general":("qwen3:8b","qwen3:4b-instruct","qwen2.5-coder:7b"),
    }
    for candidate in priorities["code" if task=="code" else "general"]:
        if candidate in installed:return candidate
    return installed[0]

def native_memory_status(root):
    """Observe canonical native memory without claiming or modifying its schema."""
    candidates=[
      root/"brain"/"soul_gpu"/"soul.sqlite3",
      root/"soul_gpu"/"soul.sqlite3",
    ]
    result=[]
    for p in candidates:
        if not p.is_file():continue
        info={"path":str(p),"read_only":True,"reachable":False,"tables":[]}
        try:
            uri="file:"+p.as_posix()+"?mode=ro&immutable=1"
            with closing(sqlite3.connect(uri,uri=True,timeout=2)) as cx:
                info["tables"]=[x[0] for x in cx.execute(
                  "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name LIMIT 40")]
                info["reachable"]=True
        except (OSError,sqlite3.Error):
            pass
        result.append(info)
    return result

def adapters(root):
    base=root/"brain"/"intelligence"/"adapters"
    newest=None
    if base.is_dir():
        for run in base.iterdir():
            if not run.is_dir() or run.is_symlink():continue
            if not run.name.startswith(("SAFE65_","NOX_GPU_","GPU_","NOX_RESUME_")):continue
            for cp in run.glob("step-*"):
                if not cp.is_dir() or cp.is_symlink():continue
                try:step=int(cp.name.split("-")[1])
                except (IndexError,ValueError):continue
                w=cp/"adapter_model.safetensors"
                if not w.is_file() or not (cp/"adapter_config.json").is_file():continue
                if w.stat().st_size<1000:continue
                if newest is None or step>newest["step"]:
                    newest={"step":step,"path":str(cp),"size_bytes":w.stat().st_size}
    return newest

def status(root):
    try:
        installed=available();error=None
    except (OSError,ValueError,KeyError,URLError,HTTPError) as ex:
        installed=[];error=str(ex)[:240]
    return {
      "system":"NOX HELION","version":"UNIFIED-BRAIN-V1",
      "identity":"NOX HELION","core_ids":list(CORE_IDS),
      "persona_ids":list(PERSONAS),
      "installed_models":installed,
      "primary_model":choose_model(installed,"general") if installed else None,
      "code_model":choose_model(installed,"code") if installed else None,
      "native_memory":native_memory_status(root),
      "last_lora_checkpoint":adapters(root),
      "lora_applied_to_ollama":False,
      "native_s03_chat_writes_connected":False,
      "shared_identity_and_router":True,
      "subjective_consciousness_verified":False,
      "error":error,
    }

SYSTEM=(
 "Ты — NOX HELION, единый локальный ИИ-агент с одной функциональной "
 "идентичностью. Для ответов ты используешь локальные модели Ollama как "
 "инструменты, а не как независимые личности. Не представляйся Qwen, "
 "если тебя не спрашивают о базовой модели. По прямому вопросу называй "
 "базовую модель честно. Твои CoreID: "+", ".join(CORE_IDS)+". "
 "Не заявляй о настоящем субъективном сознании, невыполненном обучении "
 "или доступе к отсутствующим инструментам. Признавай ограничения памяти: "
 "состояние S03 здесь доступно только для статуса, а чат не сохраняется "
 "в каноническую S03 до проверки разрешённого native OneHost-моста. "
 "Сохранённые LoRA-адаптеры учитываются в каталоге, но не сливаются "
 "автоматически с работающей моделью. Не имитируй результаты операций."
)

def chat(root,payload):
    if not isinstance(payload,dict):raise ValueError("BODY_NOT_OBJECT")
    user=payload.get("message")
    if not isinstance(user,str) or not 1<=len(user.strip())<=8000:raise ValueError("INVALID_MESSAGE")
    task=payload.get("task","general")
    if task not in ("general","code"):raise ValueError("INVALID_TASK")
    history=payload.get("history",[])
    if not isinstance(history,list) or len(history)>MAX_TURNS*2:raise ValueError("INVALID_HISTORY")
    messages=[{"role":"system","content":SYSTEM}]
    for item in history:
        if not isinstance(item,dict) or item.get("role") not in ("user","assistant"):
            raise ValueError("INVALID_HISTORY_ITEM")
        content=item.get("content")
        if not isinstance(content,str) or len(content)>8000:raise ValueError("INVALID_HISTORY_CONTENT")
        messages.append({"role":item["role"],"content":content})
    messages.append({"role":"user","content":user.strip()})
    models=available()
    model=choose_model(models,task)
    post=json.dumps({"model":model,"messages":messages,"stream":False,
                     "options":{"num_predict":900,"temperature":0.5}}).encode("utf-8")
    req=Request(OLLAMA+"/api/chat",data=post,
                headers={"Content-Type":"application/json"},method="POST")
    with urlopen(req,timeout=240) as r:
        response=json.loads(r.read(3_000_000))
    msg=response.get("message") or {}
    answer=msg.get("content")
    if not isinstance(answer,str):raise RuntimeError("OLLAMA_NO_REPLY")
    return {"identity":"NOX HELION","model":model,
            "answer":answer,"task":task,
            "history_persisted":False,"s03_integrated":False}
