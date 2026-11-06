"""Read-only local discovery. Does not create, rename or open SQLite for writing."""
from pathlib import Path
import os, sqlite3, json, time
NOX = Path(os.environ.get('NOX_ROOT',r'C:\NOX_HELION'))
SCAN = ('APP','LOGS','TRAINING','TRAIN','LEARN','MODELS','MEMORY','S03','DATA')
SKIP = {'node_modules','.git','venv','.venv','site-packages','blobs','weights','ollama','vendor','BACKUPS','tmp'}
def candidates(exts, names=(), maxfiles=1500):
    found=[];seen=set(); start=time.monotonic(); visited=0
    for folder in SCAN:
        root=NOX/folder
        if not root.is_dir():continue
        for current,dirs,files in os.walk(root):
            visited+=1
            if visited>800 or time.monotonic()-start>2.5:return found
            rel=Path(current).relative_to(root)
            if len(rel.parts)>4:dirs[:]=[];continue
            dirs[:]=[d for d in dirs if d.lower() not in SKIP]
            for f in files:
                if len(found)>=maxfiles:return found
                p=Path(current)/f
                if f.lower() in names or p.suffix.lower() in exts:
                    try:
                        if p.stat().st_size < 60*1024*1024 and str(p).lower() not in seen:
                            found.append(p);seen.add(str(p).lower())
                    except OSError:pass
    return found

def sqlite_inventory():
    dbs=[]
    for p in candidates({'.sqlite','.sqlite3','.db'},maxfiles=250):
        try:
            uri=p.resolve().as_uri()+'?mode=ro'
            with sqlite3.connect(uri,uri=True,timeout=.6) as db:
                rows=db.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 50").fetchall()
            tables=[x[0] for x in rows]
            dbs.append({'path':str(p),'bytes':p.stat().st_size,'tables':tables,'possible_s03':any('mem' in x.lower() or 'knowledge' in x.lower() or 's03' in x.lower() for x in tables)})
        except (sqlite3.Error,OSError,ValueError):pass
    return dbs[:25]

def training_inventory():
    names={'trainer_state.json','adapter_config.json','training_args.bin','trainer_log.jsonl','training_log.jsonl','training.log','trainer.log'}
    files=[]
    for p in candidates({'.jsonl'}, names=names,maxfiles=350):
        try:files.append({'path':str(p),'name':p.name,'bytes':p.stat().st_size,'modified':int(p.stat().st_mtime)})
        except OSError:pass
    return files[:70]

def status():
    return {'at':int(time.time()),'root_available':NOX.is_dir(),'root':str(NOX),'s03_candidates':sqlite_inventory(),'training_candidates':training_inventory(),
            'note':'Read-only discovery. Does not prove trainer executable contract, database write API or checkpoint validity.'}