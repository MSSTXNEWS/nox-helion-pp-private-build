#!/usr/bin/env python3
"""Exact static report-panel state fix; no service, model or trainer restart."""
import base64
from contextlib import ExitStack
import hashlib
import json
import os
import re
import time
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
COMPOSER_SHA='2063208d885654244f54a33f75d60be2169df763bf1bf027505b57c915c5b930'
OLD_JS='dcb413249a8bc99b6acf5d701047fe44ee7a3d65f8c1efe7f7e108a981f9e043'
NEW_JS='62ad2c08382ee6ef6cec3c8eb0ba4598c4c09037f442ce83a04c0344d686525a'
PREVIOUS_REQUEST='6905356266'
PREVIOUS_SOURCE='bdee1d39248833d9119045ea157fd298d7d9aa77'


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe(exc):
    value=str(exc)
    return value if re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+',value) else 'HOLD_REPORTS_'+type(exc).__name__.upper()


def primitives():
    raw=base64.b64decode(BUNDLE.get('owner_chat_composer_entry.py',''),validate=True)
    if not raw or len(raw)>100000 or digest(raw)!=COMPOSER_SHA:fail('HOLD_REPORTS_PRIMITIVES_PIN')
    module=types.ModuleType('reviewed_composer')
    exec(compile(raw,'<reviewed-composer-primitives>','exec'),module.__dict__)
    module.BUNDLE=BUNDLE;module.OLD_JS=OLD_JS;module.NEW_JS=NEW_JS
    return module


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not re.fullmatch('[0-9]{1,24}',request) or not re.fullmatch('[a-f0-9]{40}',source):
        fail('HOLD_REPORTS_OWNER_CONTEXT')
    core=primitives();deploy,evidence,helper=core.dependencies()
    path,old,new=core.sources(deploy)
    prior=json.loads(deploy.read(deploy.STATE/('owner_chat_composer_'+PREVIOUS_REQUEST+'.json')))
    if (prior.get('schema')!='NOX_OWNER_CHAT_COMPOSER_DEPLOY_V1'
            or prior.get('request')!=PREVIOUS_REQUEST or prior.get('source_sha')!=PREVIOUS_SOURCE
            or prior.get('state')!='BOUNDED_REPORTS_SOURCE_AND_HTTP_VERIFIED_BROWSER_PENDING'
            or prior.get('installed_js_sha256')!=OLD_JS or prior.get('preservation_verified') is not True
            or prior.get('rollback') is not False):fail('HOLD_REPORTS_PREVIOUS_ACCEPTANCE')
    receipt=deploy.plain(deploy.STATE/('owner_chat_reports_state_'+request+'.json'))
    if receipt.exists():fail('HOLD_REPORTS_REQUEST_ALREADY_RECORDED')
    record={'schema':'NOX_OWNER_CHAT_REPORTS_STATE_DEPLOY_V1','request':request,'source_sha':source,
        'started_at':time.time(),'state':'STARTING','proxy_restarted':False,'model_restarted':False,
        'training_control_performed':False,'protected_web29_modified':False,'rollback':False,
        'private_content_exported':False,'actual_browser_acceptance':False}
    changed=False;success=False
    def save():helper.atomic(receipt,json.dumps(record,sort_keys=True).encode())
    with ExitStack() as leases:
        leases.enter_context(deploy.lock(deploy.STATE/'media/controller.lock'))
        leases.enter_context(deploy.lock(deploy.STATE/'owner_maintenance.lock'))
        before=core.guards(deploy,evidence);model=deploy.model_identity(helper);proxy=deploy.proxy_identity(helper)
        record.update(preserved_sources=before,model_identity=model,proxy_identity=proxy,
                      training_before=evidence.training_observation(helper))
        try:
            if deploy.stopped_by_owner():fail('HOLD_REPORTS_GLOBAL_STOP')
            save();path,old,new=core.sources(deploy)
            if core.guards(deploy,evidence)!=before or deploy.model_identity(helper)!=model:
                fail('HOLD_REPORTS_PREINSTALL_SOURCE_CHANGED')
            if old!=new:
                helper.atomic(deploy.plain(deploy.ROOT/'backup/owner_chat_reports_state'/request/path.name),old)
                helper.atomic(path,new);changed=True;os.chmod(path,0o644)
                if deploy.read(path)!=new:fail('HOLD_REPORTS_INSTALL_READBACK')
            record['installed_js_sha256']=NEW_JS;save()
            record['http_acceptance']=core.live_probe(deploy,evidence)
            if (core.guards(deploy,evidence)!=before or deploy.model_identity(helper)!=model
                    or deploy.proxy_identity(helper)!=proxy):fail('HOLD_REPORTS_PRESERVATION')
            record['training_after']=evidence.training_observation(helper)
            record.update(state='REPORTS_STATE_SOURCE_AND_HTTP_VERIFIED_BROWSER_PENDING',preservation_verified=True)
            success=True
        except Exception as exc:
            record.update(state='HOLD_REPORTS_STATE_DEPLOY',reason=safe(exc))
            if changed:
                try:
                    if deploy.read(path)!=new:fail('HOLD_REPORTS_ROLLBACK_TARGET_CHANGED')
                    helper.atomic(path,old);os.chmod(path,0o644)
                    record.update(rollback=True,rollback_verified=deploy.read(path)==old)
                except Exception:record['rollback_verified']=False
        finally:
            record['finished_at']=time.time();save()
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':'chat_reports_state','data':record},separators=(',',':')),flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'chat_reports_state_failure','data':safe(exc)}),flush=True)
        raise SystemExit(2)
