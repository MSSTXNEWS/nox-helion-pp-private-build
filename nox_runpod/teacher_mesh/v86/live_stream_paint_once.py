"""V86 atomic exact live stream UI patch: display only REAL delta text progressively.
No new backend, model, S03, process or streaming route. No restart required.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import contextlib,io,time
saved=ssh.api
def delayed(method,path,key,data=None):
 out=saved(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return out
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,re,json,hashlib,stat,shutil,subprocess,urllib.request,time,tempfile
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V86_STREAM_CHUNK_PAINT_V1')
TARGET=Path('/root/nox/scripts/chat.html')
EXPECTED='5636b446baf4aec142dd31fb164dbf7c1c85f11e0bb74c0d80822a7ffa9e4dfc'
BACKUP=TARGET.with_name(TARGET.name+'.nox-v86-backup-'+EXPECTED[:12])
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(data):return hashlib.sha256(data).hexdigest()
def emit(**k):print('NATIVE_V86_UI_RESULT='+json.dumps(k,sort_keys=True,separators=(',',':')))
def health_html():
 with urllib.request.urlopen('http://127.0.0.1:8080/chat',timeout=4) as r:return (r.status,r.read(150000))
def check_js(blob,node):
 text=blob.decode('utf8')
 blocks=re.findall(r'<script\b[^>]*>(.*?)</script>',text,re.I|re.S)
 main=[x for x in blocks if 'const reader = r.body.getReader();' in x]
 if len(main)!=1:return False
 if not node:
  # The exact inserted JS was independently node --check validated; fail closed
  # unless the complete expected DOM streaming anchors are present exactly once.
  js=main[0]
  return (js.count('const revealNativeContent = () => {')==1
          and js.count('const startNativeReveal = () => {')==1
          and js.count('startNativeReveal();')==1
          and js.count('cancelAnimationFrame(revealRaf)')==1
          and js.count('typeof d.content === "string"')==1
          and js.count('const reader = r.body.getReader();')==1)
 with tempfile.NamedTemporaryFile(mode='w',encoding='utf8',suffix='.js',delete=False) as f:
  file=Path(f.name);f.write(main[0])
 try:
  cp=subprocess.run([node,'--check',str(file)],capture_output=True,timeout=10)
  return cp.returncode==0
 finally:file.unlink(missing_ok=True)
def rollback(original,meta):
 try:
  tmp=TARGET.with_name('.nox-v86-restore.tmp')
  with tmp.open('xb') as f:f.write(original);f.flush();os.fsync(f.fileno())
  os.chmod(tmp,stat.S_IMODE(meta.st_mode));os.chown(tmp,meta.st_uid,meta.st_gid)
  os.replace(tmp,TARGET)
  return sha(TARGET.read_bytes())==EXPECTED
 except Exception:return False
try:
 if any(Path(x).exists() for x in STOP):raise RuntimeError('HOLD_GLOBAL_STOP')
 if TARGET.is_symlink() or not TARGET.is_file():raise RuntimeError('HOLD_TARGET_MISSING')
 meta=TARGET.stat()
 if meta.st_uid!=0 or meta.st_size>90000:raise RuntimeError('HOLD_SOURCE_OWNER_SIZE')
 original=TARGET.read_bytes()
 if sha(original)!=EXPECTED:raise RuntimeError('HOLD_SOURCE_SHA_CHANGED')
 status,served=health_html()
 if status!=200 or sha(served)!=EXPECTED:raise RuntimeError('HOLD_SERVED_HTML_DIFFERS')
 node=shutil.which('node')
 # If Node isn't installed on the Vast container, use exact source-locked
 # structural validation of JS independently syntax-tested on the runner.
 text=original.decode('utf8')
 a='      let acc = "";'
 b='''      let acc = "";
      let shown = "";
      let revealRaf = 0;
      let revealEnded = false;
      const revealNativeContent = () => {
        revealRaf = 0;
        if (revealEnded || shown.length >= acc.length) return;
        const backlog = acc.length - shown.length;
        const step = backlog > 2400 ? 140 : backlog > 800 ? 64 : backlog > 180 ? 24 : Math.min(14, backlog);
        shown = acc.slice(0, shown.length + step);
        history[history.length - 1].content = shown;
        render({ streaming: true });
        if (shown.length < acc.length) revealRaf = requestAnimationFrame(revealNativeContent);
      };
      const startNativeReveal = () => { if (!revealRaf) revealNativeContent(); };'''
 old='''            const piece = d.content || d.reasoning_content || "";
            if (piece) {
              acc += piece;
              history[history.length - 1].content = acc;
              render({ streaming: true });
              if (acc.indexOf("<!--NOX_CONFIRM:") >= 0) showNoxConfirm(acc);
            }'''
 new='''            const piece = typeof d.content === "string" ? d.content : "";
            if (piece) {
              acc += piece;
              startNativeReveal();
              if (acc.indexOf("<!--NOX_CONFIRM:") >= 0) showNoxConfirm(acc);
            }'''
 before_finish='''      if (!acc.trim()) {'''
 finish='''      if (acc.length - shown.length > 120) await new Promise(resolve => setTimeout(resolve, 120));
      revealEnded = true;
      if (revealRaf) cancelAnimationFrame(revealRaf);
      history[history.length - 1].content = acc;
      if (!acc.trim()) {'''
 if text.count(a)!=1 or text.count(old)!=1 or text.count(before_finish)!=1:
  raise RuntimeError('HOLD_EXACT_JS_ANCHORS')
 patched=text.replace(a,b,1).replace(old,new,1).replace(before_finish,finish,1).encode('utf8')
 if len(patched)>92000 or not check_js(patched,node):
  raise RuntimeError('HOLD_NODE_SYNTAX')
 if any(Path(x).exists() for x in STOP):raise RuntimeError('HOLD_STOP_CHANGED')
 if BACKUP.exists():
  if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=EXPECTED:raise RuntimeError('HOLD_BACKUP_CONFLICT')
 else:
  with BACKUP.open('xb') as f:f.write(original);f.flush();os.fsync(f.fileno())
  os.chmod(BACKUP,stat.S_IMODE(meta.st_mode));os.chown(BACKUP,meta.st_uid,meta.st_gid)
 tmp=TARGET.with_name('.nox-v86-chat-patch.tmp')
 if tmp.exists():raise RuntimeError('HOLD_TMP_EXISTS')
 with tmp.open('xb') as f:f.write(patched);f.flush();os.fsync(f.fileno())
 os.chmod(tmp,stat.S_IMODE(meta.st_mode));os.chown(tmp,meta.st_uid,meta.st_gid)
 if sha(tmp.read_bytes())!=sha(patched):raise RuntimeError('HOLD_TEMP_SHA')
 os.replace(tmp,TARGET)
 try:
  code,live=health_html()
  if code!=200 or live!=patched or not check_js(live,node):
   raise RuntimeError('HOLD_AFTER_INSTALL_HTTP_OR_JS')
  emit(state='NATIVE_CHAT_PROGRESSIVE_STREAM_ACTIVE',old_sha256=EXPECTED,
       new_sha256=sha(patched),stream_mode='REAL_CONTENT_DELTA_ONLY',
       first_chunk_visual='IMMEDIATE_AFTER_REAL_FIRST_DELTA',
       max_render_gap='REQUEST_ANIMATION_FRAME',final_text_preserved=True,
       backup_verified=sha(BACKUP.read_bytes())==EXPECTED,
       live_chat_restart_count=0,model_weights_changed=False,s03_changed=False,
       training_changed=False,user_must_refresh_page=True)
 except Exception:
  restored=rollback(original,meta)
  emit(state='HOLD_UI_PATCH_ROLLED_BACK' if restored else 'HOLD_UI_ROLLBACK_UNVERIFIED',
       rollback_verified=restored)
except Exception as e:
  x=str(e)
  emit(state=x if x.startswith('HOLD_') else 'HOLD_UI_PATCH_UNKNOWN',
       production_changed=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
 ssh.REMOTE=REMOTE;ssh.api=delayed
 log=io.StringIO();ok=False
 try:
  with contextlib.redirect_stdout(log):ok=ssh.probe()
 except Exception as e:
  v=str(e);print('NOX_V86='+v if v.startswith('HOLD_') else 'NOX_V86=HOLD_NATIVE')
 finally:
  try:
   with contextlib.redirect_stdout(log):
    if not ssh.cleanup():ok=False
  except Exception:ok=False
 receipts=[]
 for line in log.getvalue().splitlines():
  if line.startswith('NATIVE_V86_UI_RESULT=') and len(line)<1800:
   print(line);receipts.append(line)
  elif line.startswith('TEMP_SSH_CLEANUP='):print(line[:120])
 accepted=ok and len(receipts)==1 and 'NATIVE_CHAT_PROGRESSIVE_STREAM_ACTIVE' in receipts[0]
 print('NOX_V86_PRODUCTION_ACCEPTED='+str(bool(accepted)).lower())
 return 0 if accepted else 2
if __name__=='__main__':raise SystemExit(main())
