#!/usr/bin/env python3
"""NOX queued commands: strict allowlist and local-only authenticated host integration.

This is a library for the existing NOX HTTP server to invoke. It does not
listen on a new port, execute a shell string, write GitHub, or change training
weights. Caller MUST authenticate/authorize its user session before import.
"""
from __future__ import annotations
import datetime, fcntl, json, os, pathlib, subprocess, uuid

ROOT=pathlib.Path("/workspace/nox")
STATE=ROOT/"dispatcher/nox_v3"
ALLOWED={
  "A40":{"status","gpu","pause_after_save","resume_if_safe","sync_request"},
  "A5000":{"status","gpu","pause_after_save","resume_if_safe","sync_request"},
}
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def atomic(path,doc):
 path.parent.mkdir(parents=True,exist_ok=True)
 t=path.with_suffix(".new")
 with t.open("w",encoding="utf-8") as f:
  json.dump(doc,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(t,path)
def validate(req):
 if not isinstance(req,dict):raise ValueError("INVALID_COMMAND")
 node=req.get("node");action=req.get("action")
 if node not in ALLOWED or action not in ALLOWED[node]:raise ValueError("COMMAND_NOT_ALLOWED")
 return node,action
def enqueue(req,actor,has_privileged_permission=False):
 """Call ONLY from an authenticated existing NOX application route."""
 if not actor or not isinstance(actor,str) or len(actor)>128:raise ValueError("AUTHENTICATED_ACTOR_REQUIRED")
 node,action=validate(req)
 if action in {"pause_after_save","resume_if_safe"} and not has_privileged_permission:
  raise PermissionError("OWNER_APPROVAL_REQUIRED")
 task={"id":str(uuid.uuid4()),"node":node,"action":action,"actor":actor,"created_utc":now(),
       "state":"QUEUED","source":"NOX_EXISTING_WEB","expires_utc":(
         datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=10)).isoformat()}
 d=STATE/"commands_inbox"/node
 d.mkdir(parents=True,exist_ok=True)
 atomic(d/(task["id"]+".json"),task)
 return {"id":task["id"],"state":"QUEUED","node":node,"action":action}
def status_snapshot(node):
 if node not in ALLOWED:raise ValueError("UNKNOWN_NODE")
 d=STATE/("orchestrator_status.json")
 s=STATE/("safe70_"+node+".json")
 c=STATE/("keeper_"+node+".json")
 def read(path):
  try:return json.loads(path.read_text(encoding="utf-8"))
  except (OSError,ValueError):return {}
 return {"node":node,"runtime":read(d),"safety":read(s),"controller":read(c)}
