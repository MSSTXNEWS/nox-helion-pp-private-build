"""NOX E06 host50 focused offline smoke checks. No Windows native operations."""
import unittest
from admission import BASE_COMMIT, BASE_TREE, APPROVED_ROUTE_POLICY, Hold, Denied, audit_registry, validate_origin

class AdmissionSourceTests(unittest.TestCase):
    def test_exact_origin(self):
        self.assertEqual(validate_origin("https://nox.invalid"), "https://nox.invalid")
        with self.assertRaises(Denied):
            validate_origin("http://nox.invalid")
        with self.assertRaises(Denied):
            validate_origin("https://nox.invalid:4443")
    def test_duplicate_route_is_hold(self):
        names = [row[0] for row in APPROVED_ROUTE_POLICY]
        catalog = {"version": "NOX-INTEGRATION-PACK-01", "actions": [
            {"taskId": "NIP01-%02d" % i, "routeId": route, "owner": owner,
             "risk": risk, "settings": []}
            for i, (route,owner,risk) in enumerate(APPROVED_ROUTE_POLICY,1)]}
        bindings = {"sourceBaseCommit": BASE_COMMIT, "routes": [
            {"taskId": a["taskId"], "routeId": a["routeId"],
             "owner": a["owner"], "sourceBinding": None}
            for a in catalog["actions"]]}
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
        aa=[{'taskId':f'NIP01-{i:02}','routeId':r,'owner':owner,'risk':risk,'settings':[]}
            for i,(r,owner,risk) in enumerate(APPROVED_ROUTE_POLICY,1)]
        bb=[{'taskId':a['taskId'],'routeId':a['routeId'],'owner':a['owner'],
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
                origin='https://nox.invalid',scopes=('chat.stop','helion.chat','chat.attach'),sensitive=('chat.attach',))
    def req(self,route,task):
        return {'intent':'nox.feature.request','routeId':route,'taskId':task,'settings':{}}
    def test_immutable_policy_matches_all_50_approved_owner_risks(self):
        self.assertEqual(len(APPROVED_ROUTE_POLICY),50)
        self.assertEqual(len({r for r,_,_ in APPROVED_ROUTE_POLICY}),50)
        self.assertEqual(len(audit_registry(self.cat,self.mapping)['routes']),50)

    def test_catalog_cannot_downgrade_risk_even_when_binding_map_matches(self):
        # Prior source would accept risk='safe' for a dangerous native route.
        danger=self.cat['actions'][25]  # NIP01-26 training.start
        self.assertEqual(danger['risk'],'dangerous')
        danger['risk']='safe'
        with self.assertRaisesRegex(Hold,'IMMUTABLE_ROUTE_OWNER_RISK'):
            audit_registry(self.cat,self.mapping)

    def test_catalog_cannot_forge_owner_even_when_binding_map_matches(self):
        self.cat['actions'][33]['owner']=1  # calls.dial belongs to P02 owner 2
        self.mapping['routes'][33]['owner']=1
        with self.assertRaisesRegex(Hold,'IMMUTABLE_ROUTE_OWNER_RISK'):
            audit_registry(self.cat,self.mapping)

    def test_catalog_cannot_alias_dangerous_route_even_when_both_sources_match(self):
        self.cat['actions'][48]['routeId']='pc.harmless'  # was system.pc_control
        self.mapping['routes'][48]['routeId']='pc.harmless'
        with self.assertRaisesRegex(Hold,'IMMUTABLE_ROUTE_OWNER_RISK'):
            audit_registry(self.cat,self.mapping)

    def test_all_sensitive_and_dangerous_routes_cannot_be_lowered(self):
        for idx,(_,_,risk) in enumerate(APPROVED_ROUTE_POLICY):
            if risk=='safe': continue
            with self.subTest(task=f'NIP01-{idx+1:02}',risk=risk):
                self.cat['actions'][idx]['risk']='safe'
                with self.assertRaises(Hold):audit_registry(self.cat,self.mapping)
                self.cat['actions'][idx]['risk']=risk
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
    def test_signed_ack_must_include_every_binding_field_even_when_none(self):
        # In R07 a signed ACK silently omitted required null binding fields.
        for omitted in ('targetRunId', 'fileSha256', 'fileTicketSha256'):
            with self.subTest(omitted=omitted):
                t=self.host.admit(session=self.s,actual_origin=self.s.origin,
                     request=self.req('helion.chat','NIP01-01'))
                ack={key:t[key] for key in ('runId','taskId','routeId','owner',
                    'ownerReceiptSha256','payloadSha256','sourceLockTree',
                    'sessionScopeSha256','targetRunId','fileSha256','fileTicketSha256')}
                ack.update(event='DONE',proofSha256='b'*64)
                ack.pop(omitted)
                ack['seal']=self.host._seal(ack)
                with self.assertRaisesRegex(Denied,'NATIVE_ACK_SCHEMA_INVALID'):
                    self.host.finish(t['runId'],ack)

    def test_stop_target_disappeared_before_reservation_is_denied(self):
        # A real in-process run can finish after the first active-runs check.
        r=self.req('chat.stop','NIP01-09');r['runId']='12345678-1234-1234-1234-123456789012'
        class ChangesBetweenChecks(dict):
            def __init__(self):
                super().__init__({r['runId']:('tenant','person','chat1','helion.chat')})
                self.checks=0
            def get(self,key,default=None):
                self.checks+=1
                return ('tenant','person','chat1','helion.chat') if self.checks==1 else None
        live=ChangesBetweenChecks()
        with self.assertRaisesRegex(Denied,'STOP_SCOPE_OR_OWNER_MISMATCH'):
            self.host.admit(session=self.s,actual_origin=self.s.origin,request=r,active_runs=live)
        self.assertGreaterEqual(live.checks,2)

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
        self.assertEqual(len(calls),2)
        self.assertEqual(result['state'],'ADMITTED_NOT_EXECUTED')

    def test_native_option_revoked_during_file_picker_is_denied(self):
        # A model admitted before a native callback can be uninstalled during it.
        from admission import Host50Admission, NativeFileSelection
        self.cat['actions'][5]['settings']=[{'key':'model','kind':'select',
                                              'source':'host.models.installed'}]
        host=self.make()
        req=HostScopeAndReceiptTests.req(self,'chat.attach','NIP01-06')
        req['settings']={'model':'installed-model'}
        installed={'ok':True}
        calls=[]
        def verifier(*_):
            calls.append(installed['ok'])
            return installed['ok']
        def picker(*_):
            installed['ok']=False
            return NativeFileSelection(ticket='opaque-ticket-native-777',sha256='a'*64,
                size_bytes=123,tenant='tenant',principal='person',chat='chat1')
        with self.assertRaisesRegex(Denied,'UNVERIFIED_NATIVE_SELECT_VALUE'):
            host.admit(session=self.s,actual_origin=self.s.origin,request=req,
                native_option_verifier=verifier,native_file_picker=picker)
        self.assertEqual(calls,[True,False])

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

class HostThreadSafetyTests(unittest.TestCase):
    """Offline race and type checks; no genuine native owner capability."""
    def setUp(self):
        HostScopeAndReceiptTests.setUp(self)

    def _owner_one(self, owner):
        from admission import Host50Admission, Capability
        import secrets
        route='browser.open'
        index=37  # NIP01-38 original owner E01; synthetic descriptor only
        self.mapping['routes'][index]['sourceBinding']='owner1:browser.open'
        self.host.capabilities[route]=Capability(route,owner,'owner1:browser.open',
                                                  'e'*64,BASE_TREE,True,True)
        host=Host50Admission(self.cat,self.mapping,signing_key=secrets.token_bytes(32),
                allowed_origins={'https://nox.invalid'},active_tree=BASE_TREE,
                capabilities=self.host.capabilities)
        scope=host.issue_session(tenant='tenant',principal='person',chat='chat1',
            origin='https://nox.invalid',scopes=(route,),sensitive=(route,))
        req=HostScopeAndReceiptTests.req(self,route,'NIP01-38')
        return host,scope,req

    def test_boolean_native_capability_owner_cannot_equal_owner_one(self):
        host,scope,req=self._owner_one(True)
        with self.assertRaisesRegex(Hold,'NATIVE_OWNER_CAPABILITY_UNVERIFIED'):
            host.admit(session=scope,actual_origin=scope.origin,request=req)

    def test_boolean_signed_ack_owner_cannot_equal_owner_one(self):
        host,scope,req=self._owner_one(1)
        ticket=host.admit(session=scope,actual_origin=scope.origin,request=req)
        ack={key:ticket[key] for key in ('runId','taskId','routeId','owner',
            'ownerReceiptSha256','payloadSha256','sourceLockTree','sessionScopeSha256',
            'targetRunId','fileSha256','fileTicketSha256')}
        ack.update(event='DONE',proofSha256='a'*64,owner=True)
        ack['seal']=host._seal(ack)
        with self.assertRaisesRegex(Denied,'NATIVE_ACK_INVALID'):
            host.finish(ticket['runId'],ack)

    def test_concurrent_native_ack_is_consumed_at_most_once(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        ticket=self.host.admit(session=self.s,actual_origin=self.s.origin,
            request=HostScopeAndReceiptTests.req(self,'helion.chat','NIP01-01'))
        ack={key:ticket[key] for key in ('runId','taskId','routeId','owner',
            'ownerReceiptSha256','payloadSha256','sourceLockTree','sessionScopeSha256',
            'targetRunId','fileSha256','fileTicketSha256')}
        ack.update(event='DONE',proofSha256='a'*64)
        ack['seal']=self.host._seal(ack)
        normal_seal=self.host._seal
        both_entered=threading.Event()
        counter_lock=threading.Lock()
        entered=[0]
        def slow_seal(body):
            if threading.current_thread().name.startswith('R06_ACK'):
                with counter_lock:
                    entered[0]+=1
                    if entered[0]>=2:both_entered.set()
                both_entered.wait(timeout=.08)
            return normal_seal(body)
        self.host._seal=slow_seal
        start=threading.Barrier(3)
        def worker():
            start.wait(timeout=3)
            try:
                self.host.finish(ticket['runId'],dict(ack))
                return 'ACK'
            except Denied:
                return 'DENIED'
            except Exception as e:
                return type(e).__name__
        with ThreadPoolExecutor(max_workers=2,thread_name_prefix='R06_ACK') as pool:
            a=pool.submit(worker);b=pool.submit(worker)
            start.wait(timeout=3)
            outcomes=sorted([a.result(timeout=4),b.result(timeout=4)])
        self.assertEqual(outcomes,['ACK','DENIED'])
        self.assertNotIn(ticket['runId'],self.host.pending)

    def test_native_admission_queue_stays_bounded_under_concurrency(self):
        from concurrent.futures import ThreadPoolExecutor
        from admission import MAX_PENDING
        req=HostScopeAndReceiptTests.req(self,'helion.chat','NIP01-01')
        def worker(_):
            try:
                self.host.admit(session=self.s,actual_origin=self.s.origin,request=req)
                return 'ADMITTED'
            except Hold:
                return 'HOLD'
        with ThreadPoolExecutor(max_workers=16) as pool:
            results=list(pool.map(worker,range(MAX_PENDING+40)))
        self.assertEqual(results.count('ADMITTED'),MAX_PENDING)
        self.assertEqual(results.count('HOLD'),40)
        self.assertEqual(len(self.host.pending),MAX_PENDING)


class HostAdmissionR07TOCTOUTests(unittest.TestCase):
    """Host-only races and post-audit mutation; synthetic capabilities, NO Windows claim."""
    def setUp(self):
        HostScopeAndReceiptTests.setUp(self)

    def _file(self):
        from admission import NativeFileSelection
        return NativeFileSelection(ticket='native-ticket-not-a-path',sha256='c'*64,
            size_bytes=91,tenant='tenant',principal='person',chat='chat1')

    def test_page_request_mutation_during_native_picker_is_denied(self):
        req=HostScopeAndReceiptTests.req(self,'chat.attach','NIP01-06')
        def picker(*_):
            req['routeId']='system.pc_control'
            return self._file()
        with self.assertRaisesRegex(Denied,'REQUEST_MUTATED_DURING_NATIVE_CHECKS'):
            self.host.admit(session=self.s,actual_origin=self.s.origin,
                request=req,native_file_picker=picker)
        self.assertEqual(self.host.pending,{})

    def test_sensitive_permission_denied_before_any_native_select_callback(self):
        from admission import Host50Admission
        self.cat['actions'][5]['settings']=[{
            'key':'model','kind':'select','source':'host.models.installed'}]
        host=Host50Admission(self.cat,self.mapping,signing_key=self.host.key,
            allowed_origins={'https://nox.invalid'},active_tree=BASE_TREE,
            capabilities=self.host.capabilities)
        unapproved=host.issue_session(tenant='tenant',principal='person',chat='chat1',
            origin='https://nox.invalid',scopes=('chat.attach',),sensitive=())
        req=self.req('chat.attach','NIP01-06')
        req['settings']={'model':'installed-good'}
        touched=[]
        def callback(*_):
            touched.append('native-inventory')
            return True
        with self.assertRaisesRegex(Denied,'SENSITIVE_NATIVE_PERMISSION_REQUIRED'):
            host.admit(session=unapproved,actual_origin=unapproved.origin,
                request=req,native_option_verifier=callback)
        self.assertEqual(touched,[], 'Denied scope invoked native callback')
        self.assertEqual(host.pending,{})

    def test_page_select_mutation_during_native_verifier_is_denied(self):
        from admission import Host50Admission
        self.cat['actions'][0]['settings']=[{'key':'model','kind':'select',
                                             'source':'host.models.installed'}]
        host=Host50Admission(self.cat,self.mapping,signing_key=self.host.key,
            allowed_origins={'https://nox.invalid'},active_tree=BASE_TREE,
            capabilities=self.host.capabilities)
        req=HostScopeAndReceiptTests.req(self,'helion.chat','NIP01-01')
        req['settings']={'model':'installed-good'}
        def verifier(*_):
            req['settings']['model']='forged-after-native-proof'
            return True
        with self.assertRaisesRegex(Denied,'REQUEST_MUTATED_DURING_NATIVE_CHECKS'):
            host.admit(session=self.s,actual_origin=self.s.origin,request=req,
                       native_option_verifier=verifier)
        self.assertEqual(host.pending,{})

    def test_expired_session_after_native_picker_is_denied(self):
        from unittest.mock import patch
        now=[2000000000]
        with patch('admission.time.time', side_effect=lambda:now[0]):
            s=self.host.issue_session(tenant='tenant',principal='person',chat='chat1',
                origin='https://nox.invalid',scopes=('chat.attach',),
                sensitive=('chat.attach',),duration_seconds=30)
            def picker(*_):
                now[0]+=31
                return self._file()
            with self.assertRaisesRegex(Denied,'AUTH_INVALID_OR_EXPIRED'):
                self.host.admit(session=s,actual_origin=s.origin,
                    request=HostScopeAndReceiptTests.req(self,'chat.attach','NIP01-06'),
                    native_file_picker=picker)
        self.assertEqual(self.host.pending,{})

    def test_capability_revocation_during_native_picker_is_hold(self):
        from dataclasses import replace
        def picker(*_):
            cap=self.host.capabilities['chat.attach']
            self.host.capabilities['chat.attach']=replace(cap,ready=False)
            return self._file()
        with self.assertRaisesRegex(Hold,'NATIVE_OWNER_CAPABILITY_UNVERIFIED'):
            self.host.admit(session=self.s,actual_origin=self.s.origin,
                request=HostScopeAndReceiptTests.req(self,'chat.attach','NIP01-06'),
                native_file_picker=picker)
        self.assertEqual(self.host.pending,{})

    def test_native_policy_is_immutable_after_constructor_audit(self):
        with self.assertRaises(TypeError):
            self.host.by_route['chat.attach']['risk']='safe'
        with self.assertRaises(TypeError):
            self.host.by_route['chat.attach']={'risk':'safe'}

if __name__ == "__main__":
    unittest.main()
