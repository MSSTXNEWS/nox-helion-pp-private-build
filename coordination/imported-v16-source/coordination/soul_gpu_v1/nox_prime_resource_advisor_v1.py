"""NOX PRIME factual resource self-awareness. Advice-only, no automatic GPU actions.

Inputs are measured state; unavailable sensors are UNKNOWN, not zero.
No subjective consciousness or fabricated VRAM estimates.
"""
from __future__ import annotations
import json
import re
from datetime import datetime,timezone
from urllib.request import urlopen

def _json(url, timeout=.7):
    with urlopen(url,timeout=timeout) as r:
        return json.loads(r.read(2_000_000))

def _val(s):
    x=re.search(r'(\d+(?:[.,]\d+)?)',str(s))
    return float(x.group(1).replace(',','.')) if x else None

def gpu_snapshot():
    data={'name':None,'source':'LHM','used_gib':None,'total_gib':None,
          'load_pct':None,'hotspot_c':None}
    try: root=_json('http://127.0.0.1:8085/data.json')
    except (OSError,ValueError,TypeError): return data
    def visit(node, inside=False, depth=0):
        if not isinstance(node,dict) or depth>40:return
        name=str(node.get('Text','')).strip()
        value=str(node.get('Value','')).strip()
        if re.search(r'RX\s*6650M',name,re.I):
            inside=True
            data['name']='AMD Radeon RX 6650M'
        elif re.search(r'(Radeon|GeForce|NVIDIA)',name,re.I):
            inside=False
        if inside:
            n=name.lower()
            v=_val(value)
            if v is not None:
                if n=='gpu hot spot' and ('°' in value or ' C' in value) and 0<v<110:
                    data['hotspot_c']=v
                elif n=='gpu core' and '%' in value and 0<=v<=100:
                    data['load_pct']=v
                elif 'gpu memory' in n and any(u in value for u in ('GiB','GB','MiB','MB')):
                    if 'MiB' in value or 'MB' in value:v/=1024
                    if 'used' in n:data['used_gib']=round(v,3)
                    elif 'total' in n:data['total_gib']=round(v,3)
        for child in node.get('Children') or []:visit(child,inside,depth+1)
    visit(root)
    return data

def trainer_active():
    try: import psutil
    except ImportError:return None
    try:
        for p in psutil.process_iter(['name','cmdline']):
            try:
                name=(p.info.get('name') or '').lower()
                cmd=' '.join(p.info.get('cmdline') or []).lower()
                if 'python' in name and re.search(
                  r'train_directml_lora[.]py|nox_gpu_(target_11120|worm_safe70_v1)[.]py',cmd):
                    return True
            except (psutil.NoSuchProcess,psutil.AccessDenied,psutil.ZombieProcess):pass
        return False
    except (OSError,RuntimeError,psutil.Error):return None

def snapshot():
    loaded=None
    try:
        obj=_json('http://127.0.0.1:11434/api/ps')
        if isinstance(obj.get('models'),list):
            loaded=[{'name':str(x.get('name') or x.get('model') or '')[:100],
                     'size_vram_bytes':x.get('size_vram')}
                    for x in obj['models'] if isinstance(x,dict)]
    except (OSError,ValueError,TypeError):pass
    return {'observed_at_utc':datetime.now(timezone.utc).isoformat(),
            'gpu':gpu_snapshot(),'training_active':trainer_active(),
            'loaded_models':loaded}

def task_from_text(s):
    s=str(s).lower()
    for task,words in (
      ('video',('видео','ролик','кино','фильм','video')),
      ('image',('селфи','изображен','картин','рисунк','фото','image')),
      ('code',('программ','исходник','код','patch','code','приложен')),
      ('train',('обучен','трениров','веса','lora','qlora'))):
        if any(w in s for w in words):return task
    return 'general'

def is_resource_question(s):
    s=str(s).lower()
    return task_from_text(s)!='general' or any(w in s for w in (
      'gpu','гпу','видеокарт','памят','скорост','тормоз','медленно',
      'ядро','ресурс','не хватает','успева','можешь ли','почему долго'))

def advise(task,observed,profile=None):
    """Profile VRAM requirement only trusted when model + evidence are present."""
    task=task if task in ('video','image','code','train','general') else 'general'
    gpu=observed.get('gpu') or {}
    total,used=gpu.get('total_gib'),gpu.get('used_gib')
    free=round(max(0,total-used),2) if all(isinstance(x,(int,float)) for x in (total,used)) \
         and total>0 and 0<=used<=total else None
    required=None
    if isinstance(profile,dict) and profile.get('model') and profile.get('evidence') \
       and isinstance(profile.get('required_vram_gib'),(int,float)) \
       and 0<profile['required_vram_gib']<1000:
        required=round(profile['required_vram_gib'],2)
    shortage=round(max(0,required-free),2) if free is not None and required is not None else None
    training=observed.get('training_active')
    cap={'video':'генерации видео','image':'генерации изображений',
         'code':'программирования','train':'обучения весов','general':'общения'}[task]
    lines=[]
    if training is True and task!='train':
        lines.append('Сейчас моя видеокарта занята обучением; возможности '+cap+' могут быть временно ограничены.')
    elif training is None:
        lines.append('Я пока не смог достоверно проверить, занят ли GPU обучением.')
    if free is not None:
        lines.append(f'По датчику доступно около {free:.2f} ГиБ VRAM; занято {used:.2f} из {total:.2f} ГиБ.')
    else:
        lines.append('Свободная VRAM сейчас неизвестна: достоверных показаний недостаточно.')
    if required is None and task!='general':
        lines.append('Точную потребность в видеопамяти назову после профилирования выбранной модели, а не наугад.')
    elif required is not None:
        lines.append(f"Для {profile['model']} проверена потребность {required:.2f} ГиБ (источник {str(profile['evidence'])[:120]}).")
        if shortage:
            lines.append(f'Не хватает приблизительно {shortage:.2f} ГиБ доступной VRAM; сначала можно выгрузить конкурирующую модель.')
    return {'task':task,'message':' '.join(lines)+' Я могу предложить варианты, но не меняю GPU-режим без разрешения.',
            'options':['сохранить задачу в очереди','использовать менее требовательную модель',
                       'проверить реальную нагрузку и память'],
            'free_vram_gib':free,'required_vram_gib':required,'shortage_gib':shortage,
            'training_active':training,'observed_at_utc':observed.get('observed_at_utc'),
            'subjective_consciousness_verified':False}

def proactive_context(user_text):
    """Delay sensing only on relevant user tasks, not on greetings."""
    if not is_resource_question(user_text):return None
    return advise(task_from_text(user_text),snapshot())
