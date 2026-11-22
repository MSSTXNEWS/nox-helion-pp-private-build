"""Функциональные операции памяти. payload содержит events и параметры операции.
Поля uid, ts, project, text — базовые. ts, learned, until — секунды Unix.
Операции, создающие новый снимок, возвращают данные вызывающей стороне.
"""
import copy
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher, unified_diff
from hashlib import sha256
from math import log
from statistics import median

OPS = {}
META = {}


def operation(title):
    def register(fn):
        OPS[fn.__name__] = fn
        META[fn.__name__] = title
        return fn
    return register


def words(text):
    return re.findall(r'[^\W_]+', str(text).lower().replace('ё', 'е'))


def events(p):
    return sorted(p.get('events', []), key=lambda e: (e.get('ts', 0), e['uid']))


def index(p):
    return {e['uid']: e for e in events(p)}


def focus(p):
    return index(p).get(p.get('id'), {})


def keys(p):
    return set(words(p.get('query', '')))


def selected(p, predicate):
    return [e for e in events(p) if predicate(e)]


def grouped(values, key):
    out = defaultdict(list)
    for v in values:
        out[v.get(key)].append(v)
    return out


def unique(values):
    return list(dict.fromkeys(values))


def refs(e):
    return list(e.get('sources', []))


def traverse(p, origin, adjacency):
    pending = list(adjacency.get(origin, []))
    seen = {origin}
    result = []
    while pending:
        node = pending.pop(0)
        if node in seen:
            continue
        seen.add(node)
        result.append(node)
        pending.extend(adjacency.get(node, []))
    return result


def links(p):
    return {e['uid']: refs(e) for e in events(p)}


def back(p):
    reverse = defaultdict(list)
    for uid, sources in links(p).items():
        for source in sources:
            reverse[source].append(uid)
    return reverse


def field(p, name):
    return selected(p, lambda e: name in e and e[name] == p.get(name))


def foreign_key(p, fieldname):
    return selected(p, lambda e: p.get('id') in e.get(fieldname, []))


def score(p, fn):
    result = [(fn(e), e) for e in events(p)]
    result.sort(key=lambda entry: (-entry[0], -entry[1].get('ts', 0), entry[1]['uid']))
    return [{'uid':e['uid'], 'score':round(s,6)} for s,e in result if s > 0][:max(0, p.get('limit',10))]


@operation('Восстановить события в порядке их совершения')
def chronology(p):
    return events(p)


@operation('Восстановить порядок поступления сведений в память')
def ingestion_order(p):
    return sorted(events(p), key=lambda e: (e.get('learned',e.get('ts',0)),e['uid']))


@operation('Извлечь эпизоды внутри заданного интервала')
def time_window(p):
    return selected(p, lambda e:p.get('start',0)<=e.get('ts',0)<=p.get('end',float('inf')))


@operation('Найти эпизод непосредственно перед отмеченным моментом')
def previous_episode(p):
    rows=selected(p, lambda e:e.get('ts',0)<p['at'])
    return rows[-1] if rows else None


@operation('Найти следующий эпизод после отмеченного момента')
def next_episode(p):
    return next((e for e in events(p) if e.get('ts',0)>p['at']),None)


@operation('Найти первое упоминание заданной последовательности слов')
def first_mention(p):
    q=' '.join(words(p['query']))
    return next((e for e in events(p) if q and q in ' '.join(words(e.get('text','')))),None)


@operation('Вывести продолжительные промежутки между наблюдениями')
def time_gaps(p):
    ev=events(p)
    return [{'from':a['uid'],'to':b['uid'],'seconds':b['ts']-a['ts']} for a,b in zip(ev,ev[1:]) if b['ts']-a['ts']>=p.get('gap',3600)]


@operation('Разбить хронологию на сеансы по периоду бездействия')
def sessions(p):
    chunks=[]
    for e in events(p):
        if not chunks or e['ts']-chunks[-1][-1]['ts']>p.get('gap',3600):
            chunks.append([])
        chunks[-1].append(e)
    return [[e['uid'] for e in ch] for ch in chunks]


