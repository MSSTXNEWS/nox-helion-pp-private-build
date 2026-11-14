"""V132: safe Vast API route/auth-class discrimination, GET-only, no key leakage.

Only sends NOX2 to fixed official console.vast.ai HTTPS host, never follows
redirects, never prints provider response body, account/user ID or token.
"""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


URLS={
    "V1_WITH_SLASH": "https://console.vast.ai/api/v1/instances/?limit=25",
    "V1_NO_SLASH": "https://console.vast.ai/api/v1/instances?limit=25",
    "ACCOUNT_AUTH": "https://console.vast.ai/api/v0/users/current/",
}
_ERROR_CLASSES={"deprecated_endpoint","auth_error","not_found",
                "forbidden","invalid_args","rate_limit_exceeded","unauthorized"}
OPENER=urllib.request.build_opener(NoRedirects)


def read(label:str,url:str,key:str):
    request=urllib.request.Request(
        url,method="GET",headers={
            "Authorization":"Bearer "+key,"Accept":"application/json"})
    code=0
    body=b""
    try:
        with OPENER.open(request,timeout=16) as response:
            code=response.status
            body=response.read(60000)
    except urllib.error.HTTPError as exc:
        code=exc.code
        body=exc.read(4000)
    except (OSError,TimeoutError):
        return {"route":label,"http":0,"reason":"NETWORK_UNAVAILABLE",
                "endpoint_supported":False}
    err="NONE"
    count=None
    own=None
    if body:
        try:
            value=json.loads(body)
        except (ValueError,UnicodeError):
            value=None
        if isinstance(value,dict):
            raw=value.get("error")
            if isinstance(raw,str) and raw in _ERROR_CLASSES:
                err=raw
            else:
                reason=value.get("detail")
                if isinstance(reason,str) and reason in _ERROR_CLASSES:
                    err=reason
            if label.startswith("V1_") and code==200:
                records=value.get("instances",value.get("results"))
                if isinstance(records,list):
                    count=len(records)
                    own=any(isinstance(r,dict) and str(r.get("id"))=="60509551"
                            for r in records)
                elif isinstance(records,dict) and isinstance(records.get("instances"),list):
                    records=records["instances"]
                    count=len(records)
                    own=any(isinstance(r,dict) and str(r.get("id"))=="60509551"
                            for r in records)
    return {"route":label,"http":code,"provider_error_class":err,
            "instance_count":count,"target_present":own,
            "endpoint_supported":code in (200,400,401,403,429)}


def main():
    key=os.environ.get("NOX2","")
    if not key:
        print("NOX_V132=HOLD_NOX2_MISSING")
        return 2
    results=[read(label,url,key) for label,url in URLS.items()]
    status="AUTH_VERIFIED" if results[2]["http"]==200 else "AUTH_UNVERIFIED"
    record={"state":status,"checks":results,"key_exported":False,
            "body_exported":False,"ssh_attached":False,"billable_actions":0}
    print("NOX_V132_AUTH_READONLY="+json.dumps(
        record,sort_keys=True,separators=(",",":")))
    print("NOX_V132_READONLY_COMPLETE=true")
    return 0 if status=="AUTH_VERIFIED" else 2


if __name__=="__main__":
    raise SystemExit(main())
