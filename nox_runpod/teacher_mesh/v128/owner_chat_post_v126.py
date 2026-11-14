"""V128: rerun original V114 authenticated streaming/S03 E2E on exact current OneHost.

No new test backend, daemon, DB, trainer or weight change. This invokes original
V114 test, which appends one bounded synthetic owner QA dialog to original S03.
Source SHA pins prevent testing a different concurrently modified production.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v114 import owner_v29_dialog_acceptance as original

BRIDGE_BEFORE="BRIDGE_SHA='cc27928b38f9b86d2375de8092d09dbdc34f81c6e51e8a68d36041ee71529750'"
PROXY_BEFORE="PROXY_SHA='4d90215d7099344dd5aaed2412645b764baa0228acc0b0e153cfe425217591ad'"
BRIDGE_CURRENT="BRIDGE_SHA='2c714c7f952be64a2b278c993da9d59014a43a32075281b5aa755ada02c6fb8e'"
PROXY_CURRENT="PROXY_SHA='e79aa0747511cf010f79f72150fc4e64b36b9c9ccea3b09d788a6306c63c0c95'"

def prepare():
    remote=original.REMOTE
    if remote.count(BRIDGE_BEFORE)!=1 or remote.count(PROXY_BEFORE)!=1:
        raise RuntimeError('HOLD_V128_ORIGINAL_E2E_SOURCE_DRIFT')
    if any(x in remote for x in (BRIDGE_CURRENT,PROXY_CURRENT)):
        raise RuntimeError('HOLD_V128_ALREADY_REPINNED')
    updated=remote.replace(BRIDGE_BEFORE,BRIDGE_CURRENT,1).replace(PROXY_BEFORE,PROXY_CURRENT,1)
    assert updated.count(BRIDGE_CURRENT)==1 and updated.count(PROXY_CURRENT)==1
    script=updated.partition("<<'PYREMOTE'")[2].rpartition('PYREMOTE')[0]
    compile(script,'<V128 REUSED V114 AUTH E2E>','exec')
    return updated

def main():
    original.REMOTE=prepare()
    print('NOX_V128_REUSED_ORIGINAL_V114_E2E=true')
    return original.main()

if __name__=='__main__':
    raise SystemExit(main())
