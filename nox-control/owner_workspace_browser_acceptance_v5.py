#!/usr/bin/env python3
"""Passive same-page proof; Page events bind one bounded CDP body retrieval."""
import base64
import hashlib
import json
import re
import textwrap
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

BASE = 'owner_workspace_browser_acceptance_v2.py'
BASE_SHA = 'b94fe3d57f81a582cf3bedc62bc2f6bff88a369cfb6189d65f09ff98dd49ffc4'
SCHEMA = 'NOX_OWNER_WORKSPACE_BROWSER_ACCEPTANCE_V5'
KIND = 'workspace_browser_acceptance_v5'
PINS = {
    BASE: BASE_SHA,
    'owner_workspace_browser_acceptance.py': '83cb9a19c2be4112b2f1c4fda40b838550a59524b1d3ac475b92e9f283f3548a',
    'owner_chat_page_diagnose.py': '9587860e23ee3617bd47afb3dd15ba677e4e9f3f6d80774599de59cb1a14dc8a',
    'owner_browser_stream_only_entry.py': '2ec4dde5563dd5307b9c2136b97fe3079709253f7b9617ad1037efd7f260d999',
    'owner_chat_browser_qa.py': 'b76198d8117c3912fb7e1a1ef19c01abc41aa3ac87f4ad919612342edf593587',
}


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_WORKSPACE_BROWSER_V5_' + code)


def change_once(text, old, new):
    require(text.count(old) == 1, 'COMPOSITION_SEAM')
    return text.replace(old, new, 1)


