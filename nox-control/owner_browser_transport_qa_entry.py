#!/usr/bin/env python3
"""Run one reviewed transport diagnostic through the frozen isolated QA entry."""
import base64
import hashlib
import json
import sys
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
PINS={
 'owner_chat_browser_qa.py':'b76198d8117c3912fb7e1a1ef19c01abc41aa3ac87f4ad919612342edf593587',
 'owner_browser_qa_entry.py':'8a756011dde849d818ef335e804f1a487115a08a1b524c863659b86dfeb00565',
 'owner_chat_browser_transport_qa.py':'e8d256f4ab4de1d53859c1da74237622871354b5d84442bdff1171631f9f05f0',
}


def sources():
    result={}
    for name,pin in PINS.items():
        try:raw=base64.b64decode(BUNDLE.get(name,''),validate=True)
        except (ValueError,TypeError):raise RuntimeError('HOLD_BROWSER_DIAGNOSTIC_BUNDLE_PIN') from None
        if not raw or len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=pin:
            raise RuntimeError('HOLD_BROWSER_DIAGNOSTIC_BUNDLE_PIN')
        result[name]=raw
    return result


def child_program(blobs):
    modules={name.removesuffix('.py'):{'source':base64.b64encode(blobs[name]).decode(),'sha256':PINS[name]}
             for name in ('owner_chat_browser_qa.py','owner_chat_browser_transport_qa.py')}
    return ("import base64,hashlib,json,sys,types\n"
        "sys.dont_write_bytecode=True\n"
        "items="+repr(modules)+"\n"
        "loaded={}\n"
        "for name,item in items.items():\n"
        " raw=base64.b64decode(item['source'],validate=True)\n"
        " if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise RuntimeError('HOLD_BROWSER_DIAGNOSTIC_CHILD_PIN')\n"
        " mod=types.ModuleType('_nox_private_'+name);mod.__file__='<'+name+'>'\n"
        " sys.modules[mod.__name__]=mod\n"
        " exec(compile(raw,mod.__file__,'exec'),mod.__dict__);loaded[name]=(mod,raw)\n"
        "core,raw=loaded['owner_chat_browser_qa']\n"
        "diagnostic=loaded['owner_chat_browser_transport_qa'][0]\n"
        "diagnostic.install(core,raw)\n"
        "raise SystemExit(core.main())\n").encode()


def main():
    blobs=sources();program=child_program(blobs)
    compile(program,'<reviewed-browser-diagnostic-child>','exec')
    entry=types.ModuleType('_nox_reviewed_browser_entry')
    entry.__file__='<owner_browser_qa_entry>'
    exec(compile(blobs['owner_browser_qa_entry.py'],entry.__file__,'exec'),entry.__dict__)
    # The original entry performs its unchanged STOP, reserve, isolated-runtime
    # and private-output checks. Only its exact composed QA bytes are supplied.
    entry.BUNDLE=dict(BUNDLE)
    entry.BUNDLE['owner_chat_browser_qa.py']=base64.b64encode(program).decode()
    entry.PIN=hashlib.sha256(program).hexdigest()
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':'browser_diagnostic_sources','data':{
        'source_pins':PINS,'composed_child_sha256':entry.PIN,'production_ui_changed':False,
        'fixture_number_count':40,'upstream_model_inference_not_presumed':True}},separators=(',',':')),flush=True)
    return entry.main()


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'browser_diagnostic_hold','data':{
            'reason':'HOLD_BROWSER_TRANSPORT_DIAGNOSTIC_ENTRY','private_exception_exported':False}}),flush=True)
        raise SystemExit(2)
