"""Loopback-only SOURCE harness: real A6 ASGI/SQLite, synthetic model transport.
Never deploy this test harness to OneHost. All DB/log paths belong to a temp run.
"""
import argparse,asyncio,hashlib,json,os,sqlite3,sys,time,types,uuid
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--state',type=Path,required=True);p.add_argument('--port',type=int,required=True);a=p.parse_args()
sys.path.insert(0,str(a.bundle.resolve()))
import native_v29_full_bridge as bridge
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,StreamingResponse
import uvicorn
DB=a.state/'existing-s03.sqlite';LOG=a.state/'model-invocations.jsonl'
with sqlite3.connect(DB) as db:db.execute('CREATE TABLE IF NOT EXISTS s03_items(id TEXT PRIMARY KEY,sha256 TEXT,ts REAL,text TEXT)')
sys.modules['s03_memory']=types.SimpleNamespace(DB=DB)
assert bridge.ensure_dialog_schema()
with bridge._db(True) as db:
 for dialog in ('a'*32,'b'*32,'c'*32):db.execute('INSERT OR IGNORE INTO nox_v29_dialogs VALUES(?,?,?,?,?,?,?)',(dialog,bridge.OWNER,'fixture',0,1,bridge._now(),bridge._now()))
app=FastAPI();gates={}
async def proxy(payload):
 question=payload['messages'][-1]['content'];answer='Привет 🌌 — '+question
 with LOG.open('a') as f:f.write(json.dumps({'question':question,'pid':os.getpid()},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
 async def stream():
  raw=('data: '+json.dumps({'choices':[{'delta':{'content':answer}}]},ensure_ascii=False)+'\n\n').encode();split=raw.index('🌌'.encode())+1
  yield raw[:split];yield raw[split:]
  if question.startswith('HOLD:'):await gates.setdefault(question,asyncio.Event()).wait()
  with bridge._db(True) as db:db.execute('INSERT INTO s03_items VALUES(?,?,?,?)',('fixture-'+uuid.uuid4().hex,hashlib.sha256(answer.encode()).hexdigest(),time.time(),question+' '+answer))
  yield b'data: [DONE]\n\n'
 return StreamingResponse(stream(),media_type='text/event-stream')
async def status():return {'primary_model':'SYNTHETIC_SOURCE_FIXTURE'}
bridge.register_native_v29_chat(app,{'_session_ok':lambda r:r.cookies.get('owner')=='fixture','_unauthorized':lambda:JSONResponse({'error':'unauthorized'},401),'_proxy_completion':proxy,'nox_status':status},site_dir=str(a.state))
@app.get('/__source_fixture/status')
def fixture_status():
 with bridge._db() as db:rows=[dict(x) for x in db.execute('SELECT dialog_id,exchange_id,role,content FROM nox_v29_dialog_messages ORDER BY row_id')]
 return {'fixture_kind':'SOURCE_ASGI_REAL_SQLITE_SYNTHETIC_MODEL','pid':os.getpid(),'invocations':[json.loads(s) for s in LOG.read_text().splitlines()] if LOG.exists() else [],'messages':rows}
@app.post('/__source_fixture/release')
async def release(request:Request):
 data=await request.json();gates.setdefault(data['question'],asyncio.Event()).set();return {'released':data['question']}
uvicorn.run(app,host='127.0.0.1',port=a.port,log_level='error')