CDP_SOURCE = r'''
class WorkspaceCDPProof:
    PATH='/nox-web-v29/pc/workspace.js'
    PAGE='/nox-web-v29/pc/resonance.html'
    SHA='984b604dc18d9a0c5224518e24b90e58b0b5e3bae89b2aa2996fec3dff5bb4a8'
    SIZE=7278
    def __init__(self,origin,report):
        self.origin=origin;self.frame=None;self.session=None;self.request=None;self.response=False
        self.finished=False;self.failure=None;self.decoded=0;self.encoded=0;self.listeners=[]
        self.document=None;self.navigation_generation=0;self.bound_generation=None;self.detached=False
        self.proof={'schema':'NOX_SAME_PAGE_WORKSPACE_CDP_V2','phase':'SETUP',
            'request_count':0,'response_count':0,'loading_finished':False,
            'get_response_body_calls':0,'body_sha_verified':False,'same_frame_loader_request':False,
            'additional_http_requests':0,'fallbacks_allowed':False,'private_content_exported':False,
            'prior_body_timeout_cause_proven':False,'frame_binding_source':'PRE_GOTO_PAGE_EVENTS',
            'main_frame_navigation_events':0,'main_frame_detached':False}
        report['workspace_cdp']=self.proof
    def valid_id(self,value):
        return isinstance(value,str) and re.fullmatch('[A-Za-z0-9_.:-]{1,160}',value) is not None
    def match_url(self,value,path):
        if not isinstance(value,str) or len(value)>2048:return False
        parsed=urllib.parse.urlsplit(value)
        return parsed.scheme in ('http','https') and parsed.netloc==self.origin and parsed.path==path and not parsed.query and not parsed.fragment
    def reject(self,code):
        if self.failure is None:self.failure=code;self.proof['failure']=code
    def check(self,condition=True,code='EVIDENCE'):
        if not condition:self.reject(code)
        if self.failure is not None:raise RuntimeError('HOLD_WORKSPACE_CDP_'+self.failure)
    def event(self,kind,event):
        try:
            if not isinstance(event,dict):self.reject('EVENT_SCHEMA');return
            getattr(self,'on_'+kind)(event)
        except Exception:self.reject('EVENT_SCHEMA')
    def on_navigated(self,event):
        frame=event.get('frame')
        if not isinstance(frame,dict):self.reject('FRAME_SCHEMA');return
        if frame.get('id')!=self.frame:
            if frame.get('parentId') is None:self.reject('TOP_FRAME_CHANGED')
            return
        if (frame.get('parentId') is not None or not self.valid_id(frame.get('loaderId'))
                or not isinstance(frame.get('url'),str) or len(frame['url'])>2048
                or frame.get('urlFragment') not in (None,'') or frame.get('unreachableUrl') not in (None,'')):
            self.reject('FRAME_SCHEMA');return
        self.navigation_generation+=1
        self.proof['main_frame_navigation_events']=self.navigation_generation
        if self.navigation_generation>16:self.reject('NAVIGATION_BOUND');return
        if self.request is not None:self.reject('FRAME_NAVIGATED_AFTER_REQUEST')
        self.document={'loader':frame['loaderId'],'url':frame['url']}
    def on_detached(self,event):
        if event.get('frameId')==self.frame:
            self.detached=True;self.proof['main_frame_detached']=True
            self.reject('MAIN_FRAME_DETACHED')
    def on_within_document(self,event):
        if event.get('frameId')!=self.frame:return
        self.navigation_generation+=1
        self.proof['main_frame_navigation_events']=self.navigation_generation
        if self.request is not None:self.reject('SAME_DOCUMENT_NAVIGATION_AFTER_REQUEST');return
        if (self.document is None or self.navigation_generation>16
                or not isinstance(event.get('url'),str) or len(event['url'])>2048):
            self.reject('SAME_DOCUMENT_SCOPE');return
        self.document={'loader':self.document['loader'],'url':event['url']}
    def current_document(self):
        self.check(self.request is not None and self.document is not None and not self.detached
            and self.document['loader']==self.request['loader']
            and self.match_url(self.document['url'],self.PAGE)
            and self.bound_generation==self.navigation_generation,'CURRENT_FRAME_EVENT_CHANGED')
    def on_request(self,event):
        item=event.get('request') or {};rid=event.get('requestId')
        target=self.match_url(item.get('url'),self.PATH)
        if target and item.get('urlFragment') not in (None,''):
            self.reject('REQUEST_FRAGMENT');return
        if self.request is not None and rid==self.request['id']:
            self.reject('REDIRECT_OR_DUPLICATE_REQUEST');return
        if not target:return
        self.proof['request_count']+=1
        if (self.proof['request_count']!=1 or not self.valid_id(rid) or item.get('method')!='GET'
                or event.get('type')!='Script' or event.get('frameId')!=self.frame
                or not self.valid_id(event.get('loaderId')) or 'redirectResponse' in event):
            self.reject('REQUEST_SCOPE');return
        self.request={'id':rid,'loader':event['loaderId']}
        self.bound_generation=self.navigation_generation
        self.current_document()
    def on_response(self,event):
        response=event.get('response') or {};rid=event.get('requestId')
        target=self.match_url(response.get('url'),self.PATH)
        if self.request is None or rid!=self.request['id']:
            if target:self.reject('UNBOUND_RESPONSE')
            return
        self.proof['response_count']+=1
        if (self.proof['response_count']!=1 or not target or event.get('type')!='Script'
                or event.get('frameId')!=self.frame or event.get('loaderId')!=self.request['loader']
                or type(response.get('status')) not in (int,float) or response['status']!=200
                or response.get('fromServiceWorker',False) is not False
                or response.get('fromDiskCache',False) is not False
                or response.get('fromPrefetchCache',False) is not False):
            self.reject('RESPONSE_SCOPE');return
        headers=response.get('headers')
        if not isinstance(headers,dict):self.reject('HEADERS');return
        selected={}
        for key,value in headers.items():
            if isinstance(key,str) and key.lower() in ('content-length','content-encoding'):
                key=key.lower()
                if key in selected or not isinstance(value,str) or len(value)>128:self.reject('HEADERS');return
                selected[key]=value
        length=selected.get('content-length');encoding=selected.get('content-encoding','identity').lower()
        if (encoding not in ('identity','gzip','br','deflate') or length is not None
                and (not re.fullmatch('[0-9]{1,8}',length) or not 0<int(length)<=16384)):
            self.reject('HEADER_BOUND');return
        self.response=True;self.proof['response_status']=200
    def on_data(self,event):
        if self.request is None or event.get('requestId')!=self.request['id']:return
        decoded=event.get('dataLength');encoded=event.get('encodedDataLength')
        if self.finished or type(decoded) is not int or type(encoded) is not int or decoded<0 or encoded<0:
            self.reject('DATA_SCOPE');return
        self.decoded+=decoded;self.encoded+=encoded
        if self.decoded>16384 or self.encoded>16384:self.reject('DATA_BOUND')
    def on_finished(self,event):
        if self.request is None or event.get('requestId')!=self.request['id']:return
        size=event.get('encodedDataLength')
        if (self.finished or not self.response or type(size) not in (int,float)
                or not 0<size<=32768):self.reject('FINISHED_BOUND');return
        self.finished=True;self.proof['loading_finished']=True
        self.proof['received_total_bytes']=size
        self.proof['decoded_data_bytes']=self.decoded;self.proof['encoded_data_bytes']=self.encoded
    def on_failed(self,event):
        if self.request is not None and event.get('requestId')==self.request['id']:self.reject('LOADING_FAILED')
    async def attach(self,context,page):
        self.session=await context.new_cdp_session(page)
        self.proof['phase']='INITIAL_FRAME_ID'
        tree=await asyncio.wait_for(self.session.send('Page.getFrameTree'),timeout=1)
        frame=tree.get('frameTree',{}).get('frame',{});self.frame=frame.get('id')
        self.check(self.valid_id(self.frame) and frame.get('parentId') is None,'MAIN_FRAME')
        for event,kind in (('Page.frameNavigated','navigated'),('Page.frameDetached','detached'),
                ('Page.navigatedWithinDocument','within_document'),
                ('Network.requestWillBeSent','request'),('Network.responseReceived','response'),
                ('Network.dataReceived','data'),('Network.loadingFinished','finished'),('Network.loadingFailed','failed')):
            callback=lambda value,k=kind:self.event(k,value)
            self.session.on(event,callback);self.listeners.append((event,callback))
        self.proof['phase']='ENABLE_PAGE_EVENTS'
        await asyncio.wait_for(self.session.send('Page.enable'),timeout=1)
        self.proof['phase']='ENABLE_NETWORK_EVENTS'
        await asyncio.wait_for(self.session.send('Network.enable',{'maxTotalBufferSize':1048576,
            'maxResourceBufferSize':16384,'maxPostDataSize':0}),timeout=1.5)
        self.proof['phase']='ARMED_BEFORE_NAVIGATION'
    async def read_body(self):
        self.check(self.request is not None and self.response and self.finished
            and self.proof['request_count']==self.proof['response_count']==1,'COMPLETE_RESPONSE_REQUIRED')
        self.check(0<self.decoded<=16384 and 0<=self.encoded<=16384,'DATA_EVIDENCE_REQUIRED')
        self.proof['phase']='CURRENT_FRAME_EVENT_BINDING'
        self.current_document()
        self.proof['same_frame_loader_request']=True
        self.check(self.proof['get_response_body_calls']==0,'BODY_ALREADY_REQUESTED')
        self.proof['get_response_body_calls']=1;self.proof['phase']='GET_RESPONSE_BODY'
        value=await asyncio.wait_for(self.session.send('Network.getResponseBody',{'requestId':self.request['id']}),timeout=2.5)
        self.current_document()
        self.check(isinstance(value,dict) and set(value)=={'body','base64Encoded'}
            and isinstance(value.get('body'),str) and type(value.get('base64Encoded')) is bool,'BODY_SCHEMA')
        self.check(len(value['body'])<=(21848 if value['base64Encoded'] else 16384),'BODY_BOUND')
        self.proof['phase']='DECODE_AND_HASH'
        try:
            raw=__import__('base64').b64decode(value['body'],validate=True) if value['base64Encoded'] else value['body'].encode('utf-8')
        except (ValueError,UnicodeError):
            self.reject('BODY_ENCODING');self.check()
        self.proof['returned_body_bytes']=len(raw)
        self.check(0<len(raw)<=16384,'BODY_EMPTY_OR_OVERSIZE')
        self.check(len(raw)==self.SIZE and digest(raw)==self.SHA,'BODY_SHA')
        self.proof['body_sha_verified']=True;self.proof['phase']='BODY_VERIFIED'
        return raw
    def final_check(self):
        self.current_document()
        self.check(self.proof['body_sha_verified'] is True and self.proof['get_response_body_calls']==1
            and self.proof['request_count']==self.proof['response_count']==1,'FINAL_EVIDENCE')
    async def close(self):
        if self.session is None:return
        for event,callback in self.listeners:
            try:self.session.remove_listener(event,callback)
            except Exception:self.proof['own_listener_removal_completed']=False
        try:
            await asyncio.wait_for(self.session.detach(),timeout=1)
            self.proof['own_session_detached']=True
        except Exception:self.proof['own_session_detached']=False
'''


