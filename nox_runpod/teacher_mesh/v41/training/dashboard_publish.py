"""Evidence-only publication to the EXISTING NOX V29.3 web assets.

Called by the already installed OneHost trusted scheduler, not by browser/chat.
A completed signed native receipt is required every time data is published.
"""
from __future__ import annotations
from collections.abc import Callable, Mapping
from pathlib import Path
import json, os, tempfile
from .native_receipt_export import verified_dashboard

FILENAME='nox-learning-3axes-dashboard.json'

def publish_from_native(receipts:Callable[[],Mapping],verify:Callable[[Mapping],bool],
                        native_authorize:Callable[[],bool],native_stop:Callable[[],bool],
                        *,existing_web_root:str|Path)->dict:
    if not all(callable(x) for x in (receipts,verify,native_authorize,native_stop)):
        return {'state':'HOLD_HOST_CALLBACK_MISSING','written':False}
    try:
        if native_stop() is not False or native_authorize() is not True:
            return {'state':'HOLD_STOP_OR_OWNER','written':False}
        webroot=Path(existing_web_root).resolve()
        # Must already exist on the host: no new app/backend creation.
        current=webroot/FILENAME
        if not webroot.is_dir() or not current.is_file() or current.is_symlink():
            return {'state':'HOLD_WEB_TARGET_NOT_VERIFIED','written':False}
        out=verified_dashboard(receipts,verify)
        if out['state']!='NATIVE_SOURCE_VERIFIED':
            return {'state':out['state'],'written':False}
        body=(json.dumps(out['dashboard'],ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
        if len(body)>1024*1024:return {'state':'HOLD_DASHBOARD_SIZE','written':False}
        if native_stop() is not False or native_authorize() is not True:
            return {'state':'HOLD_SCOPE_CHANGED','written':False}
        fd,tmp=tempfile.mkstemp(dir=str(webroot),prefix='.nox-learning-',suffix='.tmp')
        try:
            with os.fdopen(fd,'wb') as f:
                f.write(body);f.flush();os.fsync(f.fileno())
            os.replace(tmp,current)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        if current.read_bytes()!=body:return {'state':'HOLD_NATIVE_READBACK','written':True}
        return {'state':'PUBLISHED_VERIFIED_NATIVE_RECEIPTS','written':True,
                'axes_states':{k:v['state'] for k,v in out['dashboard']['axes'].items()},
                'overall_state':out['dashboard']['overall']['state']}
    except Exception:
        return {'state':'HOLD_NATIVE_PUBLISH_ERROR','written':False}
