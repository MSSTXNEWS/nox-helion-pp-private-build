"""Learns a local appraisal of its own actions. No transcript, user traits or raw IDs are stored."""
import hashlib
import hmac
import json
import math
import secrets
from contextlib import contextmanager

SIGNALS = ('curiosity', 'caution', 'confidence', 'initiative')
BASE = (0.48, 0.28, 0.46, 0.48)
EFFECT = {
    'novelty': (0.32, 0.04, -0.02, 0.20),
    'success': (0.02, -0.15, 0.19, 0.14),
    'failure': (-0.05, 0.34, -0.29, -0.22),
    'uncertainty': (0.12, 0.31, -0.17, -0.12),
    'correction': (0.07, 0.24, -0.14, -0.08),
    'prediction': (0.08, 0.04, 0.02, 0.04),
    'outcome': (0, 0, 0, 0),
    'feedback': (0, 0, 0, 0),
}
REASONS = {
    'propose': 'Возник повод предложить обратимый следующий шаг.',
    'question': 'Перед следующим выбором нужен недостающий факт.',
    'hold': 'Сочетание высокой осторожности и низкой уверенности откладывает инициативу.',
    'continue': 'Можно продолжить текущую работу в её согласованных пределах.',
}

@contextmanager
def atomic(db):
    db.execute('SAVEPOINT nox_functional_self')
    try:
        yield
    except BaseException:
        db.execute('ROLLBACK TO nox_functional_self')
        db.execute('RELEASE nox_functional_self')
        raise
    else:
        db.execute('RELEASE nox_functional_self')

def init(db):
    statements = (
        'CREATE TABLE IF NOT EXISTS nox_self_secret(slot INTEGER PRIMARY KEY CHECK(slot=1), key BLOB NOT NULL)',
        'CREATE TABLE IF NOT EXISTS nox_self_topics(scope TEXT, subject TEXT, body TEXT NOT NULL, PRIMARY KEY(scope,subject))',
        'CREATE TABLE IF NOT EXISTS nox_self_appraisal(scope TEXT, subject TEXT, kind TEXT, score REAL NOT NULL, n INTEGER NOT NULL, PRIMARY KEY(scope,subject,kind))',
        'CREATE TABLE IF NOT EXISTS nox_self_events(seq INTEGER PRIMARY KEY, scope TEXT NOT NULL, eid TEXT NOT NULL, subject TEXT NOT NULL, kind TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT NOT NULL, UNIQUE(scope,eid))',
        'CREATE INDEX IF NOT EXISTS nox_self_recent ON nox_self_events(scope,seq)',
    )
    with atomic(db):
        for statement in statements:
            db.execute(statement)
        db.execute('INSERT OR IGNORE INTO nox_self_secret VALUES(1,?)', (secrets.token_bytes(32),))

def clamp(x):
    return round(min(1.0, max(0.0, x)), 6)

def token(db, namespace, val):
    if not isinstance(val, str) or not val.strip() or len(val) > 512:
        raise ValueError('Нужен непустой идентификатор длиной до 512 символов.')
    secret=db.execute('SELECT key FROM nox_self_secret WHERE slot=1').fetchone()[0]
    return hmac.new(secret,(namespace+'\x00'+val).encode(),hashlib.sha256).hexdigest()

def checked_value(kind, value):
    if kind not in EFFECT:
        raise ValueError('Неизвестный тип события саморегуляции.')
    if value is None:
        if kind in ('feedback','outcome'):
            raise ValueError('Для оценки или исхода нужно числовое значение.')
        return None
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
        raise ValueError('Оценка должна быть конечным числом.')
    lower=0 if kind in ('prediction','outcome') else -1
    if not lower<=value<=1:
        raise ValueError('Оценка вне допустимого диапазона.')
    if kind not in ('feedback','prediction','outcome'):
        raise ValueError('Для такого типа наблюдения числовая оценка не предусмотрена.')
    return float(value)

def initial():
    return {'signals':dict(zip(SIGNALS, BASE)), 'experience':0,'successes':0,'failures':0,
            'matched_predictions':0,'predictions_corrected':0,'pending':None,
            'last_decision':None,'last_lesson':None,'last_error':None}

def decision(signals):
    curious,cautious,confident,initiative=(signals[k] for k in SIGNALS)
    if cautious>=0.68 and confident<0.43:
        return 'hold'
    if cautious>=0.52 or confident<0.37:
        return 'question'
    if initiative>=0.58 and curious>=0.47:
        return 'propose'
    return 'continue'

def learn(db, scope, subject, target, value):
    row=db.execute('SELECT score,n FROM nox_self_appraisal WHERE scope=? AND subject=? AND kind=?',
                   (scope,subject,target)).fetchone()
    previous,count=(float(row[0]),int(row[1])) if row else (0.0,0)
    # Bounded adaptation; old judgments can be revised after repeated feedback.
    current=round(previous+0.45*(value-previous),6)
    db.execute('INSERT INTO nox_self_appraisal VALUES(?,?,?,?,?) ON CONFLICT(scope,subject,kind) '
               'DO UPDATE SET score=excluded.score,n=excluded.n',(scope,subject,target,current,count+1))
    return {'target_kind':target,'previous':previous,'current':current,'examples':count+1}

