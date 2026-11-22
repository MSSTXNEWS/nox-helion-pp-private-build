"""Операции социального контекста. Входные метки передаёт пользователь или клиент.
turns располагаются по порядку реплик; start_ms/end_ms отсчитываются от начала встречи.
Время until и now — числа в одной шкале. Отсутствующая метка не восстанавливается догадкой.
"""
from collections import Counter, defaultdict
import re

OPS = {}
META = {}

def register(name, title):
    def attach(fn):
        OPS[name] = fn
        META[name] = title
        return fn
    return attach

def rows(p, key):
    return [row for row in p.get(key, []) if isinstance(row, dict)]

def turns(p):
    return rows(p, 'turns')

def texts(items):
    return [str(t.get('text', '')) for t in items]

def speakers(items):
    return list(dict.fromkeys(t['speaker'] for t in items if t.get('speaker')))

def tokens(text):
    return re.findall(r"[^\W_]+(?:[-’'][^\W_]+)*", str(text).casefold(), flags=re.UNICODE)

def unique(items):
    return list(dict.fromkeys(items))

def by_id(items):
    return {t['id']: t for t in items if t.get('id')}

def counts(items):
    return dict(Counter(items))

def valid_period(row):
    return all(isinstance(row.get(k), (float,int)) for k in ('start_ms','end_ms')) and 0 <= row['start_ms'] <= row['end_ms']

def duration(row):
    return row['end_ms'] - row['start_ms']

def pair_turns(p):
    items = turns(p)
    return zip(items, items[1:])

def show(title, name, fn):
    register(name, title)(fn)

# Очередь и адресация.
show('Восстановить порядок появления участников','speaker_order', lambda p:speakers(turns(p)))
show('Найти последнюю прямую реплику адресату','latest_address', lambda p:next((t for t in reversed(turns(p)) if p.get('target') and t.get('to')==p['target']),None))
show('Найти вопросы, адресованные владельцу','questions_for_owner', lambda p:[t for t in turns(p) if p.get('owner') and t.get('to')==p['owner'] and (t.get('act')=='question' or str(t.get('text','')).rstrip().endswith('?'))])
show('Извлечь передачу слова с указанием следующего участника','explicit_handoffs', lambda p:[{'from':t.get('speaker'),'to':t['to'],'turn':t.get('id')} for t in turns(p) if t.get('act')=='handoff' and t.get('to')])
show('Измерить долю реплик каждого участника','participation',lambda p:{s:n/max(1,len(turns(p))) for s,n in counts(t.get('speaker') for t in turns(p) if t.get('speaker')).items()})
show('Найти перебивания по перекрытию времени соседних голосов','overlaps',lambda p:[{'earlier':a.get('id'),'later':b.get('id'),'ms':min(a['end_ms'],b['end_ms'])-max(a['start_ms'],b['start_ms'])} for a,b in pair_turns(p) if valid_period(a) and valid_period(b) and a.get('speaker')!=b.get('speaker') and min(a['end_ms'],b['end_ms'])>max(a['start_ms'],b['start_ms'])])
show('Измерить промежутки между соседними репликами','turn_gaps',lambda p:[{'after':a.get('id'),'before':b.get('id'),'ms':b['start_ms']-a['end_ms']} for a,b in pair_turns(p) if valid_period(a) and valid_period(b) and b['start_ms']>=a['end_ms']])
show('Найти участника с самой долгой размеченной репликой','longest_turn',lambda p:max((t for t in turns(p) if valid_period(t)), key=duration,default=None))
show('Найти приглашённых участников без собственной реплики','silent_invitees',lambda p:[s for s in p.get('participants',[]) if s not in speakers(turns(p))])
show('Выделить прямой обмен двух выбранных участников','dyad',lambda p:[t for t in turns(p) if t.get('speaker') and t.get('to') and {t['speaker'],t['to']}=={p.get('owner'),p.get('target')}])