@operation('Найти эпизоды с поздней регистрацией')
def delayed_ingestion(p):
    return selected(p,lambda e:e.get('learned',e['ts'])-e['ts']>p.get('lag',0))


@operation('Собрать календарь плотности воспоминаний по UTC-дням')
def day_density(p):
    return dict(Counter(str(e['ts']//86400) for e in events(p)))


@operation('Извлечь эпизоды по точному идентификатору проекта')
def project_history(p):
    return field(p,'project')


@operation('Найти авторские высказывания указанного участника')
def authored(p):
    return field(p,'author')


@operation('Извлечь события с любым из заданных тегов')
def tag_union(p):
    tags=set(p.get('tags',[]))
    return selected(p,lambda e:bool(tags.intersection(e.get('tags',[]))))


@operation('Найти материалы на пересечении всех заданных тегов')
def tag_intersection(p):
    tags=set(p.get('tags',[]))
    return selected(p,lambda e:bool(tags) and tags.issubset(e.get('tags',[])))


@operation('Ранжировать эпизоды по редкости слов запроса в архиве')
def distinctive_search(p):
    ev=events(p)
    df=Counter(w for e in ev for w in set(words(e.get('text',''))))
    q=keys(p)
    return score(p,lambda e:sum(log(1+(len(ev)+1)/(df[w]+1)) for w in q.intersection(words(e.get('text','')))))


@operation('Выдать ближайшие текстовые совпадения при неточном воспоминании')
def fuzzy_recall(p):
    q=' '.join(words(p['query']))
    return score(p,lambda e:SequenceMatcher(None,q,' '.join(words(e.get('text',''))),autojunk=False).ratio() if q else 0)


@operation('Показать окно вокруг найденной цитаты')
def quote_context(p):
    target=focus(p).get('text','')
    needle=p['query']
    pos=target.casefold().find(needle.casefold())
    if pos<0 or not needle:
        return None
    n=max(0,p.get('radius',32))
    return {'start':pos,'end':pos+len(needle),'excerpt':target[max(0,pos-n):pos+len(needle)+n]}


@operation('Найти лексику, отличающую выбранный эпизод от остальных')
def distinguishing_terms(p):
    e=focus(p)
    rest=set(w for row in events(p) if row['uid']!=p.get('id') for w in words(row.get('text','')))
    return sorted(set(words(e.get('text','')))-rest)


@operation('Ранжировать похожие эпизоды по общим меткам')
def related_tags(p):
    tags=set(focus(p).get('tags',[]))
    def similarity(e):
        other=set(e.get('tags',[]))
        return len(tags&other)/max(1,len(tags|other)) if e['uid']!=p.get('id') else 0
    return score(p,similarity)


@operation('Показать соседние записи до и после предмета внимания')
def neighboring_episodes(p):
    ev=events(p)
    for i,e in enumerate(ev):
        if e['uid']==p.get('id'):
            n=max(0,p.get('count',1))
            return ev[max(0,i-n):i+n+1]
    return []


@operation('Восстановить историю версий выбранного предмета')
def revision_history(p):
    return field(p,'item')


@operation('Восстановить состояние предмета на дату его применения')
def revision_at(p):
    rows=[e for e in revision_history(p) if e['ts']<=p['at']]
    return rows[-1] if rows else None


@operation('Восстановить доступную тогда версию с учётом даты поступления')
def version_known_then(p):
    rows=[e for e in revision_history(p) if e['ts']<=p['at'] and e.get('learned',e['ts'])<=p['as_known']]
    return rows[-1] if rows else None


@operation('Сравнить два текста построчно')
def line_changes(p):
    a=index(p).get(p.get('id'),{}).get('text','')
    b=index(p).get(p.get('other'),{}).get('text','')
    return list(unified_diff(a.splitlines(),b.splitlines(),lineterm=''))


@operation('Показать только отредактированные поля снимков')
def changed_fields(p):
    a=focus(p)
    b=index(p).get(p.get('other'),{})
    return {k:{'old':a.get(k),'new':b.get(k)} for k in sorted(a.keys()|b.keys()) if k not in a or k not in b or a[k]!=b[k]}


@operation('Найти параллельные версии с общим родителем')
def forks(p):
    branches=grouped([e for e in events(p) if e.get('parent')],'parent')
    return {k:[e['uid'] for e in v] for k,v in branches.items() if len(v)>1}


@operation('Выбрать конечные версии выбранного объекта')
def revision_heads(p):
    ev=revision_history(p)
    parents={e.get('parent') for e in ev}
    return [e for e in ev if e['uid'] not in parents]


@operation('Найти общий предшествующий снимок двух редакций')
def common_ancestor(p):
    adj={e['uid']:[e['parent']] for e in events(p) if e.get('parent')}
    a=[p['id']]+traverse(p,p['id'],adj)
    b=set([p['other']]+traverse(p,p['other'],adj))
    return next((i for i in a if i in b),None)


@operation('Вычислить контрольный отпечаток текста версии')
def text_fingerprint(p):
    return sha256(focus(p).get('text','').encode('utf-8')).hexdigest()


@operation('Обнаружить одинаковый текст под разными идентификаторами')
def identical_versions(p):
    bins=defaultdict(list)
    for e in events(p):
        if e.get('text'):
            bins[e['text']].append(e['uid'])
    return [ids for ids in bins.values() if len(ids)>1]


@operation('Раскрыть прямые источники утверждения')
def immediate_sources(p):
    data=index(p)
    return [{'uid':k,'record':data.get(k)} for k in refs(focus(p))]


@operation('Пройти цепочку происхождения утверждения')
def source_chain(p):
    return traverse(p,p['id'],links(p))


@operation('Найти упоминания выбранного первоисточника')
def direct_citations(p):
    return foreign_key(p,'sources')


@operation('Отметить все выводы, зависящие от исправленного свидетельства')
def affected_claims(p):
    return traverse(p,p['id'],back(p))


@operation('Выделить первичные свидетельства на концах цепочки')
def evidence_roots(p):
    adj=links(p)
    return [v for v in [p['id']]+source_chain(p) if v in adj and not adj[v]]


@operation('Найти общие первоисточники двух суждений')
def shared_origins(p):
    return sorted(set(evidence_roots(p))&set(evidence_roots(dict(p,id=p['other']))))


@operation('Обнаружить ссылки на отсутствующие свидетельства')
def missing_sources(p):
    known=index(p)
    return {k:missing for k,v in links(p).items() if (missing:=[s for s in v if s not in known])}


@operation('Найти взаимные ссылки, требующие проверки независимого основания')
def circular_citations(p):
    adj=links(p)
    return [e['uid'] for e in events(p) if any(e['uid']==s or e['uid'] in traverse(p,s,adj) for s in adj[e['uid']])]


@operation('Построить профиль прямых и косвенных свидетельств')
def evidence_modes(p):
    return dict(Counter(e.get('basis','unknown') for e in events(p)))


@operation('Сопоставить свидетельства за и против одного утверждения')
def disputed_claims(p):
    by_claim=grouped([e for e in events(p) if e.get('claim')],'claim')
    return {c:{stance:[e['uid'] for e in rows if e.get('stance')==stance] for stance in ['for','against']} for c,rows in by_claim.items() if {'for','against'}<={e.get('stance') for e in rows}}


@operation('Составить перечень открытых замыслов')
def active_intents(p):
    return selected(p,lambda e:e.get('kind')=='intent' and e.get('status')=='open')


@operation('Собрать фиксированные части замысла по истории изменений')
def intent_invariants(p):
    return unique(x for e in revision_history(p) for x in e.get('keep',[]))


@operation('Извлечь свободные для изменения детали текущего замысла')
def negotiable_details(p):
    e=focus(p)
    return sorted(set(e.get('flexible',[]))-set(e.get('keep',[])))


@operation('Подобрать незакрытые вопросы к новому материалу')
def useful_to_questions(p):
    terms=keys(p)
    return selected(p,lambda e:e.get('kind')=='question' and e.get('status')=='open' and bool(terms&set(words(e.get('text',''))+e.get('tags',[]))))


@operation('Восстановить последнюю точку работы над проектом')
def resume_marker(p):
    rows=[e for e in project_history(p) if e.get('next_step')]
    return {'source':rows[-1]['uid'],'step':rows[-1]['next_step']} if rows else None


@operation('Показать отброшенные варианты вместе с причинами отказа')
def rejected_alternatives(p):
    return [{'uid':e['uid'],'reason':e.get('reason'),'alternative':e.get('text')} for e in project_history(p) if e.get('status')=='rejected']


@operation('Сопоставить решения с их предпосылками')
def assumption_map(p):
    return {e['uid']:e['assumptions'] for e in project_history(p) if e.get('assumptions')}


@operation('Проверить выполнение предварительных условий задачи')
def prerequisites(p):
    data=index(p)
    req=focus(p).get('requires',[])
    return {k:(data.get(k,{}).get('status')=='done') for k in req}


@operation('Извлечь намерения, активируемые указанным событием')
def triggered_intents(p):
    return [e for e in active_intents(p) if p.get('trigger') in e.get('triggers',[])]


@operation('Составить компактную передачу незаконченного проекта')
def handoff(p):
    rows=project_history(p)
    return {'project':p.get('project'),'recent':[e['uid'] for e in rows[-3:]],'resume':resume_marker(p),'unresolved':[e['uid'] for e in rows if e.get('status')=='open']}


@operation('Найти действующее толкование общего выражения в данном проекте')
def phrase_meaning(p):
    q=' '.join(words(p['query']))
    rows=[e for e in project_history(p) if e.get('kind')=='phrase' and q in [' '.join(words(s)) for s in e.get('aliases',[])] and e['ts']<=p['at']]
    return rows[-1] if rows else None


@operation('Собрать многоязычные названия одного общего приёма')
def aliases_for_item(p):
    return unique(a for e in revision_history(p) for a in e.get('aliases',[]))


@operation('Развести одно название между предметами по контексту')
def ambiguous_aliases(p):
    bins=defaultdict(set)
    for e in events(p):
        for alias in e.get('aliases',[]):
            if e.get('item'):
                bins[' '.join(words(alias))].add(e['item'])
    return {k:sorted(v) for k,v in bins.items() if len(v)>1}


@operation('Показать, как менялось толкование выражения')
def meaning_changes(p):
    history=[e for e in revision_history(p) if e.get('kind')=='phrase']
    return [{'from':a['uid'],'to':b['uid'],'before':a.get('text'),'after':b.get('text')} for a,b in zip(history,history[1:]) if a.get('text')!=b.get('text')]


@operation('Найти звуковые или текстовые образцы для согласованного термина')
def phrase_examples(p):
    data=index(p)
    row=phrase_meaning(p) or {}
    return [data[i] for i in row.get('examples',[]) if i in data]


@operation('Собрать речевые особенности конкретного персонажа')
def character_lexicon(p):
    rows=field(p,'speaker')
    return dict(Counter(w for e in rows for w in words(e.get('text',''))).most_common(p.get('limit',10)))


@operation('Распознать закреплённое пользователем значение жеста')
def gesture_meaning(p):
    rows=[e for e in project_history(p) if e.get('gesture')==p.get('gesture') and e.get('gesture')]
    return rows[-1].get('action') if rows else None


@operation('Найти событие появления совместного ритуала')
def ritual_origin(p):
    return next((e for e in events(p) if e.get('ritual')==p.get('ritual') and e.get('ritual')),None)


@operation('Собрать исключения из обычного рабочего правила')
def rule_exceptions(p):
    return foreign_key(p,'exception_to')


@operation('Восстановить язык конкретного источника и доступные переводы')
def translation_links(p):
    return {'original':focus(p).get('lang'),'translations':[{'language':e.get('lang'),'uid':e['uid']} for e in events(p) if e.get('translation_of')==p['id']]}


@operation('Вернуть прежнюю позицию NOX по теме')
def previous_position(p):
    rows=[e for e in revision_history(p) if e.get('author')=='NOX' and e.get('kind')=='opinion' and e['ts']<p['at']]
    return rows[-1] if rows else None


@operation('Объяснить явно записанную причину смены позиции')
def position_revision(p):
    return [{'uid':e['uid'],'previous':e['supersedes'],'reason':e.get('reason')} for e in revision_history(p) if e.get('kind')=='opinion' and e.get('supersedes')]


@operation('Собрать невыполненные обещания выбранного автора')
def outstanding_promises(p):
    return [e for e in authored(p) if e.get('kind')=='promise' and e.get('status') in ('open','waiting')]


@operation('Разделить подтверждённые результаты и попытки без подтверждения')
def execution_receipts(p):
    rows=[e for e in project_history(p) if e.get('kind')=='attempt']
    return {'confirmed':[e['uid'] for e in rows if e.get('receipt')],'unconfirmed':[e['uid'] for e in rows if not e.get('receipt')]}


@operation('Собрать историю применения конкретного умения')
def skill_cases(p):
    return field(p,'skill')


@operation('Извлечь исправления, применённые после собственных ошибок')
def repair_history(p):
    return [{'error':e['repairs'],'repair':e['uid'],'change':e.get('text')} for e in events(p) if e.get('repairs')]


@operation('Сопоставить ожидавшийся и зафиксированный результат')
def expected_actual(p):
    e=focus(p)
    if 'expected' not in e or 'observed' not in e:
        return None
    return {'expected':e['expected'],'observed':e['observed'],'matched':e['expected']==e['observed']}


@operation('Определить первую неозвученную часть размеченной реплики')
def playback_remaining(p):
    e=focus(p)
    t=p.get('played_ms',0)
    return [s for s in e.get('segments',[]) if s['end_ms']>t]


@operation('Найти обещания с истёкшим сроком исполнения')
def overdue_promises(p):
    return [e for e in outstanding_promises(p) if e.get('deadline') is not None and e['deadline']<p['at']]


@operation('Собрать проявления компетенции по независимым проектам')
def skill_coverage(p):
    out=defaultdict(set)
    for e in events(p):
        if e.get('skill') and e.get('receipt') and e.get('project'):
            out[e['skill']].add(e['project'])
    return {k:sorted(v) for k,v in out.items()}


@operation('Восстановить указатель внимания на выбранном устройстве')
def last_device_focus(p):
    rows=[e for e in field(p,'device') if e.get('anchor')]
    return rows[-1]['anchor'] if rows else None


@operation('Показать последнюю точку внимания на каждом устройстве')
def cross_device_positions(p):
    rows=[e for e in project_history(p) if e.get('device') and e.get('anchor')]
    return {device:entries[-1]['anchor'] for device,entries in grouped(rows,'device').items()}


@operation('Разрешить контекстное указание через общую привязку к объекту')
def anchored_reference(p):
    data=index(p)
    e=focus(p)
    anchor=e.get('anchor') or {}
    return {'anchor':anchor,'target':data.get(anchor.get('uid'))} if anchor else None


@operation('Извлечь комментарии, относящиеся к одному месту документа')
def anchor_comments(p):
    a=focus(p).get('anchor')
    return [e for e in events(p) if a and (e.get('anchor') or {}).get('uid')==a.get('uid') and (e.get('anchor') or {}).get('line')==a.get('line') and e.get('kind')=='comment']


@operation('Развернуть эпизоды одной беседы вместе с вложенными ответами')
def thread_descendants(p):
    adj=defaultdict(list)
    for e in events(p):
        if e.get('reply_to'):
            adj[e['reply_to']].append(e['uid'])
    return traverse(p,p['id'],adj)


@operation('Вычислить ближайшую общую тему двух разговоров')
def shared_topic(p):
    a=set(focus(p).get('tags',[]))
    b=set(index(p).get(p.get('other'),{}).get('tags',[]))
    counts=Counter(t for e in events(p) for t in set(e.get('tags',[])))
    return next(iter(sorted(a&b,key=lambda t:(counts[t],t))),None)


@operation('Собрать рабочую выжимку по роли участника')
def role_digest(p):
    return [{'uid':e['uid'],'text':e.get('text','')} for e in project_history(p) if p.get('role') in e.get('roles',[])]


@operation('Найти незакрытые вставные вопросы с обратной ссылкой на основную нить')
def open_detours(p):
    return [{'question':e['uid'],'resume':e['reply_to']} for e in project_history(p) if e.get('kind')=='question' and e.get('reply_to') and e.get('status')=='open']


@operation('Обнаружить контекстные указатели с исчезнувшей целью')
def broken_anchors(p):
    data=index(p)
    return [e['uid'] for e in events(p) if e.get('anchor') and e['anchor'].get('uid') not in data]


@operation('Подобрать эпизоды одного вымышленного мира')
def story_world(p):
    return field(p,'world')


@operation('Отфильтровать память по явной области видимости участника')
def visible_for_actor(p):
    actor=p.get('actor')
    return selected(p,lambda e:e.get('visibility')=='public' or (actor is not None and (e.get('owner')==actor or actor in e.get('audience',[]))))


@operation('Определить записи с завершившимся сроком хранения')
def expired_records(p):
    return selected(p,lambda e:e.get('until') is not None and e['until']<=p['at'])


@operation('Собрать личный экспорт в пределах выбранного проекта')
def scoped_export(p):
    allowed={e['uid'] for e in visible_for_actor(p)}
    expired={e['uid'] for e in expired_records(p)}
    return [{'uid':e['uid'],'text':e.get('text',''),'ts':e['ts']} for e in project_history(p) if e['uid'] in allowed-expired]


@operation('Составить карту производных материалов перед забыванием')
def forgetting_impact(p):
    return {'subject':p['id'],'derived':affected_claims(p),'anchors':[e['uid'] for e in events(p) if (e.get('anchor') or {}).get('uid')==p['id']]}


@operation('Создать снимок после исключения записи и производных цитат')
def without_memory(p):
    forgotten={p['id'],*affected_claims(p)}
    return [copy.deepcopy(e) for e in events(p) if e['uid'] not in forgotten and (e.get('anchor') or {}).get('uid') not in forgotten]


@operation('Сократить карточку памяти до явного списка полей')
def minimal_projection(p):
    e=focus(p)
    return {k:e[k] for k in p.get('fields',[]) if k in e}


@operation('Собрать неподтверждённые импортированные эпизоды отдельно')
def pending_imports(p):
    return selected(p,lambda e:e.get('imported') and not e.get('verified'))


@operation('Проверить разрешение переносить материал в указанный проект')
def transfer_permission(p):
    e=focus(p)
    dest=p.get('destination')
    return bool(e and dest and (e.get('project')==dest or dest in e.get('allowed_projects',[])))


@operation('Определить общую разрешённую аудиторию производной записи')
def shared_audience(p):
    data=index(p)
    ids=p.get('ids',[])
    if not ids or any(uid not in data for uid in ids):
        return []
    restrictions=[set(data[k].get('audience',[]))|({data[k]['owner']} if data[k].get('owner') else set()) for k in ids if data[k].get('visibility')!='public']
    return {'public':True} if not restrictions else sorted(set.intersection(*restrictions))


@operation('Обнаружить выводы, построенные на материалах другого художественного мира')
def world_crossings(p):
    data=index(p)
    return [{'uid':e['uid'],'source':k} for e in events(p) for k in refs(e) if k in data and e.get('world','real')!=data[k].get('world','real')]


@operation('Объединить повторные наблюдения одного события по ключу с сохранением источников')
def consolidate_duplicates(p):
    groups=defaultdict(list)
    for e in events(p):
        key=e.get('event_key') or e['uid']
        groups[key].append(e)
    return [{'event':k,'records':[e['uid'] for e in rows],'sources':unique(s for e in rows for s in refs(e))} for k,rows in groups.items()]


@operation('Найти повторяющийся опыт на независимых проектах')
def repeated_experiences(p):
    by=defaultdict(set)
    for e in events(p):
        for tag in e.get('tags',[]):
            if e.get('project'):
                by[tag].add(e['project'])
    return {k:sorted(v) for k,v in by.items() if len(v)>=max(2,p.get('min_projects',2))}


@operation('Подобрать показательные исключения к выбранному обобщению')
def counterexamples(p):
    claim=focus(p).get('claim')
    stance=focus(p).get('stance')
    return selected(p,lambda e:claim is not None and e.get('claim')==claim and {stance,e.get('stance')}=={'for','against'})


@operation('Вычислить медианный промежуток между применениями навыка')
def rehearsal_cadence(p):
    rows=skill_cases(p)
    gaps=[b['ts']-a['ts'] for a,b in zip(rows,rows[1:])]
    return median(gaps) if gaps else None


@operation('Подобрать навыки, ожидающие следующего повторения')
def rehearsals_due(p):
    rows=[e for e in events(p) if e.get('skill') and e['ts']<=p['at']]
    latest={e['skill']:e for e in rows}
    return sorted(skill for skill,e in latest.items() if 'review_after' in e and e['ts']+e['review_after']<=p['at'])


@operation('Построить указатель вех проекта по порядку')
def milestone_index(p):
    return [{'uid':e['uid'],'label':e['milestone'],'ts':e['ts']} for e in project_history(p) if e.get('milestone')]


@operation('Выдать свежие примеры опыта, покрывающие разные темы')
def diverse_recap(p):
    seen=set()
    picked=[]
    for e in reversed(project_history(p)):
        if len(picked)>=max(0,p.get('limit',5)):
            break
        tags=set(e.get('tags',[]))
        if tags-seen or not picked:
            picked.append(e['uid'])
            seen.update(tags)
    return picked


@operation('Пересчитать давность выводов относительно даты запроса')
def belief_ages(p):
    return {e['uid']:p['at']-e['ts'] for e in events(p) if e.get('kind') in ('claim','opinion') and e['ts']<=p['at']}


@operation('Развести в архиве два одноимённых объекта по явным идентификаторам записей')
def split_entity(p):
    ids=set(p.get('ids',[]))
    return [dict(e,item=p['new_item']) if e['uid'] in ids and e.get('item')==p.get('item') else copy.deepcopy(e) for e in events(p)]


@operation('Восстановить сводку предмета после исключения оспоренных источников')
def rebuild_digest(p):
    bad=set(p.get('invalid',[]))
    adj=back(p)
    for ident in list(bad):
        bad.update(traverse(p,ident,adj))
    stable=[e for e in revision_history(p) if e['uid'] not in bad]
    return {'item':p['item'],'last':stable[-1]['uid'] if stable else None,'trace':[e['uid'] for e in stable]}


SAMPLE = {
    'events':[
        {'uid':'a','ts':10,'learned':12,'project':'Cinema','author':'Иван','text':'Герой узнаёт голос','item':'voice','tags':['голос','герой'],'kind':'opinion','basis':'direct','claim':'знаком','stance':'for','owner':'Иван','audience':['редактор'],'sources':[],'ritual':'прослушивание','speaker':'смотритель','skill':'чтение','roles':['диктор'],'milestone':'эскиз','lang':'ru'},
        {'uid':'b','ts':20,'learned':23,'project':'Cinema','author':'NOX','text':'Голос звучит тише','item':'voice','tags':['голос','пауза'],'kind':'opinion','sources':['a'],'parent':'a','basis':'inference','claim':'знаком','stance':'against','skill':'чтение','receipt':'take-2','anchor':{'uid':'a','line':1},'device':'phone','expected':'громче','observed':'тише','flexible':['темп'],'keep':['голос'],'requires':['a'],'supersedes':'a','reason':'дубль 2','segments':[{'text':'голос','end_ms':350}],'owner':'Иван','gesture':'tap','action':'пауза','roles':['диктор'],'next_step':'свести дубль','review_after':5},
        {'uid':'c','ts':30,'project':'Cinema','author':'Иван','text':'Вернуть узнавание','item':'ritual','kind':'intent','status':'open','triggers':['дубль'],'sources':['b'],'tags':['герой'],'keep':['пауза'],'world':'сцена','owner':'Иван','until':100,'allowed_projects':['Studio']},
        {'uid':'d','ts':35,'project':'Cinema','author':'Иван','text':'Кто узнал голос?','kind':'question','status':'open','tags':['голос'],'reply_to':'a','parent':'a','item':'voice','owner':'Иван'},
        {'uid':'e','ts':40,'project':'Studio','author':'NOX','text':'Тихая встреча','kind':'phrase','aliases':['голос','voz'],'item':'voice','tags':['голос'],'examples':['a'],'owner':'Иван','sources':['a'],'translation_of':'a','lang':'es','skill':'чтение','receipt':'take-3'},
    ],
    'id':'b','other':'a','ids':['a','b'],'invalid':['c'],'project':'Cinema','query':'голос','at':45,'as_known':45,
    'start':10,'end':32,'gap':8,'lag':1,'tags':['голос'],'item':'voice','limit':5,'count':1,'radius':8,
    'author':'NOX','trigger':'дубль','speaker':'смотритель','gesture':'tap','ritual':'прослушивание','skill':'чтение',
    'device':'phone','role':'диктор','world':'сцена','actor':'Иван','fields':['uid','text'],'destination':'Studio',
    'new_item':'voice-2','played_ms':20,
}

# Небольшой полноразмерный срез журнала для воспроизводимых вызовов интерфейса.
SAMPLE['events'].extend([
    {'uid':'f','ts':42,'project':'Cinema','author':'NOX','kind':'phrase','item':'phrase-voice','text':'Говори мягче','aliases':['голос','voz'],'examples':['a'],'owner':'Иван'},
    {'uid':'g','ts':43,'project':'Cinema','author':'NOX','kind':'phrase','item':'phrase-voice','text':'Пауза перед первым словом','aliases':['голос','voz'],'examples':['b'],'owner':'Иван'},
    {'uid':'h','ts':44,'project':'Cinema','author':'NOX','kind':'promise','status':'open','item':'subtitles','deadline':44,'text':'Вернуть субтитры','owner':'Иван','imported':True,'verified':False},
    {'uid':'i','ts':46,'project':'Cinema','author':'NOX','kind':'attempt','receipt':'render-1','text':'Говори мягче','event_key':'mix','parent':'a','status':'rejected','reason':'ломает интонацию','assumptions':['чистая запись'],'repairs':'a','sources':['missing'],'owner':'Иван'},
    {'uid':'j','ts':47,'project':'Cinema','author':'Иван','kind':'comment','text':'Сохранить эту паузу','anchor':{'uid':'a','line':1},'exception_to':['a'],'owner':'Иван','event_key':'mix'},
    {'uid':'k','ts':48,'project':'Cinema','author':'NOX','kind':'attempt','item':'voice','text':'Сверить результат','sources':['l'],'anchor':{'uid':'missing-anchor','line':4},'owner':'Иван'},
    {'uid':'l','ts':49,'project':'Cinema','author':'NOX','kind':'claim','item':'voice','text':'Требует проверки','sources':['k'],'owner':'Иван'},
])
SAMPLES = {
    name: dict(SAMPLE, **params) for name, params in {
        'next_episode':{'at':30},
        'first_mention':{'query':'узнаёт'},
        'quote_context':{'query':'Голос'},
        'ritual_origin':{'id':'a'},
        'rule_exceptions':{'id':'a'},
        'translation_links':{'id':'a'},
        'meaning_changes':{'item':'phrase-voice'},
        'thread_descendants':{'id':'a'},
        'rehearsals_due':{'at':30},
        'expired_records':{'at':101},
        'without_memory':{'id':'a'},
        'prerequisites':{'id':'b'},
        'transfer_permission':{'id':'c'},
        'common_ancestor':{'id':'b','other':'d'},
        'forks':{'id':'a'},
        'shared_topic':{'id':'a','other':'b'},
    }.items()
}

SAMPLES = {name: SAMPLES.get(name, SAMPLE) for name in OPS}
