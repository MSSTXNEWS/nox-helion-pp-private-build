"""A local development agenda driven by attempted actions and their observed outcomes."""
import json
import math

try:
    from . import self_state
except ImportError:
    import self_state

TOPICS = {
    'voice':'голос','speech':'речь','social':'диалог','reason':'рассуждение',
    'memory':'память','project':'проекты','learning':'обучение',
    'studio':'сцена','perception':'восприятие','intent':'замысел',
    'router':'выбор действия','dialogue':'диалог','chat':'разговор','core':'ядро',
}
GOALS = {
    'prediction_gap':'Какой наблюдаемый признак поможет мне точнее предсказать исход следующего решения?',
    'execution_error':'Какое условие я упустил перед ошибкой и могу ли учесть его при следующем решении?',
    'rejected_behavior':'Как изменить способ ответа на новый похожий запрос с учётом предыдущей поправки?',
}
KINDS = frozenset(self_state.EFFECT) | {'error'}

def init(db):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nox_growth_agenda'").fetchone():
        return
    self_state.init(db)
    with self_state.atomic(db):
        db.execute('CREATE TABLE IF NOT EXISTS nox_growth_agenda(scope TEXT, subject TEXT, label TEXT, '
                   'goal TEXT, recurrence INTEGER, severity REAL, evidence TEXT, prior_decision TEXT, '
                   'status TEXT, opened INTEGER, changed INTEGER, PRIMARY KEY(scope,subject,goal))')
        db.execute('CREATE TABLE IF NOT EXISTS nox_growth_observed(seq INTEGER PRIMARY KEY, scope TEXT, '
                   'event TEXT, fingerprint TEXT NOT NULL, UNIQUE(scope,event))')
        db.execute('CREATE TABLE IF NOT EXISTS nox_growth_forecasts(scope TEXT, subject TEXT, event TEXT, '
                   'probability REAL NOT NULL, PRIMARY KEY(scope,subject))')
        db.execute('CREATE INDEX IF NOT EXISTS nox_growth_active ON nox_growth_agenda(scope,status)')

def _observation(db,sid,eid):
    row=db.execute('SELECT result FROM nox_self_events WHERE scope=? AND eid=?',(sid,eid)).fetchone()
    return json.loads(row[0]) if row else {}

def _text(ident):
    return TOPICS.get(ident.casefold().split('.',1)[0],'наблюдавшаяся операция')