# Нити диалога.
show('Составить карту тем и их участников','topic_members',lambda p:{topic:speakers(t for t in turns(p) if t.get('topic')==topic) for topic in unique(t['topic'] for t in turns(p) if t.get('topic'))})
show('Найти последнее переключение предмета разговора','last_topic_switch',lambda p:next(({'from':a['topic'],'to':b['topic'],'turn':b.get('id')} for a,b in reversed(list(pair_turns(p))) if a.get('topic') and b.get('topic') and a['topic']!=b['topic']),None))
show('Восстановить предшествующую цепочку ответов','reply_ancestry',lambda p:ancestry(p))
def ancestry(p):
    idx=by_id(turns(p)); current=p.get('turn_id'); trail=[]; seen=set()
    while current in idx and current not in seen:
        trail.append(current);seen.add(current);current=idx[current].get('reply_to')
    return trail
show('Построить ответвления от выбранной реплики','reply_children',lambda p:[t for t in turns(p) if p.get('turn_id') and t.get('reply_to')==p['turn_id']])
show('Распознать ссылки ответов на отсутствующие сообщения','dangling_replies',lambda p:[t.get('id') for t in turns(p) if t.get('reply_to') and t['reply_to'] not in by_id(turns(p))])
show('Подобрать фрагмент вокруг конкретного сообщения','context_window',lambda p:window(p))
def window(p):
    ts=turns(p); ids=[t.get('id') for t in ts]
    if p.get('turn_id') not in ids:return []
    i=ids.index(p['turn_id']); radius=max(0,int(p.get('radius',1)))
    return ts[max(0,i-radius):i+radius+1]
show('Найти вопросы, на которые ещё никто не сослался ответом','unanswered',lambda p:[t for t in turns(p) if t.get('id') and t.get('act')=='question' and t['id'] not in {v.get('reply_to') for v in turns(p) if v.get('act')=='answer'}])
show('Восстановить точку возврата по теме','topic_resume',lambda p:next((t for t in reversed(turns(p)) if p.get('topic') and t.get('topic')==p['topic']),None))
show('Выявить неоднозначное повторное употребление идентификатора','duplicate_turn_ids',lambda p:[i for i,n in counts(t['id'] for t in turns(p) if t.get('id')).items() if n>1])
show('Сгруппировать выставленные метки на одной реплике','turn_annotations',lambda p:[a for a in rows(p,'annotations') if p.get('turn_id') and a.get('turn')==p['turn_id']])

# Обязательства.
def agreements(p):
    return rows(p,'agreements')
def pending(a):
    return a.get('state') in ('accepted','in_progress')
show('Отобрать принятые обязательства владельца','owner_obligations',lambda p:[a for a in agreements(p) if pending(a) and p.get('owner') and a.get('assignee')==p['owner']])
show('Отличить ещё открытые предложения от обязательств','open_proposals',lambda p:[a for a in agreements(p) if a.get('state')=='proposed'])
show('Отсортировать открытые сроки по близости','deadlines',lambda p:sorted([a for a in agreements(p) if pending(a) and isinstance(a.get('due'),(int,float))],key=lambda a:a['due']))
show('Отметить просроченные обещания','overdue',lambda p:[a for a in agreements(p) if pending(a) and isinstance(a.get('due'),(int,float)) and isinstance(p.get('now'),(int,float)) and a['due']<p['now']])
show('Выявить готовые к исполнению обязательства','ready_commitments',lambda p:[a for a in agreements(p) if pending(a) and set(a.get('requires',[]))<=set(p.get('completed',[]))])
show('Показать недостающие условия для каждого обещания','unmet_dependencies',lambda p:{a['id']:list(v for v in a.get('requires',[]) if v not in p.get('completed',[])) for a in agreements(p) if a.get('id') and pending(a) and set(a.get('requires',[]))-set(p.get('completed',[]))})
show('Найти обязательства без назначенного исполнителя','unassigned',lambda p:[a for a in agreements(p) if pending(a) and not a.get('assignee')])
show('Сопоставить обязательства с породившими их словами','commitment_origins',lambda p:[{'commitment':a.get('id'),'source':by_id(turns(p)).get(a['turn'])} for a in agreements(p) if a.get('turn')])
show('Собрать отменённые решения с указанной причиной','withdrawals',lambda p:[{'id':a.get('id'),'reason':a.get('reason')} for a in agreements(p) if a.get('state')=='withdrawn'])
show('Выявить исполнителей с совпадающими сроками','deadline_collisions',lambda p:collisions(p))
def collisions(p):
    alloc=defaultdict(list)
    for a in agreements(p):
        if pending(a) and a.get('assignee') and isinstance(a.get('due'),(int,float)):
            alloc[a['assignee'],a['due']].append(a.get('id'))
    return [{'assignee':s,'due':t,'ids':ids} for (s,t),ids in alloc.items() if len(ids)>1]

