#!/usr/bin/env python3
"""Bounded, strictly read-only R5/R6.2 web preflight on the existing NOX site.

No browser/network, model request, credentials or native service change. An R6.2
archive is NOT considered installed just because a corresponding Drive ZIP exists.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import stat
import time

ROOT=Path("/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site")
SOURCE={
  "pc/pages/cinema/index.html":"3522533b08da046d732fd2317299d757d255ed31b5d1c984acdab4985605613c",
  "pc/pages/games/index.html":"1e51ad6eed10136922cea1a2f0380b61caef11a2fb4e5e422f8785cbc2eaff2a",
  "pc/pages/graph/index.html":"1deb4365f105c41e9ed04ec96d5b3233bfeacc43f8d686e87b17e5b22c8c1c9e",
  "pc/pages/music/index.html":"462b289417f75164bd651aae8cbe398b75202ae61821ee791f679346763182ca",
  "pc/pages/voice/index.html":"3eeeb035ce0518fb5913281f0671734588dc9231223b049baa4f11079ae5ed39",
  "pc/v24/nox-v24-menu.js":"4a0c2b5b066f21781716287aefe06b6c896e9b282c29aafd9204f0a7852da8c7",
  "pc/v24/nox-v24-chat.js":"3427be9e0a497ad0dd120daaa5007f0daa32f3c97271a10ee3b5f1567abcdd8a",
  "nox-select-tiles-v5.js":"09fdbb663407740ff991024229dff208dc84775583bae34ecf87f7670b367360",
  "nox-select-tiles-v5.css":"af30985234d6a35e58521f69bb771399294efcfe4266a5e9b391a48139692010",
  "nox-selection-corrective-v7.css":"0921f58966dc52d8c9aceaf4bb3a35c508ce22ec0d8d9e18f013cfe4b6dacdd7",
}
R62={
  "pc/v24/nox-v24-menu.js":"f1474b19c148e6e42d0a7b4f1e380a9a333317417df0d93a79ffe9627edcf9b2",
  "pc/v24/nox-v24-chat.js":"459a437b2111ce3d823afb1d4cf014869ac8dfe4da4c7b5888df7169d67ad02f",
}
LIVE={
  "pc/v24/nox-v24-chat.js":"55e4445443cd0d4cfa4d2a8775dcd8c7689890daad492b58e01c298691ac7e20"
}
MAX=256*1024

def checksum(relative):
    if relative not in SOURCE or ".." in relative.split("/"):
        return {"state":"SCOPE_HOLD"}
    parent=os.open("/",os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    fd=None
    try:
        for part in (ROOT/relative).parts[1:-1]:
            nextfd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
            os.close(parent);parent=nextfd
        fd=os.open(Path(relative).name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=parent)
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size<0 or before.st_size>MAX:
            return {"state":"FILE_SCOPE_HOLD"}
        raw=bytearray()
        while len(raw)<=MAX:
            block=os.read(fd,min(65536,MAX+1-len(raw)))
            if not block:break
            raw.extend(block)
        after=os.fstat(fd)
        if len(raw)!=before.st_size or (before.st_dev,before.st_ino,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_mtime_ns,after.st_ctime_ns):
            return {"state":"CHANGED_DURING_READ"}
        value=hashlib.sha256(raw).hexdigest()
        labels=[tag for tag,pin in (("R5_BASE",SOURCE[relative]),("R62_OFFLINE",R62.get(relative)),("V6_LIVE",LIVE.get(relative))) if value==pin]
        return {"state":"KNOWN" if labels else "UNRECOGNIZED", "version":labels,
                "sha256":value,"bytes":len(raw)}
    except FileNotFoundError:
        return {"state":"MISSING"}
    except (OSError,ValueError) as err:
        return {"state":type(err).__name__}
    finally:
        if fd is not None:os.close(fd)
        os.close(parent)

def main():
    rows={path:checksum(path) for path in SOURCE}
    result={
      "schema":"NOX_WEB_R62_OWNER_PREFLIGHT_V1", "state":"READ_ONLY",
      "instance_id":60509551,"source":"R5_DRIVE_1Xr-99ipCUZyYvlxzBtO1EFiSMqHeuSKV",
      "target_site":str(ROOT),"native_writes":0,"service_restarts":0,
      "credentials_accessed":False,"contents_exported":False,
      "observed_at":time.time(),"files":rows,
      "all_navigable_pages_match_r5":all(rows[p].get("version")==["R5_BASE"] for p in SOURCE if "/pages/" in p),
      "unrecognized_count":sum(r["state"]=="UNRECOGNIZED" for r in rows.values())
    }
    print("NOX_MAINT_WEB_R62_PREFLIGHT="+json.dumps(result,separators=(",",":"),sort_keys=True,allow_nan=False),flush=True)
    print("NOX_MAINT_INSPECT_COMPLETE=true",flush=True)
    return 0

if __name__=="__main__":raise SystemExit(main())
