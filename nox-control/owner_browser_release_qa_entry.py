#!/usr/bin/env python3
"""Compose only the reviewed private QA release observer, retaining old gates."""
import base64
import hashlib
import json
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
PINS={
 'owner_browser_transport_qa_entry.py':'6919392eaec25ced6b1d3174ad402577239a015a3935a13adedd6ee926678f01',
 'owner_chat_browser_qa.py':'8ff983e96951ad6828ab72433a52a4be1249493861d96c8e091ebdb6deb503be',
 'owner_browser_qa_entry.py':'8a756011dde849d818ef335e804f1a487115a08a1b524c863659b86dfeb00565',
 'owner_chat_browser_transport_qa.py':'e072858b427eb78dcd890117ae4fb044e96e8b3110debb546502d95d7991ba68',
 'owner_chat_browser_release_qa.py':'7eb16d658474c0a4af15050d63e332a205380e0c52bf55b73092dde35437cf16',
}


def sources():
    values={}
    for name,pin in PINS.items():
        try:raw=base64.b64decode(BUNDLE.get(name,''),validate=True)
        except (ValueError,TypeError):raise RuntimeError('HOLD_BROWSER_RELEASE_BUNDLE_PIN') from None
        if not raw or len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=pin:
            raise RuntimeError('HOLD_BROWSER_RELEASE_BUNDLE_PIN')
        values[name]=raw
    return values


def child_program(original,blobs):
    program=original(blobs).decode()
    anchor='diagnostic.install(core,raw)\n'
    if program.count(anchor)!=1:raise RuntimeError('HOLD_BROWSER_RELEASE_CHILD_ANCHOR')
    raw=blobs['owner_chat_browser_release_qa.py']
    replacement=(
        'release_raw=base64.b64decode('+repr(base64.b64encode(raw).decode())+',validate=True)\n'
        'if hashlib.sha256(release_raw).hexdigest()!='+repr(PINS['owner_chat_browser_release_qa.py'])+":raise RuntimeError('HOLD_BROWSER_RELEASE_CHILD_PIN')\n"
        "release=types.ModuleType('_nox_private_release_qa');release.__file__='<owner_chat_browser_release_qa>'\n"
        "sys.modules[release.__name__]=release\n"
        "exec(compile(release_raw,release.__file__,'exec'),release.__dict__)\n"
        "release.install(core,raw,diagnostic,loaded['owner_chat_browser_transport_qa'][1])\n")
    return program.replace(anchor,replacement,1).encode()


def main():
    blobs=sources()
    entry=types.ModuleType('_nox_reviewed_transport_entry')
    exec(compile(blobs['owner_browser_transport_qa_entry.py'],'<frozen-transport-entry>','exec'),entry.__dict__)
    original=entry.child_program
    entry.child_program=lambda values:child_program(original,values)
    entry.PINS=dict(entry.PINS,**{'owner_chat_browser_release_qa.py':PINS['owner_chat_browser_release_qa.py']})
    entry.BUNDLE=BUNDLE
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':'browser_release_sources','data':{
        'source_pins':PINS,'production_ui_changed':False,'strict_progressive_gate_unchanged':True,
        'separate_two_parts_observation':True}},separators=(',',':')),flush=True)
    return entry.main()


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'browser_release_hold',
            'data':{'reason':'HOLD_BROWSER_RELEASE_ENTRY','private_exception_exported':False}}),flush=True)
        raise SystemExit(2)
