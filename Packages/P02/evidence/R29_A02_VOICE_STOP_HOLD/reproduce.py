"""Diagnostic only: execute unchanged existing host STOP while voice ASR is active."""
import importlib.util,json,pathlib,sys,threading
repo=pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0,str(repo/'Packages/P02/worker-python'))
from test_p02_owner_route_ports import RouteTests
from p02_native_ingress import NativeIngress
from p02_owner_route_ports import register_with_existing_pack01
from p02_runtime import OllamaClient
spec=importlib.util.spec_from_file_location('real_pack_stop_probe',repo/'proposals/NOX-PACK01-50/native_bridge.py')
host=importlib.util.module_from_spec(spec);sys.modules[spec.name]=host;spec.loader.exec_module(host)
x=RouteTests();x.setUp()
try:
 catalog=json.loads((repo/'proposals/NOX-PACK01-50/catalog.json').read_text())
 dispatcher=host.NoxPackHost(catalog)
 client=OllamaClient();client.models=lambda:['offline-test-model']
 adapter=host.ExistingP02Adapter(client,x.store);adapter.register(dispatcher,receipt='OFFLINE-TEST-OWNER')
 token=threading.Event()
 register_with_existing_pack01(dispatcher,host.BoundPort,lambda _:x.scope,x.ports,
    receipt='OFFLINE-TEST-OWNER',native_stop_from_session=lambda _:token)
 allowed=frozenset(dispatcher.ports)
 session=host.NativeSession('tenant','alice','chat',allowed,allowed)
 ingress=NativeIngress(dispatcher,lambda:session,expected_run_id='R29-A02-STOP-PROBE')
 def envelope(n,route,payload):
  return json.dumps(dict(protocol='NOX-P02-NATIVE-v1',requestId=f'{n:032x}',route=route,payload=payload,runId='R29-A02-STOP-PROBE')).encode()
 seen={}
 def asr(scope,data,language,stop):
  seen['voice_received_same_host_fixture_token']=stop is token
  seen['stop_response']=json.loads(ingress.handle(envelope(2,'chat.stop',{})))
  seen['voice_token_set_after_actual_stop']=token.is_set()
  return 'привет'
 x.voice.asr=asr
 seen['voice_response']=json.loads(ingress.handle(envelope(1,'chat.voice',dict(capture_id='a'*32,source='ru',target='es',voice='es-v'))))
 seen['scope']='OFFLINE_IMPORTED_SOURCE_DIAGNOSTIC_NOT_NATIVE_ACCEPTANCE'
 seen['finding']='EXISTING_CHAT_STOP_ACK_DOES_NOT_CANCEL_VOICE_EVENT'
 print(json.dumps(seen,ensure_ascii=False,indent=2))
finally:x.tearDown()
