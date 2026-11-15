"""Read only, owner-authenticated original V112/WEB/S03 health on OneHost.

Executes only inside the already owner-approved V51 pinned single SSH
session. No training, queue enqueue, S03 writes, STOP or service mutation.
A successful health result is NOT proof of S03 native registration receipts.
"""
from __future__ import annotations
import json

REMOTE = r"""
set -euo pipefail
if [ ! -x /root/nox/venv/bin/python ] || [ ! -f /root/nox/scripts/chat_proxy.py ]; then
  echo 'NATIVE_V112_OWNER_STATUS={"state":"HOLD_ORIGINAL_OWNER_RUNTIME_MISSING"}'
else
  cd /root/nox/scripts
  /root/nox/venv/bin/python - <<'PYREMOTE'
import http.cookiejar,json,sys,urllib.request,urllib.error
from pathlib import Path
def emit(state, **fields):
    row={"state":state,**fields}
    print("NATIVE_V112_OWNER_STATUS="+json.dumps(row,sort_keys=True,separators=(",",":")))
jar=http.cookiejar.CookieJar()
try:
    # Import the original deployed owner authentication code; no replacement app.
    sys.path.insert(0,"/root/nox/scripts")
    import chat_proxy
    secret=chat_proxy._read_chat_password()
    if not isinstance(secret,str) or len(secret)<6:
        raise RuntimeError("HOLD_OWNER_CREDENTIAL_NOT_AVAILABLE")
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def get(path):
        # All URLs are fixed to the original localhost owner service, no redirects.
        req=urllib.request.Request("http://127.0.0.1:8080"+path,method="GET")
        try:
            with opener.open(req,timeout=5) as r:
                raw=r.read(12001)
                if r.status!=200 or len(raw)>12000:
                    raise RuntimeError("HOLD_OWNER_GET_HTTP_OR_SIZE")
        except urllib.error.HTTPError:
            raise RuntimeError("HOLD_OWNER_ROUTE_UNAVAILABLE")
        try:value=json.loads(raw)
        except ValueError:raise RuntimeError("HOLD_OWNER_JSON")
        if not isinstance(value,dict):raise RuntimeError("HOLD_OWNER_SCHEMA")
        return value
    login=urllib.request.Request("http://127.0.0.1:8080/chat/login",
          data=json.dumps({"password":secret}).encode(),
          headers={"Content-Type":"application/json"},method="POST")
    secret=None
    # Official login only grants an ephemeral read-only session cookie.
    try:
        with opener.open(login,timeout=5) as r:
            if r.status!=200 or len(r.read(2001))>2000:
                raise RuntimeError("HOLD_OWNER_LOGIN")
    except urllib.error.HTTPError:
        raise RuntimeError("HOLD_OWNER_LOGIN")
    if not list(jar):raise RuntimeError("HOLD_OWNER_COOKIE_ABSENT")
    session=get("/chat/session")
    if session.get("ok") is not True:
        raise RuntimeError("HOLD_OWNER_SESSION_NOT_VERIFIED")
    status=get("/api/nox/status")
    memory=get("/api/ui/memory/dialogs/status")
    ok=(status.get("backend")=="EXISTING_NATIVE_ONEHOST"
        and status.get("native_p02_bound") is True
        and status.get("native_cognitive_memory_bound") is True
        and status.get("native_dialogs_ready") is True
        and memory.get("status")=="READY"
        and memory.get("persistent_threads") is True
        and memory.get("backing_store")=="EXISTING_S03_SQLITE")
    emit("AUTH_OWNER_S03_STATUS_READY" if ok else "HOLD_ORIGINAL_OWNER_S03_NOT_READY",
         native_p02_bound=status.get("native_p02_bound") is True,
         original_s03_schema_ready=status.get("native_cognitive_memory_bound") is True,
         original_dialogs_ready=status.get("native_dialogs_ready") is True,
         original_s03_backing_store=memory.get("backing_store")=="EXISTING_S03_SQLITE",
         native_queue_jobs_verified=False,
         signed_s03_task_receipts_verified=False)
except Exception as exc:
    reason=str(exc)
    allowed=("HOLD_ORIGINAL_OWNER_S03_NOT_READY","HOLD_OWNER_CREDENTIAL_NOT_AVAILABLE",
             "HOLD_OWNER_LOGIN","HOLD_OWNER_COOKIE_ABSENT",
             "HOLD_OWNER_SESSION_NOT_VERIFIED","HOLD_OWNER_ROUTE_UNAVAILABLE",
             "HOLD_OWNER_GET_HTTP_OR_SIZE","HOLD_OWNER_JSON","HOLD_OWNER_SCHEMA")
    emit(reason if reason in allowed else "HOLD_ORIGINAL_OWNER_STATUS_EXCEPTION")
finally:
    jar.clear()
PYREMOTE
fi
"""

def native_status_evidence(rows):
    """A fresh authenticated status proves only original WEB/S03 readiness.

    No native queue ID or signed S03 registration event can be inferred.
    """
    found=[]
    for item in rows:
        if item.startswith("NATIVE_V112_OWNER_STATUS="):
            try:
                record=json.loads(item.split("=",1)[1])
            except (ValueError,TypeError):
                return False
            found.append(record)
    if len(found)!=1 or not isinstance(found[0],dict):
        return False
    row=found[0]
    return (row.get("state")=="AUTH_OWNER_S03_STATUS_READY"
            and row.get("native_p02_bound") is True
            and row.get("original_s03_schema_ready") is True
            and row.get("original_dialogs_ready") is True
            and row.get("original_s03_backing_store") is True
            and row.get("native_queue_jobs_verified") is False
            and row.get("signed_s03_task_receipts_verified") is False)
