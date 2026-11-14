"""V125 independent postdeploy V114 synthetic owner SSE→S03 E2E.

Uses the already accepted V114 script, changing only the TWO observed live
SHA preimage values in memory. No production code or owner secrets are changed.
"""
from __future__ import annotations
import ast
from nox_runpod.teacher_mesh.v114 import owner_v29_dialog_acceptance as v114

OLD_PX="PROXY_SHA='4d90215d7099344dd5aaed2412645b764baa0228acc0b0e153cfe425217591ad'"
NEW_PX="PROXY_SHA='e79aa0747511cf010f79f72150fc4e64b36b9c9ccea3b09d788a6306c63c0c95'"
OLD_BR="BRIDGE_SHA='cc27928b38f9b86d2375de8092d09dbdc34f81c6e51e8a68d36041ee71529750'"
NEW_BR="BRIDGE_SHA='2c714c7f952be64a2b278c993da9d59014a43a32075281b5aa755ada02c6fb8e'"

def main():
    remote=v114.REMOTE
    for old,new in ((OLD_PX,NEW_PX),(OLD_BR,NEW_BR)):
        if remote.count(old)!=1:
            raise RuntimeError('HOLD_OWNER_E2E_SOURCE_ANCHOR')
        remote=remote.replace(old,new,1)
    source=remote.split("<<'PYREMOTE'\n",1)[1].rsplit('\nPYREMOTE',1)[0]
    ast.parse(source)
    if 'HOLD_FULL_S03_DIALOG_STREAM_RECEIPT' not in source:
        raise RuntimeError('HOLD_DURABLE_S03_PROOF')
    v114.REMOTE=remote
    return v114.main()

if __name__=='__main__':
    raise SystemExit(main())