# Правки.
def edits(p):
    return rows(p,'edits')
def apply_edits(p):
    text=str(p.get('draft','')); applied=[]; skipped=[]
    for e in edits(p):
        old=e.get('before'); new=e.get('after')
        if isinstance(old,str) and old and isinstance(new,str) and text.count(old)==1:
            text=text.replace(old,new,1); applied.append(e.get('id'))
        else:skipped.append(e.get('id'))
    return {'text':text,'applied':applied,'skipped':skipped}
show('Применить однозначно привязанные редакторские поправки','apply_edits',apply_edits)
show('Найти правки без исходной цитаты в черновике','missing_anchors',lambda p:[e for e in edits(p) if e.get('before') and e['before'] not in p.get('draft','')])
show('Выделить неоднозначные повторы цитаты','ambiguous_anchors',lambda p:[e for e in edits(p) if e.get('before') and str(p.get('draft','')).count(e['before'])>1])
show('Составить обратную последовательность правок','reverse_patch',lambda p:[{'id':e.get('id'),'before':e['after'],'after':e['before']} for e in reversed(edits(p)) if e.get('id') in apply_edits(p)['applied'] and e.get('after')])
show('Показать существенные разногласия редакторов','conflicting_edits',lambda p:[{'quote':quote,'variants':unique(e.get('after','') for e in edits(p) if e.get('before')==quote)} for quote in unique(e['before'] for e in edits(p) if e.get('before')) if len({e.get('after','') for e in edits(p) if e.get('before')==quote})>1])
show('Сгруппировать внесённые правки по автору','edit_credits',lambda p:{s:[e.get('id') for e in edits(p) if e.get('author')==s and e.get('id') in apply_edits(p)['applied']] for s in unique(e['author'] for e in edits(p) if e.get('author'))})
show('Рассчитать изменение длительности чтения после правки','reading_delta',lambda p:(len(tokens(apply_edits(p)['text']))-len(tokens(p.get('draft',''))))*60/max(1,int(p.get('words_per_minute',150))))
show('Отобрать правки, затрагивающие охраняемую цитату','protected_edits',lambda p:[e for e in edits(p) if any(q and (q in e.get('before','') or (e.get('before') and e['before'] in q)) for q in p.get('protected',[]))])
show('Найти повторные одинаковые поправки','duplicate_edits',lambda p:[{'before':a,'after':b,'count':n} for (a,b),n in Counter((e.get('before'),e.get('after')) for e in edits(p)).items() if n>1])
show('Подготовить покадровое сравнение одобренных альтернатив','edit_previews',lambda p:[{'id':e.get('id'),'preview':apply_edits({'draft':p.get('draft',''),'edits':[e]})['text']} for e in edits(p) if e.get('approved')])

# Стиль речи.
def draft(p):
    return str(p.get('draft',''))
def sentences(p):
    return [s.strip() for s in re.split(r'(?<=[.!?…])\s+',draft(p)) if s.strip()]
show('Разбить речь на произносимые предложения','sentences',sentences)
show('Найти фразы длиннее ограничения для голоса','long_sentences',lambda p:[s for s in sentences(p) if len(tokens(s))>int(p.get('word_limit',15))])
show('Посчитать распределение длины реплик по словам','utterance_lengths',lambda p:[{'turn':t.get('id'),'words':len(tokens(t.get('text','')))} for t in turns(p)])
show('Проверить предпочтительные и нежелательные обращения','address_audit',lambda p:{'preferred':[v for v in p.get('preferred_forms',[]) if v.casefold() in tokens(draft(p))],'avoid':[v for v in p.get('avoid_forms',[]) if v.casefold() in tokens(draft(p))]})
show('Отметить подряд повторяющиеся слова в речи','repeated_words',lambda p:[{'word':b,'index':i+1} for i,(a,b) in enumerate(zip(tokens(draft(p)),tokens(draft(p))[1:])) if a==b])
show('Выделить повторяемые начала предложений','repeated_openings',lambda p:[w for w,n in counts(tokens(s)[0] for s in sentences(p) if tokens(s)).items() if n>1])
show('Укоротить черновик по границе завершённой фразы','spoken_excerpt',lambda p:excerpt(p))
def excerpt(p):
    chosen=[]; limit=max(0,int(p.get('word_limit',15))); used=0
    for s in sentences(p):
        size=len(tokens(s))
        if used+size>limit:break
        chosen.append(s);used+=size
    return ' '.join(chosen)