def notice(db,scope,event_id,kind,subject,feedback=None):
    if kind not in KINDS:
        raise ValueError('Неизвестное основание для цели.')
    self_state.checked_value('failure' if kind=='error' else kind,feedback)
    init(db)
    sid=self_state.token(db,'scope',scope)
    eid=self_state.token(db,sid+':event',event_id)
    topic=self_state.token(db,sid+':subject',subject)
    fingerprint=self_state.token(db,sid+':growth',json.dumps([topic,kind,feedback]))
    with self_state.atomic(db):
        cur=db.execute('INSERT INTO nox_growth_observed(scope,event,fingerprint) VALUES(?,?,?) '
                       'ON CONFLICT(scope,event) DO NOTHING',(sid,eid,fingerprint))
        if not cur.rowcount:
            original=db.execute('SELECT fingerprint FROM nox_growth_observed WHERE scope=? AND event=?',(sid,eid)).fetchone()
            if original[0]!=fingerprint:
                raise ValueError('Повтор события с изменённым содержанием.')
            return
        sequence=cur.lastrowid
        own=_observation(db,sid,eid)
        goal=None; severity=0.0; rated_decision=None
        if kind=='prediction':
            probability=feedback
            if probability is None and own:
                state=db.execute('SELECT body FROM nox_self_topics WHERE scope=? AND subject=?',(sid,topic)).fetchone()
                pending=json.loads(state[0]).get('pending') if state else None
                if pending and pending.get('event')==eid:
                    probability=pending['probability']
            if probability is not None:
                db.execute('INSERT INTO nox_growth_forecasts VALUES(?,?,?,?) ON CONFLICT(scope,subject) '
                           'DO UPDATE SET event=excluded.event,probability=excluded.probability',(sid,topic,eid,probability))
        elif kind=='outcome':
            forecast=db.execute('SELECT event,probability FROM nox_growth_forecasts WHERE scope=? AND subject=?',(sid,topic)).fetchone()
            prediction=None; expected=None
            if forecast:
                prediction,expected=forecast
                db.execute('DELETE FROM nox_growth_forecasts WHERE scope=? AND subject=?',(sid,topic))
            elif own and len(own.get('basis',[]))>1:
                state=db.execute('SELECT body FROM nox_self_topics WHERE scope=? AND subject=?',(sid,topic)).fetchone()
                error=json.loads(state[0]).get('last_error') if state else None
                if error and error['prediction']==own['basis'][1]:
                    prediction,expected=error['prediction'],error['expected']
            if expected is not None:
                severity=abs(expected-feedback)
                if severity>=0.25:
                    goal='prediction_gap'
                    rated_decision=prediction
                else:
                    db.execute("UPDATE nox_growth_agenda SET status='closed',changed=? WHERE scope=? "
                               "AND subject=? AND goal='prediction_gap' AND status='open' "
                               "AND COALESCE(prior_decision,'')<>?",(sequence,sid,topic,prediction))
        elif kind in ('error','failure'):
            goal='execution_error';severity=1.0
        elif kind=='correction' or (kind=='feedback' and feedback<0):
            goal='rejected_behavior'; severity=abs(feedback) if feedback is not None else 0.7
            rated_decision=(own.get('learned_change') or {}).get('decision')
        if kind=='success' or (kind=='feedback' and feedback>0 and own.get('learned_change')):
            addressed=('execution_error','rejected_behavior') if kind=='success' else ('rejected_behavior',)
            evidence=eid if kind=='success' else own['learned_change']['decision']
            for addressed_goal in addressed:
                db.execute("UPDATE nox_growth_agenda SET status='closed',changed=? WHERE scope=? AND subject=? "
                           "AND goal=? AND status='open' AND COALESCE(prior_decision,'')<>?",
                           (sequence,sid,topic,addressed_goal,evidence))
        if goal is None:
            return
        db.execute("INSERT INTO nox_growth_agenda VALUES(?,?,?,?,1,?,?,?,'open',?,?) "
                   "ON CONFLICT(scope,subject,goal) DO UPDATE SET recurrence=CASE WHEN status='open' THEN recurrence+1 ELSE 1 END, "
                   "severity=CASE WHEN status='open' THEN MAX(severity,excluded.severity) ELSE excluded.severity END, "
                   "opened=CASE WHEN status='open' THEN opened ELSE excluded.opened END,status='open',"
                   "evidence=excluded.evidence,prior_decision=excluded.prior_decision,changed=excluded.changed",
                   (sid,topic,_text(subject),goal,severity,eid,rated_decision,sequence,sequence))

def agenda(db,scope):
    init(db)
    sid=self_state.token(db,'scope',scope)
    rs=db.execute("SELECT subject,label,goal,recurrence,severity,evidence,prior_decision,changed FROM nox_growth_agenda "
                  "WHERE scope=? AND status='open'",(sid,)).fetchall()
    out=[]
    for subject,label,goal,n,severity,evidence,prior_decision,changed in rs:
        priority=round(math.log2(n+1)+severity,3)
        out.append({'subject_id':subject,'area':label,'goal':goal,'text':GOALS[goal]+' Область: '+label+'.',
                    'evidence_event':evidence,'decision_event':prior_decision,'occurrences':n,
                    'priority':priority,'last_seen':changed})
    return sorted(out,key=lambda item:(-item['priority'],-item['last_seen'],item['subject_id'],item['goal']))
