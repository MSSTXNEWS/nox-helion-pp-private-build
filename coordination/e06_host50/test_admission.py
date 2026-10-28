"""NOX E06 host50 focused offline smoke checks. No Windows native operations."""
import unittest
from admission import BASE_COMMIT, BASE_TREE, Hold, Denied, audit_registry, validate_origin

class AdmissionSourceTests(unittest.TestCase):
    def test_exact_origin(self):
        self.assertEqual(validate_origin("https://nox.invalid"), "https://nox.invalid")
        with self.assertRaises(Denied):
            validate_origin("http://nox.invalid")
        with self.assertRaises(Denied):
            validate_origin("https://nox.invalid:4443")
    def test_duplicate_route_is_hold(self):
        names = ["route%02d" % i for i in range(1, 51)]
        owners = [2] * 50
        catalog = {"version": "NOX-INTEGRATION-PACK-01", "actions": [
            {"taskId": "NIP01-%02d" % i, "routeId": names[i-1], "owner": owners[i-1], "risk": "safe", "settings": []}
            for i in range(1, 51)]}
        bindings = {"sourceBaseCommit": BASE_COMMIT, "routes": [
            {"taskId": "NIP01-%02d" % i, "routeId": names[i-1], "owner": owners[i-1], "sourceBinding": None}
            for i in range(1, 51)]}
        self.assertEqual(audit_registry(catalog,bindings)["unbound"],50)
        bindings["routes"][1]["routeId"] = names[0]
        with self.assertRaises(Hold):
            audit_registry(catalog,bindings)
    def test_no_product_progress_in_source_map(self):
        self.assertEqual(len(BASE_COMMIT),40)
        self.assertEqual(len(BASE_TREE),40)

class HostScopeAndReceiptTests(unittest.TestCase):
    """Native-contract regression only; NOT a connected Windows host test."""
    def setUp(self):
        from admission import Host50Admission, Capability
        import secrets
        names=[f'route{i:02}' for i in range(1,51)]
        names[0]='helion.chat';names[8]='chat.stop'
        aa=[{'taskId':f'NIP01-{i:02}','routeId':r,'owner':2,'risk':'safe','settings':[]}
            for i,r in enumerate(names,1)]
        bb=[{'taskId':a['taskId'],'routeId':a['routeId'],'owner':2,
             'sourceBinding':f'owner2:{a["routeId"]}' if a['routeId'] in {'helion.chat','chat.stop'} else None}
            for a in aa]
        self.cat={'version':'NOX-INTEGRATION-PACK-01','actions':aa}
        self.mapping={'sourceBaseCommit':BASE_COMMIT,'routes':bb}
        caps={a['routeId']:Capability(a['routeId'],2,f'owner2:{a["routeId"]}',
                                     'f'*64,BASE_TREE,True,True)
              for a in aa if a['routeId'] in {'helion.chat','chat.stop'}}
        self.host=Host50Admission(self.cat,self.mapping,signing_key=secrets.token_bytes(32),
                allowed_origins={'https://nox.invalid'},active_tree=BASE_TREE,capabilities=caps)
        self.s=self.host.issue_session(tenant='tenant',principal='person',chat='chat1',
                origin='https://nox.invalid',scopes=('chat.stop','helion.chat'),sensitive=())
    def req(self,route,task):
        return {'intent':'nox.feature.request','routeId':route,'taskId':task,'settings':{}}
    def test_boolean_owner_cannot_fake_integer(self):
        self.cat['actions'][0]['owner']=True;self.mapping['routes'][0]['owner']=True
        with self.assertRaises(Hold):audit_registry(self.cat,self.mapping)
    def test_stop_cross_chat_denied(self):
        r=self.req('chat.stop','NIP01-09');r['runId']='12345678-1234-1234-1234-123456789012'
        for value in [('tenant','person','chat2','helion.chat'),
                      ('tenant','person','helion.chat')]:
            with self.subTest(value=value),self.assertRaises(Denied):
                self.host.admit(session=self.s,actual_origin=self.s.origin,request=r,
                     active_runs={r['runId']:value})
    def test_same_chat_stop_is_admitted_not_executed(self):
        r=self.req('chat.stop','NIP01-09');r['runId']='12345678-1234-1234-1234-123456789012'
        ticket=self.host.admit(session=self.s,actual_origin=self.s.origin,request=r,
                 active_runs={r['runId']:('tenant','person','chat1','helion.chat')})
        self.assertEqual(ticket['state'],'ADMITTED_NOT_EXECUTED')
        self.assertEqual(ticket['targetRunId'],r['runId'])
    def test_ack_binds_payload_tree_origin_and_principal(self):
        r=self.req('helion.chat','NIP01-01')
        ticket=self.host.admit(session=self.s,actual_origin=self.s.origin,request=r)
        ack={key:ticket[key] for key in ('runId','taskId','routeId','owner',
               'ownerReceiptSha256','payloadSha256','sourceLockTree','sessionScopeSha256','targetRunId')}
        ack.update(event='DONE',proofSha256='b'*64)
        for name,bad in [('payloadSha256','d'*64),('sourceLockTree','a'*40),
                          ('sessionScopeSha256','0'*64),('targetRunId','wrong')]:
            v=dict(ack);v[name]=bad;v['seal']=self.host._seal(v)
            with self.subTest(name=name),self.assertRaises(Denied):
                self.host.finish(ticket['runId'],v)
        ack['seal']=self.host._seal(ack)
        result=self.host.finish(ticket['runId'],ack)
        self.assertEqual(result['state'],'NATIVE_ACK_EVIDENCED_NOT_E07_ACCEPTED')
        with self.assertRaises(Denied):self.host.finish(ticket['runId'],ack)
    def test_no_web_injected_command_and_origin(self):
        r=self.req('helion.chat','NIP01-01');r['settings']={'powershell':'whoami'}
        with self.assertRaises(Denied):
            self.host.admit(session=self.s,actual_origin=self.s.origin,request=r)
        r['settings']={}
        with self.assertRaises(Denied):
            self.host.admit(session=self.s,actual_origin='https://evil.invalid',request=r)
    def test_host_binding_map_remains_unintegrated(self):
        d=audit_registry(self.cat,self.mapping)
        self.assertEqual(len(d['routes']),50)
        self.assertEqual(d['nativeIntegrated'],0)
        self.assertEqual(d['windowsAccepted'],0)
        self.assertEqual(d['weightedProductProgress'],'N/D')

if __name__ == "__main__":
    unittest.main()
