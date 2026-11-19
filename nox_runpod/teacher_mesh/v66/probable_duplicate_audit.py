"""Reuse V62 tiny block reads to identify *probable* duplicate weights.

Never performs full hash, never deletes files, never exposes private paths.
Marked as probable only: no unsafe deletion decisions from fingerprints.
"""
from __future__ import annotations
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
from nox_runpod.teacher_mesh.v62 import dedup_fingerprint as existing
_old_api=ssh.api
def _delayed_api(method,path,key,data=None):
    receipt=_old_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(15)
    return receipt

def main()->int:
    ssh.REMOTE=existing.REMOTE
    ssh.api=_delayed_api
    ok=False
    try:ok=ssh.probe()
    except Exception as e:
        s=str(e)
        print("NOX_V66_FINGERPRINT="+s if s.startswith("HOLD_") and len(s)<100 else "NOX_V66_FINGERPRINT=HOLD_NATIVE")
    finally:
        try:
            if not ssh.cleanup():ok=False
        except Exception:
            print("NOX_V66_FINGERPRINT=HOLD_KEY_CLEANUP")
            ok=False
    return 0 if ok else 2

if __name__=="__main__":raise SystemExit(main())
