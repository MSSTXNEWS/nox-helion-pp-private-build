"""Source contract against the ORIGINAL immutable NoxPackHost; no staging/build."""
import importlib.util
import json
import pathlib
import sys
import threading
import unittest
from test_p02_owner_route_ports import RouteTests
from p02_owner_route_ports import register_with_existing_pack01

ROOT=pathlib.Path(__file__).resolve().parents[3]
source=ROOT/'proposals/NOX-PACK01-50'
spec=importlib.util.spec_from_file_location('existing_pack_r29',source/'native_bridge.py')
host=importlib.util.module_from_spec(spec);sys.modules[spec.name]=host;spec.loader.exec_module(host)
CATALOG=json.loads((source/'catalog.json').read_text())

class ExistingPackContract(unittest.TestCase):
    setUp=RouteTests.setUp
    tearDown=RouteTests.tearDown
    def test_real_readonly_host_registry_accepts_owner_ports_without_mutation(self):
        dispatcher=host.NoxPackHost(CATALOG)
        original_registry=dispatcher.routes
        stop=threading.Event()
        routes=register_with_existing_pack01(dispatcher,host.BoundPort,lambda _:self.scope,
                     self.ports,receipt='R29-OWNER-CANDIDATE',native_stop_from_session=lambda _:stop)
        self.assertIs(dispatcher.routes,original_registry)
        session=host.NativeSession('tenant','alice','chat',routes,routes)
        self.assertEqual(dispatcher.execute('chat.rag',{'query':'facts'},session)['context'],'data')
        self.assertEqual(dispatcher.execute('calls.history',{},session)['calls'][0]['call_id'],'id1')
        stop.set()
        with self.assertRaisesRegex(Exception,'STOPPED_BEFORE_CAPTURE'):
            dispatcher.execute('chat.voice',{'capture_id':'a'*32,'source':'ru','target':'es','voice':'es-v'},session)
        self.assertIn('a'*32,self.audio)
        self.assertEqual(len(dispatcher.routes),50)

    def test_old_call_shape_was_hold_and_now_explicitly_holds_only_unbound_voice(self):
        dispatcher=host.NoxPackHost(CATALOG)
        routes=register_with_existing_pack01(dispatcher,host.BoundPort,lambda _:self.scope,
                                             self.ports,receipt='R29-OWNER-CANDIDATE')
        session=host.NativeSession('tenant','alice','chat',routes,routes)
        status=dispatcher.advertise(session)
        self.assertEqual(status['chat.voice']['state'],'HOLD')
        self.assertEqual(status['chat.rag']['state'],'CONNECTED')
        self.assertEqual(status['calls.history']['state'],'CONNECTED')
        with self.assertRaises(host.HostHold):dispatcher.execute('chat.voice',{},session)
        self.assertIn('a'*32,self.audio)

if __name__=='__main__':unittest.main()
