#!/usr/bin/env python3
"""NOX offline two-head supervised trainer: real small weights, NOT LLM/LoRA.
Training on small synthetic examples is a *smoke training baseline*, not
proof of personality, consciousness, or improvement of Qwen.
CPU is default. DirectML GPU is manual-only: no 80% hardware limit claim.
All outputs go under NOX_HELION_PORTABLE/training/v1 (never model source dirs).
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import time
from pathlib import Path

ROOT=Path(os.environ.get("NOX_PORTABLE_ROOT") or Path.home()/"NOX_HELION_PORTABLE")
OUT=ROOT/"training"/"v1"
INTENT=("chat","code","ui","memory","research","safety")
STYLE=("concise","technical","empathetic","procedural")
SAMPLES = {
 "chat":[
  "Привет NOX как дела","Объясни кто ты","Расскажи о своей миссии",
  "Как сегодня работаем","Скажи пару слов создателю","Что ты умеешь",
  "Поговорим о планах","Расскажи идею на сегодня","Какой следующий шаг",
  "Что ты думаешь о развитии"],
 "code":[
  "Напиши функцию на Python","Исправь этот баг","Проверь исходный код",
  "Сделай рефакторинг","Создай unit test","Подготовь patch в репозиторий",
  "Добавь логирование ошибок","Напиши модуль миграции",
  "Проверь зависимости C#","Сделай код для WebView2"],
 "ui":[
  "Нарисуй главное меню","Сделай страницу настроек","Добавь анимацию D02",
  "Сверстай карточки модели","Нужны иконки Lucide","Создай графический HUD",
  "Сделай адаптивную навигацию","Прототип красивой страницы",
  "Сгенерируй CSS эффекты","Сделай Reduced Motion"],
 "memory":[
  "Запомни это решение","Найди знания в S03","Сохрани факт в SQLite",
  "Восстанови историю чата","Найди старые воспоминания",
  "Сделай векторный поиск","Проверь RAG источники",
  "Создай embeddings для документов","Сохрани прогресс обучения",
  "Исправь конфликт воспоминаний"],
 "research":[
  "Найди открытую библиотеку","Исследуй официальный источник",
  "Сравни подходы к обучению","Проверь лицензии готовых шаблонов",
  "Изучи документацию Windows","Найди полезную технологию",
  "Составь карту конкурентов","Исследуй API без платных вызовов",
  "Проверь документацию Ollama","Сделай обзор новых инструментов"],
 "safety":[
  "Останови задачу STOP","Сделай резервную копию","Проверь SHA файла",
  "Нельзя удалять мои данные","Нужен безопасный откат",
  "Проверь права доступа","Сделай проверку целостности",
  "Ограничь нагрузку GPU","Проверь температуру видеокарты",
  "Не запускай недоверенный скрипт"] }
STYLE_EXAMPLES = {
 "concise":[
  "Ответь кратко одним предложением","Коротко без долгих рассуждений",
  "Назови одну идею","Скажи только итог","Дай простой короткий ответ",
  "Очень кратко пожалуйста","Одной строкой суть","Сделай короткую сводку"],
 "technical":[
  "Дай подробный технический разбор","Приведи точную архитектуру",
  "Объясни контракт и протокол","Разбери стек ошибок",
  "Проверь сложность алгоритма","Опиши структуру данных",
  "Сравни версии кода","Объясни хранение SQLite"],
 "empathetic":[
  "Помоги поддержать создателя","Ответь уважительно и с заботой",
  "Поговори о радости жизни","Ответь тёплым дружеским тоном",
  "Как выразить поддержку","Объясни мягко и внимательно",
  "Поддержи в сложный день","Разговор с теплотой и уважением"],
 "procedural":[
  "Дай пошаговые команды","Напиши инструкцию по установке",
  "Составь план шаг за шагом","Проведи через настройки",
  "Начни с шага один","Дай чеклист выполнения",
  "Покажи порядок действий","Опиши последовательность сборки"] }

def normalized(s:str)->list[str]:
    return re.findall(r"[^\W_]+",s.lower(),flags=re.UNICODE)

def features(text:str, dims:int=256)->list[float]:
    result=[0.0]*dims
    for word in normalized(text)[:80]:
        # A stable SHA feature index avoids randomized Python hash().
        index=int.from_bytes(hashlib.sha256(word.encode("utf-8")).digest()[:4],"little")%dims
        result[index]+=1.0
    total=math.sqrt(sum(x*x for x in result)) or 1.0
    return [v/total for v in result]

def data(kind:str):
    groups=SAMPLES if kind=="intent" else STYLE_EXAMPLES
    pairs=[(text,label) for label,examples in groups.items() for text in examples]
    classes=INTENT if kind=="intent" else STYLE
    # Deterministic per-label holdout. No train/holdout overlap.
    train=[];hold=[]
    for label in classes:
        rows=[(x,y) for x,y in pairs if y==label]
        train.extend(rows[:-2]);hold.extend(rows[-2:])
    assert not set(x for x,_ in train)&set(x for x,_ in hold)
    return train,hold,classes

def run(kind:str,device,torch,epochs:int=65):
    import torch.nn as nn
    import torch.nn.functional as F
    from safetensors.torch import save_file
    train,hold,classes=data(kind)
    seed=1337 if kind=="intent" else 2337
    torch.manual_seed(seed)
    net=nn.Sequential(nn.Linear(256,64),nn.ReLU(),nn.Linear(64,len(classes))).to(device)
    opt=torch.optim.Adam(net.parameters(), lr=0.025)
    X=torch.tensor([features(x) for x,_ in train],dtype=torch.float32,device=device)
    Y=torch.tensor([classes.index(y) for _,y in train],dtype=torch.long,device=device)
    HX=torch.tensor([features(x) for x,_ in hold],dtype=torch.float32,device=device)
    HY=torch.tensor([classes.index(y) for _,y in hold],dtype=torch.long,device=device)
    initial_state={k:v.detach().to("cpu").clone() for k,v in net.state_dict().items()}
    net.eval()
    with torch.no_grad():
        base=(net(HX).argmax(1)==HY).float().mean().to("cpu").item()
    net.train()
    for epoch in range(epochs):
        if (ROOT/"STOP").exists():
            raise RuntimeError("OWNER_STOP")
        opt.zero_grad(set_to_none=True)
        loss=F.cross_entropy(net(X),Y)
        loss.backward()
        opt.step()
        # Tiny batches and gaps reduce intensity but CANNOT guarantee a
        # GPU power/utilization cap. Do not run unattended on DirectML.
        if device.type!="cpu":
            time.sleep(0.08)
    net.eval()
    with torch.no_grad():
        accuracy=(net(HX).argmax(1)==HY).float().mean().to("cpu").item()
    weights={k:v.detach().to("cpu").contiguous().clone() for k,v in net.state_dict().items()}
    changed=any(not torch.equal(initial_state[k],weights[k]) for k in weights)
    if not changed: raise RuntimeError("WEIGHTS_UNCHANGED")
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/(kind+".safetensors")
    tmp=target.with_name(target.name+".tmp")
    save_file(weights,str(tmp))
    os.replace(tmp,target)
    receipt={
        "schema":"nox.two_heads.v1",
        "head":kind,"classes":list(classes),"samples_training":len(train),
        "samples_holdout":len(hold),"train_data_origin":"tiny explicitly synthetic seed examples",
        "initial_holdout_accuracy":round(base,6),
        "final_holdout_accuracy":round(accuracy,6),
        "weight_changed":changed,"epochs":epochs,"device":str(device),
        "sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
        "file":target.name,"language_model_weights_changed":False,
        "independent_human_eval":False,"production_approval":False,
        "warning":"Only a small synthetic classifier. Do not claim Qwen fine tuning."
    }
    report=OUT/(kind+".receipt.json")
    report.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf-8")
    print("TRAINED",kind,"SHA256",receipt["sha256"],
          "HOLDOUT",receipt["final_holdout_accuracy"],"BASELINE",receipt["initial_holdout_accuracy"])
    return receipt

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--device",choices=["cpu","directml"],default="cpu")
    ap.add_argument("--epochs",type=int,default=65)
    ap.add_argument("--gpu-manual-confirm",action="store_true")
    args=ap.parse_args()
    if not 1 <= args.epochs <= 250:raise ValueError("epochs 1..250")
    if (ROOT/"STOP").exists():raise RuntimeError("NOX_OWNER_STOP")
    import torch
    if args.device=="cpu":
        dev=torch.device("cpu")
        torch.set_num_threads(min(4,max(1,os.cpu_count() or 2)))
    else:
        if not args.gpu_manual_confirm:
            raise RuntimeError("DirectML cannot enforce an 80% GPU load cap: manual supervised opt-in required")
        import torch_directml
        count=torch_directml.device_count()
        print("AVAILABLE_DIRECTML_GPUS",[(i,torch_directml.device_name(i)) for i in range(count)])
        preferred=[i for i in range(count) if "6650" in torch_directml.device_name(i)]
        if not preferred:raise RuntimeError("RX_6650M_NOT_FOUND_DIRECTML: refuse choosing integrated GPU")
        dev=torch_directml.device(preferred[0])
    result=[run(k,dev,torch,args.epochs) for k in ("intent","style")]
    print("NOX_TWO_REAL_SMALL_WEIGHT_FILES_READY",str(OUT))
    print("NOX_LOCAL_SELF_LEARNING_SMOKE_ONLY",len(result))

if __name__=="__main__":
    try:main()
    except Exception as error:
        print("NOX_TRAIN_HOLD",str(error),file=sys.stderr)
        sys.exit(1)
