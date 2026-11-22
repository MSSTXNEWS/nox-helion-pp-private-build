"""A project-local life loop, grounded in observable actions and their outcomes."""
import hashlib
import json
from pathlib import Path
import sqlite3
from . import self_state, skill_growth, curiosity

def setup(db):
    self_state.init(db)
    db.execute("""CREATE TABLE IF NOT EXISTS brain_workshop(
       scope TEXT PRIMARY KEY,enabled INTEGER NOT NULL DEFAULT 0,last TEXT,
       previous TEXT,subject TEXT NOT NULL DEFAULT 'conversation',behavior TEXT NOT NULL DEFAULT 'continue')""")
    db.execute("""CREATE TABLE IF NOT EXISTS brain_observed(scope TEXT, token TEXT, PRIMARY KEY(scope,token))""")

def open_row(db,scope):
    if not isinstance(scope,str) or not scope or scope=="default" or len(scope)>200:raise ValueError("Нужен идентификатор проекта или беседы")
    setup(db)
    db.execute("INSERT OR IGNORE INTO brain_workshop(scope) VALUES(?)",(scope,))
    return db.execute("SELECT * FROM brain_workshop WHERE scope=?",(scope,)).fetchone()

def appraisal(db,scope,token,kind,subject,value=None):
    result=self_state.observe(db,scope,token,kind,subject,value)
    curiosity.notice(db,scope,token,kind,subject,value)
    db.execute("UPDATE brain_workshop SET subject=?,behavior=? WHERE scope=?",(subject,result["next_behavior"],scope))
    return result

def experience(k,scope,token,op,data,value,successful):
    if not scope or scope=="default" or not token:return
    with k.journal() as db:
        row=open_row(db,scope)
        if not db.execute("INSERT OR IGNORE INTO brain_observed VALUES(?,?)",(scope,token)).rowcount:return
        appraisal(db,scope,token,"success" if successful else "failure",op)
        if not row["enabled"] or not successful or op not in k.ops:return
        item=json.dumps({"op":op,"input":data,"output":value},ensure_ascii=False,sort_keys=True)
        # A bounded pair of current examples exists only while the workshop is enabled.
        if len(item.encode())>24000:
            db.execute("UPDATE brain_workshop SET last=NULL,previous=NULL WHERE scope=?",(scope,))
            return
        db.execute("UPDATE brain_workshop SET previous=last,last=? WHERE scope=?",(item,scope))

def supervise(k,scope,token,action,p):
    if action=="teach":
        from . import evolve
        base=base_router()
        return evolve.submit_event(k.path.parent/"brain800-evolution",scope,base,token,p)
    with k.journal() as db:
        row=open_row(db,scope)
        if action=="agenda":return curiosity.agenda(db,scope)
        if action=="summary":
            state=self_state.reflect(db,scope)
            if not state["recent_episodes"]:return "Пока у меня нет собственного опыта в этой беседе."
            return {"пересмотренные_прогнозы":state["predictions_corrected"],
                    "что_изменило_моё_поведение":state["learned_change"],
                    "текущие_цели":curiosity.agenda(db,scope),
                    "следующее_действие":{"question":"уточнить","hold":"выдержать паузу","propose":"предложить вариант","continue":"продолжить"}[state["next_behavior"]]}
        if action=="state":return self_state.reflect(db,scope)
        if action=="skills":return skill_growth.catalog(db,scope)
        if action=="apply":return skill_growth.execute(db,scope,p["name"],p["a"],p["b"],k.run)
        if action=="revoke":return skill_growth.rollback(db,scope,p["name"],p.get("version"))
        if action in ("on","off"):
            enabled=int(action=="on")
            db.execute("UPDATE brain_workshop SET enabled=?,previous=NULL,last=NULL WHERE scope=?",(enabled,scope))
            return {"workshop":bool(enabled)}
        if action=="event":
            topic=p.get("subject","conversation")
            if topic not in k.meta and topic not in {"conversation","voice.timing","voice.pacing","dialog.question","dialog.project"}:
                raise ValueError("Для события укажите зарегистрированную операцию или известную область диалога")
            return appraisal(db,scope,token,p["kind"],topic,p.get("value"))
        if action!="feedback":raise ValueError("Неизвестное событие")
        rating=p["value"]
        if type(rating) not in (int,float) or not -1<=rating<=1:raise ValueError("Оценка от −1 до 1")
        status=appraisal(db,scope,token,"feedback",row["subject"],rating)
        if rating<=0 or not row["enabled"] or not row["previous"] or not row["last"]:return status
        a,b=json.loads(row["previous"]),json.loads(row["last"])
        bindings=[key for key,v in b["input"].items() if type(v) is type(a["output"]) and v==a["output"]]
        if len(bindings)!=1:return status
        bind=bindings[0]
        rule=a["op"]+"+"+b["op"]+"@"+bind
        status["growth"]=skill_growth.propose_observation(db,scope,token,rule,a["op"],b["op"],bind,
                     a["input"],b["input"],b["output"],k.run)
        return status

def base_router():
    import os
    return Path(os.environ.get("NOX_BRAIN800_ROUTER") or Path(__file__).with_name("router10k.npz"))

def policy(state_dir,scope):
    path=Path(state_dir)/"brain800.sqlite3"
    if not scope or scope=="default" or not path.is_file():return None
    try:
        from contextlib import closing
        with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=.25)) as db:
            row=db.execute("SELECT behavior FROM brain_workshop WHERE scope=?",(scope,)).fetchone()
        return row[0] if row else None
    except sqlite3.Error:return None

def record_turn(state_dir,scope,turn_id,intent,complete):
    """Calibrate a forecast of technical completion. A generated reply is not a quality label."""
    if not scope or scope=="default":return
    import re
    from .kernel import connect_journal
    subject="dialog."+re.sub("[^a-z0-9_.-]","_",str(intent).lower())[:60]
    try:
        with connect_journal(Path(state_dir)/"brain800.sqlite3") as db:
            open_row(db,scope)
            if not db.execute("INSERT OR IGNORE INTO brain_observed VALUES(?,?)",(scope,"dialog/"+turn_id)).rowcount:return
            db.execute("""CREATE TABLE IF NOT EXISTS completion_history(scope TEXT, subject TEXT,
                       passes INTEGER, total INTEGER, PRIMARY KEY(scope,subject))""")
            old=db.execute("SELECT passes,total FROM completion_history WHERE scope=? AND subject=?",(scope,subject)).fetchone()
            passes,total=old if old else (0,0)
            if not total:appraisal(db,scope,turn_id+"/new","novelty",subject)
            # The first forecast is a neutral prior. Later forecasts use only earlier observations.
            forecast=(passes+1)/(total+2)
            appraisal(db,scope,turn_id+"/forecast","prediction",subject,forecast)
            appraisal(db,scope,turn_id+"/observed","outcome",subject,float(bool(complete)))
            db.execute("INSERT OR REPLACE INTO completion_history VALUES(?,?,?,?)",(scope,subject,passes+int(bool(complete)),total+1))
    except (OSError,sqlite3.Error,ValueError):
        return