def observe(db,scope,event_id,kind,subject,feedback=None):
    value=checked_value(kind,feedback)
    sid=token(db,'scope',scope)
    eid=token(db,sid+':event',event_id)
    topic=token(db,sid+':subject',subject)
    fp=hashlib.sha256(json.dumps([topic,kind,value]).encode()).hexdigest()
    with atomic(db):
        inserted=db.execute('INSERT INTO nox_self_events(scope,eid,subject,kind,fingerprint,result) '
                            "VALUES(?,?,?,?,?,'{}') ON CONFLICT(scope,eid) DO NOTHING",
                            (sid,eid,topic,kind,fp))
        if not inserted.rowcount:
            prior=db.execute('SELECT fingerprint,result FROM nox_self_events WHERE scope=? AND eid=?',(sid,eid)).fetchone()
            if prior[0]!=fp:
                raise ValueError('Повтор события с изменёнными параметрами.')
            return json.loads(prior[1])
        row=db.execute('SELECT body FROM nox_self_topics WHERE scope=? AND subject=?',(sid,topic)).fetchone()
        state=json.loads(row[0]) if row else initial()
        before=state['signals']
        old_action=decision(before)
        increments=list(EFFECT[kind])
        basis=[kind]
        lesson=None
        if kind=='feedback':
            prev=state['last_decision']
            if not prev:
                raise ValueError('В этой области пока нет решения, которое можно оценить.')
            if prev.get('rated'):
                raise ValueError('Это решение уже оценено. Нужен новый эпизод.')
            # Feedback rates the previous behaviour. Approval of waiting supports caution;
            # disapproval of waiting supports a more proactive response.
            proactive = -1.0 if prev['action'] in ('hold','question') else 1.0
            appraisal_target = value * proactive
            lesson=learn(db,sid,topic,prev['kind'],appraisal_target)
            lesson.update({'decision':prev['event'],'rated_behavior':prev['action'],'rating':value,'feedback':eid})
            state['last_lesson']=lesson
            prev['rated']=True
            basis.append(prev['event'])
            # Immediate consequence of an explicit assessment of this decision.
            increments=[0.06*appraisal_target,-0.10*appraisal_target,0.08*value,0.12*appraisal_target]
        elif kind=='prediction':
            if state['pending']:
                raise ValueError('Предыдущий прогноз в этой области ещё открыт.')
            probability=value if value is not None else before['confidence']
            state['pending']={'event':eid,'probability':probability}
        elif kind=='outcome':
            pending=state['pending']
            if not pending:
                raise ValueError('Для исхода нужен связанный открытый прогноз.')
            difference=abs(value-pending['probability'])
            state['last_error']={'prediction':pending['event'],'expected':pending['probability'],
                                 'observed':value,'absolute_error':round(difference,6)}
            state['matched_predictions']+=1
            state['predictions_corrected']+=int(difference>=0.25)
            state['pending']=None
            increments=[0.10*difference,0.30*(difference-0.25),0.22*(0.25-difference),-0.08*difference]
            basis.append(pending['event'])
        if kind=='success':
            state['successes']+=1
        if kind=='failure':
            state['failures']+=1
        profile=db.execute('SELECT score FROM nox_self_appraisal WHERE scope=? AND subject=? AND kind=?',
                           (sid,topic,kind)).fetchone()
        learned=float(profile[0]) if profile else 0
        # Acquired valuation changes the next actual decision on recurrence.
        shifts=[0.08*learned,-0.28*learned,0.16*learned,0.32*learned]
        signals={key:clamp(BASE[i]+0.72*(before[key]-BASE[i])+increments[i]+shifts[i])
                 for i,key in enumerate(SIGNALS)}
        action=decision(signals)
        state.update(signals=signals,experience=state['experience']+1)
        if kind!='feedback':
            state['last_decision']={'kind':kind,'action':action,'event':eid,'rated':False}
        result={'event_id':eid,'subject_id':topic,'kind':kind,'signals':signals,'next_behavior':action,
                'previous_behavior':old_action,'reason':REASONS[action],'basis':basis,
                'learned_appraisal':learned,'learned_change':lesson,'experience':state['experience']}
        db.execute('INSERT INTO nox_self_topics VALUES(?,?,?) ON CONFLICT(scope,subject) DO UPDATE SET body=excluded.body',
                   (sid,topic,json.dumps(state,ensure_ascii=False)))
        db.execute('UPDATE nox_self_events SET result=? WHERE scope=? AND eid=?',(json.dumps(result,ensure_ascii=False),sid,eid))
    return result

def reflect(db,scope):
    sid=token(db,'scope',scope)
    rows=db.execute('SELECT subject,body FROM nox_self_topics WHERE scope=? ORDER BY subject',(sid,)).fetchall()
    known=[];unknown=[];lessons=[];corrected=0
    for topic,body in rows:
        state=json.loads(body)
        known.append({'subject_id':topic,'episodes':state['experience'],'signals':state['signals'],
                      'recorded_success':state['successes'],'recorded_failure':state['failures'],
                      'evaluated_predictions':state['matched_predictions'],'last_prediction_error':state['last_error'],
                      'next_behavior':decision(state['signals'])})
        if not state['matched_predictions']:
            unknown.append({'subject_id':topic,'reason':'no_observed_prediction_outcome'})
        if state['pending']:
            unknown.append({'subject_id':topic,'reason':'awaiting_outcome','prediction':state['pending']})
        if not state['last_lesson']:
            unknown.append({'subject_id':topic,'reason':'no_explicit_appraisal_feedback'})
        else:
            lessons.append({'subject_id':topic,**state['last_lesson']})
        corrected+=state['predictions_corrected']
    episodes=db.execute('SELECT result FROM nox_self_events WHERE scope=? ORDER BY seq DESC LIMIT 12',(sid,)).fetchall()
    recent=[json.loads(r[0]) for r in episodes]
    return {'model':'functional_self','known':known,'unknown':unknown or ([] if known else [{'reason':'no_observations'}]),
            'predictions_corrected':corrected,'learned_change':lessons,'recent_episodes':recent,
            'next_behavior':recent[0]['next_behavior'] if recent else 'question'}