def prepared():
    blobs = {}
    for name, pin in PINS.items():
        value = BUNDLE.get(name)
        require(isinstance(value, str) and 0 < len(value) <= 262144, 'BUNDLE_BOUND')
        raw = base64.b64decode(value, validate=True)
        require(0 < len(raw) <= 131072 and hashlib.sha256(raw).hexdigest() == pin, 'BUNDLE_PIN')
        blobs[name] = raw
    wrapper = types.ModuleType('_workspace_v2_frozen')
    wrapper.__file__ = '<' + BASE + '>'
    wrapper.__dict__['__NOX_' + 'BUNDLE_JSON__'] = dict(BUNDLE)
    exec(compile(blobs[BASE], wrapper.__file__, 'exec'), wrapper.__dict__)
    require(wrapper.PINS == {k: v for k, v in PINS.items() if k != BASE}, 'FROZEN_CLOSURE')
    base = wrapper.prepared(); tail = base.PAGE_TAIL
    setup = textwrap.indent(CDP_SOURCE, '            ') + (
        "            workspace_cdp=WorkspaceCDPProof(origin,report)\n"
        "            await asyncio.wait_for(workspace_cdp.attach(context,page),timeout=3)\n")
    tail = change_once(tail, "            report['browser_stage']='NAVIGATION'\n",
                       setup + "            report['browser_stage']='NAVIGATION'\n")
    tail = change_once(tail, "raw=await workspace_step('ASSET_BODY',asset.body)",
                       "raw=await workspace_step('ASSET_BODY',workspace_cdp.read_body)")
    tail = change_once(tail, "'additional_gets':0,'response_body_exported':False}",
                       "'additional_gets':0,'response_body_exported':False,'body_transport':'CDP_NETWORK_GET_RESPONSE_BODY'}")
    # The old optional public-chat body check is outside this one-asset proof.
    # Omit it so no library body helper can perform a hidden reload fallback.
    start = "            report['public_chat_source']={'expected_sha256':_page_chat_sha,'state':'NOT_BOUND'}\n"
    end = "            if report.get('response_count_truncated'):raise RuntimeError('HOLD_WORKSPACE_BROWSER_RESPONSE_BOUND')\n"
    require(tail.count(start) == tail.count(end) == 1 and tail.index(start) < tail.index(end), 'PUBLIC_CHAT_SEAM')
    tail = tail[:tail.index(start)] + (
        "            report['public_chat_source']={'expected_sha256':_page_chat_sha,'state':'NOT_READ_WORKSPACE_ONLY_SCOPE'}\n"
        "            workspace_cdp.final_check()\n") + tail[tail.index(end):]
    tail = change_once(tail, "        finally:\n            if 'network' in locals():\n",
        "        finally:\n            if 'workspace_cdp' in locals():await workspace_cdp.close()\n"
        "            if 'network' in locals():\n")
    require('.body()' not in tail and 'asset.body' not in tail, 'LIBRARY_BODY_FALLBACK')
    base.PAGE_TAIL = tail; base.SCHEMA = SCHEMA; base.KIND = KIND
    compile(base.browser_source(blobs[base.CORE]), '<workspace-cdp-browser>', 'exec')
    return base


def main():
    return prepared().main()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        reason = str(exc)
        if not re.fullmatch('HOLD_[A-Z0-9_]{1,140}', reason):
            reason = 'HOLD_WORKSPACE_BROWSER_V5_PREFLIGHT'
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': KIND, 'data': {
            'schema': SCHEMA, 'state': 'HOLD', 'reason': reason, 'private_content_exported': False}},
            separators=(',', ':')), flush=True)
        raise SystemExit(2)
