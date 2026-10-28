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
        names[0]='helion.chat';names[5]='chat.attach';names[8]='chat.stop'
        aa=[{'taskId':f'NIP01-{i:02}','routeId':r,'owner':2,'risk':'safe','settings':[]}
            for i,r in enumerate(names,1)]
        bb=[{'taskId':a['taskId'],'routeId':a['routeId'],'owner':2,
             'sourceBinding':f'owner2:{a["routeId"]}' if a['routeId'] in {'helion.chat','chat.stop','chat.attach'} else None}
            for a in aa]
        self.cat={'version':'NOX-INTEGRATION-PACK-01','actions':aa}
        self.mapping={'sourceBaseCommit':BASE_COMMIT,'routes':bb}
        caps={a['routeId']:Capability(a['routeId'],2,f'owner2:{a["routeId"]}',
                                     'f'*64,BASE_TREE,True,True)
              for a in aa if a['routeId'] in {'helion.chat','chat.stop','chat.attach'}}
        self.host=Host50Admission(self.cat,self.mapping,signing_key=secrets.token_bytes(32),
                allowed_origins={'https://nox.invalid'},active_tree=BASE_TREE,capabilities=caps)
        self.s=self.host.issue_session(tenant='tenant',principal='person',chat='chat1',
                origin='https://nox.invalid',scopes=('chat.stop','helion.chat','chat.attach'),sensitive=())
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
               'ownerReceiptSha256','payloadSha256','sourceLockTree','sessionScopeSha256',
               'targetRunId','fileSha256','fileTicketSha256')}
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
    def test_stop_done_ack_cannot_claim_confirmed_cancellation(self):
        r=self.req('chat.stop','NIP01-09');r['runId']='12345678-1234-1234-1234-123456789012'
        t=self.host.admit(session=self.s,actual_origin=self.s.origin,request=r,
               active_runs={r['runId']:('tenant','person','chat1','helion.chat')})
        ack={key:t[key] for key in ('runId','taskId','routeId','owner','ownerReceiptSha256',
            'payloadSha256','sourceLockTree','sessionScopeSha256','targetRunId','fileSha256',
            'fileTicketSha256')}
        ack.update(event='DONE',proofSha256='b'*64)
        ack['seal']=self.host._seal(ack)
        with self.assertRaises(Denied):self.host.finish(t['runId'],ack)
        ack['event']='STOP_REQUESTED';ack.pop('seal')
        ack['seal']=self.host._seal(ack)
        self.assertEqual(self.host.finish(t['runId'],ack)['state'],
                         'STOP_REQUESTED_NOT_CONFIRMED_STOPPED')
    def test_non_stop_cannot_claim_stop_requested(self):
        t=self.host.admit(session=self.s,actual_origin=self.s.origin,
                          request=self.req('helion.chat','NIP01-01'))
        ack={key:t[key] for key in ('runId','taskId','routeId','owner','ownerReceiptSha256',
            'payloadSha256','sourceLockTree','sessionScopeSha256','targetRunId','fileSha256',
            'fileTicketSha256')}
        ack.update(event='STOP_REQUESTED',proofSha256='b'*64)
        ack['seal']=self.host._seal(ack)
        with self.assertRaises(Denied):self.host.finish(t['runId'],ack)
    def test_ack_lease_expires_before_finish(self):
        t=self.host.admit(session=self.s,actual_origin=self.s.origin,
                          request=self.req('helion.chat','NIP01-01'))
        self.host.pending_deadlines[t['runId']]=0
        with self.assertRaisesRegex(Denied,'LEASE_EXPIRED'):
            self.host.finish(t['runId'],{})
        self.assertNotIn(t['runId'],self.host.pending)
    def test_unacknowledged_queue_is_bounded(self):
        from admission import MAX_PENDING, Hold
        import time
        self.host.pending.update({f'dummy-{x}':{} for x in range(MAX_PENDING)})
        deadline=time.monotonic()+500
        self.host.pending_deadlines.update({f'dummy-{x}':deadline for x in range(MAX_PENDING)})
        with self.assertRaisesRegex(Hold,'TOO_MANY'):
            self.host.admit(session=self.s,actual_origin=self.s.origin,
                 request=self.req('helion.chat','NIP01-01'))
    def test_file_picker_binds_chat_and_opaque_ticket_digest(self):
        from admission import NativeFileSelection
        from dataclasses import replace
        good=NativeFileSelection(ticket='opaque-native-ticket-777',sha256='c'*64,
             size_bytes=42,tenant='tenant',principal='person',chat='chat1')
        req=self.req('chat.attach','NIP01-06')
        with self.assertRaises(Denied):
            self.host.admit(session=self.s,actual_origin=self.s.origin,request=req,
                native_file_picker=lambda *_:replace(good,chat='chat2'))
        t=self.host.admit(session=self.s,actual_origin=self.s.origin,request=req,
                          native_file_picker=lambda *_:good)
        self.assertEqual(t['fileSha256'],'c'*64)
        self.assertEqual(len(t['fileTicketSha256']),64)
        self.assertNotIn(good.ticket,str(t))
        ack={key:t[key] for key in ('runId','taskId','routeId','owner','ownerReceiptSha256',
            'payloadSha256','sourceLockTree','sessionScopeSha256','targetRunId','fileSha256',
            'fileTicketSha256')}
        ack.update(event='DONE',proofSha256='b'*64)
        for key in ('fileSha256','fileTicketSha256'):
            spoof=dict(ack);spoof[key]='0'*64;spoof['seal']=self.host._seal(spoof)
            with self.subTest(key=key),self.assertRaises(Denied):
                self.host.finish(t['runId'],spoof)
        ack['seal']=self.host._seal(ack)
        self.assertEqual(self.host.finish(t['runId'],ack)['nativeAck'],'VERIFIED_HMAC')
    def test_ack_rejects_unexpected_signed_fields(self):
        t=self.host.admit(session=self.s,actual_origin=self.s.origin,
                          request=self.req('helion.chat','NIP01-01'))
        ack={key:t[key] for key in ('runId','taskId','routeId','owner','ownerReceiptSha256',
            'payloadSha256','sourceLockTree','sessionScopeSha256','targetRunId','fileSha256',
            'fileTicketSha256')}
        ack.update(event='DONE',proofSha256='b'*64,webClaim='force_success')
        ack['seal']=self.host._seal(ack)
        with self.assertRaises(Denied):self.host.finish(t['runId'],ack)
    def test_stop_run_id_requires_canonical_uuid(self):
        r=self.req('chat.stop','NIP01-09');r['runId']='-'*36
        with self.assertRaisesRegex(Denied,'STOP_NEEDS_EXACT_RUNID'):
            self.host.admit(session=self.s,actual_origin=self.s.origin,request=r,
               active_runs={r['runId']:('tenant','person','chat1','helion.chat')})
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