show('Найти подготовленные места для вдоха','breath_notes',lambda p:[m.start() for m in re.finditer(r'[,;:—…]|(?<=[.!?])\s',draft(p))])
show('Извлечь явно обозначенную авторскую цитату','quoted_voice',lambda p:[m.group(1) for m in re.finditer(r'«([^»]+)»',draft(p))])
show('Найти в тексте согласованные термины мастерской','house_terms',lambda p:[term for term in p.get('glossary',{}) if re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',draft(p),re.I)])

# Сотрудничество и варианты.
def options(p):
    return rows(p,'options')
def votes(p):
    # Последний голос участника выражает его текущий выбор.
    return {v['member']:v for v in rows(p,'votes') if v.get('member') and v.get('option') in by_id(options(p))}
show('Подсчитать актуальные голоса по вариантам','vote_totals',lambda p:counts(v['option'] for v in votes(p).values()))
show('Показать все варианты с максимальной поддержкой','vote_leaders',lambda p:leaders(p))
def leaders(p):
    c=OPS['vote_totals'](p)
    return [k for k,v in c.items() if v==max(c.values(),default=0)]
show('Найти участников без выраженного выбора','unvoted',lambda p:[s for s in p.get('participants',[]) if s not in votes(p)])
show('Показать мотивы каждого голосующего','ballot_reasons',lambda p:{s:v['reason'] for s,v in votes(p).items() if v.get('reason')})
show('Найти признаки, общие для всех предложений','common_features',lambda p:sorted(set.intersection(*(set(o.get('features',[])) for o in options(p)))) if options(p) else [])
show('Выделить признаки, отличающие варианты','distinct_features',lambda p:{o['id']:sorted(set(o.get('features',[]))-set(OPS['common_features'](p))) for o in options(p) if o.get('id')})
show('Убрать варианты с явно запрещённым признаком','respect_veto',lambda p:[o for o in options(p) if set(o.get('features',[])).isdisjoint(p.get('veto',[]))])
show('Отобрать решения с полным покрытием пожеланий','meet_requirements',lambda p:[o for o in options(p) if set(p.get('required',[]))<=set(o.get('features',[]))])
show('Построить слепое сравнение без имён авторов','blind_options',lambda p:[{'position':i+1,'content':o.get('content','')} for i,o in enumerate(options(p))])
show('Собрать согласованную комбинацию фрагментов','combine_fragments',lambda p:{part:by_id(options(p))[source]['parts'][part] for part,source in p.get('selection',{}).items() if part in by_id(options(p)).get(source,{}).get('parts',{})})

# Контроль инициативы.
def proposals(p):
    return rows(p,'ideas')
show('Вернуть инициативы для текущего открытого проекта','project_ideas',lambda p:[i for i in proposals(p) if i.get('project')==p.get('project') and i.get('state')=='open'])
show('Поднять отложенные идеи при наступлении события','triggered_ideas',lambda p:[i for i in proposals(p) if i.get('trigger') in p.get('events',[]) and i.get('state')=='deferred'])
show('Исключить предложения для закрытой темы','respect_closed_topics',lambda p:[i for i in proposals(p) if i.get('topic') not in p.get('closed_topics',[]) and i.get('state') not in ('closed','rejected')])
show('Разгрузить внимание ограничением числа предложений','attention_budget',lambda p:sorted(OPS['project_ideas'](p),key=lambda i:-int(i.get('priority',0)))[:max(0,int(p.get('budget',1)))])
show('Удержать необязательные предложения в тихом режиме','quiet_hold',lambda p:[i.get('id') for i in proposals(p) if p.get('quiet') and i.get('state')=='open' and not i.get('requested')])
show('Разделить отказ от идеи и перенос её показа','defer_or_reject',lambda p:{state:[i.get('id') for i in proposals(p) if i.get('state')==state] for state in ('deferred','rejected')})
show('Найти инициативы с назначенной точкой возврата','return_points',lambda p:[{'idea':i.get('id'),'anchor':i['anchor']} for i in proposals(p) if i.get('anchor') and i.get('state') in ('open','deferred')])
show('Предотвратить повторное вручение одного эскиза','unseen_ideas',lambda p:[i for i in proposals(p) if i.get('id') and i['id'] not in p.get('shown',[]) and i.get('state')=='open'])
show('Отобрать находки, которые имеют доступный артефакт','presentable_ideas',lambda p:[i for i in proposals(p) if i.get('artifact') in p.get('available_artifacts',[]) and i.get('state')=='open'])
show('Связать творческую находку с её автором','idea_attribution',lambda p:[{'id':i.get('id'),'author':i.get('author'),'sources':i.get('source_turns',[])} for i in proposals(p) if i.get('author')])

# Границы и неопределённость.
def prefs(p):
    return rows(p,'preferences')
def active(r,p):
    return ('until' not in r or (isinstance(p.get('now'),(float,int)) and p['now']<=r['until'])) and (not r.get('project') or r.get('project')==p.get('project'))
show('Выбрать предпочтения текущего проекта и времени','active_preferences',lambda p:[r for r in prefs(p) if active(r,p)])
show('Показать явно названные предпочтения владельца','declared_taste',lambda p:[r for r in prefs(p) if r.get('source')=='explicit' and r.get('speaker')==p.get('owner') and active(r,p)])
show('Развести догадки и подтверждённые правила','inferred_preferences',lambda p:[r for r in prefs(p) if r.get('source')=='inferred' and active(r,p)])
show('Выявить конфликт активных указаний о стиле','preference_conflicts',lambda p:[{'key':k,'values':unique(r.get('value') for r in prefs(p) if r.get('key')==k and active(r,p))} for k in unique(r['key'] for r in prefs(p) if r.get('key') and active(r,p)) if len({r.get('value') for r in prefs(p) if r.get('key')==k and active(r,p)})>1])
show('Отозвать действие временных договорённостей по сроку','expired_preferences',lambda p:[r for r in prefs(p) if isinstance(r.get('until'),(int,float)) and isinstance(p.get('now'),(int,float)) and r['until']<p['now']])
show('Показать неизвестные человеку основания рекомендации','unseen_sources',lambda p:[s for s in p.get('source_turns',[]) if s not in p.get('acknowledged_turns',[])])
show('Скрыть элементы вне явно разрешённой аудитории','audience_view',lambda p:[r for r in rows(p,'notes') if p.get('audience') and p['audience'] in r.get('audiences',[])])
show('Отделить игровые обещания от реальных','roleplay_promises',lambda p:[t for t in turns(p) if t.get('act')=='promise' and t.get('context')=='roleplay'])
show('Найти персональные выводы с недостатком подтверждений','thin_evidence',lambda p:[r for r in prefs(p) if r.get('source')=='inferred' and len(set(r.get('evidence',[])))<int(p.get('min_evidence',2))])
show('Собрать доступные основания для конкретного предпочтения','preference_evidence',lambda p:[by_id(turns(p))[i] for i in unique(i for r in prefs(p) if r.get('key')==p.get('key') for i in r.get('evidence',[])) if i in by_id(turns(p))])

# Слышимость и языки.
def clips(p):
    return [x for x in rows(p,'clips') if valid_period(x)]
def played(p):
    return max(0,int(p.get('played_ms',0)))
show('Отметить полностью воспроизведённые фразы','played_clips',lambda p:[c.get('id') for c in clips(p) if c['end_ms']<=played(p)])
show('Вычислить точку продолжения внутри незаконченной фразы','resume_audio',lambda p:next(({'clip':c.get('id'),'offset_ms':max(0,played(p)-c['start_ms'])} for c in sorted(clips(p),key=lambda x:x['start_ms']) if c['end_ms']>played(p)),None))
show('Восстановить транскрипт полностью проигранной речи','played_transcript',lambda p:' '.join(texts(sorted((c for c in clips(p) if c['end_ms']<=played(p)),key=lambda c:c['start_ms']))))
show('Посчитать время оставшегося аудиоматериала','remaining_audio_ms',lambda p:sum(max(0,c['end_ms']-max(c['start_ms'],played(p))) for c in clips(p)))
show('Выделить частично проигранную фразу для подсветки','partial_clip',lambda p:[c.get('id') for c in clips(p) if c['start_ms']<played(p)<c['end_ms']])
show('Найти явно размеченные смены языка','language_switches',lambda p:[{'at':b.get('id'),'from':a['lang'],'to':b['lang']} for a,b in pair_turns(p) if a.get('lang') and b.get('lang') and a['lang']!=b['lang']])
show('Сверить сохранность имён при переводе','translation_names',lambda p:[name for name in p.get('names',[]) if name in draft(p) and name not in p.get('translation','')])
show('Проверить числа в паре оригинал–перевод','translation_numbers',lambda p:{'source':re.findall(r'\d+(?:[.,]\d+)?',draft(p)),'target':re.findall(r'\d+(?:[.,]\d+)?',p.get('translation','')),'matches':re.findall(r'\d+',draft(p))==re.findall(r'\d+',p.get('translation',''))})
show('Выбрать согласованный перевод словаря мастерской','translated_glossary',lambda p:{k:v[p['language']] for k,v in p.get('glossary',{}).items() if isinstance(v,dict) and p.get('language') in v})
show('Найти ремарки об интонации для диктора','voice_directions',lambda p:re.findall(r'\[([^\]]+)\]',draft(p)))

# Осмысление и восстановление взаимопонимания.
def claims(p):
    return rows(p,'claims')
show('Обнаружить несовпадающие позиции по одному вопросу','disagreement_map',lambda p:{k:{s:unique(c.get('stance') for c in claims(p) if c.get('issue')==k and c.get('speaker')==s) for s in speakers([c for c in claims(p) if c.get('issue')==k])} for k in unique(c['issue'] for c in claims(p) if c.get('issue')) if len({c.get('stance') for c in claims(p) if c.get('issue')==k})>1})
show('Найти уже согласованные утверждения двух участников','shared_claims',lambda p:[{'issue':k,'stance':v} for k,v in unique((c.get('issue'),c.get('stance')) for c in claims(p)) if p.get('owner') and p.get('target') and {p['owner'],p['target']}<=set(speakers([c for c in claims(p) if (c.get('issue'),c.get('stance'))==(k,v)]))])
show('Выделить последнее изменение позиции каждого автора','stance_changes',lambda p:stance_changes(p))
def stance_changes(p):
    latest={}; changes={}
    for c in claims(p):
        key=(c.get('speaker'),c.get('issue'))
        if key in latest and latest[key]!=c.get('stance'): changes[key]={'speaker':key[0],'issue':key[1],'from':latest[key],'to':c.get('stance'),'turn':c.get('turn')}
        latest[key]=c.get('stance')
    return list(changes.values())
show('Развести мнение автора и пересказ чужого мнения','reported_beliefs',lambda p:[{'speaker':t.get('speaker'),'attributed_to':t['attributed_to'],'text':t.get('text')} for t in turns(p) if t.get('attributed_to') and t.get('attributed_to')!=t.get('speaker')])
show('Найти точки спора, для которых указано решающее условие','settling_conditions',lambda p:[{'issue':c.get('issue'),'speaker':c.get('speaker'),'condition':c['condition']} for c in claims(p) if c.get('condition')])
show('Восстановить явное исправление автора и его объект','explicit_corrections',lambda p:[{'turn':t.get('id'),'corrects':t['corrects'],'old':by_id(turns(p)).get(t['corrects'],{}).get('text'),'new':t.get('text')} for t in turns(p) if t.get('corrects')])
show('Извлечь заявленные самим человеком переживания','self_reported_feelings',lambda p:[{'speaker':t.get('speaker'),'turn':t.get('id'),'words':t['self_reported_feeling']} for t in turns(p) if t.get('self_reported_feeling')])
show('Собрать разные причины одного и того же выбора','convergent_reasons',lambda p:{o:unique(v['reason'] for v in votes(p).values() if v.get('option')==o and v.get('reason')) for o in unique(v.get('option') for v in votes(p).values()) if len({v.get('reason') for v in votes(p).values() if v.get('option')==o and v.get('reason')})>1})
show('Найти слова участников, оставшиеся без согласованного толкования','unresolved_terms',lambda p:[x for x in p.get('ambiguous_terms',[]) if x not in p.get('glossary',{})])
show('Восстановить вклад людей в совместное решение','decision_credits',lambda p:[{'decision':a.get('id'),'participants':speakers([by_id(turns(p))[i] for i in a.get('contributions',[]) if i in by_id(turns(p))])} for a in agreements(p) if a.get('contributions')])

SAMPLE={
    'owner':'Иван','target':'NOX','participants':['Иван','NOX','Марк'],'turn_id':'t2','topic':'голос','project':'Cinema','now':10,'language':'es','audience':'монтаж',
    'turns':[{'id':'t1','speaker':'Иван','to':'NOX','topic':'голос','act':'question','text':'Оставим паузу?','lang':'ru','start_ms':0,'end_ms':1600},
             {'id':'t2','speaker':'NOX','to':'Иван','topic':'голос','act':'answer','text':'Да, перед именем.','reply_to':'t1','lang':'ru','start_ms':1300,'end_ms':2050},
             {'id':'t3','speaker':'Иван','to':'Марк','topic':'музыка','act':'handoff','text':'Ahora tú.','lang':'es','start_ms':2600,'end_ms':3200,'corrects':'t2','self_reported_feeling':'доволен'}],
    'draft':'Иван говорит: «Hola». [Тихо] Пауза, пауза. Встреча через 2 дня.','translation':'Iván dice hola. En 2 días.','word_limit':5,'names':['Иван'],'protected':['Hola'],'preferred_forms':['Иван'],'avoid_forms':['мессир'],
    'agreements':[{'id':'a','assignee':'Иван','state':'accepted','requires':['звук'],'due':8,'turn':'t1','contributions':['t1','t2']},{'id':'b','state':'proposed'}],
    'completed':['звук'],'edits':[{'id':'e1','before':'Hola','after':'Vuelve','author':'Иван','approved':True},{'id':'e2','before':'Hola','after':'Ven','author':'NOX'}],
    'options':[{'id':'o1','content':'Первый дубль','features':['мягко','имя'],'parts':{'голос':'take1'}},{'id':'o2','content':'Второй дубль','features':['имя'],'parts':{'текст':'take2'}}],
    'votes':[{'member':'Иван','option':'o1','reason':'тембр'},{'member':'NOX','option':'o1','reason':'пауза'}],'required':['имя'],'selection':{'голос':'o1','текст':'o2'},
    'ideas':[{'id':'i','state':'open','project':'Cinema','author':'NOX','anchor':'s1','artifact':'звук','source_turns':['t1'],'priority':1}],
    'preferences':[{'project':'Cinema','speaker':'Иван','source':'explicit','key':'тон','value':'тихо','until':20,'evidence':['t1']}],'key':'тон','quiet':True,'available_artifacts':['звук'],
    'notes':[{'text':'Сдвинуть паузу','audiences':['монтаж']}],'glossary':{'пауза':{'es':'pausa'}},'ambiguous_terms':['ритм'],'source_turns':['t1','t2'],'acknowledged_turns':['t1'],
    'claims':[{'speaker':'Иван','issue':'пауза','stance':'до имени','turn':'t1'},{'speaker':'NOX','issue':'пауза','stance':'после имени','turn':'t2','condition':'новый дубль'}],
    'clips':[{'id':'c1','text':'Привет','start_ms':0,'end_ms':400},{'id':'c2','text':'Иван','start_ms':400,'end_ms':850}],'played_ms':500,
    'annotations':[{'turn':'t2','label':'замысел'}]
}
