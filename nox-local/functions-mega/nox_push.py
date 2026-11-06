"""Optional real web push sender. Requires VAPID, pywebpush, and a running local server."""
from pathlib import Path
from urllib.parse import urlsplit
import json, threading, time
import nox_services as svc
SUBS=svc.ROOT/'nox_push_subscriptions.json'
LOCK=threading.Lock()
_ALLOWED=('fcm.googleapis.com','updates.push.services.mozilla.com','web.push.apple.com','*.push.apple.com')

def valid(subscription):
 try:
  ep=subscription['endpoint'];url=urlsplit(ep);keys=subscription['keys']
  host=url.hostname or ''
  return url.scheme=='https' and host in ('fcm.googleapis.com','updates.push.services.mozilla.com','web.push.apple.com','push.services.mozilla.com') and isinstance(keys.get('p256dh'),str) and isinstance(keys.get('auth'),str) and len(ep)<2500
 except (TypeError,KeyError,ValueError):return False

def subscriptions():
 try:
  data=json.loads(SUBS.read_text('utf-8'));return data if isinstance(data,list) else []
 except (OSError,ValueError):return []

def add(sub):
 if not valid(sub):return False
 with LOCK:
  data=subscriptions();data=[x for x in data if x.get('endpoint')!=sub['endpoint']];data.append(sub)
  temp=SUBS.with_suffix('.partial');temp.write_text(json.dumps(data[-10:]),'utf-8');temp.replace(SUBS)
 return True

def send(title,body):
 cfg=svc.load_config(); info=svc.push_status()
 if info['webpush_server']!='READY':return {'status':'HOLD','reason':info['reason']}
 from pywebpush import webpush,WebPushException
 messages=[]
 for s in subscriptions():
  try:
   webpush(subscription_info=s,data=json.dumps({'title':title,'body':body},ensure_ascii=False),vapid_private_key=cfg['vapid_private_key'],vapid_claims={'sub':cfg['vapid_subject']},ttl=3600)
   messages.append({'delivered_to_gateway':True})
  except WebPushException as ex:messages.append({'delivered_to_gateway':False,'error':str(ex)[:150]})
 return {'status':'SENT_TO_GATEWAY' if any(x.get('delivered_to_gateway') for x in messages) else 'HOLD','sent':sum(bool(x.get('delivered_to_gateway')) for x in messages),'subscribers':len(messages),'browser_delivery_verified':False}

class TrainerLogWatcher(threading.Thread):
 daemon=True
 def __init__(self):super().__init__(name='NoxLocalTrainingNotificationWatcher');self.last='';self.running=True
 def run(self):
  while self.running:
   try:
    st=svc.training_status();sample=st.get('log',{}).get('last') if isinstance(st.get('log'),dict) else None
    # Notify only on confirmed completion marker; never guess completion from loss decrease
    if sample and isinstance(sample,dict) and 'train_runtime' in sample:
     marker=json.dumps(sample,sort_keys=True)
     if self.last and marker!=self.last:send('NOX обучение','Тренер записал итоговые метрики. Проверь checkpoints и качество.')
     self.last=marker
   except Exception:pass
   time.sleep(20)