class HostSettingPolicyTests(unittest.TestCase):
    """Synthetic owner-capability tests; no actual installed model or native host."""
    def setUp(self):
        HostScopeAndReceiptTests.setUp(self)
        from admission import Host50Admission
        self.make = lambda: Host50Admission(self.cat,self.mapping,signing_key=self.host.key,
              allowed_origins={'https://nox.invalid'},active_tree=BASE_TREE,
              capabilities=self.host.capabilities)
        self.action = self.cat['actions'][0]
        self.request = HostScopeAndReceiptTests.req(self,'helion.chat','NIP01-01')

    def test_static_select_rejects_outside_allowed_options(self):
        self.action['settings']=[{'key':'profile','kind':'select',
            'options':[['eco','ECO'],['balanced','Balanced']]}]
        host=self.make()
        self.request['settings']={'profile':'DROP TABLE'}
        with self.assertRaisesRegex(Denied,'STATIC_SELECT_OPTION_DENIED'):
            host.admit(session=self.s,actual_origin=self.s.origin,request=self.request)

    def test_static_select_accepts_exact_value_as_admitted_not_done(self):
        self.action['settings']=[{'key':'profile','kind':'select',
            'options':[['eco','ECO'],['balanced','Balanced']]}]
        host=self.make();self.request['settings']={'profile':'eco'}
        result=host.admit(session=self.s,actual_origin=self.s.origin,request=self.request)
        self.assertEqual(result['state'],'ADMITTED_NOT_EXECUTED')

    def test_source_select_requires_native_verifier(self):
        self.action['settings']=[{'key':'model','kind':'select','source':'host.models.installed'}]
        host=self.make();self.request['settings']={'model':'uninstalled-model'}
        with self.assertRaisesRegex(Hold,'NATIVE_SELECT_VERIFIER_MISSING'):
            host.admit(session=self.s,actual_origin=self.s.origin,request=self.request)

    def test_source_select_rejects_owner_verifier_false_or_exception(self):
        self.action['settings']=[{'key':'model','kind':'select','source':'host.models.installed'}]
        host=self.make();self.request['settings']={'model':'uninstalled-model'}
        with self.assertRaisesRegex(Denied,'UNVERIFIED_NATIVE_SELECT'):
            host.admit(session=self.s,actual_origin=self.s.origin,request=self.request,
                native_option_verifier=lambda *_:False)
        with self.assertRaisesRegex(Hold,'NATIVE_SELECT_VERIFIER_FAILED'):
            host.admit(session=self.s,actual_origin=self.s.origin,request=self.request,
                native_option_verifier=lambda *_:1/0)
        with self.assertRaisesRegex(Denied,'UNVERIFIED_NATIVE_SELECT'):
            host.admit(session=self.s,actual_origin=self.s.origin,request=self.request,
                native_option_verifier=lambda *_:1)

    def test_source_select_native_verifier_exact_call_but_no_execution(self):
        self.action['settings']=[{'key':'model','kind':'select','source':'host.models.installed'}]
        host=self.make();self.request['settings']={'model':'installed-by-host'}
        calls=[]
        def verifier(*args):
            calls.append(args)
            return args[0]==self.s and args[1:]==('helion.chat','model','host.models.installed','installed-by-host')
        result=host.admit(session=self.s,actual_origin=self.s.origin,request=self.request,
            native_option_verifier=verifier)
        self.assertEqual(len(calls),1)
        self.assertEqual(result['state'],'ADMITTED_NOT_EXECUTED')

    def test_catalog_rejects_unknown_native_source(self):
        self.action['settings']=[{'key':'model','kind':'select','source':'host.run.shell'}]
        with self.assertRaisesRegex(Hold,'UNTRUSTED_NATIVE_OPTION_SOURCE'):
            self.make()

    def test_catalog_rejects_duplicate_or_invalid_selects(self):
        bad=[
            [{'key':'profile','kind':'select','options':[['eco','ECO'],['eco','dup']]}],
            [{'key':'profile','kind':'select','options':[['eco','ECO']], 'source':'host.models.installed'}],
            [{'key':'profile','kind':'input','options':[['eco','ECO']]}],
            [{'key':'profile','kind':'select','options':[]}],
            [{'key':'profile','kind':'select','options':[['eco']]}],
        ]
        for settings in bad:
            with self.subTest(settings=settings):
                self.action['settings']=settings
                with self.assertRaises(Hold):self.make()

    def test_native_select_bool_and_object_never_pass(self):
        self.action['settings']=[{'key':'model','kind':'select','source':'host.models.installed'}]
        host=self.make()
        for bad in (True,42,{'x':'y'},['a']):
            with self.subTest(bad=bad):
                self.request['settings']={'model':bad}
                with self.assertRaises(Denied):
                    host.admit(session=self.s,actual_origin=self.s.origin,
                        request=self.request,native_option_verifier=lambda *_:True)

if __name__ == "__main__":
    unittest.main()
