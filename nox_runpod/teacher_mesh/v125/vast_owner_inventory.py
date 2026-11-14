"""Vast.ai owner instance inventory via current read-only v1 API.

Never creates, starts, stops, replaces or changes an instance. Never exports
NOX2 or any other instance IDs; reports only whether the expected existing NOX
OneHost is present and its provider-reported status.
"""
from __future__ import annotations
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

EXPECTED=60509551
BASES=(
    "https://console.vast.ai/api/v1/instances",
    "https://console.vast.ai/api/v1/instances/",
    "https://cloud.vast.ai/api/v1/instances/",
    "https://cloud.vast.ai/api/v1/instances",
)

def fetch(page: str, token: str) -> tuple[int, dict]:
    query={"limit":"25"}
    if page: query["after_token"]=page
    for base in BASES:
        url=base+"?"+urllib.parse.urlencode(query)
        request=urllib.request.Request(url,headers={
            "Authorization":"Bearer "+token,
            "Accept":"application/json"},method="GET")
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request,timeout=20) as resp:
                    body=resp.read(350000)
                    return resp.status,json.loads(body)
            except urllib.error.HTTPError as exc:
                if exc.code==429 and attempt<2:
                    time.sleep((8,18)[attempt])
                    continue
                if exc.code==404:
                    break  # Only alternate official Vast.ai URL path/origin.
                return exc.code,{}
            except (TimeoutError,urllib.error.URLError,ValueError,OSError):
                return 0,{}
    return 404,{}

def main() -> int:
    key=os.environ.get("NOX2","")
    if not key:
        print('NOX_VAST_V1_OWNER_INVENTORY={"state":"HOLD_NOX2"}')
        return 2
    total=0
    target=None
    cursor=""
    complete=False
    visited=set()
    for index in range(5):
        code,body=fetch(cursor,key)
        if code!=200 or not isinstance(body,dict):
            print("NOX_VAST_V1_OWNER_INVENTORY="+json.dumps({
                "state":"HOLD_PROVIDER_LIST_HTTP","http":code,
                "no_instances_mutated":True,"credentials_exported":False},
                separators=(',',':')))
            return 2
        instances=body.get("instances",body.get("data"))
        if isinstance(instances,dict):
            values=list(instances.values())
        elif isinstance(instances,list):
            values=instances
        else:
            print('NOX_VAST_V1_OWNER_INVENTORY={"state":"HOLD_RESPONSE_SCHEMA","no_instances_mutated":true}')
            return 2
        total+=len(values)
        for obj in values:
            if not isinstance(obj,dict):continue
            try:instance_id=int(obj.get("id",-1))
            except (TypeError,ValueError):continue
            if instance_id==EXPECTED:
                target=obj
        next_token=body.get("next_token")
        if not isinstance(next_token,str) or not next_token:
            complete=True
            break
        if next_token in visited:
            break
        visited.add(next_token)
        cursor=next_token
    status=None
    gpus=None
    if target is not None:
        raw=str(target.get("actual_status","")).lower()
        status=raw if re.fullmatch(r'[a-z_]{1,35}',raw) else "UNKNOWN"
        try:gpus=int(target.get("num_gpus"))
        except (TypeError,ValueError):pass
    print("NOX_VAST_V1_OWNER_INVENTORY="+json.dumps({
        "state":"VAST_V1_OWNER_LIST_READ_ONLY",
        "owner_instances_count":total,
        "complete_pagination":complete,
        "expected_existing_nox_found":target is not None,
        "expected_nox_status":status,
        "expected_nox_gpus":gpus,
        "no_instances_mutated":True,
        "credentials_exported":False,
    },sort_keys=True,separators=(',',':')))
    return 0 if complete else 2

if __name__=="__main__":
    raise SystemExit(main())
