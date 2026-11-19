"""NOX V117: complete existing owner-cookie opt-in Vikhr -> NOX -> S03 test.

Derives from the physically accepted V114 owner-cookie/dialog E2E without
changing installed servers, source, S03 schema or model weights. Every check
runs inside Vast; no password, cookie, private conversation or log text is
exported to GitHub. It adds one clearly synthetic owner QA turn to S03.
"""
from __future__ import annotations

import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
from nox_runpod.teacher_mesh.v114.owner_v29_dialog_acceptance import REMOTE as V114


def replace_exact(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError("HOLD_V114_BASELINE_SOURCE_DRIFT")
    return source.replace(old, new, 1)


def construct_remote() -> str:
    remote = V114
    remote = replace_exact(
        remote,
        "NATIVE_AUDIT_SCHEMA=NOX_V114_AUTH_NATIVE_WEB_DIALOG_S03_ONEHOST_V1",
        "NATIVE_AUDIT_SCHEMA=NOX_V117_AUTH_TEACHER_MAIN_S03_E2E_V1",
    )
    remote = replace_exact(
        remote,
        "NATIVE_V114_RESULT=", "NATIVE_V117_RESULT=",
    )
    # The existing V51 SSH transport forwards only native stdout lines
    # strictly shorter than 800 bytes. Emit a minimal, independently useful
    # receipt instead of the large V114 diagnostic object.
    remote = replace_exact(
        remote,
        "def emit(**obj):print('NATIVE_V117_RESULT='+json.dumps(obj,sort_keys=True,separators=(',',':')))",
        """def emit(**obj):
 keys=('state','teacher_hint_marker_seen','teacher_optin_exact',
       'live_s03_committed','native_dialog_history_readback','dialog_list_readback',
       'first_delta_ms','total_ms','model_weights_changed','user_private_data_exported')
 compact={key:obj[key] for key in keys if key in obj}
 print('NATIVE_V117_RESULT='+json.dumps(compact,sort_keys=True,separators=(',',':')))""",
    )
    remote = replace_exact(
        remote,
        "NATIVE_V114_HTTP=", "NATIVE_V117_HTTP=",
    )
    remote = replace_exact(
        remote,
        " print('NATIVE_V114_COOKIE_META='+json.dumps([{'name':c.name,'path':c.path} for c in jar]))",
        " print('NATIVE_V117_COOKIE_PRESENT=true')",
    )
    remote = replace_exact(
        remote,
        " prompt='[QA '+marker+'] Сколько будет 17 умножить на 19? Ответь только числом.'",
        " prompt='@учитель: 17*19'",
    )
    # Grant a *bounded* idle window for the current owner session. No stream,
    # slot, service or GPU process is cancelled or restarted; STOP still wins.
    remote = replace_exact(
        remote,
        """ with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as response:
  slots=json.loads(response.read(30000))
 if not isinstance(slots,list) or len(slots)!=6 or any(
   r.get('is_processing',r.get('processing',False)) for r in slots if isinstance(r,dict)):
  raise RuntimeError('HOLD_ONEHOST_BUSY')""",
        """ idle=False
 for idle_attempt in range(5):
  if stop():raise RuntimeError('HOLD_STOP_WHILE_WAITING_FOR_IDLE')
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as response:
   slots=json.loads(response.read(30000))
  idle=(isinstance(slots,list) and len(slots)==6 and all(
   isinstance(r,dict) and (r.get('is_processing') if 'is_processing' in r
                           else r.get('processing')) is False for r in slots))
  if idle:break
  if idle_attempt!=4:time.sleep(3)
 if not idle:raise RuntimeError('HOLD_ONEHOST_BUSY')""",
    )
    # The exact owner teacher hook logs this one marker only when its verified
    # native teacher evidence was actually injected for the model answer.
    remote = replace_exact(
        remote,
        " if stop():raise RuntimeError('HOLD_STOP_BEFORE_MODEL')\n start=time.monotonic()",
        """ if stop():raise RuntimeError('HOLD_STOP_BEFORE_MODEL')
 teacher_log=Path(chat_proxy.LOGS)/'proxy.log'
 if not teacher_log.is_file() or teacher_log.is_symlink():
  raise RuntimeError('HOLD_TEACHER_AUDIT_LOG_NOT_FOUND')
 log_start=teacher_log.stat().st_size
 start=time.monotonic()""",
    )
    remote = replace_exact(
        remote,
        " emit(state='V114_FULL_AUTH_OWNER_WEB_DIALOG_S03_STREAM_PASS',",
        """ # Teacher was only admitted for the exact public opt-in request, and this
 # postflight marker is read only for bytes appended after our preflight.
 if not teacher_log.is_file() or teacher_log.stat().st_size < log_start:
  raise RuntimeError('HOLD_TEACHER_AUDIT_LOG_ROTATED')
 with teacher_log.open('rb') as log_stream:
  log_stream.seek(log_start)
  log_tail=log_stream.read(128000)
 if b'nox_v113_verified_local_teacher_hint_applied=1' not in log_tail:
  raise RuntimeError('HOLD_NATIVE_TEACHER_HINT_NOT_OBSERVED')
 emit(state='V117_OWNER_OPTIN_TEACHER_NOX_S03_PASS',
   teacher_hint_marker_seen=True,teacher_optin_exact=True,""",
    )
    remote = replace_exact(
        remote,
        "NATIVE_V114_AUTH_FULL_E2E_ACCEPTED=true",
        "NATIVE_V117_TEACHER_S03_E2E_ACCEPTED=true",
    )
    remote = replace_exact(
        remote,
        "NATIVE_V114_PRIVATE_OWNER_AUTH_EXPORTED=false",
        "NATIVE_V117_PRIVATE_OWNER_AUTH_EXPORTED=false",
    )
    # Parse embedded python without executing anything until the existing
    # V51 authenticated, temporary-key owner SSH transport approves it.
    py=remote.split(" - <<'PYREMOTE'\n",1)[1].rsplit("\nPYREMOTE",1)[0]
    compile(py,"<NOX-V117-existing-owner>", "exec")
    return remote


REMOTE=construct_remote()


def main():
    ssh.REMOTE=REMOTE
    old=ssh.api

    def settled(method,path,key,data=None):
        for attempt in range(4):
            try:
                value=old(method,path,key,data)
                if method=="POST" and path.endswith("/ssh/"):
                    time.sleep(12)
                return value
            except RuntimeError as exc:
                if (method!="GET" or str(exc)!="HOLD_VAST_API_HTTP_429"
                        or attempt==3):
                    raise
                time.sleep((10,20,40)[attempt])
    ssh.api=settled
    captured=io.StringIO()
    completed=False
    try:
        with contextlib.redirect_stdout(captured):
            completed=ssh.probe()
    except Exception as exc:
        desc=str(exc)
        print("NOX_V117_HOLD="+(desc if desc.startswith("HOLD_") and len(desc)<90
                               else "HOLD_NATIVE_CONNECTION"))
    finally:
        try:
            with contextlib.redirect_stdout(captured):
                if ssh.cleanup() is not True:
                    completed=False
        except Exception:
            completed=False
    statuses=[]
    key_revoked=False
    seen_success=False
    for line in captured.getvalue().splitlines():
        if line.startswith("NATIVE_V117_RESULT=") and len(line)<2000:
            statuses.append(line)
            print(line)
        elif line.startswith("NATIVE_V117_TEACHER_S03_E2E_ACCEPTED="):
            print(line)
            seen_success=(line=="NATIVE_V117_TEACHER_S03_E2E_ACCEPTED=true")
        elif line.startswith("TEMP_SSH_CLEANUP="):
            print(line[:120])
            key_revoked=key_revoked or line.endswith("DETACHED_AND_VERIFIED")
    passed=bool(completed and key_revoked and seen_success
                and len(statuses)==1
                and '"state":"V117_OWNER_OPTIN_TEACHER_NOX_S03_PASS"' in statuses[0])
    print("NOX_V117_OWNER_TEACHER_S03_E2E="+("PASS" if passed else "HOLD"))
    return 0 if passed else 2


if __name__=="__main__":
    raise SystemExit(main())
